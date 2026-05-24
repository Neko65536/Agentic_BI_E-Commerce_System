# agents/llm_client.py

from __future__ import annotations

import json
from typing import Any

import openai
from openai import OpenAI

from config.settings import LLM_SETTINGS


class LLMClientError(RuntimeError):
    """LLM 调用失败或配置错误。"""

class LLMClient:
    """
    LLM 客户端封装。
    """
    def __init__(self):
        if not LLM_SETTINGS.api_key:
            raise LLMClientError("未配置 LLM_API_KEY，请先检查 .env")

        self.client = OpenAI(
            api_key=LLM_SETTINGS.api_key,
            base_url=LLM_SETTINGS.base_url,
            timeout=LLM_SETTINGS.timeout_seconds,
            max_retries=1,
        )

    def chat_text(self, messages: list[dict[str, str]]) -> str:
        """
        普通文本对话调用。
        先用于测试连通性。
        """
        try:
            response = self.client.chat.completions.create(
                model=LLM_SETTINGS.model,
                messages=messages,
                temperature=LLM_SETTINGS.temperature,
            )
        except openai.APIError as exc:
            raise LLMClientError(f"LLM API 调用失败：{exc}") from exc

        content = response.choices[0].message.content
        return content or ""


    def chat_json(self, messages: list[dict[str, str]]) -> dict[str, Any]:
        """
        要求模型返回 JSON。

        智谱文档说明结构化输出可以使用：
        response_format={"type": "json_object"}
        """

        try:
            response = self.client.chat.completions.create(
                model=LLM_SETTINGS.model,
                messages=messages,
                temperature=LLM_SETTINGS.temperature,
                response_format={"type": "json_object"},
            )
        except openai.APIError as exc:
            raise LLMClientError(f"LLM JSON 调用失败：{exc}") from exc

        content = response.choices[0].message.content or ""

        try:
            return json.loads(content)
        except json.JSONDecodeError as exc:
            raise LLMClientError(f"LLM 返回的不是合法 JSON：{content}") from exc