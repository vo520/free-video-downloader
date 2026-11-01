"""回归：并发配额扣减 / 事件循环阻塞 / 中途额度耗尽（第 7 轮自主排查）。

本轮修复的三个真实缺陷：

1. `check_and_increment_summary` 跨天分支无条件 `SET daily_summary_count = 1`，
   同一天首批并发请求互相覆盖计数，实际放行次数超过每日上限
   → 改为单条带条件的原子 UPDATE（跨天重置与同日 +1 合并进同一条 CASE）。

2. `check_summary_quota`（只读）与 `check_and_increment_summary`（消费）各写一份
   VIP 过期解析，naive 时间字符串与带时区的 now 比较会抛 TypeError → 统一抽
   `_is_vip_active`，两处口径一致。

3. SSE 生成器 / async 路由里直接调用同步 SQLite（check_summary_quota、
   check_and_increment_summary、add_history）会阻塞事件循环；且扣减结果被忽略，
   字幕提取期间（可达 120s）额度被并发耗尽时仍继续调用 LLM
   → 全部丢线程池 + 检查扣减结果，失败即发 error 事件并中止。

另：`get_db()` 缺 busy_timeout，并发写会立刻抛 "database is locked"。
"""
import os
import sys
import asyncio
import atexit
import tempfile
import threading

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import database  # noqa: E402

# 使用临时库，避免污染开发库（data/app.db）。
_TMP_DB = tempfile.mkstemp(suffix=".db")[1]
database.DB_PATH = _TMP_DB
database.init_db()


def _cleanup_tmp():
    for suffix in ("", "-wal", "-shm"):
        p = _TMP_DB + suffix
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass


atexit.register(_cleanup_tmp)

import pytest  # noqa: E402


@pytest.fixture()
def fresh_user(tmp_path, monkeypatch):
    """指向临时库的 users 表，并创建一个普通（非 VIP）用户。"""
    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "app.db"))
    database.init_db()
    uid = database.create_user(f"r7-{os.urandom(4).hex()}@example.com", "x")["id"]
    return uid


# ===== 1. 并发配额扣减 =====


def test_concurrent_first_use_of_day_respects_limit(fresh_user):
    """跨天后的首批并发请求不得互相覆盖计数，实际放行次数不得超过每日上限。

    旧实现：跨天分支无条件 `SET daily_summary_count = 1`，每个并发请求都把自己
    算成当天第 1 次 → 放行次数 = 并发数（可远超 3 次/日上限）。
    """
    limit = database.FREE_DAILY_SUMMARY_LIMIT
    n = 12
    barrier = threading.Barrier(n)
    results = []
    lock = threading.Lock()

    def worker():
        barrier.wait()
        ok, _ = database.check_and_increment_summary(fresh_user)
        with lock:
            results.append(ok)

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert len(results) == n, "并发线程未全部完成（可能死锁或抛错）"
    assert sum(1 for r in results if r) == limit, (
        f"并发放行次数应为每日上限 {limit}，实际 {sum(1 for r in results if r)}"
    )

    # 落库的计数必须与实际放行次数一致
    user = database.get_user_by_id(fresh_user)
    assert user["daily_summary_count"] == limit, (
        f"落库计数应为 {limit}，实际 {user['daily_summary_count']}"
    )


def test_concurrent_same_day_requests_do_not_overspend(fresh_user):
    """同一天内并发请求总数（含已有消耗）不得超过每日上限。"""
    limit = database.FREE_DAILY_SUMMARY_LIMIT
    # 先用掉 1 次
    assert database.check_and_increment_summary(fresh_user)[0] is True

    n = 10
    barrier = threading.Barrier(n)
    results = []
    lock = threading.Lock()

    def worker():
        barrier.wait()
        ok, _ = database.check_and_increment_summary(fresh_user)
        with lock:
            results.append(ok)

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    allowed = sum(1 for r in results if r)
    assert allowed == limit - 1, (
        f"同日并发总放行次数应为 {limit - 1}（已有 1 次），实际 {allowed}"
    )


def test_quota_exhausted_returns_not_allowed(fresh_user):
    """额度用尽后扣减必须返回 not allowed，且计数不再增长。"""
    limit = database.FREE_DAILY_SUMMARY_LIMIT
    for _ in range(limit):
        assert database.check_and_increment_summary(fresh_user)[0] is True
    ok, remaining = database.check_and_increment_summary(fresh_user)
    assert ok is False
    assert remaining == 0
    user = database.get_user_by_id(fresh_user)
    assert user["daily_summary_count"] == limit


