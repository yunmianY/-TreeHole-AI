"""JWT 令牌创建/验证 与 密码哈希。"""

from datetime import datetime, timedelta, timezone

import bcrypt
from jose import jwt, JWTError

from app.core.config import settings

# ── 密码哈希 ──


def hash_password(password: str) -> str:
    """对明文密码做 bcrypt 哈希。"""
    # bcrypt 要求密码不超过 72 字节
    password_bytes = password.encode("utf-8")[:72]
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password_bytes, salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证明文密码是否与哈希值匹配。"""
    password_bytes = plain_password.encode("utf-8")[:72]
    hashed_bytes = hashed_password.encode("utf-8")
    return bcrypt.checkpw(password_bytes, hashed_bytes)


# ── JWT ──

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """创建 JWT access token。

    Args:
        data: 要编码到 token 中的 claims（至少包含 "sub" 即 user_id）。
        expires_delta: 过期时间偏移量，默认使用配置中的值。

    Returns:
        编码后的 JWT 字符串。
    """
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    )
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, settings.secret_key, algorithm=settings.algorithm)


def decode_access_token(token: str) -> dict | None:
    """解码 JWT token，返回 payload；无效或过期则返回 None。"""
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        return payload
    except JWTError:
        return None
