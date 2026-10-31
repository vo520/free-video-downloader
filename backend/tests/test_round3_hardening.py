"""回归：SSE 帧解析(CRLF)、缓存过期校验、TTL 兜底、URL 归一化口径统一、
支付回滚与 webhook 兜底、订单失败原因落库。"""
import os
import sys
from unittest import mock

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import video_cache_db
from video_cache_db import VideoCacheDB
from database import canonical_video_url


@pytest.fixture()
def db(tmp_path):
    video_cache_db.VIDEO_CACHE_DB_PATH = str(tmp_path / "vc.db")
    return VideoCacheDB()


# ===== URL 归一化口径 =====

def test_canonical_video_url_matches_history_rule():
    assert canonical_video_url("http://www.Example.com/v#frag") == "https://example.com/v"
    assert canonical_video_url("https://example.com/v") == "https://example.com/v"
    # 纯数字抖音 ID 补全为完整链接，与 /api/parse 处理一致
    assert canonical_video_url("7001234") == "https://douyin.com/video/7001234"


def test_cache_and_history_use_same_url_key(db):
    """同一视频的不同 URL 形态必须落成同一条缓存记录（与 history 去重口径一致）。"""
    db.save_video({
        "url": "http://www.Example.com/v#frag",
        "video_info": {"platform": "youtube", "video_id": "a", "title": "t"},
        "metadata": {},
        "success": True,
    })
    db.save_video({
        "url": "https://example.com/v",
        "video_info": {"platform": "youtube", "video_id": "a", "title": "t2"},
        "metadata": {},
        "success": True,
    })
    assert db.count_videos() == 1
    # 按原始形态也能查到（查/写口径必须一致）
    assert db.get_video("http://www.Example.com/v#frag") is not None
    assert db.get_video("https://example.com/v") is not None


def test_numeric_douyin_id_cache_key(db):
    db.save_video({
        "url": "7001234",
        "video_info": {"platform": "douyin", "video_id": "7001234", "title": "t"},
        "metadata": {},
        "success": True,
    })
    assert db.get_video("https://www.douyin.com/video/7001234") is not None


# ===== 缓存有效期校验 =====

def _manager(db):
    import video_cache_manager
    mgr = video_cache_manager.VideoCacheManager.__new__(video_cache_manager.VideoCacheManager)
    mgr.db = db
    return mgr


def test_validate_cache_rejects_expired_by_timestamp(db):
    """过期判定必须看 cache_expires_at，而不只是 cache_status。
    系统从不对任何行写 'expired'（cleanup 是直接 DELETE），只看状态会误判有效。"""
    db.save_video({
        "url": "https://expired.test/v",
        "video_info": {"platform": "youtube", "video_id": "a", "title": "t"},
        "metadata": {},
        "success": True,
    })
    # 手动把到期时间改到过去，状态仍为 active
    db.update_cache_status("https://expired.test/v", "active", "2000-01-01T00:00:00+00:00")

    result = _manager(db).validate_cache("https://expired.test/v")
    assert result["valid"] is False
    assert result["reason"] == "缓存已过期"


def test_validate_cache_accepts_future_expiry(db):
    db.save_video({
        "url": "https://valid.test/v",
        "video_info": {"platform": "youtube", "video_id": "a", "title": "t"},
        "metadata": {},
        "success": True,
    })
    db.update_cache_status("https://valid.test/v", "active", "2099-01-01T00:00:00+00:00")
    assert _manager(db).validate_cache("https://valid.test/v")["valid"] is True


# ===== TTL 兜底 =====

def test_get_cache_ttl_falls_back_on_null_or_nonpositive(db):
    mgr = _manager(db)
    with mock.patch.object(db, "get_cache_rules", return_value=[{
        "rule_name": "r", "is_active": True, "platform": "", "url_pattern": "",
        "quality": "", "min_duration": 0, "max_duration": 0,
        "ttl_seconds": None, "priority": None,
    }]):
        # ttl_seconds 为 NULL / priority 为 NULL 都不能抛异常，且回退默认值
        assert mgr.get_cache_ttl("https://x.test/v", "youtube", "720p", 10) == 86400

    with mock.patch.object(db, "get_cache_rules", return_value=[{
        "rule_name": "r", "is_active": True, "platform": "", "url_pattern": "",
        "quality": "", "min_duration": 0, "max_duration": 0,
        "ttl_seconds": 0, "priority": 5,
    }]):
        # 非正数 TTL 会写出「已过期」的时间点，必须兜底
        assert mgr.get_cache_ttl("https://x.test/v", "youtube", "720p", 10) == 86400


