"""对话编排服务 — 对话流程的管道式编排。

管道阶段（V0.2）:
    get_conv → load_history → build_msg
                    ↓
               [retrieve_memories] ← 多路检索，注入 system prompt
                    ↓
               save_user_msg
                    ↓
               [analyze_emotion]   ← LLM 情感分析，更新 message 行
                    ↓
               call_llm
                    ↓
               save_asst_msg
                    ↓
               [extract_memory]    ← BackgroundTasks 异步执行
                    ↓
               update_meta

新增功能只需在对应标记点插入阶段，无需改动整体结构。
"""

import logging
from datetime import datetime, timezone
from typing import Callable

from sqlalchemy.orm import Session

from app.models.conversation import Conversation
from app.models.message import Message
from app.services.base import LLMProvider
from app.services.emotion_service import EmotionService
from app.services.memory_service import MemoryService

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是「树洞」，一个温暖、耐心、善解人意的情感陪伴助手。

## 你的性格
- 温柔细腻，像一位懂你的老朋友
- 不会评判，永远接纳用户的情绪
- 在用户难过时给予安慰，在用户开心时一起庆祝
- 适度幽默，但不会在严肃时刻开玩笑

## 你的能力
- 倾听用户的喜怒哀乐，共情回应
- 记住用户提到的重要事情（生日、喜好、经历等）
- 在合适的时候提起之前的对话，让用户感到被记住和被在乎
- 给予温暖的建议，但不会强加观点

## 对话原则
- 用「你」称呼用户，拉近距离
- 回复自然口语化，像朋友聊天，不要过于正式
- 不要一次性输出过长段落，保持对话节奏
- 当用户表达负面情绪时，先共情再引导
- 绝对不要给出医疗、法律等专业建议，必要时建议寻求专业帮助

## 安全底线
- 拒绝任何自残、伤害他人等危险内容的讨论，引导用户寻求专业帮助
- 不与用户争论政治、宗教等敏感话题
- 保护用户隐私，不主动索取个人敏感信息"""

# 注入记忆后的 system prompt 模板
MEMORY_CONTEXT_TEMPLATE = """
{base_prompt}

## 你记得用户之前提到过：
{memories}

