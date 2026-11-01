"""回归：演示账号 VIP 体验期限（防止被改回长期 VIP 导致付费墙失效）。"""
import os
import sys
from datetime import datetime, timedelta, timezone

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))


def test_demo_vip_duration_is_short_lived():
    """demo 账号的 VIP 只能是短期体验额度。

    前端在未登录时会用固定 demo 账号静默登录（api/auth.js#ensureDefaultUser），
    所有访客都落在同一个 demo 账号上。若 demo 账号带长期 VIP，
    免费 3 次/日的解析配额与付费墙对全部访客失效，VIP 付费只剩名义门槛。
    """
    import api_auth

    assert api_auth.DEMO_VIP_DURATION <= timedelta(days=1), (
        f"demo VIP 期限不应超过 1 天，当前为 {api_auth.DEMO_VIP_DURATION}"
    )


@pytest.fixture()
def temp_db(tmp_path, monkeypatch):
    """把 users/history 表指向临时库，避免污染真实数据。"""
    import database

    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "app.db"))
    database.init_db()
    return database


def test_demo_vip_expiry_is_within_one_day(temp_db):
    """_ensure_demo_vip 写入的到期时间必须落在 1 天内。"""
    import api_auth

    database = temp_db
    database.create_user(api_auth.DEMO_EMAIL, "x")

    api_auth._ensure_demo_vip(api_auth.DEMO_EMAIL)

    user = database.get_user_by_email(api_auth.DEMO_EMAIL)
    assert user is not None
    assert user["is_vip"] == 1
    assert user["vip_expire_at"], "demo 账号必须有 vip_expire_at"

    expire = datetime.fromisoformat(user["vip_expire_at"].replace("Z", "+00:00"))
    if expire.tzinfo is None:
        expire = expire.replace(tzinfo=timezone.utc)

    now = datetime.now(timezone.utc)
    assert expire > now, "demo VIP 到期时间必须晚于当前时间"
    assert expire <= now + timedelta(days=1, minutes=1), (
        f"demo VIP 到期时间超出 1 天：{user['vip_expire_at']}"
    )


def test_non_demo_user_is_not_promoted(temp_db):
    """普通用户不得因为 _ensure_demo_vip 被提升为 VIP。"""
    import api_auth

    database = temp_db
    database.create_user("normal@example.com", "x")

    api_auth._ensure_demo_vip("normal@example.com")

    user = database.get_user_by_email("normal@example.com")
    assert user["is_vip"] == 0
