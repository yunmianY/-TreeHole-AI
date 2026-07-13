"""向量存储 — ChromaDB 实现。

设计说明：
- VectorStore 是抽象接口，当前实现 ChromaDBStore。
- 每个用户有独立的 ChromaDB collection（user_{user_id}），数据隔离。
- 后续可替换为 Qdrant / Milvus 等，只需实现 VectorStore 接口。
"""

import logging
from abc import ABC, abstractmethod
from pathlib import Path

logger = logging.getLogger(__name__)

# ChromaDB 数据持久化目录（backend/data/chroma/）
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent
_CHROMA_PATH = _BACKEND_DIR / "data" / "chroma"


class VectorStore(ABC):
    """向量存储抽象接口。"""

    @abstractmethod
    def add(self, user_id: str, memory_id: str, embedding: list[float], metadata: dict) -> None:
        """添加一条记忆向量。"""
        ...

    @abstractmethod
    def search(self, user_id: str, embedding: list[float], k: int = 5) -> list[dict]:
        """语义搜索最相似的 k 条记忆。

        Returns: [{"id": ..., "metadata": {...}, "score": ...}, ...]
        """
        ...

    @abstractmethod
    def delete(self, user_id: str, memory_id: str) -> None:
        """删除一条记忆向量。"""
        ...

    @abstractmethod
    def count(self, user_id: str) -> int:
        """统计用户的记忆数量。"""
        ...


# ── ChromaDB 实现 ──

class ChromaDBStore(VectorStore):
    """基于 ChromaDB 的向量存储实现。

    每个用户使用独立 collection，名称: "memories_{user_id}"
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._client = None
        return cls._instance

    def _get_client(self):
        if self._client is None:
            import chromadb
            _CHROMA_PATH.mkdir(parents=True, exist_ok=True)
            self._client = chromadb.PersistentClient(path=str(_CHROMA_PATH))
            logger.info(f"ChromaDB initialized at {_CHROMA_PATH}")
        return self._client

    def _collection_name(self, user_id: str) -> str:
        # 替换特殊字符确保合法
        safe = user_id.replace("-", "_")
        return f"memories_{safe}"

    def _get_collection(self, user_id: str):
        client = self._get_client()
        name = self._collection_name(user_id)
        return client.get_or_create_collection(name=name)

    def add(self, user_id: str, memory_id: str, embedding: list[float], metadata: dict) -> None:
        col = self._get_collection(user_id)
        col.add(
            ids=[memory_id],
            embeddings=[embedding],
            metadatas=[metadata],
        )

    def search(self, user_id: str, embedding: list[float], k: int = 5) -> list[dict]:
        col = self._get_collection(user_id)
        if col.count() == 0:
            return []
        results = col.query(query_embeddings=[embedding], n_results=min(k, col.count()))
        items = []
        if results["ids"] and results["ids"][0]:
            for i, mid in enumerate(results["ids"][0]):
                items.append({
                    "id": mid,
                    "metadata": results["metadatas"][0][i] if results["metadatas"] else {},
                    "score": 1.0 - results["distances"][0][i] if results["distances"] else 0,
                })
        return items

    def delete(self, user_id: str, memory_id: str) -> None:
        col = self._get_collection(user_id)
        col.delete(ids=[memory_id])

    def count(self, user_id: str) -> int:
        col = self._get_collection(user_id)
        return col.count()
