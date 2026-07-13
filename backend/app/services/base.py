"""LLM Provider 抽象基类 — 方便后续接入不同大模型。

扩展方式：
    1. 继承 LLMProvider
    2. 实现 chat() 方法
    3. 在 config.py 中添加对应的 provider 配置
"""

from abc import ABC, abstractmethod


class LLMProvider(ABC):
    """大模型调用统一接口。"""

    @abstractmethod
    def chat(self, messages: list[dict], **kwargs) -> str:
        """发送消息列表给大模型，返回生成的文本。

        Args:
            messages: [{"role": "system"|"user"|"assistant", "content": "..."}]
            **kwargs: provider-specific parameters (temperature, max_tokens, etc.)

        Returns:
            模型生成的回复文本。
        """
        ...
