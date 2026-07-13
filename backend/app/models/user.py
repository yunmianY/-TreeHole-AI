"""用户表 — 存储账号与认证信息。"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, DateTime
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import relationship

from app.core.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


def _gen_uuid():
    return str(uuid.uuid4())


class User(Base):
    __tablename__ = "users"

    id = Column(String, primary_key=True, default=_gen_uuid)
    username = Column(String, unique=True, nullable=False, index=True)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime, default=_utcnow)
    settings = Column(JSON, default=dict)  # 用户配置（主题、模型偏好等）

    # 关系
    conversations = relationship("Conversation", back_populates="user", lazy="dynamic")
