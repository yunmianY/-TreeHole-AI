"""记忆服务 — 记忆提取、多路检索(RRF融合)、冲突解决。

职责：
1. extract_memories: 对话后异步提取长期记忆，LLM → JSON → dedup → 存储
2. retrieve: 多路检索（向量 + FTS5 关键词），RRF 融合返回 Top-K
3. dedup: 语义去重，相似记忆合并重要度
"""

import json
import logging
import re
from datetime import datetime, timezone

from sqlalchemy.orm import Session
from sqlalchemy import text

from app.models.memory import MemoryNode
from app.services.base import LLMProvider
from app.services.embedding_service import EmbeddingProvider
from app.services.vector_store import VectorStore

logger = logging.getLogger(__name__)

# ── 记忆提取 Prompt ──
_EXTRACT_PROMPT = """分析以下对话，提取值得长期记忆的重要信息。返回一个 JSON 数组（最多5条），每条包含：
- content: 记忆文本，一句话概括（如"用户生日是5月20日"、"用户升职了非常开心"）
- emotion_label: 情感标签 (joy/sadness/anger/fear/neutral)
- importance: 重要度 0~1，生活重大事件/个人偏好 > 日常琐事

注意：
- 只提取对了解用户有帮助的长期信息
- 不要提取临时性、一次性的闲聊
- 如果没有值得记忆的内容，返回空数组 []

对话：
{conversation}"""

# RRF 参数
RRF_K = 60


