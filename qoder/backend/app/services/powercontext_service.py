"""PowerContext integration service — handles user memory and learning state."""

from __future__ import annotations

import json
import uuid
import logging
import tempfile
from datetime import datetime, timedelta
from pathlib import Path
import httpx
from app.config import settings

logger = logging.getLogger(__name__)

_scope_id: str | None = None
_scope_init_failed = False
_SCOPE_IDEMPOTENCY_KEY = "zhixu-learning-scope-v1"
_SCOPE_TITLE = "知序学习助手"
_SCOPE_SUMMARY = "知序学习助手的默认记忆作用域，用于追踪用户学习状态和知识掌握情况"


def _scope_cache_path() -> Path:
    """Keep the scope pointer on the backend data volume, not in container /tmp."""
    preferred = Path(settings.SEEKDB_DATABASE_PATH) / "zhixu_pc_scope_id"
    try:
        preferred.parent.mkdir(parents=True, exist_ok=True)
        return preferred
    except OSError:
        return Path(tempfile.gettempdir()) / "zhixu_pc_scope_id"


async def _scope_exists(client: httpx.AsyncClient, scope_id: str) -> bool:
    try:
        resp = await client.get(f"{settings.POWERCONTEXT_URL}/v1/scopes/{scope_id}")
        return resp.status_code < 300
    except httpx.HTTPError:
        return False


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

    cache = _scope_cache_path()
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            if cache.exists():
                try:
                    cached = cache.read_text().strip()
                except OSError:
                    cached = ""
                if cached and await _scope_exists(client, cached):
                    _scope_id = cached
                    return _scope_id

            resp = await client.post(
                f"{settings.POWERCONTEXT_URL}/v1/scopes",
                headers={"Content-Type": "application/json"},
                json={
                    "idempotency_key": _SCOPE_IDEMPOTENCY_KEY,
                    "title": _SCOPE_TITLE,
                    "summary": _SCOPE_SUMMARY,
                },
            )
            if resp.status_code < 300:
                data = resp.json()
                _scope_id = data.get("scope_id") or data.get("id")
                if _scope_id:
                    try:
                        cache.write_text(_scope_id)
                    except OSError:
                        pass
                    logger.info(f"PowerContext scope ready: {_scope_id}")
                    return _scope_id
    except Exception as e:
        logger.warning(f"PowerContext scope auto-creation failed: {e}")

    _scope_init_failed = True
    _scope_id = "zhixu-default"
    return _scope_id


async def _request(method: str, path: str, **kwargs) -> dict | None:
    """Make HTTP request to PowerContext API."""
    url = f"{settings.POWERCONTEXT_URL}{path}"
    headers = {
        "Content-Type": "application/json",
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


# ── Source capture ─────────────────────────────────────────────

async def capture_learning_note(content: str, note_type: str = "study_session") -> dict | None:
    """Capture a learning interaction as a ContentSource in PowerContext."""
    scope_id = await _ensure_scope()
    return await _request("POST", "/v1/sources/content", json={
        "scope_id": scope_id,
        "source_id": f"{note_type}-{uuid.uuid4().hex}",
        "content": content,
        "metadata": {
            "timestamp": datetime.utcnow().isoformat(),
            "note_type": note_type,
        },
    })


async def capture_chat_interaction(
    user_msg: str,
    assistant_msg: str,
    topic: str = "",
    user_id: str = "default",
) -> dict | None:
    """Archive the interaction as a Source and keep a recallable Atomic Memory.

    Topic Memory processing needs an LLM worker, so without it Sources are never
    distilled into searchable memory. Writing an Atomic Memory directly keeps the
    write -> recall loop working in demo deployments too.
    """
    content = f"User {user_id} asked: {user_msg}\nAssistant answered: {assistant_msg}"
    if topic:
        content = f"Topic: {topic}\n{content}"
    await capture_learning_note(content, note_type="chat_interaction")
    return await save_memory(
        key=f"user:{user_id}:chat:{uuid.uuid4().hex}",
        content=content,
        memory_type="chat_interaction",
    )


# ── Atomic Memory ──────────────────────────────────────────────

async def save_memory(key: str, content: str, memory_type: str = "fact") -> dict | None:
    """Save a memory artifact using PowerContext's remember API.
    Returns the full response including artifact_id for tracking."""
    scope_id = await _ensure_scope()
    result = await _request("POST", "/v1/memory/remember", json={
        "scope_id": scope_id,
        "kind": memory_type,
        "text": content,
        "reason": f"Memory key: {key}",
    })
    if result and result.get("records"):
        first_record = result["records"][0]
        artifact = first_record.get("artifact", {})
        return {
            "artifact_id": artifact.get("artifact_id"),
            "family": artifact.get("family"),
            "kind": first_record.get("kind"),
            "text": first_record.get("text"),
            "state": first_record.get("state"),
            "changed": result.get("changed"),
        }
    return result


async def search_memory(query: str, limit: int = 10) -> list[dict]:
    """Search memories by semantic similarity + full-text.
    Returns list of memory objects from hits[].memory structure."""
    scope_id = await _ensure_scope()
    result = await _request("POST", "/v1/memory/search", json={
        "scope_id": scope_id,
        "query": query,
        "limit": limit,
    })
    if not result:
        return []
    hits = result.get("hits", [])
    return [hit.get("memory", {}) for hit in hits if hit.get("memory")]


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
            "family": artifact.get("family"),
            "revision": artifact.get("revision"),
            "kind": entry.get("kind"),
            "text": entry.get("text"),
            "state": entry.get("state"),
            "state_version": entry.get("state_version"),
        })
    return parsed