# ===== 2. VIP 口径统一 =====


def test_expired_vip_is_treated_as_free_user(fresh_user):
    """已过期的 VIP 必须按免费用户处理（只读与消费两侧口径一致）。

    旧实现两处各写一份 VIP 解析，且只捕获 ValueError —— naive 时间字符串
    走 `datetime.fromisoformat(s).replace(tzinfo=utc)` 分支没问题，但格式非法时
    TypeError 未被捕获 → 500。
    """
    from datetime import datetime, timedelta, timezone

    expire = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    with database.get_db() as conn:
        conn.execute(
            "UPDATE users SET is_vip = 1, vip_expire_at = ? WHERE id = ?",
            (expire, fresh_user),
        )

    allowed, remaining = database.check_summary_quota(fresh_user)
    assert allowed is True
    assert remaining == database.FREE_DAILY_SUMMARY_LIMIT, (
        "过期 VIP 应按免费用户计算剩余额度"
    )

    consumed, remaining = database.check_and_increment_summary(fresh_user)
    assert consumed is True
    assert remaining == database.FREE_DAILY_SUMMARY_LIMIT - 1


def test_garbled_vip_expire_does_not_crash(fresh_user):
    """vip_expire_at 为脏数据时不得抛异常（两处口径一致，按非 VIP 处理）。"""
    with database.get_db() as conn:
        conn.execute(
            "UPDATE users SET is_vip = 1, vip_expire_at = ? WHERE id = ?",
            ("not-a-date", fresh_user),
        )

    allowed, remaining = database.check_summary_quota(fresh_user)
    assert allowed is True
    assert remaining == database.FREE_DAILY_SUMMARY_LIMIT

    consumed, _ = database.check_and_increment_summary(fresh_user)
    assert consumed is True


def test_active_vip_is_unlimited(fresh_user):
    """有效 VIP：只读与消费都返回无限（remaining = -1）。"""
    from datetime import datetime, timedelta, timezone

    expire = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    with database.get_db() as conn:
        conn.execute(
            "UPDATE users SET is_vip = 1, vip_expire_at = ? WHERE id = ?",
            (expire, fresh_user),
        )

    allowed, remaining = database.check_summary_quota(fresh_user)
    assert allowed is True and remaining == -1

    consumed, remaining = database.check_and_increment_summary(fresh_user)
    assert consumed is True and remaining == -1

    # VIP 不消耗免费次数
    user = database.get_user_by_id(fresh_user)
    assert (user["daily_summary_count"] or 0) == 0


def test_auth_response_uses_shared_vip_parser(fresh_user):
    """登录/注册响应必须与配额接口共用同一 VIP 判定（第 3 处重复实现已收敛）。

    旧实现：api_auth._build_user_response 自己写了一份过期解析且只捕获
    ValueError。vip_expire_at 存成非字符串（SQLite 动态类型，脏数据/手工改库
    都可能出现）时 `"+" in expire_str` 抛 TypeError 直接 500；而且与
    database._is_vip_active 各写一套，口径一旦漂移就会出现
    「登录说 VIP、AI 总结扣次数」的矛盾。
    """
    import api_auth

    from datetime import datetime, timedelta, timezone

    def response():
        return api_auth._build_user_response(database.get_user_by_id(fresh_user))

    # 1) 有效 VIP：is_vip 与到期时间都要正确返回
    expire = (datetime.now(timezone.utc) + timedelta(days=30)).isoformat()
    with database.get_db() as conn:
        conn.execute(
            "UPDATE users SET is_vip = 1, vip_expire_at = ? WHERE id = ?",
            (expire, fresh_user),
        )
    resp = response()
    assert resp["is_vip"] is True
    assert resp["vip_expire_at"] == expire

    # 2) 过期 VIP：按免费用户返回，且不外露到期时间
    expired = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    with database.get_db() as conn:
        conn.execute(
            "UPDATE users SET is_vip = 1, vip_expire_at = ? WHERE id = ?",
            (expired, fresh_user),
        )
    resp = response()
    assert resp["is_vip"] is False
    assert resp["vip_expire_at"] is None

    # 3) 脏数据（非字符串）：不得抛 TypeError；结果与配额接口口径一致
    with database.get_db() as conn:
        conn.execute(
            "UPDATE users SET is_vip = 1, vip_expire_at = 12345 WHERE id = ?",
            (fresh_user,),
        )
    resp = response()
    assert resp["is_vip"] is False
    allowed, remaining = database.check_summary_quota(fresh_user)
    assert allowed is True and remaining == database.FREE_DAILY_SUMMARY_LIMIT


