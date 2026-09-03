"""回归测试：history 表的 snapshot 字段契约。

真实 BUG：点击解析历史会触发 /api/parse 重跑 yt-dlp（用户期望直接从 DB 显示）。
根因：history 表只存了 title/platform/thumbnail，formats/duration/uploader 等 videoData
关键字段从未落库，导致即便改前端也无法"直接显示"。
修复：history 新增 snapshot 列存完整 result；add_history 接收 snapshot 参数；
get_history 把 snapshot 反序列化为对象返回（前端拿到的就是 dict，不需 JSON.parse）。

测试覆盖：
- add_history(snapshot=dict) → DB 行存的是 snapshot_json 字符串
- get_history 返回行里 snapshot 是 dict（与原 result 完全一致）
- add_history(snapshot=None) → 仍能写入，snapshot 字段为 None（兼容旧调用）
- upsert 路径：snapshot 也被刷新（最近一次解析的 snapshot 覆盖历史值）
"""
import os
import sys
import json
import atexit
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import database


_TMP_DB = tempfile.mkstemp(suffix=".db")[1]
database.DB_PATH = _TMP_DB


def _cleanup_tmp():
    for suffix in ("", "-wal", "-shm"):
        p = _TMP_DB + suffix
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass


atexit.register(_cleanup_tmp)


def _make_user(email_suffix=""):
    """直接插入一个测试用户，避开注册路由的 bcrypt 依赖。
    每个测试用独立 email（共享进程级 DB，全局唯一）。"""
    database.init_db()
    email = f"snap{email_suffix}@test.com" if email_suffix else "snap@test.com"
    with database.get_db() as conn:
        conn.execute(
            "INSERT INTO users (email, password_hash, is_vip, created_at) "
            "VALUES (?, ?, ?, datetime('now'))",
            (email, "x", 0),
        )
        uid = conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone()["id"]
    return uid


def test_add_history_snapshot_roundtrip():
    """add_history(snapshot=dict) 后 get_history 返回的 snapshot 是 dict。"""
    uid = _make_user("_1")
    result = {
        "title": "示例视频",
        "platform": "抖音",
        "thumbnail": "https://cdn.example.com/cover.jpg",
        "duration": 35,
        "duration_string": "00:35",
        "uploader": "示例作者",
        "view_count": 12345,
        "description": "简介",
        "formats": [
            {"format_id": "douyin_nowm", "ext": "mp4", "resolution": "1080x1920", "height": 1920,
             "filesize": None, "filesize_approx": None, "vcodec": "h264", "acodec": "aac",
             "label": "无水印 MP4 (1920p)"},
        ],
        "subtitles": [],
        "automatic_captions": [],
    }
    database.add_history(
        uid, "parse",
        video_url="https://v.douyin.com/iJ7abcdef/",
        title=result["title"],
        platform=result["platform"],
        thumbnail=result["thumbnail"],
        snapshot=result,
    )
    rows, total = database.get_history(uid, htype="parse")
    assert total == 1
    row = rows[0]
    # snapshot 反序列化为 dict，并与原 result 内容一致
    assert isinstance(row["snapshot"], dict)
    assert row["snapshot"]["title"] == "示例视频"
    assert row["snapshot"]["platform"] == "抖音"
    assert row["snapshot"]["duration"] == 35
    assert row["snapshot"]["uploader"] == "示例作者"
    assert len(row["snapshot"]["formats"]) == 1
    assert row["snapshot"]["formats"][0]["format_id"] == "douyin_nowm"


def test_add_history_without_snapshot_still_works():
    """不传 snapshot 时字段为 None（兼容旧调用，download/summary 类型无 snapshot）。"""
    uid = _make_user("_2")
    database.add_history(
        uid, "download",
        video_url="https://example.com/v",
        title="下载测试",
        platform="YouTube",
        thumbnail="https://example.com/cover.jpg",
        extra={"format_id": "best"},
    )
    rows, _ = database.get_history(uid, htype="download")
    assert rows[0]["snapshot"] is None


def test_add_history_snapshot_refresh_on_upsert():
    """upsert 路径：同一 (user_id,type,video_url) 第二次写入时 snapshot 被覆盖。"""
    uid = _make_user("_3")
    url = "https://example.com/same"
    database.add_history(
        uid, "parse", video_url=url, title="t1", platform="p1", thumbnail="thumb1",
        snapshot={"title": "t1", "platform": "p1", "duration": 10},
    )
    database.add_history(
        uid, "parse", video_url=url, title="t2-updated", platform="p2", thumbnail="thumb2",
        snapshot={"title": "t2-updated", "platform": "p2", "duration": 99},
    )
    rows, total = database.get_history(uid, htype="parse")
    assert total == 1, "upsert 应保持单条，不应插入重复行"
    assert rows[0]["snapshot"]["title"] == "t2-updated"
    assert rows[0]["snapshot"]["duration"] == 99


def test_snapshot_rejects_non_serializable_gracefully():
    """不可 JSON 序列化的对象作 snapshot 时，落库为 None 且不抛异常（add_history best-effort 不变）。"""
    uid = _make_user("_4")
    # set 不可 JSON 序列化，会触发 TypeError → snapshot_json=None
    ok = database.add_history(
        uid, "parse",
        video_url="https://example.com/bad",
        title="t", platform="p", thumbnail="th",
        snapshot={"bad": {1, 2, 3}},  # set → TypeError
    )
    assert ok is True, "best-effort 不应因 snapshot 不可序列化而抛异常"
    rows, _ = database.get_history(uid, htype="parse", limit=10)
    row = next(r for r in rows if r["video_url"] == "https://example.com/bad")
    assert row["snapshot"] is None


def test_init_db_idempotent_on_alter_table():
    """init_db 幂等：第二次执行不应因 snapshot 列已存在而抛错。"""
    database.init_db()
    # 再次执行：ALTER TABLE ADD snapshot 会因 duplicate column 报错，被 try/except 吞掉
    database.init_db()
    database.init_db()
    # 仍能插入新行（说明表结构完整）
    database.add_history(
        1, "parse",
        video_url="https://example.com/x",
        title="x", platform="x", thumbnail="x",
        snapshot={"x": 1},
    )