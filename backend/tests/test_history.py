"""用户云端历史 API 测试（解析/下载/总结）。

验证点：
- 未登录访问 /api/history 必须被拒（401/403）。
- 登录后可写入（经 add_history，避开真实解析/下载的网络依赖）并读取。
- 按类型筛选（type=）生效。
- 删除/清空的归属校验：A 不能删除/看到 B 的记录。
- extra 字段以 JSON 字符串落库并能被前端重新 parse。

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


def test_history_requires_auth(client):
    # 未携带 token 应被依赖 Depends(get_current_user) 拒绝
    r = client.get("/api/history")
    assert r.status_code in (401, 403)


def test_history_list_empty(client):
    token, _ = _register(client, "empty@test.com")
    r = client.get("/api/history", headers=_auth(token))
    assert r.status_code == 200
    body = r.json()
    assert body["success"] is True
    assert body["data"] == []
    assert body["total"] == 0


def test_history_crud_and_ownership(client):
    token_a, uid_a = _register(client, "a@test.com")
    token_b, uid_b = _register(client, "b@test.com")
    ha = _auth(token_a)

    # 直接走 add_history 写入（避开真实解析/下载网络依赖）
    database.add_history(uid_a, "parse", video_url="https://x.com/1", title="t1", platform="yt")
    database.add_history(uid_a, "download", video_url="https://x.com/2", title="t2", extra={"format_id": "best"})
    database.add_history(uid_b, "parse", video_url="https://x.com/3", title="t3")

    # A 仅能看到自己的 2 条
    r = client.get("/api/history", headers=ha)
    assert r.status_code == 200
    assert r.json()["total"] == 2

    # 按类型筛选
    r = client.get("/api/history?type=download", headers=ha)
    assert r.json()["total"] == 1

    # 取 A 的一条 parse 记录用于删除
    rows = client.get("/api/history", headers=ha).json()["data"]
    hid = [x for x in rows if x["type"] == "parse"][0]["id"]

    # B 不能删除 A 的记录（归属校验 → 404）
    rb = client.delete(f"/api/history/{hid}", headers=_auth(token_b))
    assert rb.status_code == 404

    # A 删除自己的记录
    rd = client.delete(f"/api/history/{hid}", headers=ha)
    assert rd.status_code == 200
    assert client.get("/api/history", headers=ha).json()["total"] == 1

    # A 清空自己的全部
    rc = client.post("/api/history/clear", json={}, headers=ha)
    assert rc.status_code == 200
    assert client.get("/api/history", headers=ha).json()["total"] == 0

    # B 的记录不受影响（隔离正确）
    assert client.get("/api/history", headers=_auth(token_b)).json()["total"] == 1


def test_history_extra_json_roundtrip(client):
    token, uid = _register(client, "extra@test.com")
    database.add_history(
        uid, "summary",
        video_url="https://x.com/s", title="s",
        extra={"summary": "全文总结", "mindmap": "# 思维导图"},
    )
    r = client.get("/api/history", headers=_auth(token))
    row = r.json()["data"][0]
    # extra 由服务端直接解析为对象返回（契约更干净，前端无需再做 JSON.parse）；
    # 解析失败/为空时应为 None。
    assert isinstance(row["extra"], dict)
    assert row["extra"]["summary"] == "全文总结"
    assert row["extra"]["mindmap"] == "# 思维导图"


def test_history_extra_null_when_empty(client):
    # 未传 extra（或解析失败）时，API 应返回 null 而非字符串/异常值，前端 parsedExtra 走 {} 兜底。
    token, uid = _register(client, "extranull@test.com")
    database.add_history(uid, "parse", video_url="https://x.com/n", title="n")
    r = client.get("/api/history", headers=_auth(token))
    assert r.json()["data"][0]["extra"] is None


def test_history_list_no_truncation(client):
    # 回归：前端"打开拉全量"依赖 limit 足够大；放宽上限后即使历史超过旧默认值也不应被截断。
    token, uid = _register(client, "many@test.com")
    for i in range(120):
        database.add_history(uid, "parse", video_url=f"https://x.com/v{i}", title=f"v{i}")
    r = client.get("/api/history?limit=1000", headers=_auth(token))
    body = r.json()
    assert body["success"] is True
    assert body["total"] == 120
    assert len(body["data"]) == 120
    # 时间倒序（最新插入的 v119 在最前）
    assert body["data"][0]["title"] == "v119"
