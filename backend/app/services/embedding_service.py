"""Embedding 服务 — 文本向量化抽象与实现。

提供两种实现：
- TF-IDFEmbeddingProvider: 基于 sklearn TfidfVectorizer，离线运行，不依赖网络下载
- SentenceTransformersProvider: 基于 sentence-transformers，需下载模型（默认关闭）

默认使用 TF-IDF，轻量级且支持中文分词。
"""

import logging
from abc import ABC, abstractmethod

import numpy as np

logger = logging.getLogger(__name__)


class EmbeddingProvider(ABC):
    """文本向量化统一接口。"""

    @abstractmethod
    def embed(self, text: str) -> list[float]:
        """将单条文本转为向量。"""
        ...

    @abstractmethod
    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量文本向量化。"""
        ...


# ── TF-IDF 实现（默认，离线可用）──

class TFIDFEmbeddingProvider(EmbeddingProvider):
    """基于 sklearn TfidfVectorizer 的轻量 Embedding。

    优势：
    - 完全离线，无需下载任何模型
    - 支持中文（通过字符级 ngram）
    - 首次使用时自动拟合语料库
    - 向量维度 256（可配置）

    后续可替换为 SentenceTransformers 等更强大的模型。
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._vectorizer = None
            cls._instance._fitted = False
            cls._instance._corpus = []
        return cls._instance

    def _get_vectorizer(self):
        if self._vectorizer is None:
            from sklearn.feature_extraction.text import TfidfVectorizer
            self._vectorizer = TfidfVectorizer(
                analyzer="char_wb",  # 字符级 ngram（支持中文）
                ngram_range=(2, 4),
                max_features=256,
                sublinear_tf=True,
            )
        return self._vectorizer

    def _ensure_fit(self):
        """确保 vectorizer 已拟合。首次调用时会用内置语料库 + 累积文本拟合。"""
        if not self._fitted:
            v = self._get_vectorizer()
            if self._corpus:
                v.fit(self._corpus)
            else:
                # 内置种子语料库（帮助初始化词表）
                seed_corpus = _get_seed_corpus()
                v.fit(seed_corpus)
            self._fitted = True
            logger.info(f"TF-IDF vectorizer fitted, vocab size: {len(v.vocabulary_)}")

    def _add_to_corpus(self, text: str):
        """将新文本加入累积语料库（最多保留 1000 条）。"""
        self._corpus.append(text)
        if len(self._corpus) > 1000:
            self._corpus = self._corpus[-1000:]
            # 语料库更新后重新拟合
            if self._vectorizer is not None:
                v = self._vectorizer
                v.fit(self._corpus)
                logger.debug(f"TF-IDF refitted, vocab: {len(v.vocabulary_)}")

    def embed(self, text: str) -> list[float]:
        try:
            self._ensure_fit()
            v = self._get_vectorizer()
            vec = v.transform([text]).toarray()[0]
            # L2 归一化
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm
            return vec.tolist()
        except Exception as e:
            logger.error(f"Embedding failed: {e}")
            raise

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        try:
            self._ensure_fit()
            # 将新文本加入语料库
            for t in texts:
                self._add_to_corpus(t)
            v = self._get_vectorizer()
            mat = v.transform(texts).toarray()
            norms = np.linalg.norm(mat, axis=1, keepdims=True)
            norms[norms == 0] = 1
            mat = mat / norms
            return mat.tolist()
        except Exception as e:
            logger.error(f"Batch embedding failed: {e}")
            raise


def _get_seed_corpus() -> list[str]:
    """内置种子语料库，包含常见中文情感/记忆表达。"""
    return [
        "今天很开心升职了",
        "今天很难过被批评了",
        "我喜欢爬山和户外运动",
        "我害怕打雷和闪电",
        "我的生日是五月二十号",
        "我和朋友吵架了后来和好了",
        "我是一名程序员工作很忙",
        "我喜欢猫不喜欢狗",
        "周末去了公园散步放松",
        "最近压力很大睡不着觉",
        "家人身体健康我很感恩",
        "看了场电影觉得很感动",
        "学会了做新菜很有成就感",
        "下雨天心情不好",
        "和朋友聚会很开心",
        "工作上遇到了挫折",
        "旅行让我感到自由",
        "想念远方的家人",
        "收到了意外的礼物",
        "对未来感到迷茫",
    ]


# ── Sentence-Transformers 实现（可选，需下载模型）──

class SentenceTransformersProvider(EmbeddingProvider):
    """基于 sentence-transformers 的语义 Embedding（需连接 HuggingFace 下载模型）。

    使用 paraphrase-multilingual-MiniLM-L12-v2：
    - 支持 50+ 语言（含中文），向量维度 384
    - 模型约 420MB，首次使用自动下载
    - 需要能够访问 huggingface.co

    如果遇到 SSL 错误，设置环境变量：
        export HF_HUB_DISABLE_SSL_VERIFY=1
    """

    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._model = None
        return cls._instance

    def _get_model(self):
        if self._model is None:
            import os
            os.environ.setdefault("HF_HUB_DISABLE_SSL_VERIFY", "1")
            from sentence_transformers import SentenceTransformer
            logger.info("Loading SentenceTransformer model (first run downloads ~420MB)...")
            self._model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
            logger.info("SentenceTransformer model loaded.")
        return self._model

    def embed(self, text: str) -> list[float]:
        model = self._get_model()
        return model.encode(text, normalize_embeddings=True).tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        model = self._get_model()
        embeddings = model.encode(texts, normalize_embeddings=True)
        return embeddings.tolist()
