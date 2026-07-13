"""共享服务单例 — ChatService 和 LLM Provider 全局唯一实例。

Web API (/api/chat) 和微信机器人都使用同一个 ChatService，
确保记忆、情感分析、会话数据在双通道间共享。
"""

from app.services.deepseek_provider import DeepSeekProvider
from app.services.embedding_service import TFIDFEmbeddingProvider
from app.services.vector_store import ChromaDBStore
from app.services.emotion_service import EmotionService
from app.services.memory_service import MemoryService
from app.services.chat_service import ChatService

# LLM Provider（基于 settings.llm_* 配置）
_llm = DeepSeekProvider()

# ChatService 单例
_chat_service = ChatService(
    llm_provider=_llm,
    emotion_service=EmotionService(llm_provider=_llm),
    memory_service=MemoryService(
        llm_provider=_llm,
        embedding_provider=TFIDFEmbeddingProvider(),
        vector_store=ChromaDBStore(),
    ),
)


def get_chat_service() -> ChatService:
    """获取全局唯一的 ChatService 实例。"""
    return _chat_service


def get_llm_provider() -> DeepSeekProvider:
    """获取全局唯一的 LLM Provider 实例。"""
    return _llm
