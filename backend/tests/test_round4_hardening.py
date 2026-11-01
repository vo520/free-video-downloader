"""回归：事件循环阻塞（认证/历史/订单）、缓存状态与热门标记的原子性、
到期时间格式一致性。"""
import os
import sys
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import video_cache_db
from video_cache_db import VideoCacheDB


@pytest.fixture()
def db(tmp_path):
    video_cache_db.VIDEO_CACHE_DB_PATH = str(tmp_path / "vc.db")
    return VideoCacheDB()


def _manager(db):
    import video_cache_manager
    mgr = video_cache_manager.VideoCacheManager.__new__(video_cache_manager.VideoCacheManager)
    mgr.db = db
    mgr._hot_cache_threshold = 3
    return mgr


# ===== 事件循环阻塞 =====

def test_login_route_is_sync():
    """bcrypt 耗时 300~600ms，登录/注册必须是同步路由（FastAPI 放线程池），
    否则整个事件循环被卡住。"""
    import api_auth

    assert not asyncio.iscoroutinefunction(api_auth.login), "login 必须是同步路由"
    assert not asyncio.iscoroutinefunction(api_auth.register), "register 必须是同步路由"


def test_auth_dependencies_are_sync():
    """get_current_user / get_optional_user 内部是同步 SQLite 查询。"""
    import auth

    assert not asyncio.iscoroutinefunction(auth.get_current_user)
    assert not asyncio.iscoroutinefunction(auth.get_optional_user)


def test_history_routes_are_sync():
    import api_history

    assert not asyncio.iscoroutinefunction(api_history.list_history)
    assert not asyncio.iscoroutinefunction(api_history.remove_history)
    assert not asyncio.iscoroutinefunction(api_history.clear_my_history)


def test_order_list_route_is_sync():
    import api_payment

    assert not asyncio.iscoroutinefunction(api_payment.list_orders)


import asyncio  # noqa: E402  （放在 assert 之后导入不影响用例语义）


# ===== 缓存状态与热门标记 =====

def _save(db, url="https://x.test/v"):
    db.save_video({
        "url": url,
        "video_info": {"platform": "youtube", "video_id": "a", "title": "t"},
        "metadata": {},
        "success": True,
    })


def test_update_status_active_refreshes_expiry(db):
    """置为 active 时必须刷新到期时间，否则保留旧的已过期时间会被立即清理。"""
    _save(db)
    # 先把到期时间改到过去
    db.update_cache_status("https://x.test/v", "active", "2000-01-01T00:00:00+00:00")
    # 不传 expires_at 再置为 active
    assert db.update_cache_status("https://x.test/v", "active") is True

    row = db.get_video("https://x.test/v")
    assert row["cache_status"] == "active"
    # 到期时间应被刷新到未来，不再是过去时刻
    assert row["cache_expires_at"] > "2026-01-01T00:00:00+00:00"


def test_update_status_non_active_keeps_expiry(db):
    """非 active 状态不应改动到期时间。"""
    _save(db)
    db.update_cache_status("https://x.test/v", "active", "2099-01-01T00:00:00+00:00")
    before = db.get_video("https://x.test/v")["cache_expires_at"]
    db.update_cache_status("https://x.test/v", "expired")
    after = db.get_video("https://x.test/v")["cache_expires_at"]
    assert before == after


def test_hit_count_and_hot_marking(db):
    """命中数自增 + 阈值标记热门。"""
    _save(db)
    mgr = _manager(db)

    assert mgr.process_cache_hit("https://x.test/v") is False
    assert mgr.process_cache_hit("https://x.test/v") is False
    # 第三次达到阈值(3)，应标记热门
    assert mgr.process_cache_hit("https://x.test/v") is True

    row = db.get_video("https://x.test/v")
    assert row["cache_hit_count"] == 3
    assert row["is_hot"] == 1


def test_hot_marking_is_idempotent(db):
    """已达阈值后再次命中不应重复返回「本次标记了热门」。"""
    _save(db)
    mgr = _manager(db)
    for _ in range(3):
        mgr.process_cache_hit("https://x.test/v")
    assert mgr.process_cache_hit("https://x.test/v") is False
    assert db.get_video("https://x.test/v")["is_hot"] == 1


# ===== 时间格式一致性 =====

def test_update_order_stripe_session_uses_iso_utc(tmp_path, monkeypatch):
    """updated_at 必须与其它订单写入使用同一 ISO 格式，
    否则同一列混用 "YYYY-MM-DD HH:MM:SS" 与 ISO 格式，按字符串比较会出错。"""
    import database

    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "app.db"))
    database.init_db()
    user = database.create_user("iso@example.com", "x")
    database.create_order(user["id"], "SA_ISO_1", 990, "cny", "monthly")

    database.update_order_stripe_session("SA_ISO_1", "cs_test_1")
    row = database.get_order_by_no("SA_ISO_1")
    assert row["stripe_session_id"] == "cs_test_1"
    # ISO 格式：T 分隔且带时区后缀
    assert "T" in row["updated_at"], row["updated_at"]
    assert "+00:00" in row["updated_at"] or row["updated_at"].endswith("Z"), row["updated_at"]


def test_checkout_binding_failure_keeps_order_pending(tmp_path, monkeypatch):
    """回归：会话已创建但 session_id 绑定写库失败时，订单必须保持 pending。

    根因：原实现把订单置 failed。而 webhook 的 complete_order /
    complete_order_by_order_no 都带 status='pending' 守卫，failed 订单永不匹配
    → 用户实际已付款但 VIP 永不激活。保持 pending 后，webhook 可按 metadata.order_no
    兜底补绑 session_id 并完成订单。
    """
    import database
    import api_payment

    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "app.db"))
    database.init_db()
    user = database.create_user("checkout_bind@example.com", "x")

    monkeypatch.setenv("STRIPE_SECRET_KEY", "sk_test_key")
    monkeypatch.setenv("STRIPE_PRICE_ID_MONTHLY", "price_test")

    class _Session:
        id = "cs_bind_fail_1"
        url = "https://checkout.stripe.test/cs_bind_fail_1"

    monkeypatch.setattr(
        api_payment.stripe.checkout.Session, "create", lambda **kwargs: _Session()
    )

    def _boom(*args, **kwargs):
        raise RuntimeError("db write failed")

    monkeypatch.setattr(api_payment, "update_order_stripe_session", _boom)

    resp = api_payment.create_checkout_session(
        api_payment.CreateCheckoutRequest(plan_type="monthly"), user
    )
    # 会话可用，仍要把 checkout_url 交给用户，不能因绑定失败而 500
    assert resp["success"] is True
    assert resp["data"]["checkout_url"] == _Session.url

    order_no = resp["data"]["order_no"]
    order = database.get_order_by_no(order_no)
    assert order["status"] == "pending", "绑定失败不得把订单置为 failed"
    assert order["stripe_session_id"] is None

    # webhook 的 order_no 兜底路径必须能完成订单并补绑 session_id
    completed = database.complete_order_by_order_no(order_no, _Session.id, "pi_bind_fail_1")
    assert completed is not None
    refreshed = database.get_order_by_no(order_no)
    assert refreshed["status"] == "paid"
    assert refreshed["stripe_session_id"] == _Session.id