# ===== 3. busy_timeout =====

def test_get_db_sets_busy_timeout(fresh_user):
    """get_db 必须设置 busy_timeout，否则并发写立刻抛 database is locked。"""
    with database.get_db() as conn:
        timeout = conn.execute("PRAGMA busy_timeout").fetchone()[0]
    assert timeout == 30000, f"busy_timeout 应为 30000ms，实际 {timeout}"


def test_concurrent_history_writes_all_succeed(fresh_user):
    """并发写历史不得因锁冲突丢失记录。"""
    n = 10
    barrier = threading.Barrier(n)
    errors = []

    def worker(i):
        barrier.wait()
        for j in range(5):
            try:
                database.add_history(
                    fresh_user, "parse", video_url=f"https://x.com/v{i}-{j}", title="t"
                )
            except Exception as e:  # add_history 内部吞异常，这里只兜底意外抛出
                errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)

    assert not errors, f"并发写历史出现异常: {errors[:3]}"
    _, total = database.get_history(fresh_user, htype="parse", limit=1000)
    assert total == n * 5, f"并发写历史丢失记录：期望 {n * 5}，实际 {total}"


# ===== 4. SSE 中途额度耗尽（扣减结果必须被检查）=====


class _FakeRequest:
    async def is_disconnected(self):
        return False


class _SpySummarizer:
    def __init__(self):
        self.summary_calls = 0
        self.mindmap_calls = 0
        self.chat_calls = 0

    def summarize_stream(self, text, lang):
        self.summary_calls += 1
        yield "token"

    def generate_mindmap(self, text, lang):
        self.mindmap_calls += 1
        return "# mindmap"

    def chat_stream(self, text, question):
        self.chat_calls += 1
        yield "ans"


class _FakeExtractor:
    def extract(self, url):
        return {"has_subtitle": True, "full_text": "字幕全文", "segments": []}


@pytest.fixture()
def api_mod(monkeypatch):
    import api_summarize

    monkeypatch.setattr(api_summarize, "_get_summarizer", lambda: _SpySummarizer())
    monkeypatch.setattr(api_summarize, "_get_extractor", lambda: _FakeExtractor())
    return api_summarize


def test_summarize_aborts_when_quota_consumption_fails(fresh_user, api_mod):
    """字幕提取期间额度被并发耗尽：必须发 error 事件并中止，不得再调 LLM。

    旧实现忽略 check_and_increment_summary 的 allowed，扣减失败仍继续生成总结
    → 用户可突破每日免费上限。
    """
    import api_summarize

    user = {"id": fresh_user, "email": "u@example.com"}
    req = api_summarize.SummarizeRequest(url="https://x.com/v", title="t", platform="x")

    # 预检通过（模拟预检时额度尚有），但真正扣减时已被并发耗尽
    monkey = pytest.MonkeyPatch()
    monkey.setattr(api_summarize, "check_summary_quota", lambda _uid: (True, 1))
    monkey.setattr(api_summarize, "check_and_increment_summary", lambda _uid: (False, 0))
    try:
        async def collect():
            return [ev async for ev in api_summarize._summarize_stream(req, user, _FakeRequest())]

        events = asyncio.run(collect())
    finally:
        monkey.undo()

    event_types = [ev.event for ev in events if getattr(ev, "event", None)]
    assert "error" in event_types, f"扣减失败应发 error 事件，实际 {event_types}"
    assert "summary" not in event_types, "扣减失败后不得继续输出总结内容"
    assert "done" not in event_types

    # 错误事件必须带上 need_vip，前端才能引导开通 VIP
    err_ev = next(ev for ev in events if getattr(ev, "event", None) == "error")
    import json

    payload = json.loads(err_ev.data)
    assert payload.get("need_vip") is True
    assert "用完" in payload.get("message", "")


