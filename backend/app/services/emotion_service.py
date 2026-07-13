"""情感分析服务 — LLM prompt-based 方案。

一次 LLM 调用同时完成打分（-1~1）和分类标签。
"""

import json
import logging
import re

from app.services.base import LLMProvider

logger = logging.getLogger(__name__)

_EMOTION_PROMPT = """分析以下用户消息的情感状态。你必须只返回一个JSON对象，格式严格如下，不要任何其他文字：
{{"score": 0.8, "label": "joy"}}

- score: -1.0(非常负面) 到 1.0(非常正面)
- label: 从 [joy, sadness, anger, fear, surprise, neutral] 中选择

用户消息：{message}

JSON:"""


class EmotionService:
    """情感分析服务。"""

    def __init__(self, llm_provider: LLMProvider):
        self._llm = llm_provider

    def analyze(self, message: str) -> dict:
        """分析一条用户消息的情感。

        Returns: {"score": float, "label": str}，解析失败返回 neutral。
        """
        prompt = _EMOTION_PROMPT.format(message=message)
        try:
            response = self._llm.chat(
                [{"role": "user", "content": prompt}],
                temperature=0.3,
            )
            return self._parse(response)
        except Exception as e:
            logger.warning(f"Emotion analysis failed: {e}")
            return {"score": 0.0, "label": "neutral"}

    @staticmethod
    def _parse(text: str) -> dict:
        """从 LLM 回复中尽力提取 JSON 情感结果。"""
        if not text:
            return {"score": 0.0, "label": "neutral"}

        text = text.strip()

        # 方法1: 直接解析
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return EmotionService._normalize(data)
        except (json.JSONDecodeError, ValueError, TypeError):
            pass

        # 方法2: 正则提取 JSON 对象（支持嵌套）
        for pattern in [
            r'\{[^{}]*"score"[^{}]*\}',       # 单层花括号含 score
            r'\{.*?"score".*?\}',              # 贪婪匹配含 score
            r'\{[^{}]*\}',                     # 任意单层花括号
        ]:
            m = re.search(pattern, text, re.DOTALL)
            if m:
                try:
                    data = json.loads(m.group())
                    if isinstance(data, dict) and "score" in data:
                        return EmotionService._normalize(data)
                except (json.JSONDecodeError, ValueError, TypeError):
                    continue

        # 方法3: 正则直接提取数字和标签
        score_match = re.search(r'(-?\d+\.?\d*)', text)
        score = float(score_match.group(1)) if score_match else 0.0
        label = "neutral"
        for lbl in ["joy", "sadness", "anger", "fear", "surprise", "neutral"]:
            if lbl in text.lower():
                label = lbl
                break

        logger.debug(f"Fallback parse: score={score}, label={label} from '{text[:100]}'")
        return {"score": max(-1.0, min(1.0, score)), "label": label}

    @staticmethod
    def _normalize(data: dict) -> dict:
        """标准化情感数据。"""
        try:
            score = float(data.get("score", 0))
        except (ValueError, TypeError):
            score = 0.0
        return {
            "score": max(-1.0, min(1.0, score)),
            "label": str(data.get("label", "neutral")).lower(),
        }
