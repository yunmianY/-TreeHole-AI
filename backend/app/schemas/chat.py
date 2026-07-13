"""聊天相关请求/响应 schema。"""

from typing import Optional

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """发送消息请求。

    设计说明：
    - conversation_id 为 None 时，ChatService 自动创建新会话。
    - streaming 预留字段，V0.1 仅支持非流式（默认 False）。
    """
    message: str = Field(..., min_length=1, description="用户消息文本")
    conversation_id: Optional[str] = Field(None, description="会话ID，为空则创建新会话")
    streaming: bool = Field(False, description="是否流式返回（V0.1 暂不支持）")


class ChatResponse(BaseModel):
    """聊天回复响应。"""
    message_id: int
    conversation_id: str
    role: str = "assistant"
    content: str
