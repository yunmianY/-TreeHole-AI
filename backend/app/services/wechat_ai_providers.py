"""微信机器人 AI 提供商 — 支持 DeepSeek 和 DusAPI 两种后端。

从 weixin-ClawBot-API 项目迁移，用于微信聊天通道的独立 AI 配置。
"""

import time
import requests
from dataclasses import dataclass
from abc import ABC, abstractmethod

version = "1.0.1"


def log(message, level="INFO"):
    print(f"[WeChat-AI] [{level}] {message}")


# ========== DeepSeek Provider ==========

@dataclass
class DeepSeekConfig:
    api_key: str
    base_url: str = "https://api.deepseek.com"
    model: str = "deepseek-v4-flash"
    prompt: str = "你是一个有帮助的AI助手。"


class DeepSeekAPI:
    """DeepSeek OpenAI-compatible chat/completions client."""

    def __init__(self, config: DeepSeekConfig):
        self.config = config
        self.api_key = config.api_key
        self.base_url = config.base_url.rstrip("/")
        self.model = config.model

    def chat(self, message, model=None, stream=False, prompt=None, history=None):
        if stream:
            log("DeepSeekAPI 当前封装未启用流式响应，已按非流式请求处理", "WARN")
        if model is None:
            model = self.model
        if prompt is None:
            prompt = self.config.prompt

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "User-Agent": f"treehole-wechat-bot/{version}",
        }
        messages = [{"role": "system", "content": prompt}]
        if history:
            for h in history:
                role = "assistant" if h.get("attr") == "self" else "user"
                text = h.get("content", "")
                t = h.get("time", "")
                content = f"[{t}] {text}" if t else text
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": message})

        payload = {
            "model": model,
            "messages": messages,
            "max_tokens": 1024,
            "stream": False,
        }
        if model == "deepseek-v4-flash":
            payload["thinking"] = {"type": "disabled"}
        endpoint = f"{self.base_url}/chat/completions"
        retry_delays = [2, 4, 8, 16, 32]
        max_retries = 5
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                response = requests.post(endpoint, headers=headers, json=payload, timeout=60)
                response.raise_for_status()
                data = response.json()
                result = data["choices"][0]["message"].get("content", "")
                if not result:
                    log("DeepSeekAPI 响应中未找到文本内容", "WARN")
                    return "AI 未返回有效内容"

                if attempt > 0:
                    log(f"DeepSeekAPI 第 {attempt} 次重试成功：{result[:100]}...")
                else:
                    log(f"DeepSeekAPI 返回成功：{result[:100]}...")
                return result

            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    delay = retry_delays[attempt]
                    log(f"DeepSeekAPI 第 {attempt + 1} 次失败（{type(e).__name__}），{delay}s 后重试...", "WARNING")
                    time.sleep(delay)
                else:
                    log(f"DeepSeekAPI 已重试 {max_retries} 次，最终失败: {last_error}", "ERROR")

        return "API接口失效，请联系管理员"


# ========== DusAPI Provider ==========

@dataclass
class DusConfig:
    api_key: str
    base_url: str
    model1: str = "claude-sonnet-4-5"
    prompt: str = "你是一个有帮助的AI助手。"


class DusAPI:
    """
    DusAPI 兼容接口封装类
    两种模型均使用 Anthropic 格式（x-api-key + /v1/messages），
    根据模型名称自动选择响应解析方式：
    - 包含 'claude' → 按 claude 解析（content[0]['text']）
    - 包含 'gpt' 或其他 → 按 gpt 解析（遍历 content 找 type=='text'）
    """

    def __init__(self, config: DusConfig):
        self.config = config
        self.DS_NOW_MOD = config.model1
        self.api_key = config.api_key
        self.base_url = config.base_url.rstrip('/')

    def chat(self, message, model=None, stream=False, prompt=None, history=None):
        if model is None:
            model = self.DS_NOW_MOD
        if prompt is None:
            prompt = self.config.prompt

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
            'user-agent': f'treehole-wechat-bot/{version}'
        }
        messages = []
        if history:
            for h in history:
                role = "assistant" if h.get('attr') == 'self' else "user"
                t = h.get('time', '')
                content = f"[{t}] {h.get('content', '')}" if t else h.get('content', '')
                messages.append({"role": role, "content": content})
        messages.append({"role": "user", "content": message})
        payload = {
            "model": model,
            "max_tokens": 1024,
            "system": prompt,
            "messages": messages,
        }
        api_endpoint = f"{self.base_url}/v1/messages"
        retry_delays = [2, 4, 8, 16, 32]
        max_retries = 5
        last_error = None

        for attempt in range(max_retries + 1):
            try:
                response = requests.post(api_endpoint, headers=headers, json=payload, timeout=30)
                response.raise_for_status()
                response.encoding = 'utf-8'
                response_data = response.json()

                if 'claude' in model.lower():
                    result = response_data['content'][0]['text']
                else:
                    result = None
                    for content_block in response_data['content']:
                        if content_block.get('type') == 'text':
                            result = content_block['text']
                            break
                    if result is None:
                        log(level="WARN", message="DusAPI 响应中未找到文本内容")
                        return "AI 未返回有效内容"

                if attempt > 0:
                    log(message=f"DusAPI 第 {attempt} 次重试成功：{result[:100]}...")
                else:
                    log(message=f"DusAPI 返回成功：{result[:100]}...")
                return result

            except Exception as e:
                last_error = e
                if attempt < max_retries:
                    delay = retry_delays[attempt]
                    log(level="WARNING", message=f"DusAPI 第 {attempt + 1} 次失败（{type(e).__name__}），{delay}s 后重试...")
                    time.sleep(delay)
                else:
                    log(level="ERROR", message=f"DusAPI 已重试 {max_retries} 次，最终失败: {last_error}")

        return "API接口失效，请联系管理员"


# ========== Provider Factory ==========

def create_wechat_ai(provider: str, api_key: str, base_url: str, model: str, prompt: str):
    """根据配置创建微信机器人 AI 实例。"""
    if provider == "deepseek":
        config = DeepSeekConfig(
            api_key=api_key,
            base_url=base_url,
            model=model,
            prompt=prompt,
        )
        return DeepSeekAPI(config)
    elif provider == "dusapi":
        config = DusConfig(
            api_key=api_key,
            base_url=base_url,
            model1=model,
            prompt=prompt,
        )
        return DusAPI(config)
    else:
        raise ValueError(f"不支持的 AI 提供商: {provider}，可选: deepseek, dusapi")
