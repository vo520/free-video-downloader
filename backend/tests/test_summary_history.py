"""AI 总结落库测试（回归：修复 req.title / req.platform AttributeError 导致 summary 历史从未写入）。

直接驱动 /api/summarize 的 SSE 端点，但用 monkeypatch 替掉真实字幕提取与 AI 模型调用，
验证：总结成功流结束后，type=summary 的历史记录被正确写入，且 extra 含 summary/mindmap，
title 取自信请求体。

使用临时数据库（patch database.DB_PATH），不污染开发库 data/app.db。
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


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


class _FakeSummarizer:
    def summarize_stream(self, text, lang):
        for t in ["总结", "内容", "要点"]:
            yield t

    def generate_mindmap(self, text, lang):
        return "# 思维导图\n- 分支A\n- 分支B"


class _FakeExtractor:
    def extract(self, url):
        return {"has_subtitle": True, "full_text": "字幕全文", "segments": []}


def test_summary_history_logged_after_stream(client, monkeypatch):
    # 替掉真实依赖，避免网络/AI 调用；保留真实 _summarize_stream + add_history 链路。
    monkeypatch.setattr(api_summarize, "_get_summarizer", lambda: _FakeSummarizer())
    monkeypatch.setattr(api_summarize, "_get_extractor", lambda: _FakeExtractor())

    token, _ = _register(client, "sum@test.com")
    # 触发总结 SSE（TestClient 会消费完整流，使 done 之后的 add_history 真正执行）。
    r = client.post(
        "/api/summarize",
        json={"url": "https://x.com/v", "title": "测试视频", "language": "zh"},
        headers=_auth(token),
    )
    assert r.status_code == 200

    # 断言：summary 历史已落库，且字段正确（回归此前 req.title AttributeError 导致不落库）。
    resp = client.get("/api/history", params={"type": "summary"}, headers=_auth(token))
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    assert body["total"] == 1

    row = body["data"][0]
    assert row["type"] == "summary"
    assert row["title"] == "测试视频"          # 来自请求体 title，证明 req.title 不再触发 AttributeError
    assert row["video_url"] == "https://x.com/v"

    extra = row["extra"]
    if isinstance(extra, str):
        extra = json.loads(extra)
    assert "总结内容要点" in extra["summary"]     # token 已正确拼接为全文
    assert "思维导图" in extra["mindmap"]         # 思维导图已保存
