"""MiniMax API 客户端:OpenAI 兼容的 chat completions 调用(代码生成/修改)。

- 国内平台 base_url: https://api.minimaxi.com/v1(默认)
- 国际平台 base_url: https://api.minimax.io/v1
- 模型通过 SDDCTX_MINIMAX_MODEL 配置,默认 MiniMax-M2.1

仅做同步 HTTP 调用,响应原文全量留档,作为 MiniMax 开发记录的一部分。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import httpx

from sddctx.config import Settings, redact


class MiniMaxError(RuntimeError):
    """MiniMax API 调用失败。"""


@dataclass
class ChatResult:
    content: str
    reasoning: str
    finish_reason: str | None
    usage: dict
    model: str
    request_messages: list[dict] = field(default_factory=list)
    raw_response: dict = field(default_factory=dict)


class MiniMaxClient:
    def __init__(self, settings: Settings) -> None:
        if not settings.minimax_api_key:
            raise MiniMaxError(
                "缺少 MiniMax API Key:请设置环境变量 SDDCTX_MINIMAX_API_KEY(或 MINIMAX_API_KEY)。"
                "国内平台 https://api.minimaxi.com/v1,国际平台 https://api.minimax.io/v1,"
                "可用 SDDCTX_MINIMAX_BASE_URL 切换。"
            )
        self._settings = settings

    def chat(self, system_prompt: str, user_prompt: str) -> ChatResult:
        url = self._settings.minimax_base_url.rstrip("/") + "/chat/completions"
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]
        payload: dict = {
            "model": self._settings.minimax_model,
            "messages": messages,
            "temperature": self._settings.minimax_temperature,
        }
        if self._settings.minimax_max_tokens:
            payload["max_tokens"] = self._settings.minimax_max_tokens
        headers = {
            "Authorization": f"Bearer {self._settings.minimax_api_key}",
            "Content-Type": "application/json",
        }
        try:
            response = httpx.post(url, json=payload, headers=headers, timeout=600.0)
        except httpx.HTTPError as error:
            raise MiniMaxError(f"MiniMax 请求失败({url}):{error}") from error
        if response.status_code != 200:
            raise MiniMaxError(
                f"MiniMax 返回 HTTP {response.status_code}:{response.text[:500]}"
            )
        try:
            body = response.json()
        except json.JSONDecodeError as error:
            raise MiniMaxError(f"MiniMax 响应不是 JSON:{response.text[:200]}") from error
        choices = body.get("choices") or []
        if not choices:
            raise MiniMaxError(f"MiniMax 响应缺少 choices:{json.dumps(body, ensure_ascii=False)[:300]}")
        message = choices[0].get("message") or {}
        content = message.get("content") or ""
        if not content.strip():
            raise MiniMaxError("MiniMax 返回的 content 为空,无法继续。")
        return ChatResult(
            content=content,
            reasoning=message.get("reasoning_content") or "",
            finish_reason=choices[0].get("finish_reason"),
            usage=body.get("usage") or {},
            model=body.get("model") or self._settings.minimax_model,
            request_messages=messages,
            raw_response=body,
        )


def write_chat_log(run_dir: Path, result: ChatResult, settings: Settings) -> None:
    """把一次 MiniMax 调用完整留档(密钥脱敏)。"""
    run_dir.mkdir(parents=True, exist_ok=True)
    request_payload = {
        "base_url": settings.minimax_base_url,
        "model": result.model,
        "temperature": settings.minimax_temperature,
        "max_tokens": settings.minimax_max_tokens,
        "api_key": redact(settings.minimax_api_key),
        "messages": result.request_messages,
    }
    (run_dir / "minimax-request.json").write_text(
        json.dumps(request_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (run_dir / "minimax-response.json").write_text(
        json.dumps(result.raw_response, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    reasoning_md = ""
    if result.reasoning:
        reasoning_md = f"\n## 思维链(reasoning_content)\n\n{result.reasoning}\n"
    (run_dir / "minimax-response.md").write_text(
        f"# MiniMax 响应\n\n- model: {result.model}\n"
        f"- finish_reason: {result.finish_reason}\n"
        f"- usage: {json.dumps(result.usage, ensure_ascii=False)}\n"
        f"{reasoning_md}\n## content\n\n{result.content}\n",
        encoding="utf-8",
    )


__all__ = ["ChatResult", "MiniMaxClient", "MiniMaxError", "write_chat_log"]
