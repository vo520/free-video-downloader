"""
支付 Webhook 幂等自测

验证：同一 Stripe session 在「至少一次投递」语义下被重复回调时，
complete_order 仅激活一次 VIP、不会产生第二次 paid_at（即不重复计费 / 不重复延期）。

做法：mock stripe.Webhook.construct_event 模拟重复投递，直接驱动 api_payment.stripe_webhook，
全程使用临时库，不触碰真实 backend/data/app.db。
"""
import os
import sys
import tempfile

# 1) 将 database 指向临时库（避免触碰真实 data/app.db）
_TMP = tempfile.mkdtemp(prefix="fvd_test_")
_TMP_DB = os.path.join(_TMP, "test_app.db")
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))  # backend/

import database

database.DB_PATH = _TMP_DB
database.get_db_path = lambda: _TMP_DB

# 2) 导入支付模块（需在 mock stripe 之前；api_payment 内部 import stripe）
import api_payment

# 3) mock stripe.Webhook.construct_event，避免真实验签
import stripe

_EVENT = {}


def _fake_construct_event(payload, sig_header, secret):
    return _EVENT


stripe.Webhook.construct_event = _fake_construct_event


# 4) 最小请求桩：实现 request.body() 与 request.headers.get()
class _FakeRequest:
    async def body(self):
        return b"{}"

    @property
    def headers(self):
        return {}


def _setup():
    database.init_db()
    with database.get_db() as conn:
        conn.execute(
            "INSERT INTO users (email, password_hash) VALUES (?, ?)",
            ("idempotency_test@example.com", "x"),
        )
        uid = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    database.create_order(uid, "ORD_IDEM_1", 990, "cny", "monthly")
    database.update_order_stripe_session("ORD_IDEM_1", "sess_idem_123")
    return uid


def _assert_state(tag):
    with database.get_db() as conn:
        order = conn.execute(
            "SELECT status, paid_at FROM orders WHERE order_no='ORD_IDEM_1'"
        ).fetchone()
        user = conn.execute(
            "SELECT is_vip, vip_expire_at FROM users "
            "WHERE id=(SELECT user_id FROM orders WHERE order_no='ORD_IDEM_1')"
        ).fetchone()
    assert order["status"] == "paid", f"[{tag}] 订单状态应为 paid，实际 {order['status']}"
    assert order["paid_at"] is not None, f"[{tag}] paid_at 不应为空"
    assert user["is_vip"] == 1, f"[{tag}] is_vip 应为 1"
    assert user["vip_expire_at"] is not None, f"[{tag}] vip_expire_at 不应为空"
    return order["paid_at"]


async def _run():
    os.environ.setdefault("STRIPE_WEBHOOK_SECRET", "test_secret")
    os.environ.setdefault("STRIPE_SECRET_KEY", "test_key")

    _setup()

    _EVENT.clear()
    _EVENT.update({
        "type": "checkout.session.completed",
        "data": {"object": {
            "id": "sess_idem_123",
            "payment_status": "paid",
            "payment_intent": "pi_idem_123",
        }},
    })

    req = _FakeRequest()

    # 第一次投递
    await api_payment.stripe_webhook(req)
    paid_at_1 = _assert_state("first")

    # 第二次投递（Stripe 至少一次投递语义下的重复回调）
    await api_payment.stripe_webhook(req)
    paid_at_2 = _assert_state("second")

    # 幂等核心断言：paid_at 不应因重复投递而改变
    assert paid_at_1 == paid_at_2, (
        f"幂等失败：重复 webhook 改变了 paid_at ({paid_at_1} -> {paid_at_2})"
    )

    # 第三次投递（async_payment_succeeded 分支也应幂等）
    _EVENT["type"] = "checkout.session.async_payment_succeeded"
    await api_payment.stripe_webhook(req)
    paid_at_3 = _assert_state("third")
    assert paid_at_3 == paid_at_1, "async_payment_succeeded 分支未保持幂等"

    print(
        "WEBHOOK IDEMPOTENCY OK: "
        f"VIP 激活 1 次，paid_at 在 3 次重复投递下保持稳定 ({paid_at_1})"
    )


if __name__ == "__main__":
    import asyncio

    asyncio.run(_run())