async def forget_memory(memory: dict) -> bool:
    """Soft-delete a memory revision via the atomic-memory lifecycle endpoint."""
    artifact_id = memory.get("artifact_id")
    revision = memory.get("revision")
    state_version = memory.get("state_version")
    if not artifact_id or revision is None or state_version is None:
        return False
    scope_id = await _ensure_scope()
    result = await _request("POST", "/v1/atomic-memory/lifecycle", json={
        "scope_id": scope_id,
        "target": {
            "artifact": {
                "family": memory.get("family") or "atomic-memory",
                "artifact_id": artifact_id,
                "revision": revision,
            },
            "state_version": state_version,
        },
        "state": "forgotten",
    })
    return result is not None


# ── Learning state management ──────────────────────────────────

async def update_topic_mastery(
    user_id: str,
    topic: str,
    mastery: str,
    note: str = "",
) -> dict | None:
    """Update mastery level for a specific topic.
    Finds the latest existing state, saves the new revision, then soft-deletes
    the superseded artifact so each topic keeps a single active record."""
    all_memories = await list_memories()
    existing_mem = None
    existing_state = None

    for mem in all_memories:
        if mem.get("kind") != "learning_state" or mem.get("state") != "active":
            continue
        try:
            text = mem.get("text", "{}")
            data = json.loads(text) if isinstance(text, str) else text
            if not (isinstance(data, dict) and data.get("user_id") == user_id and data.get("topic") == topic):
                continue
            if existing_state is None or str(data.get("last_reviewed", "")) > str(existing_state.get("last_reviewed", "")):
                existing_mem = mem
                existing_state = data
        except (json.JSONDecodeError, KeyError, TypeError):
            continue

    state = {
        "user_id": user_id,
        "topic": topic,
        "mastery": mastery,
        "review_count": 0,
        "last_reviewed": datetime.utcnow().isoformat(),
        "note": note,
    }

    if existing_state:
        state["review_count"] = existing_state.get("review_count", 0) + 1
        state["first_seen"] = existing_state.get("first_seen", existing_state.get("last_reviewed") or datetime.utcnow().isoformat())

    next_review = _calc_next_review(mastery, state["review_count"])
    state["next_review"] = next_review.isoformat() if next_review else None

    key = f"user:{user_id}:topic:{topic}"
    saved = await save_memory(key, json.dumps(state, ensure_ascii=False), "learning_state")

    if saved and existing_mem:
        await forget_memory(existing_mem)

    return saved


async def get_user_learning_state(user_id: str) -> list[dict]:
    """Get all learning state memories for a user."""
    memories = await list_memories()
    user_memories = []
    seen_topic: dict[str, int] = {}
    for mem in memories:
        try:
            if mem.get("kind") != "learning_state" or mem.get("state") != "active":
                continue
            text = mem.get("text", "{}")
            state = json.loads(text) if isinstance(text, str) else text
            if not (isinstance(state, dict) and state.get("user_id") == user_id):
                continue
            topic = state.get("topic", "")
            if topic in seen_topic:
                prior = user_memories[seen_topic[topic]]
                if str(state.get("last_reviewed", "")) > str(prior.get("last_reviewed", "")):
                    user_memories[seen_topic[topic]] = state
                continue
            seen_topic[topic] = len(user_memories)
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


# ── PreparedContext ────────────────────────────────────────────

async def prepare_context(user_id: str, query: str = "") -> dict | None:
    """Get a bounded recall context for the user."""
    scope_id = await _ensure_scope()
    normalized_query = query.strip() or f"learning progress user {user_id}"
    return await _request("POST", "/v1/context/prepare", json={
        "scope_id": scope_id,
        "query": normalized_query,
        "max_bytes": 4096,
    })


# ── Experience ─────────────────────────────────────────────────

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
