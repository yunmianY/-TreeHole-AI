"""记忆节点表 — 长期记忆存储，含 FTS5 全文索引。"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import Column, String, DateTime, Float, Boolean, Text, event
from sqlalchemy.dialects.sqlite import JSON

from app.core.database import Base, engine


def _utcnow():
    return datetime.now(timezone.utc)


def _gen_uuid():
    return str(uuid.uuid4())


class MemoryNode(Base):
    """记忆节点 — 对齐开发文档 4.4 节。

    同时存储在关系库（结构化查询）和向量库（语义检索）。
    """

    __tablename__ = "memories"

    id = Column(String, primary_key=True, default=_gen_uuid)
    user_id = Column(String, nullable=False, index=True)
    content = Column(Text, nullable=False)  # 记忆文本（一句话）
    emotion_label = Column(String(20), nullable=True)  # joy/sadness/anger/fear/neutral
    importance = Column(Float, default=0.5)  # 0~1 重要度
    source_message_ids = Column(JSON, default=list)  # 来源消息 ID 列表
    created_at = Column(DateTime, default=_utcnow)
    last_accessed = Column(DateTime, default=_utcnow)
    deprecated = Column(Boolean, default=False)

    def to_dict(self):
        return {
            "id": self.id,
            "content": self.content,
            "emotion_label": self.emotion_label,
            "importance": self.importance,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }


# ── FTS5 全文搜索虚拟表 ──

_FTS_SETUP_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    content,
    content='memories',
    content_rowid='rowid'
);

CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories
BEGIN
    INSERT INTO memories_fts(rowid, content) VALUES (new.rowid, new.content);
END;

CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories
BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content) VALUES('delete', old.rowid, old.content);
END;

CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories
BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content) VALUES('delete', old.rowid, old.content);
    INSERT INTO memories_fts(rowid, content) VALUES (new.rowid, new.content);
END;
"""


@event.listens_for(MemoryNode.__table__, "after_create")
def _create_fts(target, connection, **kw):
    """在 memories 表创建后自动创建 FTS5 虚拟表和触发器。"""
    # 逐条执行 SQL 语句
    for stmt in _FTS_SETUP_SQL.strip().split(";"):
        stmt = stmt.strip()
        if stmt:
            connection.exec_driver_sql(stmt)
