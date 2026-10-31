"""LLM service — calls OpenAI-compatible chat completion API."""

from __future__ import annotations

import httpx
from app.config import settings


async def chat_completion(
    messages: list[dict],
    temperature: float = 0.7,
    max_tokens: int = 2048,
) -> str:
    """Call LLM and return the assistant's response text."""
    if not settings.LLM_API_KEY:
        return "[LLM_API_KEY not configured — returning empty response]"

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{settings.LLM_API_BASE}/chat/completions",
            headers={
                "Authorization": f"Bearer {settings.LLM_API_KEY}",
                "Content-Type": "application/json",
            },
            json={
                "model": settings.LLM_MODEL,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data["choices"][0]["message"]["content"]


def build_chat_prompt(
    user_message: str,
    retrieved_context: list[dict],
    memory_context: str | None = None,
    learning_state: list[dict] | None = None,
) -> list[dict]:
    """Build the prompt messages for the chat endpoint, fusing SeekDB retrieval + PowerContext memory."""
    system_parts = ["你是「知序」，一个智能学习助手。你能帮助用户理解知识、复习功课、追踪学习进度。"]

    if retrieved_context:
        context_text = "\n\n---\n\n".join(
            f"[来源: {c.get('title', '未知')}] (相关度: {c.get('score', 0):.2f})\n{c.get('snippet', '')}"
            for c in retrieved_context
        )
        system_parts.append(f"以下是从用户知识库中检索到的相关资料：\n\n{context_text}")

    if memory_context:
        system_parts.append(f"用户的学习记忆上下文：\n{memory_context}")

    if learning_state:
        weak = [s for s in learning_state if s.get("mastery") in ("needs_review", "learning")]
        if weak:
            weak_text = "、".join(s.get("topic", "") for s in weak[:5])
            system_parts.append(f"用户当前的薄弱知识点：{weak_text}")

    system_parts.append("请基于以上资料回答用户的问题。如果资料中有相关信息，请引用并说明出处。如果资料不足，可以结合自己的知识回答，但要标注哪些是自己的补充。")

    return [
        {"role": "system", "content": "\n\n".join(system_parts)},
        {"role": "user", "content": user_message},
    ]
