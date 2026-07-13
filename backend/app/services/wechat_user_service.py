"""微信用户映射服务 — 将 WeChat 用户 ID 映射到 TreeHole 用户账号。

每个微信用户首次对话时自动创建 TreeHole 账号（用户名 = wx_{from_id}），
后续消息复用已有账号。密码随机生成且不可登录（仅用于数据库约束），
微信扫码本身就是认证。
"""

import logging
import uuid

from sqlalchemy.orm import Session

from app.models.user import User
from app.core.security import hash_password

logger = logging.getLogger(__name__)

WECHAT_USERNAME_PREFIX = "wx_"


class WeChatUserService:
    """微信用户 ↔ TreeHole 用户映射。

    - get_or_create_user(db, wx_id): 查询或自动注册
    - 已映射的用户缓存在内存中，避免重复查库
    """

    def __init__(self):
        self._cache: dict[str, User] = {}

    def get_or_create_user(self, db: Session, wx_id: str) -> User:
        """根据微信用户 ID 获取或创建对应的 TreeHole 用户。

        首次对话时自动注册 — 用户名 = wx_{from_id}，密码随机（不可用于 Web 登录）。
        """
        if wx_id in self._cache:
            return self._cache[wx_id]

        username = f"{WECHAT_USERNAME_PREFIX}{wx_id}"
        user = db.query(User).filter(User.username == username).first()

        if not user:
            user = User(
                id=str(uuid.uuid4()),
                username=username,
                hashed_password=hash_password(str(uuid.uuid4())),  # 随机密码
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            logger.info(f"[WeChat] 自动创建用户: {username}")

        self._cache[wx_id] = user
        return user

    def clear_cache(self):
        """清空映射缓存（重连后调用）。"""
        self._cache.clear()
