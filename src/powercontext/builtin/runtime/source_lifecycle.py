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

"""Source withdrawal lifecycle propagation across Memory and Topic Memory."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select

from powercontext.artifacts import ArtifactRef
from powercontext.builtin.artifacts.memory.models import MemoryCitation
from powercontext.builtin.artifacts.topic_memory import TopicMemorySearchHit
from powercontext.builtin.persistence.tables import SOURCE_LIFECYCLE_NODES_TABLE
from powercontext.builtin.runtime.models import GetMemoryEntryRequest
from powercontext.sources import SourceMaterialization, SourceRef

_LIFECYCLE_PURPOSES = frozenset({"generation", "audit"})
_POLICIES = frozenset({"all", "any"})
_NODE_KINDS = frozenset({"source", "memory", "topic"})


class SourceLifecycleError(ValueError):
    """Raise for lifecycle registration, event, or resolution violations."""


class SourceLifecycleEvent(BaseModel):
    """One strict availability event for a registered lifecycle Source."""

    model_config = ConfigDict(extra="forbid")

    node_id: str
    reason: str
    revision: int = Field(strict=True, gt=0)
    sequence: int = Field(strict=True, gt=0)
    available: bool = Field(strict=True)

    @field_validator("node_id", "reason")
    @classmethod
    def _require_text(cls, value: str) -> str:
        if not value or not value.strip():
            message = "must be a non-empty string with content"
            raise ValueError(message)
        return value


@dataclass(slots=True)
class _LifecycleNode:
    kind: str
    reference: dict[str, object]
    parents: tuple[str, ...]
    policy: str
    revision: int
    sequence: int
    reason: str | None
    available: bool

    def document_bytes(self) -> bytes:
        import json as _json

        return _json.dumps(self.document(), sort_keys=True, separators=(",", ":")).encode("utf-8")

    def document(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "reference": self.reference,
            "parents": list(self.parents),
            "policy": self.policy,
            "revision": self.revision,
            "sequence": self.sequence,
            "reason": self.reason,
            "available": self.available,
        }

    @classmethod
    def from_document(cls, document: dict[str, Any], /) -> _LifecycleNode:
        return cls(
            kind=document["kind"],
            reference=document["reference"],
            parents=tuple(document["parents"]),
            policy=document["policy"],
            revision=int(document["revision"]),
            sequence=int(document["sequence"]),
            reason=document.get("reason"),
            available=bool(document["available"]),
        )


def _parse_reference(node: _LifecycleNode, /):
    if node.kind == "source":
        return SourceRef.model_validate(node.reference)
    if node.kind == "memory":
        return MemoryCitation.model_validate(node.reference)
    if node.kind == "topic":
        return ArtifactRef.model_validate(node.reference)
    message = f"unknown lifecycle node kind {node.kind!r}"
    raise SourceLifecycleError(message)


def _require_positive(value: object, name: str, /) -> int:
    if type(value) is not int or value < 1:
        message = f"{name} must be a positive integer"
        raise SourceLifecycleError(message)
    return value


def _require_node_name(value: str, name: str, /) -> str:
    if not isinstance(value, str) or not value.strip():
        message = f"{name} must be a non-empty string with content"
        raise SourceLifecycleError(message)
    return value


class SourceLifecycleService:
    """Propagate Source availability through the scope evidence DAG."""

    def __init__(self, runtime, scope_id: str, /) -> None:
        self._runtime = runtime
        self.scope_id = scope_id

    async def _database(self):
        async with self._runtime._context(self.scope_id) as context:
            return context.triggers._services.database

    async def _load_nodes(self) -> dict[str, _LifecycleNode]:
        database = await self._database()
        async with database.transaction() as connection:
            rows = await connection.execute(
                select(SOURCE_LIFECYCLE_NODES_TABLE.c.node_id, SOURCE_LIFECYCLE_NODES_TABLE.c.document).where(
                    SOURCE_LIFECYCLE_NODES_TABLE.c.scope_id == self.scope_id
                )
            )
            import json as _json

            return {
                node_id: _LifecycleNode.from_document(_json.loads(bytes(document).decode("utf-8")))
                for node_id, document in rows
            }

    async def _save_node(self, node_id: str, node: _LifecycleNode, /) -> None:
        database = await self._database()
        async with database.transaction() as connection:
            table = SOURCE_LIFECYCLE_NODES_TABLE
            existing = await connection.execute(
                select(table.c.scope_id).where(table.c.scope_id == self.scope_id, table.c.node_id == node_id)
            )
            values = {"kind": node.kind, "document": node.document_bytes()}
            if existing.first() is None:
                await connection.execute(table.insert().values(scope_id=self.scope_id, node_id=node_id, **values))
            else:
                await connection.execute(
                    table.update().where(table.c.scope_id == self.scope_id, table.c.node_id == node_id).values(**values)
                )

    async def register_source(self, node_id: str, source_ref: SourceRef, /, *, revision: int) -> None:
        """Register one evidence Source with its lifecycle revision."""

        _require_node_name(node_id, "node_id")
        _require_positive(revision, "revision")
        if not isinstance(source_ref, SourceRef):
            message = "source_ref must be a SourceRef"
            raise SourceLifecycleError(message)
        async with self._runtime._scope_operation(self.scope_id), self._runtime._locked(self.scope_id):
            nodes = await self._load_nodes()
            existing = nodes.get(node_id)
            if existing is not None:
                if (
                    existing.kind != "source"
                    or existing.reference != source_ref.model_dump(mode="json")
                    or existing.revision != revision
                ):
                    message = f"node {node_id!r} is already registered differently"
                    raise SourceLifecycleError(message)
                return
            async with self._runtime._context(self.scope_id) as context:
                services = context.triggers._services
                async with services.database.transaction() as connection:
                    stored = await services.repositories.sources.get(connection, self.scope_id, source_ref)
                if stored.value.materialization != SourceMaterialization.CAPTURED:
                    message = "source must be captured and readable"
                    raise SourceLifecycleError(message)
            nodes[node_id] = _LifecycleNode(
                kind="source",
                reference=source_ref.model_dump(mode="json"),
                parents=(),
                policy="all",
                revision=revision,
                sequence=0,
                reason=None,
                available=True,
            )
            await self._save_node(node_id, nodes[node_id])

    async def register_memory(self, node_id: str, citation: MemoryCitation, /, *, parents, policy) -> None:
        """Register one Memory entry whose availability follows its parents."""

        await self._register_derived(node_id, citation, MemoryCitation, "memory", parents, policy)

    async def register_topic(self, node_id: str, artifact_ref: ArtifactRef, /, *, parents, policy) -> None:
        """Register one Topic Memory whose availability follows its parents."""

        if not isinstance(artifact_ref, ArtifactRef) or artifact_ref.family != "topic-memory":
            message = "topic reference must belong to topic-memory"
            raise SourceLifecycleError(message)
        await self._register_derived(node_id, artifact_ref, ArtifactRef, "topic", parents, policy)

    async def _register_derived(
        self,
        node_id: str,
        reference,
        reference_class,
        kind: str,
        parents,
        policy: str,
        /,
    ) -> None:
        _require_node_name(node_id, "node_id")
        if policy not in _POLICIES:
            message = "policy must be 'all' or 'any'"
            raise SourceLifecycleError(message)
        parent_tuple = tuple(parents)
        if not parent_tuple:
            message = "derived nodes require at least one parent"
            raise SourceLifecycleError(message)
        if len(set(parent_tuple)) != len(parent_tuple):
            message = "parents must not repeat"
            raise SourceLifecycleError(message)
        if node_id in parent_tuple:
            message = "derived nodes cannot be their own parent"
            raise SourceLifecycleError(message)
        if not isinstance(reference, reference_class):
            message = f"reference must be a {reference_class.__name__}"
            raise SourceLifecycleError(message)
        async with self._runtime._scope_operation(self.scope_id), self._runtime._locked(self.scope_id):
            nodes = await self._load_nodes()
            existing = nodes.get(node_id)
            document = reference.model_dump(mode="json")
            if existing is not None:
                if (
                    existing.kind != kind
                    or existing.reference != document
                    or existing.parents != parent_tuple
                    or existing.policy != policy
                ):
                    message = f"node {node_id!r} is already registered differently"
                    raise SourceLifecycleError(message)
                await self._reconcile(nodes)
                return
            for parent in parent_tuple:
                if parent not in nodes:
                    message = f"parent node {parent!r} is not registered"
                    raise SourceLifecycleError(message)
            await self._verify_reference(kind, reference)
            support = [nodes[parent].available for parent in parent_tuple]
            available = all(support) if policy == "all" else any(support)
            node = _LifecycleNode(
                kind=kind,
                reference=document,
                parents=parent_tuple,
                policy=policy,
                revision=0,
                sequence=0,
                reason=None,
                available=available,
            )
            nodes[node_id] = node
            await self._save_node(node_id, node)
            await self._reconcile(nodes)

    async def _verify_reference(self, kind: str, reference, /) -> None:
        if kind == "memory":
            memory = self._runtime.memory.for_scope(self.scope_id)
            record = await memory.get(GetMemoryEntryRequest(citation=reference))
            if record.entry is None:
                message = "memory citation is not readable"
                raise SourceLifecycleError(message)
            return
        if kind == "topic":
            await self._runtime.records.for_scope(self.scope_id).get_artifact_revision(
                reference.family, reference.artifact_id, reference.revision
            )
            return
        message = f"unknown lifecycle node kind {kind!r}"
        raise SourceLifecycleError(message)

    async def apply(self, event: SourceLifecycleEvent, /) -> list[str]:
        """Apply one Source availability event and return every available node."""

        if not isinstance(event, SourceLifecycleEvent):
            message = "event must be a SourceLifecycleEvent"
            raise SourceLifecycleError(message)
        async with self._runtime._scope_operation(self.scope_id), self._runtime._locked(self.scope_id):
            nodes = await self._load_nodes()
            node = nodes.get(event.node_id)
            if node is None or node.kind != "source":
                message = f"source node {event.node_id!r} is not registered"
                raise SourceLifecycleError(message)
            if event.revision != node.revision:
                message = f"event revision {event.revision} does not match lifecycle revision {node.revision}"
                raise SourceLifecycleError(message)
            if event.sequence < node.sequence:
                message = "event sequence must not move backwards"
                raise SourceLifecycleError(message)
            replay = event.sequence == node.sequence
            if replay and (node.available != event.available or node.reason != event.reason):
                message = "an event with this sequence was already applied differently"
                raise SourceLifecycleError(message)
            if not replay:
                node.available = event.available
                node.sequence = event.sequence
                node.reason = event.reason
            _propagate(nodes)
            if not replay:
                await self._save_node(event.node_id, node)
            # A previous attempt may have persisted the Source event before a
            # descendant write failed. Replays must finish those writes too.
            for changed_id, changed in nodes.items():
                if changed.kind != "source":
                    await self._save_node(changed_id, changed)
            await self._reconcile(nodes)
        return sorted(node_id for node_id, node in nodes.items() if node.available)

    async def resolve(self, node_id: str, /, *, purpose: str):
        """Return the original node reference for one lifecycle purpose."""

        if purpose not in _LIFECYCLE_PURPOSES:
            message = "purpose must be 'generation' or 'audit'"
            raise SourceLifecycleError(message)
        _require_node_name(node_id, "node_id")
        async with self._runtime._scope_operation(self.scope_id):
            nodes = await self._load_nodes()
            node = nodes.get(node_id)
            if node is None:
                message = f"node {node_id!r} is not registered"
                raise SourceLifecycleError(message)
            if purpose == "generation" and not node.available:
                message = f"node {node_id!r} is not available for generation"
                raise SourceLifecycleError(message)
            return _parse_reference(node)

    async def _reconcile(self, nodes: dict[str, _LifecycleNode], /) -> None:
        """Drive native Memory states to the propagated availability."""

        memory_nodes = [node for node in nodes.values() if node.kind == "memory"]
        if not memory_nodes:
            return
        memory = self._runtime.memory.for_scope(self.scope_id)
        page = await memory.list(include_inactive=True)
        states = {record.entry.entry_id: record.state for record in page.entries}
        for node in memory_nodes:
            citation = _parse_reference(node)
            state = states.get(citation.entry_id)
            if state is None:
                message = "registered memory citation is no longer readable"
                raise SourceLifecycleError(message)
            if node.available and state != "active":
                await self._set_memory_state(node, True, node.reason or "source-lifecycle restore")
            elif not node.available and state == "active":
                await self._set_memory_state(node, False, node.reason or "source-lifecycle withdrawal")

    async def _set_memory_state(self, node: _LifecycleNode, available: bool, reason: str | None, /) -> None:
        from powercontext.builtin.statistics import ModelUsagePurpose

        citation = MemoryCitation.model_validate(node.reference)
        async with self._runtime._context(
            self.scope_id, embedding_purpose=ModelUsagePurpose.MEMORY_INDEXING
        ) as context:
            service = context.artifacts.memory
            current = await service.head(context.artifacts.memory_artifact_id)
            entry = next(
                (item for item in await service.entries(current) if item.entry_id == citation.entry_id),
                None,
            )
            if entry is None:
                message = "registered memory citation is no longer readable"
                raise SourceLifecycleError(message)
            if available:
                await service.reactivate(current, entries=(entry,), reason=reason)
            else:
                await service.forget(current, entries=(entry,), reason=reason)


def _propagate(nodes: dict[str, _LifecycleNode], /) -> None:
    """Recompute derived availability to a fixed point in registration-free order."""

    derived = [node for node in nodes.values() if node.kind != "source"]
    for _ in range(len(derived) + 1):
        changed = False
        for node in derived:
            support = [nodes[parent].available for parent in node.parents]
            value = all(support) if node.policy == "all" else any(support)
            if value != node.available:
                node.available = value
                changed = True
        if not changed:
            break


async def available_topic_hits(
    runtime, scope_id: str, hits: tuple[TopicMemorySearchHit, ...], /
) -> tuple[TopicMemorySearchHit, ...]:
    """Exclude withdrawn topics without loading storage for an empty result."""

    if not hits:
        return hits
    database = None
    async with runtime._context(scope_id) as context:
        database = context.triggers._services.database
    async with database.transaction() as connection:
        rows = await connection.execute(
            select(SOURCE_LIFECYCLE_NODES_TABLE.c.document).where(
                SOURCE_LIFECYCLE_NODES_TABLE.c.scope_id == scope_id,
                SOURCE_LIFECYCLE_NODES_TABLE.c.kind == "topic",
            )
        )
        import json as _json

        hidden = frozenset(
            parsed["reference"]["artifact_id"]
            for (document,) in rows
            for parsed in [_json.loads(bytes(document).decode("utf-8"))]
            if not bool(parsed.get("available", True))
        )
    return tuple(hit for hit in hits if hit.artifact_ref.artifact_id not in hidden)


class LifecycleApplication:
    """Select the scoped source-lifecycle service."""

    def __init__(self, runtime, /) -> None:
        self._runtime = runtime

    def for_scope(self, scope_id: str, /) -> SourceLifecycleService:
        return SourceLifecycleService(self._runtime, scope_id)


__all__ = ["LifecycleApplication", "SourceLifecycleError", "SourceLifecycleEvent", "SourceLifecycleService"]
