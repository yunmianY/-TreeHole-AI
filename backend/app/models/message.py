"""消息表 — 存储对话中的每条消息。

预留字段说明：
- emotion_score / emotion_label: V0.2 情感分析使用
- metadata: JSON 扩展字段（图片URL、语音URL等）
"""

from datetime import datetime, timezone

from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Float, Text
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import relationship

from app.core.database import Base


def _utcnow():
    return datetime.now(timezone.utc)


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=False, index=True)
    role = Column(String(20), nullable=False)  # 'user' | 'assistant' | 'system'
    content = Column(Text, nullable=False)
    timestamp = Column(DateTime, default=_utcnow, index=True)

    # ── V0.2 预留字段 ──
    emotion_score = Column(Float, nullable=True)  # -1..1
    emotion_label = Column(String(20), nullable=True)  # joy/sadness/anger/fear/neutral
    metadata_ = Column("metadata", JSON, default=dict)  # 图片URL、语音URL等

    # 关系
    conversation = relationship("Conversation", back_populates="messages")
