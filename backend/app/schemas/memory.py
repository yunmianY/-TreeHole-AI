"""记忆相关请求/响应 schema。"""

from typing import Optional

from pydantic import BaseModel, Field


class MemorySearchRequest(BaseModel):
    """记忆检索请求。"""
    query: str = Field(..., min_length=1, description="搜索关键词")
    limit: int = Field(5, ge=1, le=20, description="返回条数")


class MemoryItem(BaseModel):
    """单条记忆响应。"""
    id: str
    content: str
    emotion_label: Optional[str] = None
    importance: float
    created_at: str
