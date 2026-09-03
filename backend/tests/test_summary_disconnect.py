"""SSE 客户端断连保护回归测试。

真实 BUG：_summarize_stream / _chat_stream 在客户端中途关闭/路由切走后仍继续 yield，
生成器继续调用 LLM、跑 generate_mindmap、写 add_history 总结历史——浪费 LLM API 配额
与算力，并把用户根本看不到的总结写入历史污染"最近总结"列表。

修复：在每次 yield 前 await request.is_disconnected()，断开即 return。
本测试验证断开后 mindmap 不被调用、add_history 不被触发、事件流提前结束。
"""
import os
import sys
import json
import atexit
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import database

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

import asyncio
from fastapi.testclient import TestClient  # noqa: E402
import main  # noqa: E402
import api_summarize  # noqa: E402
import pytest  # noqa: E402


@pytest.fixture
def client():
    with TestClient(main.app) as c:
        yield c


def _register(c, email, password="Test123456"):
    r = c.post("/api/auth/register", json={"email": email, "password": password})
    assert r.status_code == 200, r.text
    body = r.json()["data"]
    return body["token"], body["user"]["id"]


class _FakeRequest:
    """模拟 Starlette Request：第 N 次调用 is_disconnected() 起返回 True（表示已断开）。"""

    def __init__(self, disconnect_after_calls=2):
        self._calls = 0
        self._disconnect_after = disconnect_after_calls

    async def is_disconnected(self):
        self._calls += 1
        return self._calls > self._disconnect_after


class _SpySummarizer:
    """记录 generate_mindmap / chat_stream 调用次数，用于断言断连后被跳过。"""

    def __init__(self):
        self.mindmap_calls = 0
        self.summary_yield_count = 0

    def summarize_stream(self, text, lang):
        for t in ["token1", "token2", "token3"]:
            self.summary_yield_count += 1
            yield t

    def generate_mindmap(self, text, lang):
        self.mindmap_calls += 1
        return "# mindmap\n- 分支"

    def chat_stream(self, text, question):
        for t in ["ans1", "ans2", "ans3"]:
            yield t


class _FakeExtractor:
    def extract(self, url):
        return {"has_subtitle": True, "full_text": "字幕全文", "segments": []}


def test_summarize_returns_early_on_client_disconnect(client, monkeypatch):
    """客户端中途断开：服务端应立即停止 yield、不调 generate_mindmap、不写 summary 历史。"""
    add_history_calls = []
    real_add_history = api_summarize.add_history

    def spy_add_history(*args, **kwargs):
        add_history_calls.append((args, kwargs))
        return real_add_history(*args, **kwargs)

    monkeypatch.setattr(api_summarize, "add_history", spy_add_history)
    summarizer_spy = _SpySummarizer()
    monkeypatch.setattr(api_summarize, "_get_summarizer", lambda: summarizer_spy)
    monkeypatch.setattr(api_summarize, "_get_extractor", lambda: _FakeExtractor())

    token, uid = _register(client, "disc-sum@test.com")
    user = {"id": uid, "email": "disc-sum@test.com"}
    req = api_summarize.SummarizeRequest(
        url="https://x.com/v", title="测试视频", platform="x", language="zh"
    )

    # disconnect_after_calls=2：第一个 token 之前 _calls=1 → False（yield 出去）；
    # 第二个 token 之前 _calls=2 → True → return，不再 yield 后续 token/mindmap/quota/done，
    # 也不再调 generate_mindmap / add_history。
    fake_req = _FakeRequest(disconnect_after_calls=2)

    async def collect():
        return [ev async for ev in api_summarize._summarize_stream(req, user, fake_req)]

    events = asyncio.run(collect())

    # 断言 1：generate_mindmap 没被调用（节省一次 LLM 调用）
    assert summarizer_spy.mindmap_calls == 0, (
        f"应跳过 mindmap，实际调了 {summarizer_spy.mindmap_calls} 次"
    )
    # 断言 2：add_history 没被调用（避免污染总结历史）
    assert len(add_history_calls) == 0, (
        f"客户端断开后不应写 history，实际写了 {len(add_history_calls)} 条"
    )
    # 断言 3：事件流提前结束，不含 mindmap/quota/done
    event_types = [ev.event for ev in events if getattr(ev, "event", None)]
    assert "mindmap" not in event_types
    assert "quota" not in event_types
    assert "done" not in event_types
    # 断言 4：subtitle + 至少一个 summary 已发出（断在流中段而非入口）
    assert "subtitle" in event_types
    assert "summary" in event_types
    # 断言 5：DB 中确实没有 summary 历史
    resp = client.get("/api/history", params={"type": "summary"}, headers={
        "Authorization": f"Bearer {token}"
    })
    assert resp.status_code == 200
    assert resp.json()["total"] == 0


def test_chat_returns_early_on_client_disconnect(client, monkeypatch):
    """客户端在 /api/chat 流中途断开：不再 yield 后续 token。"""
    summarizer_spy = _SpySummarizer()
    monkeypatch.setattr(api_summarize, "_get_summarizer", lambda: summarizer_spy)
    monkeypatch.setattr(api_summarize, "_get_extractor", lambda: _FakeExtractor())

    token, uid = _register(client, "disc-chat@test.com")
    user = {"id": uid, "email": "disc-chat@test.com"}
    req = api_summarize.ChatRequest(
        url="https://x.com/v", question="讲了什么？", subtitle_text="已提供的字幕"
    )
    fake_req = _FakeRequest(disconnect_after_calls=2)

    async def collect():
        return [ev async for ev in api_summarize._chat_stream(req, user, fake_req)]

    events = asyncio.run(collect())
    event_types = [ev.event for ev in events if getattr(ev, "event", None)]
    # 至少有一个 answer 已发出（说明没在入口就退出），但无 done
    assert "answer" in event_types
    assert "done" not in event_types