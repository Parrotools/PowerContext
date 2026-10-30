# Copyright (c) 2026 OceanBase.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Pi coding-agent session branch capture with durable incremental history."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import ClassVar
from urllib.parse import quote

from pydantic import BaseModel, JsonValue

from powercontext.limits import MAX_SOURCE_ID_LENGTH
from powercontext.sources import (
    TEXT_EVIDENCE_PROJECTION_KEY,
    AdapterSourceDefinition,
    TextEvidence,
)
from powercontext.sources.connectors import (
    ConnectorRunCompletion,
    ConnectorRunSession,
    ConnectorRunStatus,
)
from powercontext.sources.models import Source, SourceMaterialization

PI_EVENT_SOURCE_NAME = "pi-event"
PI_SESSION_CONNECTOR_NAME = "pi-session-history"
_UTF8_BOM = "\ufeff"
_CHECKPOINT_VERSION = 1


class PiSessionInput(BaseModel):
    """Raw Pi v3 session JSONL bytes with an optional explicit leaf node."""

    content: bytes
    leaf_id: str | None = None


class PiEventInput(BaseModel):
    """One visible session event on the selected branch, root to leaf."""

    session_id: str
    event_id: str
    parent_id: str | None
    event_type: str
    role: str
    content: str
    record: dict[str, JsonValue]


class PiEventSource(Source):
    """A captured Pi session event whose identity is session plus event ID."""

    source_id: str
    session_id: str
    event_id: str
    parent_id: str | None
    event_type: str
    role: str
    content: str
    record: dict[str, JsonValue]


def pi_event_source_id(session_id: str, event_id: str, /) -> str:
    """Build the collision-free event identity from its immutable components."""

    identity = f"pi:{quote(session_id, safe='')}:{quote(event_id, safe='')}"
    if len(identity) > MAX_SOURCE_ID_LENGTH:
        message = f"pi event source_id must not exceed {MAX_SOURCE_ID_LENGTH} characters"
        raise ValueError(message)
    return identity


def _decode_lines(content: bytes, /) -> list[dict[str, JsonValue]]:
    try:
        text = content.decode("utf-8")
    except UnicodeDecodeError as error:
        message = "session content must be valid UTF-8"
        raise ValueError(message) from error
    if text.startswith(_UTF8_BOM):
        text = text.removeprefix(_UTF8_BOM)
    records: list[dict[str, JsonValue]] = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError as error:
            message = f"session line is not valid JSON: {error.msg}"
            raise ValueError(message) from error
        if not isinstance(record, dict):
            message = "session records must be JSON objects"
            raise ValueError(message)  # noqa: TRY004 - invalid serialized data
        records.append(record)
    if not records:
        message = "session content must contain a session header"
        raise ValueError(message)
    return records


def _node_parent(record: dict[str, JsonValue], /) -> str | None:
    if "parentId" not in record:
        message = "every session node must carry parentId"
        raise ValueError(message)
    parent_id = record.get("parentId")
    if parent_id is None or parent_id == "":
        return None
    if not isinstance(parent_id, str):
        message = "parentId must be a string or null"
        raise ValueError(message)  # noqa: TRY004 - invalid serialized data
    return parent_id


def _load_graph(records: list[dict[str, JsonValue]], /) -> tuple[str, dict[str, dict[str, JsonValue]], list[str]]:
    """Validate the session header and node graph without selecting a branch."""

    header = records[0]
    if header.get("type") != "session" or header.get("version") != 3:
        message = "first session record must declare type=session and version=3"
        raise ValueError(message)
    session_id = header.get("id")
    if not isinstance(session_id, str) or not session_id:
        message = "session header must carry a non-empty string id"
        raise ValueError(message)

    nodes: dict[str, dict[str, JsonValue]] = {}
    order: list[str] = []
    for record in records[1:]:
        node_id = record.get("id")
        if not isinstance(node_id, str) or not node_id:
            message = "every session node must carry a non-empty string id"
            raise ValueError(message)
        if node_id in nodes:
            message = f"session node id {node_id!r} appears more than once"
            raise ValueError(message)
        parent_id = _node_parent(record)
        if parent_id is not None and parent_id not in nodes:
            message = f"session node {node_id!r} references unseen parent {parent_id!r}"
            raise ValueError(message)
        nodes[node_id] = record
        order.append(node_id)
    return session_id, nodes, order


