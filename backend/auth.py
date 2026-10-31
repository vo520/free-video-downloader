import os
import re
import secrets
import warnings
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# 不再硬编码弱密钥。未配置 JWT_SECRET 时生成随机临时密钥（仅本次进程有效，重启即失效），
# 避免被利用默认密钥伪造 Token；生产环境必须通过环境变量设置固定密钥。
JWT_SECRET = os.getenv("JWT_SECRET")
if not JWT_SECRET:
    JWT_SECRET = secrets.token_hex(32)
    warnings.warn(
        "JWT_SECRET 未设置，已使用随机临时密钥（进程重启后失效）。"
        "生产环境请通过环境变量 JWT_SECRET 配置固定密钥，否则已签发的 Token 会在重启后失效。",
        RuntimeWarning,
    )
JWT_ALGORITHM = "HS256"
JWT_EXPIRE_HOURS = 72

security = HTTPBearer(auto_error=False)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(password.encode(), hashed.encode())


def create_token(user_id: int, email: str) -> str:
    payload = {
        "sub": str(user_id),
        "email": email,
        "exp": datetime.now(timezone.utc) + timedelta(hours=JWT_EXPIRE_HOURS),
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        # 防御：缺 sub 或 sub 非整数时按无效 Token 处理，避免 int() 抛 KeyError 导致 500
        if "sub" not in payload:
            raise jwt.InvalidTokenError("missing sub")
        payload["sub"] = int(payload["sub"])
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token 已过期，请重新登录")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="无效的 Token")


def validate_email(email: str) -> bool:
    return bool(re.match(r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$", email))


def validate_password(password: str) -> str | None:
    """返回 None 表示校验通过，否则返回错误信息"""
    if len(password) < 6:
        return "密码长度不能少于 6 位"
    if len(password) > 50:
        return "密码长度不能超过 50 位"
    return None


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """必须登录

    同步函数（FastAPI 会放入线程池执行）：内部 get_user_by_id 是同步 SQLite 查询，
    若写成 async def 会在事件循环里执行同步 IO，阻塞其它请求。
    """
    if not credentials:
        raise HTTPException(status_code=401, detail="请先登录")
    payload = decode_token(credentials.credentials)
    from database import get_user_by_id
    user = get_user_by_id(payload["sub"])
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user


def get_optional_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict | None:
    """可选登录：已登录返回用户信息，未登录返回 None

    同 get_current_user：同步函数，避免同步 SQLite 查询阻塞事件循环。
    """
    if not credentials:
        return None
    try:
        payload = decode_token(credentials.credentials)
        from database import get_user_by_id
        return get_user_by_id(payload["sub"])
    except HTTPException:
        return None
