"""DeepSeek LLM Provider — 基于 LangChain ChatOpenAI（DeepSeek 兼容 OpenAI API）。"""

from langchain_openai import ChatOpenAI
from langchain_core.messages import HumanMessage, SystemMessage, AIMessage

from app.core.config import settings
from app.services.base import LLMProvider

_ROLE_MAP = {
    "system": SystemMessage,
    "user": HumanMessage,
    "assistant": AIMessage,
}


class DeepSeekProvider(LLMProvider):
    """通过 DeepSeek API 调用大模型。

    DeepSeek 的 API 与 OpenAI 完全兼容，使用 LangChain 的 ChatOpenAI 作为底层客户端。
    每次调用时从 settings 读取最新配置，避免模块级实例化时的初始化顺序问题。
    """

    def __init__(self):
        self._client = None

    def _get_client(self) -> ChatOpenAI:
        """延迟创建客户端，确保读取到最新的环境变量配置。"""
        if self._client is None:
            self._client = ChatOpenAI(
                model=settings.llm_model,
                api_key=settings.llm_api_key,
                base_url=settings.llm_base_url,
                temperature=0.8,
                max_tokens=1024,
            )
        return self._client

    def chat(self, messages: list[dict], **kwargs) -> str:
        """调用 DeepSeek 聊天模型。

        Args:
            messages: 标准消息列表（dict 格式，兼容 OpenAI API）。
            **kwargs: 透传参数（temperature, max_tokens 等）。

        Returns:
            模型回复文本。
        """
        client = self._get_client()

        # 将 dict 转换为 LangChain message 对象
        lc_messages = []
        for m in messages:
            role = m["role"]
            content = m["content"]
            msg_cls = _ROLE_MAP.get(role, HumanMessage)
            lc_messages.append(msg_cls(content=content))

        # 支持运行时覆盖参数
        if kwargs:
            client.temperature = kwargs.get("temperature", client.temperature)
            client.max_tokens = kwargs.get("max_tokens", client.max_tokens)

        response = client.invoke(lc_messages)
        return response.content
