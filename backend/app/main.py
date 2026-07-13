"""AI树洞 (TreeHole AI) — FastAPI 应用入口。

启动方式：
    cd backend
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

支持通道：
    - Web 聊天（Vue SPA 前端）
    - 微信聊天（WeChat iLink Bot，需在 .env 中启用 WECHAT_BOT_ENABLED=true）
"""

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.database import engine, Base
from app.core.config import settings

logger = logging.getLogger(__name__)

# 微信机器人实例（模块级，供 lifespan 使用）
_wechat_bot = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期：启动时建表 + 启动微信机器人，关闭时停止。"""
    global _wechat_bot

    # 导入所有模型，确保 Base.metadata 完整
    import app.models  # noqa: F401
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created")

    # ── 启动微信机器人 ──
    if settings.wechat_bot_enabled:
        from app.services.wechat_bot import WeChatBot
        logger.info("Starting WeChat bot...")
        _wechat_bot = WeChatBot(settings)
        try:
            await _wechat_bot.start()
        except Exception as e:
            logger.error(f"WeChat bot failed to start: {e}")
            print(f"\n[WARNING] 微信机器人启动失败: {e}")
            print("[WARNING] Web 聊天功能不受影响，可正常使用\n")

    yield

    # ── 关闭微信机器人 ──
    if _wechat_bot and _wechat_bot.is_running:
        await _wechat_bot.stop()


app = FastAPI(
    title="TreeHole AI — 你的私人情感树洞",
    description="一个能记住你开心与不开心瞬间的聊天AI，支持 Web + 微信双通道",
    version="0.3.0",
    lifespan=lifespan,
)

# ── CORS 配置 ──
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 开发阶段允许所有来源，生产环境应限制
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 注册路由 ──
from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.conversation import router as conversation_router
from app.api.memory import router as memory_router

app.include_router(auth_router)
app.include_router(chat_router)
app.include_router(conversation_router)
app.include_router(memory_router)


@app.get("/")
def root():
    """健康检查。"""
    return {
        "name": "TreeHole AI",
        "version": "0.3.0",
        "status": "running",
        "wechat_bot": {
            "enabled": settings.wechat_bot_enabled,
            "running": _wechat_bot is not None and _wechat_bot.is_running,
        },
    }


@app.get("/api/wechat/status")
def wechat_status():
    """查询微信机器人状态。"""
    return {
        "enabled": settings.wechat_bot_enabled,
        "running": _wechat_bot is not None and _wechat_bot.is_running,
        "provider": settings.wechat_bot_provider if settings.wechat_bot_enabled else None,
    }