class MemoryService:
    """记忆提取与检索服务。

    使用方式:
        svc = MemoryService(llm_provider, embedding_provider, vector_store)
        # 提取记忆
        memories = svc.extract_memories(db, user_id, recent_messages)
        # 检索记忆
        results = svc.retrieve(db, user_id, user_message)
    """

    def __init__(
        self,
        llm_provider: LLMProvider,
        embedding_provider: EmbeddingProvider,
        vector_store: VectorStore,
    ):
        self._llm = llm_provider
        self._embed = embedding_provider
        self._vector = vector_store

    # ── 记忆提取 ──

    def extract_memories(self, db: Session, user_id: str, recent_messages: list[dict]) -> int:
        """从最近对话中提取长期记忆并存储。

        Args:
            db: 数据库会话（注意：此方法在后台线程运行，需要独立的 session）
            user_id: 用户 ID
            recent_messages: 最近的消息列表 [{"role": "user/assistant", "content": "..."}]

        Returns: 提取的记忆条数
        """
        # 构建对话文本
        conversation_text = "\n".join(
            f"{'用户' if m['role'] == 'user' else '树洞'}：{m['content']}"
            for m in recent_messages[-6:]  # 最近 6 条（3 轮）
        )
        # 调用 LLM 提取
        try:
            response = self._llm.chat(
                [{"role": "user", "content": _EXTRACT_PROMPT.format(conversation=conversation_text)}],
                temperature=0.3,
            )
            items = self._parse_extraction(response)
        except Exception as e:
            logger.error(f"Memory extraction LLM call failed: {e}")
            return 0

        if not items:
            return 0

        count = 0
        for item in items:
            content = item.get("content", "").strip()
            if not content or len(content) < 4:
                continue
            importance = max(0.0, min(1.0, float(item.get("importance", 0.5))))
            emotion_label = item.get("emotion_label", "neutral")

            # 语义去重
            if self._is_duplicate(user_id, content):
                logger.debug(f"Skipping duplicate memory: {content[:50]}")
                continue

            # 计算 embedding 并存储
            try:
                embedding = self._embed.embed(content)
            except Exception as e:
                logger.error(f"Embedding failed: {e}")
                continue

            # 写入关系库
            memory = MemoryNode(
                user_id=user_id,
                content=content,
                emotion_label=emotion_label,
                importance=importance,
                source_message_ids=[],
            )
            db.add(memory)
            db.commit()
            db.refresh(memory)

            # 写入向量库
            self._vector.add(
                user_id=user_id,
                memory_id=memory.id,
                embedding=embedding,
                metadata={"content": content, "emotion": emotion_label, "importance": importance},
            )
            count += 1

        logger.info(f"Extracted {count} memories for user {user_id}")
        return count

    # ── 多路检索 ──

    def retrieve(self, db: Session, user_id: str, query: str, top_k: int = 3) -> list[dict]:
        """多路检索 + RRF 融合，返回最相关的记忆。

        Returns: [{"content": "...", "emotion_label": "...", "importance": ...}, ...]
        """
        # 路 1: 向量语义检索
        try:
            q_embedding = self._embed.embed(query)
            vector_results = self._vector.search(user_id, q_embedding, k=5)
        except Exception as e:
            logger.warning(f"Vector search failed: {e}")
            vector_results = []

        # 路 2: FTS5 关键词检索
        keyword_results = self._fts5_search(db, query)

        # 路 3: RRF 融合
        fused = self._rrf_fuse(vector_results, keyword_results, top_k=top_k)
        return fused

    # ── 辅助方法 ──

    def _parse_extraction(self, text: str) -> list[dict]:
        """解析 LLM 记忆提取结果。"""
        # 尝试直接解析
        try:
            data = json.loads(text.strip())
            if isinstance(data, list):
                return data
            if isinstance(data, dict) and "memories" in data:
                return data["memories"]
        except json.JSONDecodeError:
            pass
        # 正则提取 JSON 数组
        m = re.search(r'\[.*\]', text, re.DOTALL)
        if m:
            try:
                return json.loads(m.group())
            except json.JSONDecodeError:
                pass
        logger.warning(f"Failed to parse memory extraction: {text[:200]}")
        return []

    def _is_duplicate(self, user_id: str, content: str) -> bool:
        """检查新记忆是否与已有记忆语义重复。

        通过向量相似度判断：在 ChromaDB 中搜索相似记忆，
        如果最高相似度 > 0.85，视为重复。
        """
        try:
            embedding = self._embed.embed(content)
            results = self._vector.search(user_id, embedding, k=1)
            if results and results[0]["score"] > 0.85:
                return True
        except Exception:
            pass
        return False

    def _fts5_search(self, db: Session, query: str, limit: int = 5) -> list[dict]:
        """SQLite FTS5 全文搜索（中文友好版）。

        FTS5 对中文支持有限，因此同时尝试：
        1. FTS5 MATCH（适合已分词的英文/中文词组）
        2. LIKE 模糊匹配（中文回退方案）
        """
        results = []
        try:
            fts_query = " ".join(query.replace('"', '').replace("'", ""))
            if not fts_query.strip():
                return []

            sql = text(
                "SELECT m.id, m.content, m.emotion_label, m.importance, m.created_at, "
                "rank FROM memories_fts f JOIN memories m ON m.rowid = f.rowid "
                "WHERE memories_fts MATCH :q AND m.deprecated = 0 "
                "ORDER BY rank LIMIT :limit"
            )
            rows = db.execute(sql, {"q": f'"{fts_query}"', "limit": limit}).fetchall()
            for r in rows:
                results.append({
                    "id": r[0], "content": r[1],
                    "emotion_label": r[2], "importance": r[3],
                    "created_at": r[4].isoformat() if r[4] else None,
                })
        except Exception as e:
            logger.debug(f"FTS5 MATCH failed (expected for Chinese): {e}")

        # 回退：LIKE 模糊搜索
        if not results:
            try:
                like_pattern = f"%{query}%"
                rows = (
                    db.query(MemoryNode)
                    .filter(
                        MemoryNode.deprecated == False,
                        MemoryNode.content.like(like_pattern),
                    )
                    .order_by(MemoryNode.created_at.desc())
                    .limit(limit)
                    .all()
                )
                for r in rows:
                    results.append({
                        "id": r.id, "content": r.content,
                        "emotion_label": r.emotion_label,
                        "importance": r.importance,
                        "created_at": r.created_at.isoformat() if r.created_at else None,
                    })
            except Exception as e:
                logger.warning(f"LIKE fallback search failed: {e}")

        return results

    def _rrf_fuse(
        self,
        vector_results: list[dict],
        keyword_results: list[dict],
        top_k: int = 3,
    ) -> list[dict]:
        """RRF (Reciprocal Rank Fusion) 融合多路检索结果。

        score = Σ 1/(k + rank_i), k=60
        """
        scores = {}

        # 向量路
        for rank, item in enumerate(vector_results):
            mid = item["id"]
            score = 1.0 / (RRF_K + rank + 1)
            if mid not in scores:
                scores[mid] = {
                    "score": 0,
                    "content": item.get("metadata", {}).get("content", ""),
                    "emotion_label": item.get("metadata", {}).get("emotion", "neutral"),
                    "importance": item.get("metadata", {}).get("importance", 0.5),
                }
            scores[mid]["score"] += score

        # 关键词路
        for rank, item in enumerate(keyword_results):
            mid = item["id"]
            score = 1.0 / (RRF_K + rank + 1)
            if mid not in scores:
                scores[mid] = {
                    "score": 0,
                    "content": item["content"],
                    "emotion_label": item.get("emotion_label", "neutral"),
                    "importance": item.get("importance", 0.5),
                }
            scores[mid]["score"] += score

        # 排序取 Top-K
        sorted_items = sorted(scores.values(), key=lambda x: x["score"], reverse=True)
        return sorted_items[:top_k]
