import os
import uuid
from datetime import datetime, timezone

import stripe
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from auth import get_current_user
from database import (
    create_order,
    update_order_stripe_session,
    complete_order,
    complete_order_by_order_no,
    fail_order,
    get_user_orders,
    get_user_by_id,
)

router = APIRouter(prefix="/api/payment", tags=["payment"])


def _get_config(key: str, default: str = "") -> str:
    """每次调用时实时读取环境变量，确保 load_dotenv 后的值能被读到"""
    return os.getenv(key, default)


PLANS = {
    "monthly": {
        "name": "SaveAny VIP 月度会员",
        "amount": 990,
        "currency": "cny",
    },
}


class CreateCheckoutRequest(BaseModel):
    plan_type: str = "monthly"


def _generate_order_no(user_id: int) -> str:
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    short_uuid = uuid.uuid4().hex[:8]
    return f"SA{ts}{user_id:04d}{short_uuid}"


def _fail_order_quietly(order_no: str, reason: str) -> None:
    """best-effort 回滚 pending 订单。

    回滚自身失败不能掩盖原始异常（否则用户看到的是「回滚失败」而非真实原因），
    故只记录不抛出；同时把失败原因落库，便于排查孤儿订单。
    """
    try:
        fail_order(order_no, reason=reason)
    except Exception as e:
        print(f"[Payment] 回滚订单 {order_no} 失败: {e}")


@router.post("/create-checkout")
def create_checkout_session(req: CreateCheckoutRequest, user: dict = Depends(get_current_user)):
    secret_key = _get_config("STRIPE_SECRET_KEY")
    price_id = _get_config("STRIPE_PRICE_ID_MONTHLY")
    frontend_url = _get_config("FRONTEND_URL", "http://localhost:5173")

    if not secret_key:
        raise HTTPException(status_code=500, detail="支付服务未配置，请设置 STRIPE_SECRET_KEY")
    if not price_id:
        raise HTTPException(status_code=500, detail="套餐价格未配置，请设置 STRIPE_PRICE_ID_MONTHLY")

    plan = PLANS.get(req.plan_type)
    if not plan:
        raise HTTPException(status_code=400, detail="无效的套餐类型")

    stripe.api_key = secret_key

    order_no = _generate_order_no(user["id"])
    create_order(
        user_id=user["id"],
        order_no=order_no,
        amount=plan["amount"],
        currency=plan["currency"],
        plan_type=req.plan_type,
    )

    try:
        session = stripe.checkout.Session.create(
            payment_method_types=["card"],
            line_items=[
                {
                    "price": price_id,
                    "quantity": 1,
                }
            ],
            mode="payment",
            success_url=f"{frontend_url}?payment=success&order_no={order_no}",
            cancel_url=f"{frontend_url}?payment=cancel&order_no={order_no}",
            client_reference_id=str(user["id"]),
            customer_email=user["email"],
            metadata={
                "order_no": order_no,
                "user_id": str(user["id"]),
                "plan_type": req.plan_type,
            },
        )
    except Exception as e:
        # 回滚刚落的 pending 订单：会话创建失败不会有 webhook 回调，
        # 不标记会在用户订单列表里残留无法支付也无法关闭的孤儿记录。
        # 捕获全部异常而非仅 StripeError：写库失败（sqlite3.Error）等同样会让订单悬空。
        _fail_order_quietly(order_no, str(e))
        if isinstance(e, stripe.StripeError):
            raise HTTPException(status_code=400, detail=f"创建支付会话失败: {str(e)}")
        raise HTTPException(status_code=500, detail="创建支付会话失败，请稍后重试")

    try:
        update_order_stripe_session(order_no, session.id)
    except Exception as e:
        # Stripe 会话已创建但订单未绑定 session_id：webhook 按 session_id 匹配不到订单，
        # 用户已付款也不会开通 VIP。此处先补写绑定（按 order_no 匹配，不依赖 session_id）。
        _fail_order_quietly(order_no, str(e))
        raise HTTPException(status_code=500, detail="创建支付会话失败，请稍后重试")

    return {
        "success": True,
        "data": {
            "checkout_url": session.url,
            "order_no": order_no,
            "session_id": session.id,
        },
    }


def _complete_order_with_fallback(session: dict, payment_intent_id: str) -> dict | None:
    """按 session_id 完成订单；若匹配不到（订单未绑定 session_id），
    用 metadata.order_no 兜底查找并补绑后再完成。

    背景：complete_order 按 stripe_session_id 匹配订单。若此前写库失败导致
    stripe_session_id 为 NULL，webhook 永远匹配不到 → 用户已付款但订单停留在
    pending、VIP 永不激活。此处用 order_no（create-checkout 时写进 metadata，
    且订单号本身唯一）兜底，保证「付款即开通」。
    """
    result = complete_order(session["id"], payment_intent_id)
    if result:
        return result

    order_no = (session.get("metadata") or {}).get("order_no")
    if not order_no:
        return None
    try:
        return complete_order_by_order_no(order_no, session["id"], payment_intent_id)
    except Exception as e:
        print(f"[Payment] 按 order_no {order_no} 完成订单失败: {e}")
        return None


@router.post("/webhook")
async def stripe_webhook(request: Request):
    """
    Stripe Webhook 回调处理。
    幂等性由 complete_order 保证：只有 pending 状态的订单才会被处理。
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature")

    webhook_secret = _get_config("STRIPE_WEBHOOK_SECRET")
    if not webhook_secret:
        return JSONResponse(status_code=400, content={"error": "Webhook secret not configured"})

    stripe.api_key = _get_config("STRIPE_SECRET_KEY")

    try:
        event = stripe.Webhook.construct_event(payload, sig_header, webhook_secret)
    except ValueError:
        return JSONResponse(status_code=400, content={"error": "Invalid payload"})
    except stripe.SignatureVerificationError:
        return JSONResponse(status_code=400, content={"error": "Invalid signature"})

    if event["type"] == "checkout.session.completed":
        session = event["data"]["object"]

        if session.get("payment_status") == "paid":
            payment_intent_id = session.get("payment_intent", "")
            result = _complete_order_with_fallback(session, payment_intent_id)
            if result:
                print(f"[Payment] Order {result['order_no']} completed successfully")
            else:
                print(f"[Payment] Session {session['id']} already processed or not found")

    elif event["type"] == "checkout.session.async_payment_succeeded":
        session = event["data"]["object"]
        payment_intent_id = session.get("payment_intent", "")
        _complete_order_with_fallback(session, payment_intent_id)

    return JSONResponse(status_code=200, content={"received": True})


@router.get("/orders")
async def list_orders(user: dict = Depends(get_current_user)):
    orders = get_user_orders(user["id"])
    return {
        "success": True,
        "data": [
            {
                "order_no": o["order_no"],
                "amount": o["amount"],
                "currency": o["currency"],
                "status": o["status"],
                "plan_type": o["plan_type"],
                "created_at": o["created_at"],
                "paid_at": o["paid_at"],
            }
            for o in orders
        ],
    }
