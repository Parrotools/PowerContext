"""PowerContext integration service — handles user memory and learning state."""

from __future__ import annotations

import json
import uuid
import logging
from datetime import datetime, timedelta
from pathlib import Path
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

_scope_id: str | None = None
_scope_init_failed = False
_SCOPE_CACHE = Path("/tmp/zhixu_pc_scope_id")


async def _ensure_scope() -> str:
    """Ensure the scope exists, auto-create if needed. Returns scope_id."""
    global _scope_id, _scope_init_failed

    if _scope_id:
        return _scope_id

    if _scope_init_failed:
        return settings.POWERCONTEXT_SCOPE_ID

    configured = settings.POWERCONTEXT_SCOPE_ID
    if configured and configured != "zhixu-default":
        _scope_id = configured
        return _scope_id

    if _SCOPE_CACHE.exists():
        try:
            _scope_id = _SCOPE_CACHE.read_text().strip()
            if _scope_id:
                return _scope_id
        except Exception:
            pass

    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.post(
                f"{settings.POWERCONTEXT_URL}/v1/scopes",
                headers={"Content-Type": "application/json"},
                json={
                    "idempotency_key": str(uuid.uuid4()),
                    "title": "知序学习助手",
                    "summary": "知序学习助手的默认记忆作用域，用于追踪用户学习状态和知识掌握情况",
                },
            )
            if resp.status_code < 300:
                data = resp.json()
                _scope_id = data.get("scope_id") or data.get("id")
                if _scope_id:
                    _SCOPE_CACHE.write_text(_scope_id)
                    logger.info(f"PowerContext scope auto-created: {_scope_id}")
                    return _scope_id
    except Exception as e:
        logger.warning(f"PowerContext scope auto-creation failed: {e}")

    _scope_init_failed = True
    _scope_id = "zhixu-default"
    return _scope_id


def _headers() -> dict:
    return {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {settings.POWERCONTEXT_SCOPE_ID}",
    }


async def _request(method: str, path: str, **kwargs) -> dict | None:
    url = f"{settings.POWERCONTEXT_URL}{path}"
    scope_id = await _ensure_scope()
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {scope_id}",
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.request(method, url, headers=headers, **kwargs)
            if resp.status_code < 300:
                return resp.json() if resp.text else None
            logger.warning(f"PowerContext {method} {path} -> {resp.status_code}: {resp.text[:200]}")
            return None
    except Exception as e:
        logger.warning(f"PowerContext request failed: {e}")
        return None


# ── Source capture ─────────────────────────────────────────

async def capture_learning_note(content: str, note_type: str = "study_session") -> dict | None:
    """Capture a learning interaction as a Source in PowerContext."""
    scope_id = await _ensure_scope()
    return await _request("POST", "/v1/sources/content", json={
        "scope_id": scope_id,
        "type": "content",
        "content_type": note_type,
        "body": {"text": content},
        "metadata": {"timestamp": datetime.utcnow().isoformat()},
    })


async def capture_chat_interaction(user_msg: str, assistant_msg: str, topic: str = "") -> dict | None:
    """Record a Q&A interaction for memory extraction."""
    content = f"User asked: {user_msg}\nAssistant answered: {assistant_msg}"
    if topic:
        content = f"Topic: {topic}\n{content}"
    return await capture_learning_note(content, note_type="chat_interaction")


# ── Atomic Memory ──────────────────────────────────────────

async def save_memory(key: str, content: str, memory_type: str = "fact") -> dict | None:
    """Save a memory artifact using PowerContext's remember API."""
    scope_id = await _ensure_scope()
    return await _request("POST", "/v1/memory/remember", json={
        "scope_id": scope_id,
        "kind": memory_type,
        "text": content,
        "reason": f"Memory key: {key}",
    })


async def search_memory(query: str, limit: int = 10) -> list[dict]:
    """Search memories by semantic similarity + full-text."""
    scope_id = await _ensure_scope()
    result = await _request("POST", "/v1/memory/search", json={
        "scope_id": scope_id,
        "query": query,
        "limit": limit,
    })
    return result.get("entries", []) if result else []


async def get_memory(artifact_id: str) -> dict | None:
    """Get a specific memory entry."""
    scope_id = await _ensure_scope()
    result = await _request("POST", "/v1/memory/entries/get", json={
        "scope_id": scope_id,
        "artifact_id": artifact_id,
    })
    if result and result.get("entries"):
        return result["entries"][0]
    return None


