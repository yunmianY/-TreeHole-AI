"""应用配置 — 通过环境变量集中管理所有可配置项。"""

from pathlib import Path
from pydantic_settings import BaseSettings

# 项目根目录（backend/），用于拼接相对路径，确保从任意目录启动都能正确找到文件
_BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    """应用全局配置，所有值可从 .env 文件或环境变量注入。"""

    # ── LLM ──
    llm_api_key: str = "your_api_key_here"
    llm_base_url: str = "https://api.deepseek.com"
    llm_model: str = "deepseek-chat"

    # ── JWT ──
    secret_key: str = "change-me-to-a-random-secret-string"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440  # 24h

    # ── WeChat Bot ──
    wechat_bot_enabled: bool = False
    wechat_bot_provider: str = "deepseek"  # deepseek / dusapi（微信端独立 AI 配置，不共享 Web 端 LLM 配置）
    wechat_bot_api_key: str = ""
    wechat_bot_base_url: str = "https://api.deepseek.com"
    wechat_bot_model: str = "deepseek-v4-flash"
    wechat_bot_prompt: str = "你是一个有帮助的AI助手，请用中文简洁地回复。字数尽量少一些"

    # ── Database ──
    database_url: str = "sqlite:///./data/treehole.db"

    class Config:
        env_file = str(_BACKEND_DIR / ".env")
        env_file_encoding = "utf-8"
        case_sensitive = False

    @property
    def resolved_database_url(self) -> str:
        """将 sqlite 相对路径转为从 backend/ 目录解析的绝对路径。

        例如 "sqlite:///./data/treehole.db" → "sqlite:///D:/.../backend/data/treehole.db"
        PostgreSQL 等非 sqlite URL 直接原样返回。
        """
        url = self.database_url
        if not url.startswith("sqlite:///"):
            return url
        rel_path = url[len("sqlite:///"):]  # "./data/treehole.db"
        abs_path = (_BACKEND_DIR / rel_path).resolve()
        # 确保 data 目录存在
        abs_path.parent.mkdir(parents=True, exist_ok=True)
        return f"sqlite:///{abs_path}"


settings = Settings()