def test_chat_aborts_when_quota_consumption_fails(fresh_user, api_mod):
    """AI 问答同样必须检查扣减结果，扣减失败即中止，不得调用 LLM。"""
    import api_summarize
    import json

    user = {"id": fresh_user, "email": "u@example.com"}
    req = api_summarize.ChatRequest(
        url="https://x.com/v", question="讲了什么？", subtitle_text="字幕"
    )

    monkey = pytest.MonkeyPatch()
    monkey.setattr(api_summarize, "check_summary_quota", lambda _uid: (True, 1))
    monkey.setattr(api_summarize, "check_and_increment_summary", lambda _uid: (False, 0))
    try:
        async def collect():
            return [ev async for ev in api_summarize._chat_stream(req, user, _FakeRequest())]

        events = asyncio.run(collect())
    finally:
        monkey.undo()

    event_types = [ev.event for ev in events if getattr(ev, "event", None)]
    assert "error" in event_types, f"扣减失败应发 error 事件，实际 {event_types}"
    assert "answer" not in event_types, "扣减失败后不得输出回答内容"

    err_ev = next(ev for ev in events if getattr(ev, "event", None) == "error")
    payload = json.loads(err_ev.data)
    assert payload.get("need_vip") is True


# ===== 5. 裸数字抖音 ID 与 /api/parse 口径一致 =====


def test_normalize_request_url_expands_numeric_douyin_id():
    """裸数字抖音 ID 必须补全为完整链接（与 /api/parse 一致）。"""
    import api_summarize

    assert api_summarize._normalize_request_url("7001234") == (
        "https://www.douyin.com/video/7001234"
    )
    # 非纯数字不做转换（避免把 YouTube 的 11 位 ID 误判为抖音）
    assert api_summarize._normalize_request_url("dQw4w9WgXcQ") == "dQw4w9WgXcQ"
    assert api_summarize._normalize_request_url("https://x.com/v") == "https://x.com/v"
    # 空白应被裁掉
    assert api_summarize._normalize_request_url("  7001234  ") == (
        "https://www.douyin.com/video/7001234"
    )


def test_numeric_douyin_id_passes_summarize_url_validation():
    """裸数字抖音 ID 不得被 SSRF 校验误判为非法链接。

    背景：/api/parse 支持粘贴抖音视频 ID，前端会把原始输入原样传给
    /api/summarize；若不补全，_validate_video_url 会以
    「仅支持公网 http/https 视频链接」拒掉 —— 用户能解析成功的视频却生成不了总结。
    """
    import api_summarize

    normalized = api_summarize._normalize_request_url("7001234")
    # 校验用的是补全后的 URL（离线环境下无法解析主机时不拦截，符合既有约定）
    assert api_summarize._validate_video_url(normalized) in (
        None,
        "无法解析视频链接主机",
        "不支持的链接地址",
    )


def test_history_uses_canonical_url_key(fresh_user):
    """history 的去重键必须与 video_cache 一致（裸数字抖音 ID 补全为完整链接）。

    背景：canonical_video_url 的文档明确要求「history 与 video_cache 两张表
    都必须用本函数归一」，但 add_history 此前只用 _normalize_video_url，
    导致裸数字 ID 在两表对不上，同一视频出现两条记录。
    """
    database.add_history(fresh_user, "parse", video_url="7001234", title="t1")
    database.add_history(
        fresh_user, "parse", video_url="https://www.douyin.com/video/7001234", title="t2"
    )
    _, total = database.get_history(fresh_user, htype="parse")
    assert total == 1, f"裸数字 ID 与完整链接应归一为同一条，实际 {total} 条"

    rows, _ = database.get_history(fresh_user, htype="parse")
    assert rows[0]["video_url"] == "https://douyin.com/video/7001234"
    assert rows[0]["title"] == "t2"


# ===== 6. sub 非整数的 Token 必须 401，不得 500 =====


def test_decode_token_rejects_non_integer_sub():
    """sub 为 "abc" 时 decode_token 必须抛 401，而不是裸 ValueError。

    旧实现只捕获 jwt.InvalidTokenError，int("abc") 的 ValueError 会一路冒泡，
    FastAPI 兜底成 500 —— 任何人带上一个结构合法但 sub 非数字的 Token
    都能把接口打成 5xx（且 get_current_user 依赖它，影响所有鉴权路由）。
    """
    import jwt
    from fastapi import HTTPException

    import auth

    for sub in ("abc", "1.5", ""):
        token = jwt.encode({"sub": sub}, auth.JWT_SECRET, algorithm=auth.JWT_ALGORITHM)
        with pytest.raises(HTTPException) as exc_info:
            auth.decode_token(token)
        assert exc_info.value.status_code == 401, f"sub={sub!r} 应返回 401"
        assert exc_info.value.detail == "无效的 Token"


