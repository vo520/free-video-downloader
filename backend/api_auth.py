from datetime import datetime, timezone, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from auth import (
    create_token,
    get_current_user,
    hash_password,
    validate_email,
    validate_password,
    verify_password,
)
from database import create_user, get_user_by_email, get_db

router = APIRouter(prefix="/api/auth", tags=["auth"])

# 演示账号：登录后默认开通 VIP（一年有效期），仅作为前端体验/演示用。
DEMO_EMAIL = "demo@local.com"
DEMO_VIP_DURATION = timedelta(days=365)


class RegisterRequest(BaseModel):
    email: str
    password: str


class LoginRequest(BaseModel):
    email: str
    password: str


def _ensure_demo_vip(email: str) -> None:
    """若 email 为演示账号，则强制开通 VIP（默认一年）。

    不论注册还是登录入口，都保证 demo 账号以 VIP 身份返回，避免出现 demo
    因早期注册而被锁在普通用户态的情况。
    """
    if email != DEMO_EMAIL:
        return
    expire_at = (datetime.now(timezone.utc) + DEMO_VIP_DURATION).isoformat()
    with get_db() as conn:
        conn.execute(
            "UPDATE users SET is_vip = 1, vip_expire_at = ?, updated_at = datetime('now') "
            "WHERE email = ?",
            (expire_at, email),
        )


def _user_response_for(email: str, user: dict) -> dict:
    """读取最新 user 并构造响应。用于注册/登录后立即反映 demo VIP 写入。"""
    fresh = get_user_by_email(email) or user
    return _build_user_response(fresh)


def _build_user_response(user: dict) -> dict:
    is_vip = False
    vip_expire_at = None
    if user.get("is_vip") and user.get("vip_expire_at"):
        try:
            expire_str = user["vip_expire_at"]
            if "+" in expire_str or "Z" in expire_str:
                expire = datetime.fromisoformat(expire_str.replace("Z", "+00:00"))
            else:
                expire = datetime.fromisoformat(expire_str).replace(tzinfo=timezone.utc)
            is_vip = expire > datetime.now(timezone.utc)
            vip_expire_at = user["vip_expire_at"]
        except ValueError:
            pass

    return {
        "id": user["id"],
        "email": user["email"],
        "is_vip": is_vip,
        "vip_expire_at": vip_expire_at,
    }


@router.post("/register")
def register(req: RegisterRequest):
    # 先归一化再校验：避免带首尾空格的合法邮箱被拒；小写避免 User@x.com 与 user@x.com 重复注册。
    email = req.email.strip().lower()
    if not validate_email(email):
        raise HTTPException(status_code=400, detail="邮箱格式不正确")

    err = validate_password(req.password)
    if err:
        raise HTTPException(status_code=400, detail=err)

    if get_user_by_email(email):
        raise HTTPException(status_code=400, detail="该邮箱已注册")

    hashed = hash_password(req.password)
    try:
        user = create_user(email, hashed)
    except Exception:
        # 并发注册同邮箱：唯一约束兜底，避免直接 500，转为友好提示。
        if get_user_by_email(email):
            raise HTTPException(status_code=400, detail="该邮箱已注册")
        raise

    # 演示账号注册即默认开通 VIP，便于前端体验完整功能。
    _ensure_demo_vip(email)

    token = create_token(user["id"], email)

    return {
        "success": True,
        "data": {
            "token": token,
            "user": _user_response_for(email, user),
        },
    }


@router.post("/login")
def login(req: LoginRequest):
    # 与注册一致归一化为小写，避免 Foo@x / foo@x 被视为两个账号导致无法登录
    email = req.email.strip().lower()
    user = get_user_by_email(email)
    if not user:
        raise HTTPException(status_code=400, detail="邮箱或密码错误")

    if not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=400, detail="邮箱或密码错误")

    # 演示账号登录后默认开通 VIP（一年有效期），便于前端体验完整功能。
    _ensure_demo_vip(email)
    user = get_user_by_email(email) or user

    token = create_token(user["id"], user["email"])
    return {
        "success": True,
        "data": {
            "token": token,
            "user": _build_user_response(user),
        },
    }


@router.get("/me")
async def get_me(user: dict = Depends(get_current_user)):
    return {
        "success": True,
        "data": _build_user_response(user),
    }
