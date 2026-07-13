"""聊天 API 路由 — 核心对话接口（V0.2 集成记忆+情感）。"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from sqlalchemy.orm import Session

from app.api.deps import get_db, get_current_user
from app.core.database import SessionLocal
from app.models.user import User
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.shared import get_chat_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["聊天"])

# 共享 ChatService 单例
_chat_service = get_chat_service()


# ── BackgroundTasks 中执行的记忆提取 ──

def _extract_memories_bg(user_id: str, recent_messages: list[dict]):
    """在后台线程中执行记忆提取（独立 DB session）。"""
    db = SessionLocal()
    try:
        count = _chat_service.extract_memories_sync(db, user_id, recent_messages)
        if count:
            logger.info(f"Extracted {count} memories for user {user_id}")
    except Exception as e:
        logger.error(f"Memory extraction failed: {e}")
    finally:
        db.close()


@router.post("/chat", response_model=ChatResponse)
def chat(
    body: ChatRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """发送消息给树洞，获取 AI 回复。

    V0.2 新增：记忆检索注入 + 情感分析 + 异步记忆提取。
    """
    try:
        result = _chat_service.send_message(
            db=db,
            user_id=current_user.id,
            message=body.message,
            conversation_id=body.conversation_id,
        )

        # 读取待处理的记忆提取上下文，加入 BackgroundTasks
        ctx = _chat_service.pop_extraction_context()
        if ctx:
            user_id, messages = ctx
            background_tasks.add_task(_extract_memories_bg, user_id, messages)

        return ChatResponse(**result)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"对话处理失败: {str(e)}",
        )