async def list_memories() -> list[dict]:
    """List all memory entries."""
    scope_id = await _ensure_scope()
    result = await _request("POST", "/v1/memory/entries/list", json={
        "scope_id": scope_id,
        "include_inactive": True,
    })
    if not result:
        return []

    entries = result.get("entries", [])
    parsed = []
    for entry in entries:
        artifact = entry.get("artifact", {})
        parsed.append({
            "artifact_id": artifact.get("artifact_id"),
            "kind": entry.get("kind"),
            "text": entry.get("text"),
            "state": entry.get("state"),
        })
    return parsed


async def forget_memory(family: str, artifact_id: str) -> bool:
    """Mark a memory as forgotten (soft-delete, restorable)."""
    result = await _request("POST", f"/v1/atomic-memory/{family}/{artifact_id}/forget")
    return result is not None


# ── Learning state management ──────────────────────────────

async def update_topic_mastery(
    user_id: str,
    topic: str,
    mastery: str,
    note: str = "",
) -> dict | None:
    """Update mastery level for a specific topic."""
    key = f"user:{user_id}:topic:{topic}"
    existing = await get_memory(key)

    state = {
        "user_id": user_id,
        "topic": topic,
        "mastery": mastery,
        "review_count": 0,
        "last_reviewed": datetime.utcnow().isoformat(),
        "note": note,
    }
    if existing and existing.get("text"):
        try:
            old = json.loads(existing["text"]) if isinstance(existing["text"], str) else existing["text"]
            if isinstance(old, dict):
                state["review_count"] = old.get("review_count", 0) + 1
        except (json.JSONDecodeError, KeyError, TypeError):
            pass

    next_review = _calc_next_review(mastery, state["review_count"])
    state["next_review"] = next_review.isoformat() if next_review else None

    return await save_memory(key, json.dumps(state, ensure_ascii=False), "learning_state")


async def get_user_learning_state(user_id: str) -> list[dict]:
    """Get all learning state memories for a user."""
    memories = await list_memories()
    user_memories = []
    for mem in memories:
        try:
            if mem.get("kind") != "learning_state":
                continue
            text = mem.get("text", "{}")
            state = json.loads(text) if isinstance(text, str) else text
            if isinstance(state, dict) and state.get("user_id") == user_id:
                user_memories.append(state)
        except (json.JSONDecodeError, KeyError, TypeError):
            continue
    return user_memories


async def get_weak_topics(user_id: str) -> list[dict]:
    """Get topics that need review."""
    state = await get_user_learning_state(user_id)
    return [
        s for s in state
        if s.get("mastery") in ("needs_review", "learning")
    ]


async def get_due_for_review(user_id: str) -> list[dict]:
    """Get topics due for review based on spaced repetition schedule."""
    state = await get_user_learning_state(user_id)
    now = datetime.utcnow()
    due = []
    for s in state:
        next_review_str = s.get("next_review")
        if next_review_str:
            try:
                next_review = datetime.fromisoformat(next_review_str)
                if next_review <= now:
                    due.append(s)
            except (ValueError, TypeError):
                continue
    return due


def _calc_next_review(mastery: str, review_count: int) -> datetime | None:
    """Calculate next review date using a simplified spaced repetition schedule."""
    intervals = {
        "unseen": 0,
        "learning": 1,
        "needs_review": 0.5,
        "mastered": 7,
    }
    base_days = intervals.get(mastery, 1)
    multiplier = max(1, review_count)
    days = base_days * multiplier
    if days <= 0:
        return datetime.utcnow() + timedelta(days=1)
    return datetime.utcnow() + timedelta(days=min(days, 30))


# ── PreparedContext ────────────────────────────────────────

async def prepare_context(user_id: str, query: str = "") -> dict | None:
    """Get a bounded recall context for the user."""
    scope_id = await _ensure_scope()
    return await _request("POST", "/v1/context/prepare", json={
        "scope_id": scope_id,
        "subject_id": user_id,
        "query": query,
        "sections": ["memory", "experience", "profile"],
        "byte_budget": 4096,
    })


# ── Experience ─────────────────────────────────────────────

async def propose_experience(
    situation: str,
    action: str,
    outcome: str,
    lesson: str,
) -> dict | None:
    """Propose a new experience for review."""
    scope_id = await _ensure_scope()
    return await _request("POST", "/v1/experience/propose", json={
        "scope_id": scope_id,
        "situation": situation,
        "action": action,
        "outcome": outcome,
        "lesson": lesson,
    })
