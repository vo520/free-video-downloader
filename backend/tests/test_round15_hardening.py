"""第 15 轮回归：

1. bcrypt 5.0 对超过 72 字节的密码抛 ValueError，而原 validate_password 只按
   字符数(6~50)校验 —— 25 个以上中文字符就能通过校验，随后在 hash_password /
   verify_password 里炸成 500。注册需按 UTF-8 字节数拒绝，登录需安全返回 400。
2. /api/proxy/thumbnail 原用 client.get 全量缓冲响应后才检查 10MB 上限，
   未认证接口可被超大图片打爆内存；改为 client.stream 边读边限量并在超限时立即中断。
"""
import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import auth


def test_validate_password_rejects_multibyte_over_72_bytes():
    # 24 个中文 = 72 字节，恰好等于 bcrypt 上限，应通过
    assert auth.validate_password("中" * 24) is None
    # 25 个中文 = 75 字节，字符数只有 25（远小于 50），但字节数越界
    err = auth.validate_password("中" * 25)
    assert err is not None and "72" in err


def test_hash_and_verify_password_tolerate_overlong_input():
    """hash/verify 对超长密码不得抛 ValueError（旧实现会 500）。"""
    long_password = "a" * 100
    hashed = auth.hash_password(long_password)
    assert auth.verify_password(long_password, hashed) is True
    # 与实际存储密码不一致的超长输入只返回 False，不能抛异常
    assert auth.verify_password("中" * 40, hashed) is False


def test_register_rejects_overlong_multibyte_password(tmp_path, monkeypatch):
    import database
    from fastapi.testclient import TestClient
    import main

    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "app.db"))
    database.init_db()

    with TestClient(main.app) as c:
        r = c.post(
            "/api/auth/register",
            json={"email": "long@example.com", "password": "中" * 30},
        )
    # 原实现：validate_password 通过 → bcrypt ValueError → 500
    assert r.status_code == 400, r.text
    assert "72" in r.json()["detail"]
    assert database.get_user_by_email("long@example.com") is None


def test_login_with_overlong_password_returns_400_not_500(tmp_path, monkeypatch):
    import database
    from fastapi.testclient import TestClient
    import main

    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "app.db"))
    database.init_db()

    with TestClient(main.app) as c:
        r = c.post(
            "/api/auth/register",
            json={"email": "normal@example.com", "password": "Test123456"},
        )
        assert r.status_code == 200, r.text

        # 超长多字节密码登录：旧实现 bcrypt.checkpw 抛 ValueError → 500
        r = c.post(
            "/api/auth/login",
            json={"email": "normal@example.com", "password": "中" * 30},
        )
    assert r.status_code == 400, r.text
    assert r.json()["detail"] == "邮箱或密码错误"


def test_thumbnail_proxy_aborts_oversized_stream_early(monkeypatch):
    from fastapi.testclient import TestClient
    import httpx
    import main

    consumed = []

    class _FakeResponse:
        status_code = 200
        headers = {"content-type": "image/jpeg"}

        def raise_for_status(self):
            return None

        async def aiter_bytes(self, chunk_size):
            # 共 50MB，超过 10MB 上限后代理必须停止读取
            for _ in range(50):
                consumed.append(1)
                yield b"x" * (1024 * 1024)

    class _FakeStream:
        async def __aenter__(self):
            return _FakeResponse()

        async def __aexit__(self, *exc):
            return False

    monkeypatch.setattr(
        main.socket,
        "getaddrinfo",
        lambda *a, **k: [(None, None, None, None, ("93.184.216.34", 0))],
    )
    monkeypatch.setattr(httpx.AsyncClient, "stream", lambda self, *a, **k: _FakeStream())

    r = TestClient(main.app).get(
        "/api/proxy/thumbnail", params={"url": "https://img.example.com/a.jpg"}
    )

    assert r.status_code == 413, r.text
    # 读到第 11MB 时立即中断，而不是把 50MB 全部读进内存
    assert len(consumed) == 11
