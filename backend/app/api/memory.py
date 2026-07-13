"""记忆检索 API — 调试与浏览。"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import text

from app.api.deps import get_db, get_current_user
from app.models.user import User
from app.models.memory import MemoryNode
from app.schemas.memory import MemoryItem
from app.services.memory_service import MemoryService
from app.services.deepseek_provider import DeepSeekProvider
from app.services.embedding_service import TFIDFEmbeddingProvider
from app.services.vector_store import ChromaDBStore

router = APIRouter(prefix="/api/memories", tags=["记忆"])

_memory_service = MemoryService(
    llm_provider=DeepSeekProvider(),
    embedding_provider=TFIDFEmbeddingProvider(),
    vector_store=ChromaDBStore(),
)


@router.get("/search", response_model=list[MemoryItem])
def search_memories(
    q: str = Query(..., min_length=1, description="搜索关键词"),
    limit: int = Query(5, ge=1, le=20),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """多路检索用户的长期记忆（调试用）。"""
    try:
        results = _memory_service.retrieve(db, current_user.id, q, top_k=limit)
        return [
            MemoryItem(
                id=r.get("content", "")[:8],
                content=r["content"],
                emotion_label=r.get("emotion_label"),
                importance=r.get("importance", 0.5),
                created_at="",
            )
            for r in results
        ]
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"检索失败: {e}")


@router.get("", response_model=list[MemoryItem])
def list_memories(
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """列出用户的所有记忆（按创建时间倒序）。"""
    memories = (
        db.query(MemoryNode)
        .filter(MemoryNode.user_id == current_user.id, MemoryNode.deprecated == False)
        .order_by(MemoryNode.created_at.desc())
        .limit(limit)
        .all()
    )
    return [
        MemoryItem(
            id=m.id,
            content=m.content,
            emotion_label=m.emotion_label,
            importance=m.importance,
            created_at=m.created_at.isoformat() if m.created_at else "",
        )
        for m in memories
    ]
