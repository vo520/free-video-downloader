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

# 演示（访客）账号：前端在未登录时用它静默建立会话，让访客也能用 AI 总结等需要登录的能力。
# 该账号是所有访客共用的公共账号，凭据写在源码里 —— 因此它的历史记录不能当作用户数据使用。
DEMO_EMAIL = "demo@local.com"

security = HTTPBearer(auto_error=False)


def is_shared_demo_user(user: dict | None) -> bool:
    """判断 user 是否为公共演示账号。

    前端 api/auth.js#ensureDefaultUser 会在未登录时静默用该账号登录，
    所有访客因此落在同一个 user_id 上。若把访客的解析/下载/总结记录写进这个账号，
    等于把每个人的记录公开给任何知道演示凭据的人（凭据就在源码里），
    且访客自己也看不到（云端历史抽屉仅对登录用户挂载）。
    因此共享账号只用于"借用登录态"，不承载用户历史。
    """
    return bool(user) and (user.get("email") or "").lower() == DEMO_EMAIL


def get_admin_emails() -> set[str]:
    """读取管理员邮箱白名单（环境变量 ADMIN_EMAILS，逗号分隔）。

    每次调用都重新读环境变量：便于测试用 monkeypatch 覆盖，
    也允许运行期改环境变量后立即生效（无需重启进程）。
    默认空集合 —— 即默认没有任何管理员，破坏性操作需显式配置。
    """
    raw = os.getenv("ADMIN_EMAILS", "")
    return {item.strip().lower() for item in raw.split(",") if item.strip()}


def is_admin_user(user: dict | None) -> bool:
    """判断用户是否具备管理员权限。

    公共演示账号 demo@local.com 永远不是管理员：它的凭据写在源码里，
    任何人都能拿到，给它管理员权限等于把后台开放给全网。
    """
    if not user:
        return False
    email = (user.get("email") or "").strip().lower()
    if not email or email == DEMO_EMAIL:
        return False
    return email in get_admin_emails()


# bcrypt 只处理密码的前 72 字节，bcrypt 5.0 起对超长输入直接抛 ValueError，
# 会冒泡成注册/登录 500。这里统一按 72 字节截断（与旧版 bcrypt 的隐式截断行为一致），
# 既保证历史长密码仍能登录，也为 hash_password 兜底。
_BCRYPT_MAX_BYTES = 72


def _bcrypt_bytes(password: str) -> bytes:
    return password.encode("utf-8")[:_BCRYPT_MAX_BYTES]


def hash_password(password: str) -> str:
    return bcrypt.hashpw(_bcrypt_bytes(password), bcrypt.gensalt()).decode()


def verify_password(password: str, hashed: str) -> bool:
    return bcrypt.checkpw(_bcrypt_bytes(password), hashed.encode())


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
        # 防御：缺 sub 或 sub 非整数时按无效 Token 处理。
        # int() 对 "abc" 抛 ValueError、对 None/列表等抛 TypeError，二者都不会被下面的
        # jwt.InvalidTokenError 分支捕获，会直接冒泡成 500 —— 必须在这里归一成无效 Token。
        if "sub" not in payload:
            raise jwt.InvalidTokenError("missing sub")
        try:
            payload["sub"] = int(payload["sub"])
        except (ValueError, TypeError):
            raise jwt.InvalidTokenError("invalid sub")
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
    # 字符数达标不代表字节数达标：bcrypt 上限是 72 字节，中文/emoji 等
    # 多字节字符会在 25~50 个字符时就越界，必须按 UTF-8 字节数再校验一次。
    if len(password.encode("utf-8")) > _BCRYPT_MAX_BYTES:
        return "密码过长：UTF-8 编码后不能超过 72 字节（中文约 24 个字符）"
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


def require_admin(user: dict = Depends(get_current_user)) -> dict:
    """管理员闸门：非管理员一律 403。

    同步函数（FastAPI 放进线程池）：内部 get_user_by_id 是同步 SQLite 查询。
    定义在 get_current_user 之后（Depends 需在定义时就能取到被依赖函数）。
    """
    if not is_admin_user(user):
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return user
