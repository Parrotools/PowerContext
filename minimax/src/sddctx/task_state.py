"""任务状态层:通过 PowerContext(PowerContextClient SDK)保存与复用任务进展。

角色分工:seekdb 存"工程资料"(规格/代码/测试),PowerContext 存"任务进展
与验证结果"。这里封装:
- Scope 自动创建(幂等);
- 任务看板(board:已完成/待办/验证结果)以 Memory 条目保存;
- 重启后按任务号搜索并加载最新看板(状态复用);
- 每次 PowerContext 读写追加到 records/powercontext-log.md(技术使用记录)。
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from sddctx.config import Settings

BOARD_KIND = "task-board"
VERIFICATION_KIND = "verification"
_BOARD_QUERY_PREFIX = "sddctx task-board"


class TaskStateError(RuntimeError):
    """PowerContext 不可达或返回异常。"""


class TaskBoard(BaseModel):
    task_id: str
    objective: str
    completed: list[str] = Field(default_factory=list)
    pending: list[str] = Field(default_factory=list)
    verification: list[dict] = Field(default_factory=list)
    updated_at: str = ""
    memory_citation: dict | None = None


class VerificationRecord(BaseModel):
    task_id: str
    phase: str                    # before | after
    command: str
    exit_code: int
    passed: bool
    log_path: str
    code_version: str
    detail: str = ""
    executed_at: str = ""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class PowerContextLog:
    """把每次 PowerContext 读写追加到记录文件(状态写入与复用记录)。"""

    def __init__(self, log_path: Path) -> None:
        self._log_path = log_path

    def write(self, action: str, detail: dict) -> None:
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        header_needed = not self._log_path.exists()
        with self._log_path.open("a", encoding="utf-8") as handle:
            if header_needed:
                handle.write("# PowerContext 状态写入与复用记录\n\n由 sddctx 自动追加。存储:PowerContext Server(v1.2.0)Memory/Handoff。\n\n")
            handle.write(f"## {_now()} — {action}\n\n")
            handle.write("```json\n")
            handle.write(json.dumps(detail, ensure_ascii=False, indent=2, default=str))
            handle.write("\n```\n\n")


class TaskStateClient:
    """PowerContext SDK 的同步门面(内部 asyncio)。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._log = PowerContextLog(settings.powercontext_log)
        self._scope_id: str | None = None

    # -- 基础 ---------------------------------------------------------------

    def _client(self):
        from powercontext.client import PowerContextClient  # noqa: PLC0415

        return PowerContextClient(
            self._settings.powercontext_url,
            token=self._settings.powercontext_token,
            timeout=30.0,
        )

    async def _ensure_scope_async(self, client) -> str:
        from powercontext.http import CreateScopeRequest, ScopeQueryField  # noqa: PLC0415

        if self._scope_id:
            return self._scope_id
        key = self._settings.project_key
        page = await client.list_scopes(query=f"sddctx:{key}", query_field=ScopeQueryField.TITLE, limit=10)
        for descriptor in page.items:
            if descriptor.title == f"sddctx:{key}":
                self._scope_id = descriptor.scope_id
                self._log.write("scope.reuse", {"scope_id": descriptor.scope_id, "title": descriptor.title})
                return self._scope_id
        created = await client.create_scope(
            CreateScopeRequest(
                title=f"sddctx:{key}",
                summary=f"SDD 上下文管理系统的任务状态范围({key})",
                idempotency_key=f"sddctx-{key}",
            )
        )
        self._scope_id = created.scope_id
        self._log.write("scope.create", {"scope_id": created.scope_id, "title": created.title})
        return self._scope_id

    async def _remember_async(self, client, kind: str, text: str, reason: str) -> dict:
        from powercontext.http import RememberMemoryRequest  # noqa: PLC0415

        scope_id = await self._ensure_scope_async(client)
        response = await client.remember_memory(
            RememberMemoryRequest(scope_id=scope_id, kind=kind, text=text, reason=reason)
        )
        entry = response.entry
        citation = entry.citation.model_dump(mode="json") if entry is not None else None
        self._log.write(
            "memory.remember",
            {"scope_id": scope_id, "kind": kind, "text_head": text[:200], "citation": citation},
        )
        return citation

    async def _search_async(self, client, query: str, limit: int = 10) -> list[dict]:
        from powercontext.http import SearchMemoryRequest  # noqa: PLC0415

        scope_id = await self._ensure_scope_async(client)
        response = await client.search_memory(
            SearchMemoryRequest(scope_id=scope_id, query=query, limit=limit)
        )
        entries = []
        for hit in response.hits:
            entries.append(_entry_to_dict(hit))
        self._log.write(
            "memory.search",
            {"scope_id": scope_id, "query": query, "hits": [entry.get("citation") for entry in entries]},
        )
        return entries

    # -- 对外 API ------------------------------------------------------------

    def ensure_scope(self) -> str:
        async def _run() -> str:
            async with self._client() as client:
                return await self._ensure_scope_async(client)

        try:
            return asyncio.run(_run())
        except Exception as error:  # noqa: BLE001
            raise TaskStateError(f"PowerContext 不可用({self._settings.powercontext_url}):{error}") from error

    def remember_board(self, board: TaskBoard) -> dict:
        board.updated_at = _now()
        payload = board.model_dump(mode="json", exclude={"memory_citation"})
        text = json.dumps(
            {"query_key": f"{_BOARD_QUERY_PREFIX} {board.task_id}", **payload},
            ensure_ascii=False,
        )
        async def _run() -> dict:
            async with self._client() as client:
                return await self._remember_async(
                    client, BOARD_KIND, text, reason=f"任务看板:{board.task_id}"
                )

        try:
            citation = asyncio.run(_run())
        except TaskStateError:
            raise
        except Exception as error:  # noqa: BLE001
            raise TaskStateError(f"保存任务看板失败:{error}") from error
        self._log.write("board.save", {"task_id": board.task_id, "citation": citation})
        return citation

    def remember_verification(self, record: VerificationRecord) -> dict:
        record.executed_at = _now()
        text = json.dumps(
            {"query_key": f"sddctx verification {record.task_id} {record.phase}", **record.model_dump(mode="json")},
            ensure_ascii=False,
        )
        async def _run() -> dict:
            async with self._client() as client:
                return await self._remember_async(
                    client, VERIFICATION_KIND, text, reason=f"验证结果:{record.task_id}/{record.phase}"
                )

        try:
            citation = asyncio.run(_run())
        except TaskStateError:
            raise
        except Exception as error:  # noqa: BLE001
            raise TaskStateError(f"保存验证结果失败:{error}") from error
        self._log.write("verification.save", record.model_dump(mode="json"))
        return citation

    def load_board(self, task_id: str | None) -> TaskBoard | None:
        """重启后读取最新任务看板;task_id 为 None 时取全部看板中最新的一条。"""

        async def _run() -> TaskBoard | None:
            async with self._client() as client:
                query = f"{_BOARD_QUERY_PREFIX} {task_id}" if task_id else _BOARD_QUERY_PREFIX
                entries = await self._search_async(client, query, limit=10)
                boards: list[TaskBoard] = []
                for entry in entries:
                    parsed = _parse_board_entry(entry)
                    if parsed is not None:
                        boards.append(parsed)
                if not boards:
                    return None
                if task_id:
                    boards = [board for board in boards if board.task_id == task_id] or boards
                boards.sort(key=lambda board: board.updated_at, reverse=True)
                return boards[0]

        try:
            return asyncio.run(_run())
        except TaskStateError:
            raise
        except Exception as error:  # noqa: BLE001
            raise TaskStateError(f"读取任务看板失败:{error}") from error

    def load_verifications(self, task_id: str | None = None) -> list[VerificationRecord]:
        async def _run() -> list[VerificationRecord]:
            async with self._client() as client:
                query = f"sddctx verification {task_id}" if task_id else "sddctx verification"
                entries = await self._search_async(client, query, limit=20)
                records: list[VerificationRecord] = []
                for entry in entries:
                    parsed = _parse_verification_entry(entry)
                    if parsed is not None:
                        records.append(parsed)
                records.sort(key=lambda record: record.executed_at, reverse=True)
                return records

        try:
            return asyncio.run(_run())
        except TaskStateError:
            raise
        except Exception as error:  # noqa: BLE001
            raise TaskStateError(f"读取验证结果失败:{error}") from error