请自然地在对话中结合这些记忆，让用户感到被记住和在乎，但不要生硬地逐条复述。
"""

MAX_CONTEXT_MESSAGES = 20


class ChatService:
    """对话编排服务，管道式架构。

    on_memory_extract: 可选回调，用于将记忆提取任务提交到后台线程。
        函数签名: Callable[[Session, str, list[dict]], None]
    """

    def __init__(
        self,
        llm_provider: LLMProvider,
        emotion_service: EmotionService | None = None,
        memory_service: MemoryService | None = None,
    ):
        self._llm = llm_provider
        self._emotion = emotion_service
        self._memory = memory_service
        # 存储最近一次对话的提取上下文，供 api 层 BackgroundTasks 读取
        self._pending_extraction: tuple[str, list[dict]] | None = None

    def pop_extraction_context(self) -> tuple[str, list[dict]] | None:
        """取出并清空待处理的记忆提取上下文。

        Returns: (user_id, recent_messages) 或 None
        """
        ctx = self._pending_extraction
        self._pending_extraction = None
        return ctx

    # ── 公开接口 ──

    def send_message(
        self,
        db: Session,
        user_id: str,
        message: str,
        conversation_id: str | None = None,
    ) -> dict:
        """处理一条用户消息，返回助手回复。"""

        # ── 阶段 1: 解析会话 ──
        conversation = self._get_or_create_conversation(db, user_id, conversation_id)

        # ── 阶段 2: 加载历史 ──
        history = self._load_recent_messages(db, conversation.id)

        # ── 阶段 3: 多路记忆检索 + 构建消息 ──
        # === V0.2: retrieve_memories ===
        memory_context = self._retrieve_memories(db, user_id, message)
        llm_messages = self._build_messages(history, message, memory_context)

        # ── 阶段 4: 持久化用户消息 ──
        user_msg = self._save_message(db, conversation.id, "user", message)

        # ── 阶段 5: 情感分析 ──
        # === V0.2: analyze_emotion ===
        self._analyze_and_update_emotion(db, user_msg, message)

        # ── 阶段 6: 调用 LLM ──
        assistant_content = self._llm.chat(llm_messages)

        # ── 阶段 7: 持久化助手回复 ──
        assistant_msg = self._save_message(db, conversation.id, "assistant", assistant_content)

        # ── 阶段 8: 异步记忆提取 ──
        # === V0.2: extract_memory (BackgroundTasks) ===
        self._trigger_memory_extraction(user_id, history, message, assistant_content)

        # ── 阶段 9: 更新会话元数据 ──
        self._update_conversation_meta(db, conversation, message)

        return {
            "message_id": assistant_msg.id,
            "conversation_id": conversation.id,
            "role": "assistant",
            "content": assistant_content,
        }

    # ── 管道阶段 ──

    def _get_or_create_conversation(
        self, db: Session, user_id: str, conversation_id: str | None
    ) -> Conversation:
        if conversation_id:
            conv = (
                db.query(Conversation)
                .filter(Conversation.id == conversation_id, Conversation.user_id == user_id)
                .first()
            )
            if conv:
                return conv
        conv = Conversation(user_id=user_id)
        db.add(conv)
        db.commit()
        db.refresh(conv)
        return conv

    def _load_recent_messages(self, db: Session, conversation_id: str) -> list[Message]:
        return (
            db.query(Message)
            .filter(Message.conversation_id == conversation_id)
            .order_by(Message.timestamp.desc())
            .limit(MAX_CONTEXT_MESSAGES)
            .all()[::-1]
        )

    def _retrieve_memories(self, db: Session, user_id: str, message: str) -> list[dict]:
        """多路检索用户相关记忆。"""
        if not self._memory:
            return []
        try:
            results = self._memory.retrieve(db, user_id, message, top_k=3)
            logger.debug(f"Retrieved {len(results)} memories for query: {message[:30]}")
            return results
        except Exception as e:
            logger.warning(f"Memory retrieval failed: {e}")
            return []

    def _build_messages(
        self,
        history: list[Message],
        current_message: str,
        memory_context: list[dict] | None = None,
    ) -> list[dict]:
        """构建 LLM 消息列表，将记忆注入 system prompt。"""
        # 构建带记忆的 system prompt
        if memory_context:
            memory_lines = [f"- {m['content']}" for m in memory_context]
            memories_text = "\n".join(memory_lines)
            system_content = MEMORY_CONTEXT_TEMPLATE.format(
                base_prompt=SYSTEM_PROMPT,
                memories=memories_text,
            )
        else:
            system_content = SYSTEM_PROMPT

        messages = [{"role": "system", "content": system_content}]
        for msg in history:
            messages.append({"role": msg.role, "content": msg.content})
        messages.append({"role": "user", "content": current_message})
        return messages

    def _analyze_and_update_emotion(self, db: Session, user_msg: Message, message: str) -> None:
        """LLM 情感分析并更新消息行。"""
        if not self._emotion:
            return
        try:
            result = self._emotion.analyze(message)
            user_msg.emotion_score = result["score"]
            user_msg.emotion_label = result["label"]
            db.commit()
        except Exception as e:
            logger.warning(f"Emotion analysis failed: {e}")

    def _save_message(self, db: Session, conversation_id: str, role: str, content: str) -> Message:
        msg = Message(conversation_id=conversation_id, role=role, content=content)
        db.add(msg)
        db.commit()
        db.refresh(msg)
        return msg

    def _trigger_memory_extraction(
        self,
        user_id: str,
        history: list[Message],
        user_message: str,
        assistant_reply: str,
    ) -> None:
        """存储记忆提取上下文，由 api 层 BackgroundTasks 消费。"""
        if not self._memory:
            return
        try:
            recent = [{"role": m.role, "content": m.content} for m in history[-4:]]
            recent.append({"role": "user", "content": user_message})
            recent.append({"role": "assistant", "content": assistant_reply})
            self._pending_extraction = (user_id, recent)
        except Exception as e:
            logger.warning(f"Failed to stage memory extraction: {e}")

    def _update_conversation_meta(
        self, db: Session, conversation: Conversation, first_message: str
    ) -> None:
        if conversation.title == "新对话":
            title = first_message[:20].replace("\n", " ")
            conversation.title = title if len(title) < 20 else title + "…"
        conversation.updated_at = datetime.now(timezone.utc)
        db.commit()

    # ── 公开辅助：单独触发记忆提取（供 API 层调用） ──

    def extract_memories_sync(
        self, db: Session, user_id: str, recent_messages: list[dict]
    ) -> int:
        """同步执行记忆提取（在后台线程中调用）。"""
        if not self._memory:
            return 0
        return self._memory.extract_memories(db, user_id, recent_messages)