def test_decode_token_missing_sub_is_401():
    """缺 sub 依然按无效 Token 处理（回归保护既有行为）。"""
    import jwt
    from fastapi import HTTPException

    import auth

    token = jwt.encode({"email": "a@b.com"}, auth.JWT_SECRET, algorithm=auth.JWT_ALGORITHM)
    with pytest.raises(HTTPException) as exc_info:
        auth.decode_token(token)
    assert exc_info.value.status_code == 401


def test_decode_token_accepts_numeric_sub():
    """正常 Token（sub 为数字字符串）必须解析为 int。"""
    import jwt

    import auth

    token = auth.create_token(42, "a@b.com")
    payload = auth.decode_token(token)
    assert payload["sub"] == 42
    assert payload["email"] == "a@b.com"


# ===== 7. 字幕 URL 存在但解析出 0 段时，必须按「无字幕」返回 =====


def test_subtitle_extractor_empty_segments_is_no_subtitle(monkeypatch):
    """字幕 URL 能选到、但下载解析后没有任何分段，必须 has_subtitle=False。

    旧实现只看「选到了字幕 URL」就返回 has_subtitle=True + full_text=""，
    上游 _summarize_stream / _chat_stream 会照常扣减一次免费额度，
    再拿空字符串去调用 LLM —— 用户既被扣次数又拿不到任何总结。
    """
    import summarizer

    extractor = summarizer.SubtitleExtractor()
    monkeypatch.setattr(
        extractor,
        "_get_video_info",
        lambda url: {
            "subtitles": {"zh-Hans": [{"ext": "json3", "url": "https://x.test/sub.json3"}]},
            "automatic_captions": {},
        },
    )
    # yt-dlp 拉取失败 / 字幕文件无正文时返回空列表
    monkeypatch.setattr(extractor, "_download_and_parse", lambda *a, **kw: [])

    result = extractor.extract("https://example.test/video/1")
    assert result["has_subtitle"] is False
    assert result["segments"] == []
    assert result["full_text"] == ""


def test_subtitle_extractor_non_empty_segments_still_ok(monkeypatch):
    """有分段时正常返回（回归保护，避免上面的防御误伤主流程）。"""
    import summarizer

    extractor = summarizer.SubtitleExtractor()
    monkeypatch.setattr(
        extractor,
        "_get_video_info",
        lambda url: {
            "subtitles": {"zh-Hans": [{"ext": "json3", "url": "https://x.test/sub.json3"}]},
            "automatic_captions": {},
        },
    )
    monkeypatch.setattr(
        extractor,
        "_download_and_parse",
        lambda *a, **kw: [{"start": 0.0, "end": 1.5, "text": "第一句"}],
    )

    result = extractor.extract("https://example.test/video/1")
    assert result["has_subtitle"] is True
    assert result["full_text"] == "第一句"


def test_bilibili_empty_body_is_no_subtitle(monkeypatch):
    """B 站字幕接口有 subtitles 但 body 全是空内容时，同样按无字幕处理。"""
    import summarizer

    class _FakeResp:
        def __init__(self, data):
            self._data = data

        def json(self):
            return self._data

    def _fake_get(url, headers=None, timeout=None):
        if "web-interface/view" in url:
            return _FakeResp({"data": {"cid": 1, "aid": 2}})
        if "dm/view" in url:
            return _FakeResp(
                {
                    "data": {
                        "subtitle": {
                            "subtitles": [
                                {"lan": "zh", "subtitle_url": "//x.test/sub.json"}
                            ]
                        }
                    }
                }
            )
        return _FakeResp({"body": [{"content": "   ", "from": 0, "to": 1}]})

    monkeypatch.setattr(summarizer.httpx, "get", _fake_get)

    result = summarizer.SubtitleExtractor()._extract_bilibili(
        "https://www.bilibili.com/video/BV1xx411c7mD"
    )
    assert result["has_subtitle"] is False
    assert result["full_text"] == ""
