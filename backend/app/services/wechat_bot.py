"""微信机器人服务 — 通过 WeChat iLink API 连接微信进行 AI 聊天。

与 Web 聊天共享同一个 ChatService 管道，因此微信消息也会：
- 写入 messages 表（消息记录）
- 写入 memories 表 + ChromaDB 向量库（记忆提取）
- 执行情感分析（emotion_score / emotion_label）
- 管理会话（conversations 表）
- 自动注册微信用户（username = wx_{from_id}）

用法：
    from app.services.shared import get_chat_service
    bot = WeChatBot(settings, chat_service=get_chat_service())
    await bot.start()
"""

import asyncio
import base64
import io
import json
import logging
import random
import re
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote

import aiohttp

from app.core.database import SessionLocal
from app.services.wechat_user_service import WeChatUserService

logger = logging.getLogger(__name__)

# ========== WeChat iLink 常量 ==========
CHANNEL_VERSION = "2.4.3"
ILINK_APP_ID = "bot"
ILINK_APP_CLIENT_VERSION = str((2 << 16) | (4 << 8) | 3)
BOT_AGENT = "TreeHole-WeChat/1.0.0 (python)"
DEFAULT_BASE_URL = "https://ilinkai.weixin.qq.com"

COMMANDS_MSG = (
    "连接成功！\n"
    "可用指令：\n"
    "/help  /指令   - 查看全部指令列表\n"
    "/time          - 查询当前连接剩余时间\n"
    "/重新连接       - 立即触发重新连接（需确认）\n"
    "\n非指令输入即为 AI 对话"
)

# ========== 自动重连配置 ==========
RECONNECT_CONFIG = {
    "session_duration": 24 * 3600,
    "warning_before": 2 * 3600,
    "reminder_interval": 30 * 60,
    "force_before": 30 * 60,
    "qrcode_scan_timeout": 600,
}