def test_refresh_cache_uses_update_result(db):
    """update_cache_status 返回是否真的改到了记录，记录不存在时 refresh_cache 应返回 False。"""
    mgr = _manager(db)
    assert mgr.refresh_cache("https://none.test/v") is False


# ===== 支付链路 =====

def test_fail_order_records_reason(tmp_path, monkeypatch):
    import database

    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "app.db"))
    database.init_db()
    user = database.create_user("fail_reason@example.com", "x")
    order = database.create_order(user["id"], "SA_T1", 990, "cny", "monthly")

    assert database.fail_order("SA_T1", reason="会话创建失败") is True
    row = database.get_order_by_no("SA_T1")
    assert row["status"] == "failed"
    assert row["fail_reason"] == "会话创建失败"


def test_complete_order_by_order_no_fallback(tmp_path, monkeypatch):
    """stripe_session_id 未绑定时，按 order_no 仍能完成订单并开通 VIP。"""
    import database

    monkeypatch.setattr(database, "DB_PATH", str(tmp_path / "app.db"))
    database.init_db()
    user = database.create_user("fallback@example.com", "x")
    order = database.create_order(user["id"], "SA_T2", 990, "cny", "monthly")

    # 模拟 create-checkout 写库失败：stripe_session_id 未绑定
    assert database.complete_order("cs_test_missing", "pi_1") is None

    result = database.complete_order_by_order_no("SA_T2", "cs_test", "pi_1")
    assert result is not None
    assert result["status"] == "paid"
    updated = database.get_user_by_id(user["id"])
    assert updated["is_vip"] == 1
    assert updated["vip_expire_at"]


def test_create_checkout_rolls_back_pending_order(monkeypatch):
    """会话创建失败时必须把 pending 订单标记为 failed，不能留孤儿记录。"""
    import api_payment

    calls = {}

    def fake_create_order(*a, **k):
        calls["order_no"] = k.get("order_no") or (a[1] if len(a) > 1 else None)
        return {"order_no": calls["order_no"], "status": "pending"}

    def fake_fail(order_no, reason=""):
        calls["failed"] = (order_no, reason)
        return True

    def boom(*a, **k):
        raise RuntimeError("network down")

    monkeypatch.setattr(api_payment, "create_order", fake_create_order)
    monkeypatch.setattr(api_payment, "fail_order", fake_fail)
    monkeypatch.setattr(api_payment.stripe.checkout.Session, "create", boom)
    monkeypatch.setattr(
        api_payment, "_get_config",
        lambda key, default="": {"STRIPE_SECRET_KEY": "sk_test",
                                 "STRIPE_PRICE_ID_MONTHLY": "price_test"}.get(key, default),
    )

    # 直接调用路由函数体（绕过鉴权依赖），验证异常路径的回滚
    from fastapi import HTTPException

    with pytest.raises(HTTPException):
        api_payment.create_checkout_session(
            api_payment.CreateCheckoutRequest(plan_type="monthly"),
            {"id": 1, "email": "a@b.c"},
        )

    # 非 StripeError（如网络/写库异常）也必须回滚，原实现只捕获 StripeError
    assert calls.get("failed") is not None
    assert calls["failed"][0] == calls["order_no"]


def test_webhook_falls_back_to_order_no(monkeypatch):
    """webhook 按 session_id 匹配不到订单时，用 metadata.order_no 兜底完成订单。"""
    import api_payment

    seen = {}

    def fake_complete(session_id, payment_intent_id):
        seen["by_session"] = session_id
        return None  # 模拟 stripe_session_id 未绑定导致匹配不到

    def fake_complete_by_no(order_no, session_id, payment_intent_id):
        seen["by_order_no"] = order_no
        return {"order_no": order_no, "status": "paid"}

    monkeypatch.setattr(api_payment, "complete_order", fake_complete)
    monkeypatch.setattr(api_payment, "complete_order_by_order_no", fake_complete_by_no)

    session = {
        "id": "cs_123",
        "payment_intent": "pi_1",
        "metadata": {"order_no": "SA_FALLBACK_0001"},
    }
    result = api_payment._complete_order_with_fallback(session, "pi_1")

    assert seen["by_session"] == "cs_123"
    assert seen["by_order_no"] == "SA_FALLBACK_0001"
    assert result["status"] == "paid"
