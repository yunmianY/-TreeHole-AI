"""会话相关请求/响应 schema。"""

from typing import Optional

from pydantic import BaseModel, Field


class ConversationCreateRequest(BaseModel):
    """创建会话请求。"""
    title: Optional[str] = Field("新对话", max_length=200)


class ConversationUpdateRequest(BaseModel):
    """更新会话请求（重命名）。"""
    title: str = Field(..., min_length=1, max_length=200)


class ConversationResponse(BaseModel):
    """会话摘要响应（列表用）。"""
    id: str
    title: str
    created_at: str
    updated_at: str
    message_count: int = 0  # 消息数量

    class Config:
        from_attributes = True


class MessageInConversation(BaseModel):
    """会话中的单条消息。"""
    id: int
    role: str
    content: str
    timestamp: str
    emotion_score: Optional[float] = None
    emotion_label: Optional[str] = None

    class Config:
        from_attributes = True
