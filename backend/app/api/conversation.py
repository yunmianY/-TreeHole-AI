"""会话管理 API 路由。"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.conversation import Conversation
from app.models.message import Message
from app.schemas.conversation import (
    ConversationCreateRequest,
    ConversationUpdateRequest,
    ConversationResponse,
    MessageInConversation,
)

router = APIRouter(prefix="/api/conversations", tags=["会话"])


@router.post("", response_model=ConversationResponse, status_code=201)
def create_conversation(
    body: ConversationCreateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """创建新会话。"""
    conv = Conversation(user_id=current_user.id, title=body.title or "新对话")
    db.add(conv)
    db.commit()
    db.refresh(conv)
    return ConversationResponse(
        id=conv.id,
        title=conv.title,
        created_at=conv.created_at.isoformat(),
        updated_at=conv.updated_at.isoformat(),
        message_count=0,
    )


@router.get("", response_model=list[ConversationResponse])
def list_conversations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取当前用户的会话列表（按更新时间倒序，附带消息数）。"""
    convs = (
        db.query(Conversation)
        .filter(Conversation.user_id == current_user.id)
        .order_by(Conversation.updated_at.desc())
        .all()
    )

    result = []
    for c in convs:
        count = db.query(func.count(Message.id)).filter(
            Message.conversation_id == c.id
        ).scalar() or 0
        result.append(
            ConversationResponse(
                id=c.id,
                title=c.title,
                created_at=c.created_at.isoformat(),
                updated_at=c.updated_at.isoformat(),
                message_count=count,
            )
        )
    return result


@router.get("/{conversation_id}/messages", response_model=list[MessageInConversation])
def get_messages(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """获取某个会话的消息历史（需是会话所属用户）。"""
    conv = _get_user_conv(db, conversation_id, current_user.id)

    messages = (
        db.query(Message)
        .filter(Message.conversation_id == conversation_id)
        .order_by(Message.timestamp.asc())
        .all()
    )

    return [
        MessageInConversation(
            id=m.id,
            role=m.role,
            content=m.content,
            timestamp=m.timestamp.isoformat(),
            emotion_score=m.emotion_score,
            emotion_label=m.emotion_label,
        )
        for m in messages
    ]


# ── 辅助函数 ──

def _get_user_conv(db: Session, conv_id: str, user_id: str) -> Conversation:
    """查询会话并验证归属，否则 404。"""
    conv = (
        db.query(Conversation)
        .filter(Conversation.id == conv_id, Conversation.user_id == user_id)
        .first()
    )
    if not conv:
        raise HTTPException(status_code=404, detail="会话不存在")
    return conv


# ── 更新会话 ──

@router.patch("/{conversation_id}", response_model=ConversationResponse)
def update_conversation(
    conversation_id: str,
    body: ConversationUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """重命名会话。"""
    conv = _get_user_conv(db, conversation_id, current_user.id)
    conv.title = body.title
    db.commit()
    db.refresh(conv)

    count = db.query(func.count(Message.id)).filter(
        Message.conversation_id == conv.id
    ).scalar() or 0

    return ConversationResponse(
        id=conv.id,
        title=conv.title,
        created_at=conv.created_at.isoformat(),
        updated_at=conv.updated_at.isoformat(),
        message_count=count,
    )