def _entry_to_dict(hit: object) -> dict:
    """SearchMemoryResponse 命中项 → 平铺 dict(kind/text/citation)。"""
    entry = getattr(hit, "entry", hit)
    result = {
        "kind": getattr(entry, "kind", None),
        "text": getattr(entry, "text", None),
    }
    citation = getattr(entry, "citation", None)
    if citation is not None:
        result["citation"] = citation.model_dump(mode="json")
    return result


def _parse_board_entry(entry: dict) -> TaskBoard | None:
    text = entry.get("text") or ""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    if not isinstance(payload, dict) or "query_key" not in payload:
        return None
    payload.pop("query_key", None)
    try:
        return TaskBoard.model_validate(payload)
    except Exception:  # noqa: BLE001
        return None


def _parse_verification_entry(entry: dict) -> VerificationRecord | None:
    text = entry.get("text") or ""
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None
    payload.pop("query_key", None)
    try:
        return VerificationRecord.model_validate(payload)
    except Exception:  # noqa: BLE001
        return None


async def _search_entries(pc, settings: Settings, query: str) -> list[dict]:
    """在已打开的 PowerContextClient 上搜索当前 scope 的 Memory 条目。"""
    from powercontext.http import SearchMemoryRequest  # noqa: PLC0415

    log = PowerContextLog(settings.powercontext_log)
    key = settings.project_key

    from powercontext.http import CreateScopeRequest, ScopeQueryField  # noqa: PLC0415

    page = await pc.list_scopes(query=f"sddctx:{key}", query_field=ScopeQueryField.TITLE, limit=10)
    scope_id = next(
        (descriptor.scope_id for descriptor in page.items if descriptor.title == f"sddctx:{key}"),
        None,
    )
    if scope_id is None:
        created = await pc.create_scope(
            CreateScopeRequest(
                title=f"sddctx:{key}",
                summary=f"SDD 上下文管理系统的任务状态范围({key})",
                idempotency_key=f"sddctx-{key}",
            )
        )
        scope_id = created.scope_id
        log.write("scope.create", {"scope_id": scope_id})
    response = await pc.search_memory(SearchMemoryRequest(scope_id=scope_id, query=query, limit=10))
    entries = [_entry_to_dict(hit) for hit in response.hits]
    log.write("memory.search", {"scope_id": scope_id, "query": query, "hit_count": len(entries)})
    return entries


async def load_board(settings: Settings, task_id: str | None) -> TaskBoard | None:
    """供 context_builder 复用的异步入口(在事件循环内 await 调用)。"""
    from powercontext.client import PowerContextClient  # noqa: PLC0415

    query = f"{_BOARD_QUERY_PREFIX} {task_id}" if task_id else _BOARD_QUERY_PREFIX
    async with PowerContextClient(
        settings.powercontext_url, token=settings.powercontext_token, timeout=30.0
    ) as pc:
        entries = await _search_entries(pc, settings, query)
    boards = [parsed for entry in entries if (parsed := _parse_board_entry(entry)) is not None]
    if not boards:
        return None
    if task_id:
        boards = [board for board in boards if board.task_id == task_id] or boards
    boards.sort(key=lambda board: board.updated_at, reverse=True)
    return boards[0]


__all__ = [
    "TaskBoard",
    "TaskStateClient",
    "TaskStateError",
    "VerificationRecord",
    "load_board",
]