def _visible_body(content: JsonValue, /) -> str:
    """Join visible text blocks and tool calls; thinking and image stay out."""

    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for block in content:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type")
        if block_type == "text" and isinstance(block.get("text"), str):
            parts.append(block["text"])
        elif block_type == "toolCall":
            name = block.get("name")
            call_id = block.get("id")
            arguments = block.get("arguments")
            if arguments is None:
                arguments = {}
            serialized = json.dumps(arguments, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            parts.append(f"[tool_call {name} {call_id}] {serialized}")
    return "\n".join(parts)


def _tool_result_text(content: JsonValue, /) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "\n".join(
        block["text"]
        for block in content
        if isinstance(block, dict) and block.get("type") == "text" and isinstance(block.get("text"), str)
    )


def _event_role_body(
    event_type: str,
    record: dict[str, JsonValue],
    /,
) -> tuple[str, str] | None:
    """Return the visible (role, body) for one node, or None when invisible."""

    if event_type == "message":
        return _message_role_body(record)
    if event_type in ("compaction", "branch_summary"):
        summary = record.get("summary")
        if not isinstance(summary, str) or not summary:
            return None
        return event_type, summary
    if event_type == "custom_message":
        body = _visible_body(record.get("content"))
        if not body:
            return None
        return "custom", body
    return None


def _message_role_body(record: dict[str, JsonValue], /) -> tuple[str, str] | None:
    message = record.get("message")
    if not isinstance(message, dict):
        return None
    role = message.get("role")
    if not isinstance(role, str) or not role:
        return None
    if role == "toolResult":
        body = (
            f"[tool_result {message.get('toolName')} {message.get('toolCallId')}] "
            f"{_tool_result_text(message.get('content'))}"
        )
        return role, body
    if role == "bashExecution":
        command = message.get("command")
        output = message.get("output")
        body = f"$ {command if isinstance(command, str) else ''}\n{output if isinstance(output, str) else ''}"
        return role, body
    body = _visible_body(message.get("content"))
    if not body:
        return None
    return role, body


def parse_pi_session(value: PiSessionInput, /) -> tuple[PiEventInput, ...]:
    """Parse and validate the whole file, then emit the selected branch root to leaf."""

    records = _decode_lines(value.content)
    session_id, nodes, order = _load_graph(records)
    leaf_id = value.leaf_id if value.leaf_id is not None else (order[-1] if order else None)
    if leaf_id is None or leaf_id not in nodes:
        message = "selected leaf node does not exist in the session"
        raise ValueError(message)

    path: list[str] = []
    cursor: str | None = leaf_id
    while cursor is not None:
        path.append(cursor)
        cursor = _node_parent(nodes[cursor])
    path.reverse()

    events: list[PiEventInput] = []
    for node_id in path:
        record = nodes[node_id]
        event_type = record.get("type")
        if not isinstance(event_type, str):
            continue
        role_body = _event_role_body(event_type, record)
        if role_body is None:
            continue
        role, body = role_body
        events.append(
            PiEventInput(
                session_id=session_id,
                event_id=node_id,
                parent_id=_node_parent(record),
                event_type=event_type,
                role=role,
                content=f"{role}: {body}",
                record=record,
            )
        )
    return tuple(events)


class PiEventSourceAdapter:
    """Resolve and read one immutable Pi session event Source."""

    input_class = PiEventInput
    name = PI_EVENT_SOURCE_NAME
    source_class = PiEventSource

    async def resolve(self, value: PiEventInput, /) -> PiEventSource:
        source_id = pi_event_source_id(value.session_id, value.event_id)
        return PiEventSource(
            name=source_id,
            materialization=SourceMaterialization.CAPTURED,
            source_id=source_id,
            session_id=value.session_id,
            event_id=value.event_id,
            parent_id=value.parent_id,
            event_type=value.event_type,
            role=value.role,
            content=value.content,
            record=value.record,
        )

    async def read(self, source: PiEventSource, /) -> PiEventInput:
        return PiEventInput(
            session_id=source.session_id,
            event_id=source.event_id,
            parent_id=source.parent_id,
            event_type=source.event_type,
            role=source.role,
            content=source.content,
            record=source.record,
        )


class PiEventTextEvidenceProjection:
    """Project one event as exact textual evidence with its identity metadata."""

    name = TEXT_EVIDENCE_PROJECTION_KEY.name
    version = TEXT_EVIDENCE_PROJECTION_KEY.version
    source_class = PiEventSource
    output_class: ClassVar[type[BaseModel]] = TextEvidence

    def project(self, source: PiEventSource, /) -> TextEvidence:
        return TextEvidence(
            source_type=PI_EVENT_SOURCE_NAME,
            source_id=source.source_id,
            content=source.content,
            metadata={
                "session_id": source.session_id,
                "event_id": source.event_id,
                "parent_id": source.parent_id,
                "event_type": source.event_type,
                "role": source.role,
            },
        )


PI_EVENT_SOURCE_DEFINITION = AdapterSourceDefinition(
    PiEventSourceAdapter(),
    version="1",
    projections=(PiEventTextEvidenceProjection(),),
)


def _record_digest(record: dict[str, JsonValue], /) -> str:
    encoded = json.dumps(record, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


class PiSessionConnector:
    """Incrementally capture one session file's selected branch through a binding."""

    name = PI_SESSION_CONNECTOR_NAME
    version = "1"
    source_definitions = frozenset({PI_EVENT_SOURCE_NAME})

    def __init__(self, path: Path | str, leaf_id: str | None = None, /) -> None:
        self._path = Path(path)
        self._leaf_id = leaf_id

    async def run(self, session: ConnectorRunSession, /) -> ConnectorRunCompletion:
        raw = self._path.read_bytes()
        records = _decode_lines(raw)
        session_id, _nodes, _order = _load_graph(records)
        events = parse_pi_session(PiSessionInput(content=raw, leaf_id=self._leaf_id))

        imported = _decode_checkpoint(session.checkpoint, session_id)
        for record in records[1:]:
            node_id = record.get("id")
            if isinstance(node_id, str) and node_id in imported and imported[node_id] != _record_digest(record):
                message = f"imported session event {node_id!r} was rewritten"
                raise ValueError(message)

        for event in events:
            if event.event_id in imported:
                continue
            await session.submit(event.event_id, PI_EVENT_SOURCE_NAME, event)
            imported[event.event_id] = _record_digest(event.record)
        checkpoint = {
            "version": _CHECKPOINT_VERSION,
            "session_id": session_id,
            "events": imported,
        }
        return ConnectorRunCompletion(status=ConnectorRunStatus.COMPLETE, checkpoint=checkpoint)


def _decode_checkpoint(checkpoint: object, session_id: str, /) -> dict[str, str]:
    if checkpoint is None:
        return {}
    if (
        not isinstance(checkpoint, dict)
        or type(checkpoint.get("version")) is not int
        or checkpoint.get("version") != _CHECKPOINT_VERSION
    ):
        message = "invalid or unsupported session checkpoint"
        raise ValueError(message)
    if checkpoint.get("session_id") != session_id:
        message = "checkpoint session does not match session file"
        raise ValueError(message)
    events = checkpoint.get("events")
    if not isinstance(events, dict) or any(
        not isinstance(key, str)
        or not key
        or not isinstance(value, str)
        or len(value) != 64
        or any(char not in "0123456789abcdef" for char in value)
        for key, value in events.items()
    ):
        message = "invalid session checkpoint event digests"
        raise ValueError(message)
    return {str(key): str(value) for key, value in events.items()}


__all__ = [
    "PI_EVENT_SOURCE_DEFINITION",
    "PiEventInput",
    "PiEventSource",
    "PiSessionConnector",
    "PiSessionInput",
    "parse_pi_session",
    "pi_event_source_id",
]