class WeChatBot:
    """微信机器人服务。

    封装了 WeChat iLink Bot API 的完整交互流程：
    扫码登录 → 长轮询收消息 → ChatService 管道 → AI 回复 → 自动重连。
    """

    def __init__(self, settings, chat_service=None):
        """
        Args:
            settings: app.core.config.Settings 实例
            chat_service: ChatService 实例（可选，默认从 shared.py 获取）
        """
        self._settings = settings

        # 延迟导入，避免循环依赖
        if chat_service is None:
            from app.services.shared import get_chat_service
            chat_service = get_chat_service()
        self._chat_service = chat_service

        self._user_service = WeChatUserService()
        self._session: aiohttp.ClientSession | None = None
        self._running = False
        self._task: asyncio.Task | None = None
        self._bot_token_ref: list[str] = [""]
        self._bot_base_url_ref: list[str] = [""]
        self._executor = ThreadPoolExecutor(max_workers=4)

        # 微信用户 → 会话 ID 映射（同一微信用户复用同一个 conversation）
        self._conversations: dict[str, str] = {}

    # ── 公开接口 ──

    @property
    def is_running(self) -> bool:
        return self._running

    async def start(self):
        """启动微信机器人（阻塞直到扫码登录成功，之后在后台运行）。"""
        if self._running:
            logger.warning("WeChat bot is already running")
            return

        if not self._settings.wechat_bot_enabled:
            logger.info("WeChat bot is disabled in config, skipping start")
            return

        logger.info(
            f"WeChat bot starting — messages will go through ChatService pipeline "
            f"(model={self._settings.llm_model})"
        )

        self._session = aiohttp.ClientSession()
        self._running = True

        try:
            login_result = await self._login_with_qrcode()
            self._bot_token_ref[0] = login_result["bot_token"]
            self._bot_base_url_ref[0] = login_result.get("baseurl", "")
            logger.info(f"WeChat bot logged in, baseurl={self._bot_base_url_ref[0]}")

            self._task = asyncio.create_task(self._message_loop())
            logger.info("WeChat bot started successfully")
        except Exception as e:
            logger.error(f"WeChat bot start failed: {e}")
            self._running = False
            if self._session:
                await self._session.close()
                self._session = None
            raise

    async def stop(self):
        """停止微信机器人。"""
        logger.info("Stopping WeChat bot...")
        self._running = False

        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

        if self._session:
            await self._session.close()
            self._session = None

        self._executor.shutdown(wait=False)
        logger.info("WeChat bot stopped")

    # ── 消息处理（同步，在 executor 中运行）──

    def _process_message_sync(
        self, wx_id: str, text: str, conv_id: str | None
    ) -> dict:
        """在独立 DB session 中通过 ChatService 管道处理微信消息。

        完整管道（由 ChatService.send_message 编排）：
            1. 解析/创建会话
            2. 加载历史消息
            3. 多路记忆检索 → 注入 system prompt
            4. 持久化用户消息 → messages 表
            5. LLM 情感分析 → emotion_score / emotion_label
            6. 调用 LLM 生成回复
            7. 持久化助手回复 → messages 表
            8. 暂存记忆提取上下文
            9. 更新会话元数据

        然后同步执行记忆提取 → memories 表 + ChromaDB。
        """
        db = SessionLocal()
        try:
            # 1. 映射微信用户 → TreeHole 用户
            user = self._user_service.get_or_create_user(db, wx_id)

            # 2. 通过 ChatService 管道处理消息
            result = self._chat_service.send_message(
                db=db,
                user_id=user.id,
                message=text,
                conversation_id=conv_id,
            )

            # 3. 同步执行记忆提取（Web 端用 BackgroundTasks，微信端在 executor 线程内同步完成）
            ctx = self._chat_service.pop_extraction_context()
            if ctx:
                uid, messages = ctx
                count = self._chat_service.extract_memories_sync(db, uid, messages)
                if count:
                    logger.info(f"[WeChat] 为用户 {uid} 提取了 {count} 条记忆")

            return result

        except Exception as e:
            logger.error(f"[WeChat] 消息处理失败: {e}", exc_info=True)
            return {
                "message_id": None,
                "conversation_id": conv_id or "",
                "role": "assistant",
                "content": "抱歉，我暂时无法回复，请稍后再试 🌱",
            }
        finally:
            db.close()

    # ── 登录流程 ──

    async def _login_with_qrcode(self, base_url: str = DEFAULT_BASE_URL) -> dict:
        refresh_count = 0
        max_refresh_count = 3
        while True:
            data = await self._fetch_login_qrcode(base_url)
            qrcode = data["qrcode"]
            qrcode_img_content = data.get("qrcode_img_content", "")

            print(f"\n{'='*60}")
            print(f"[WeChat Bot] 请使用微信扫描以下二维码完成登录：")
            print(f"qrcode: {qrcode}")
            self._save_qrcode_content(str(qrcode_img_content or qrcode))
            self._render_terminal_qr(str(qrcode_img_content or qrcode))
            print("等待扫码...")
            print(f"{'='*60}\n")

            login_result = await self._wait_login_confirmation(qrcode, base_url)
            if login_result.get("bot_token"):
                return login_result
            if login_result.get("already_connected"):
                print("[WeChat Bot] 服务端提示此端已连接过，重新生成二维码。")
            elif login_result.get("expired"):
                print("[WeChat Bot] 二维码已过期，正在重新生成...")
            elif login_result.get("verify_code_blocked"):
                print("[WeChat Bot] 多次输入配对码错误，正在刷新二维码...")
            elif login_result.get("timeout"):
                print("[WeChat Bot] 登录等待超时，正在重新生成二维码...")

            refresh_count += 1
            if refresh_count >= max_refresh_count:
                raise RuntimeError("二维码多次失效或登录失败，请稍后重试。")

    # ── 消息循环 ──

    async def _message_loop(self):
        """长轮询消息循环（后台运行）。"""
        last_contact = {"from_id": None, "context_token": None}
        typing_ticket_cache = {}
        welcomed_users = set()
        reconnect_asked = asyncio.Event()
        warning_active = [False]
        reconnect_in_progress = [False]
        login_time_ref = [time.time()]
        manual_reconnect_pending = {}

        reconnect_task = asyncio.create_task(self._reconnect_timer(
            last_contact, typing_ticket_cache, reconnect_asked,
            warning_active, reconnect_in_progress, login_time_ref,
        ))

        get_updates_buf = ""
        logger.info("WeChat bot message loop started (ChatService pipeline)")

        try:
            while self._running:
                result = await self._api_post(
                    "ilink/bot/getupdates",
                    {"get_updates_buf": get_updates_buf, "base_info": self._base_info()},
                )
                get_updates_buf = result.get("get_updates_buf") or get_updates_buf

                for msg in result.get("msgs") or []:
                    if msg.get("message_type") != 1:
                        continue
                    text = msg.get("item_list", [{}])[0].get("text_item", {}).get("text", "")
                    from_id = msg["from_user_id"]
                    context_token = msg["context_token"]
                    print(f"[WeChat] 收到消息: {text}")

                    last_contact["from_id"] = from_id
                    last_contact["context_token"] = context_token

                    # ── 指令处理（不走 ChatService 管道）──

                    # 手动重连确认
                    if manual_reconnect_pending.get(from_id) and text.strip().upper() in ("Y", "N"):
                        del manual_reconnect_pending[from_id]
                        if text.strip().upper() == "Y":
                            await self._send_msg(from_id, context_token, "好的，正在重新连接...")
                            await self._do_reconnect(last_contact, typing_ticket_cache,
                                                     reconnect_asked, warning_active,
                                                     reconnect_in_progress, login_time_ref)
                        else:
                            await self._send_msg(from_id, context_token, "已取消重新连接")
                        continue

                    # 定时预警 Y/N
                    if warning_active[0] and text.strip().upper() in ("Y", "N"):
                        if text.strip().upper() == "Y":
                            reconnect_asked.set()
                            await self._send_msg(from_id, context_token, "好的，正在重新连接...")
                        else:
                            await self._send_msg(from_id, context_token, "好的，稍后再提醒您")
                        continue

                    # 首次交互
                    if from_id not in welcomed_users:
                        welcomed_users.add(from_id)
                        await self._send_msg(from_id, context_token, COMMANDS_MSG)
                        continue

                    # /help /指令
                    if text.strip() in ("/help", "/指令"):
                        await self._send_msg(from_id, context_token, COMMANDS_MSG)
                        continue

                    # /time
                    if text.strip() == "/time":
                        _rem = max(0, login_time_ref[0] + RECONNECT_CONFIG["session_duration"] - time.time())
                        _h, _m, _s = int(_rem // 3600), int((_rem % 3600) // 60), int(_rem % 60)
                        _ts = f"{_h} 小时 {_m} 分钟" if _h > 0 else f"{_m} 分钟 {_s} 秒"
                        await self._send_msg(from_id, context_token, f"当前连接剩余时间：{_ts}")
                        continue

                    # /重新连接
                    if text.strip() == "/重新连接":
                        if reconnect_in_progress[0]:
                            await self._send_msg(from_id, context_token, "重连正在进行中，请稍候...")
                        else:
                            manual_reconnect_pending[from_id] = True
                            await self._send_msg(from_id, context_token,
                                                 "确认要立即重新连接吗？\n回复 Y 确认重连 / N 取消")
                        continue

                    # ── 正常对话：通过 ChatService 管道处理 ──

                    # 获取 typing_ticket
                    if from_id not in typing_ticket_cache:
                        cfg = await self._api_post(
                            "ilink/bot/getconfig",
                            {"ilink_user_id": from_id, "context_token": context_token,
                             "base_info": self._base_info()},
                        )
                        typing_ticket_cache[from_id] = cfg.get("typing_ticket", "")
                    typing_ticket = typing_ticket_cache[from_id]

                    # 发送"正在输入"
                    if typing_ticket:
                        await self._api_post(
                            "ilink/bot/sendtyping",
                            {"ilink_user_id": from_id, "typing_ticket": typing_ticket,
                             "status": 1, "base_info": self._base_info()},
                        )

                    # ── 核心：ChatService 管道（阻塞调用，放入线程池）──
                    conv_id = self._conversations.get(from_id)
                    loop = asyncio.get_event_loop()
                    result = await loop.run_in_executor(
                        self._executor,
                        self._process_message_sync,
                        from_id, text, conv_id,
                    )
                    reply = result["content"]
                    # 保存 conversation_id 供下次复用
                    if result.get("conversation_id"):
                        self._conversations[from_id] = result["conversation_id"]

                    # 发送回复
                    client_id = f"treehole-weixin-{random.randint(0, 0xFFFFFFFF):08x}"
                    send_result = await self._api_post(
                        "ilink/bot/sendmessage",
                        {
                            "msg": {
                                "from_user_id": "",
                                "to_user_id": from_id,
                                "client_id": client_id,
                                "message_type": 2,
                                "message_state": 2,
                                "context_token": context_token,
                                "item_list": [{"type": 1, "text_item": {"text": reply}}],
                            },
                            "base_info": self._base_info(),
                        },
                    )
                    print(f"[WeChat] sendmessage 返回: {send_result}")
                    print(f"[WeChat] 已回复: {reply[:50]}...")

                    # 取消"正在输入"
                    if typing_ticket:
                        await self._api_post(
                            "ilink/bot/sendtyping",
                            {"ilink_user_id": from_id, "typing_ticket": typing_ticket,
                             "status": 2, "base_info": self._base_info()},
                        )

        except asyncio.CancelledError:
            logger.info("WeChat bot message loop cancelled")
        except Exception as e:
            logger.error(f"WeChat bot message loop error: {e}", exc_info=True)
        finally:
            reconnect_task.cancel()
            try:
                await reconnect_task
            except asyncio.CancelledError:
                pass

    # ── 重连逻辑 ──

    async def _reconnect_timer(self, last_contact, typing_ticket_cache, reconnect_asked,
                               warning_active, reconnect_in_progress, login_time_ref):
        cfg = RECONNECT_CONFIG
        while self._running:
            elapsed = time.time() - login_time_ref[0]
            first_wait = max(0, cfg["session_duration"] - cfg["warning_before"] - elapsed)
            try:
                await asyncio.sleep(first_wait)
            except asyncio.CancelledError:
                return

            remaining = login_time_ref[0] + cfg["session_duration"] - time.time()
            if remaining <= cfg["force_before"]:
                force_msg = "[自动] 连接即将到期，开始强制重新连接..."
                print(f"[WeChat] {force_msg}")
                if last_contact["from_id"] and last_contact["context_token"]:
                    await self._send_msg(last_contact["from_id"], last_contact["context_token"], force_msg)
                await self._do_reconnect(last_contact, typing_ticket_cache, reconnect_asked,
                                         warning_active, reconnect_in_progress, login_time_ref)
                continue

            remaining_h = remaining / 3600
            warn_msg = f"[提醒] 连接还剩约 {remaining_h:.1f} 小时到期，是否现在重新连接？回复 Y 立即重连，N 稍后提醒"
            print(f"[WeChat] {warn_msg}")
            if last_contact["from_id"] and last_contact["context_token"]:
                await self._send_msg(last_contact["from_id"], last_contact["context_token"], warn_msg)
            warning_active[0] = True

            while self._running:
                remaining = login_time_ref[0] + cfg["session_duration"] - time.time()
                if remaining <= cfg["force_before"]:
                    force_msg = "[自动] 连接即将到期，开始强制重新连接..."
                    print(f"[WeChat] {force_msg}")
                    if last_contact["from_id"] and last_contact["context_token"]:
                        await self._send_msg(last_contact["from_id"], last_contact["context_token"], force_msg)
                    await self._do_reconnect(last_contact, typing_ticket_cache, reconnect_asked,
                                             warning_active, reconnect_in_progress, login_time_ref)
                    break

                wait_secs = max(0.0, min(float(cfg["reminder_interval"]),
                                         remaining - cfg["force_before"]))
                try:
                    await asyncio.wait_for(reconnect_asked.wait(), timeout=wait_secs)
                    reconnect_asked.clear()
                    await self._do_reconnect(last_contact, typing_ticket_cache, reconnect_asked,
                                             warning_active, reconnect_in_progress, login_time_ref)
                    break
                except asyncio.TimeoutError:
                    remaining = login_time_ref[0] + cfg["session_duration"] - time.time()
                    if remaining <= cfg["force_before"]:
                        continue
                    remaining_m = remaining / 60
                    remind_msg = (f"[提醒] 连接还剩约 {remaining_m:.0f} 分钟，"
                                  f"是否现在重新连接？回复 Y 立即重连，N 继续等待")
                    print(f"[WeChat] {remind_msg}")
                    if last_contact["from_id"] and last_contact["context_token"]:
                        await self._send_msg(last_contact["from_id"], last_contact["context_token"], remind_msg)

    async def _do_reconnect(self, last_contact, typing_ticket_cache, reconnect_asked,
                            warning_active, reconnect_in_progress, login_time_ref):
        if reconnect_in_progress[0]:
            return
        reconnect_in_progress[0] = True
        warning_active[0] = False
        reconnect_asked.clear()

        print("[WeChat] 开始重连流程...")
        from_id = last_contact["from_id"]
        ctx = last_contact["context_token"]

        _base = self._bot_base_url_ref[0] or DEFAULT_BASE_URL
        try:
            data = await self._fetch_login_qrcode(_base)
            qrcode = data["qrcode"]
            qrcode_url = data.get("qrcode_img_content", qrcode)
        except Exception as e:
            print(f"[WeChat] 获取二维码失败: {e}")
            reconnect_in_progress[0] = False
            login_time_ref[0] = time.time()
            return

        qr_msg = f"[重连] 请扫码完成新连接：{qrcode_url}"
        print(f"[WeChat] {qr_msg}")
        self._render_terminal_qr(qrcode_url)
        await self._send_msg(from_id, ctx, qr_msg)

        login_result = await self._wait_login_confirmation(
            qrcode, _base,
            timeout_seconds=RECONNECT_CONFIG["qrcode_scan_timeout"],
            allow_already_connected=True,
        )
        if login_result.get("already_connected"):
            print("[WeChat] 服务端提示已连接过，继续沿用当前连接")
            new_token = self._bot_token_ref[0]
            new_base_url = self._bot_base_url_ref[0]
        else:
            new_token = login_result.get("bot_token")
            new_base_url = login_result.get("baseurl", self._bot_base_url_ref[0])

        if new_token is None:
            print("[WeChat] 扫码超时，重连未完成")
            await self._send_msg(from_id, ctx, "[失败] 扫码超时，重连未完成，下次到期前会再次提醒")
            login_time_ref[0] = time.time()
            reconnect_in_progress[0] = False
            return

        self._bot_token_ref[0] = new_token
        self._bot_base_url_ref[0] = new_base_url
        typing_ticket_cache.clear()
        self._user_service.clear_cache()
        self._conversations.clear()  # 重连后开始新会话
        print("[WeChat] 新连接已建立，token 已切换")
        await self._send_msg(from_id, ctx, "[完成] 新连接已建立，已自动切换，继续使用")

        reconnect_in_progress[0] = False
        login_time_ref[0] = time.time()

    # ── iLink API 方法 ──

    @staticmethod
    def _base_info() -> dict:
        return {"channel_version": CHANNEL_VERSION, "bot_agent": BOT_AGENT}

    @staticmethod
    def _make_headers(token: str | None = None) -> dict:
        uin = str(random.randint(0, 0xFFFFFFFF))
        headers = {
            "Content-Type": "application/json",
            "AuthorizationType": "ilink_bot_token",
            "X-WECHAT-UIN": base64.b64encode(uin.encode()).decode(),
            "iLink-App-Id": ILINK_APP_ID,
            "iLink-App-ClientVersion": ILINK_APP_CLIENT_VERSION,
        }
        if token:
            headers["Authorization"] = f"Bearer {token}"
        return headers

    async def _api_get(self, path: str, token: str | None = None) -> dict:
        url = f"{self._bot_base_url_ref[0] or DEFAULT_BASE_URL}/{path}"
        async with self._session.get(url, headers=self._make_headers(token)) as res:
            text = await res.text()
            print(f"  [GET {path}] HTTP {res.status} → {text[:200]}")
            try:
                return json.loads(text)
            except Exception:
                return {}

    async def _api_post(self, path: str, body: dict, token_override: str | None = None) -> dict:
        token = token_override if token_override is not None else self._bot_token_ref[0]
        url = f"{self._bot_base_url_ref[0] or DEFAULT_BASE_URL}/{path}"
        async with self._session.post(url, json=body, headers=self._make_headers(token)) as res:
            text = await res.text()
            print(f"  [{path}] HTTP {res.status} → {text[:200]}")
            try:
                return json.loads(text)
            except Exception:
                return {}

    async def _send_msg(self, to_id: str, context_token: str, text: str):
        if not to_id or not context_token:
            print(f"[WeChat通知] {text}")
            return
        try:
            client_id = f"treehole-weixin-{random.randint(0, 0xFFFFFFFF):08x}"
            await self._api_post(
                "ilink/bot/sendmessage",
                {
                    "msg": {
                        "from_user_id": "",
                        "to_user_id": to_id,
                        "client_id": client_id,
                        "message_type": 2,
                        "message_state": 2,
                        "context_token": context_token,
                        "item_list": [{"type": 1, "text_item": {"text": text}}],
                    },
                    "base_info": self._base_info(),
                },
            )
        except Exception as e:
            print(f"[WeChat通知] 发送失败({e})，降级打印: {text}")

    async def _fetch_login_qrcode(self, base_url: str = DEFAULT_BASE_URL) -> dict:
        body = {"local_token_list": [self._bot_token_ref[0]] if self._bot_token_ref[0] else []}
        data = await self._api_post("ilink/bot/get_bot_qrcode?bot_type=3", body, None)
        if data.get("qrcode"):
            return data
        print("[WeChat] POST 获取二维码未返回 qrcode，尝试兼容旧版 GET 流程。")
        return await self._api_get("ilink/bot/get_bot_qrcode?bot_type=3", None)

    async def _poll_login_status(self, qrcode: str, base_url: str = DEFAULT_BASE_URL,
                                  verify_code: str | None = None) -> dict:
        endpoint = f"ilink/bot/get_qrcode_status?qrcode={quote(qrcode, safe='')}"
        if verify_code:
            endpoint += f"&verify_code={quote(verify_code, safe='')}"
        status = await self._api_get(endpoint, None)
        state = status.get("status", "")

        if state == "confirmed" or status.get("bot_token"):
            return {
                "bot_token": status.get("bot_token"),
                "baseurl": status.get("baseurl") or status.get("base_url") or base_url,
            }
        if state == "binded_redirect" or status.get("binded_redirect"):
            return {"already_connected": True}
        if state == "expired":
            return {"expired": True}
        if state == "scaned_but_redirect":
            redirect_host = status.get("redirect_host")
            if redirect_host:
                return {"redirect_base": f"https://{redirect_host}"}
            return {}
        if state == "scaned":
            return {"scanned": True, "verify_code_accepted": bool(verify_code)}
        elif state in ("need_verifycode", "verify_code_blocked") or status.get("need_verifycode"):
            if state == "verify_code_blocked":
                return {"verify_code_blocked": True}
            return {"need_verifycode": True, "retry_verifycode": bool(verify_code)}
        elif state and state != "wait":
            print(f"[WeChat] 登录状态: {state}")

        return {}

    async def _wait_login_confirmation(self, qrcode: str, base_url: str = DEFAULT_BASE_URL,
                                        timeout_seconds: int | None = None,
                                        allow_already_connected: bool = False) -> dict:
        deadline = time.time() + timeout_seconds if timeout_seconds else None
        current_base_url = base_url
        pending_verify_code = None
        scanned_printed = False

        while True:
            if deadline and time.time() >= deadline:
                return {"timeout": True}

            try:
                result = await self._poll_login_status(qrcode, current_base_url, pending_verify_code)
            except Exception as e:
                print(f"[WeChat] 轮询扫码状态失败，稍后重试: {e}")
                await asyncio.sleep(1)
                continue

            if result.get("bot_token"):
                return result
            if result.get("already_connected"):
                return result if allow_already_connected else {"already_connected": True}
            if result.get("expired"):
                return result
            if result.get("verify_code_blocked"):
                return result
            if result.get("redirect_base"):
                current_base_url = result["redirect_base"]
                print(f"[WeChat] 扫码轮询切换到新节点: {current_base_url}")
                continue
            if result.get("scanned"):
                if pending_verify_code and result.get("verify_code_accepted"):
                    pending_verify_code = None
                if not scanned_printed:
                    print("[WeChat] 已扫码，等待手机端确认...")
                    scanned_printed = True
            if result.get("need_verifycode"):
                prompt = "你输入的数字不匹配，请重新输入: " if result.get("retry_verifycode") else "请输入手机微信显示的数字配对码: "
                pending_verify_code = input(prompt).strip()
                continue

            await asyncio.sleep(1)

    # ── 二维码渲染（终端）──

    @staticmethod
    def _render_terminal_qr(content: str):
        if not content:
            return
        if content.startswith("http") and WeChatBot._render_terminal_image_from_url(content):
            return
        WeChatBot._render_generated_qr(content)

    @staticmethod
    def _render_terminal_image_from_url(url: str) -> bool:
        try:
            from PIL import Image
        except ImportError:
            return False
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = resp.read()
            image = Image.open(io.BytesIO(data)).convert("L")
            max_width = 72
            scale = max(1, int(image.width / max_width))
            width = max(1, int(image.width / scale))
            height = max(1, int(image.height / scale))
            image = image.resize((width, height))
            print()
            for y in range(height):
                print("".join("██" if image.getpixel((x, y)) < 128 else "  " for x in range(width)))
            print()
            return True
        except Exception as e:
            print(f"[WeChat] 二维码图片渲染失败: {e}")
            return False

    @staticmethod
    def _render_generated_qr(content: str):
        try:
            import qrcode
        except ImportError:
            print("[WeChat] 未安装 qrcode/Pillow，无法在终端渲染二维码")
            return
        qr = qrcode.QRCode(border=1)
        qr.add_data(content)
        qr.make(fit=True)
        matrix = qr.get_matrix()
        print()
        for row in matrix:
            print("".join("██" if cell else "  " for cell in row))
        print()

    @staticmethod
    def _save_qrcode_content(content: str):
        if not content:
            return
        if content.startswith("data:image/"):
            header, b64 = content.split(",", 1)
            m = re.search(r"data:image/(\w+)", header)
            ext = m.group(1) if m else "png"
            with open(f"qrcode.{ext}", "wb") as f:
                f.write(base64.b64decode(b64))
            print(f"[WeChat] 二维码已保存到 qrcode.{ext}")
        elif content.startswith("<svg"):
            with open("qrcode.svg", "w", encoding="utf-8") as f:
                f.write(content)
            print("[WeChat] 二维码已保存到 qrcode.svg")
        elif content.startswith("http"):
            pass
        else:
            try:
                with open("qrcode.png", "wb") as f:
                    f.write(base64.b64decode(content))
                print("[WeChat] 二维码已保存到 qrcode.png")
            except Exception:
                pass
