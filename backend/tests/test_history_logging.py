"""验证"解析/总结成功 → 自动落库历史"的端到端接线（不只是历史 CRUD 自身）。

避开真实解析/下载/AI 的网络与算力依赖：
- 用 monkeypatch 把 main.downloader.parse_video 替换为假结果。
- 解析成功后断言 /api/history 中确实多出一条 type=parse 的记录（标题/平台/URL 正确）。

核心验证点：
- 已登录用户解析 → 历史被写入。
- 匿名用户解析（无 token） → 历史不写入（best-effort 跳过，主流程仍 200）。
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import database

_TMP_DB = tempfile.mkstemp(suffix=".db")[1]
database.DB_PATH = _TMP_DB
database.init_db()

import atexit


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


_FAKE_PARSE = {
    "title": "Fake Title",
    "platform": "youtube",
    "thumbnail": "http://x/y.jpg",
    "id": "vid1",
    "uploader": "up",
    "duration": 120,
}


def test_parse_logs_history_when_authed(client, monkeypatch):
    monkeypatch.setattr(main.downloader, "parse_video", lambda url: dict(_FAKE_PARSE))

    token, _ = _register(client, "parse_log@test.com")
    url = "https://www.youtube.com/watch?v=abc"
    r = client.post("/api/parse", json={"url": url}, headers=_auth(token))
    assert r.status_code == 200, r.text
    assert r.json()["success"] is True

    h = client.get("/api/history", headers=_auth(token)).json()
    assert h["total"] == 1
    row = h["data"][0]
    assert row["type"] == "parse"
    assert row["title"] == "Fake Title"
    assert row["platform"] == "youtube"
    # video_url 经归一化存储（去 www.、强制 https），与去重逻辑一致
    assert row["video_url"] == "https://youtube.com/watch?v=abc"


def test_parse_does_not_log_when_anonymous(client, monkeypatch):
    monkeypatch.setattr(main.downloader, "parse_video", lambda url: dict(_FAKE_PARSE))

    token, _ = _register(client, "anon_log@test.com")
    # 匿名解析（无 token）应当成功，但不落库
    r = client.post("/api/parse", json={"url": "https://www.youtube.com/watch?v=xyz"})
    assert r.status_code == 200, r.text

    h = client.get("/api/history", headers=_auth(token)).json()
    assert h["total"] == 0
