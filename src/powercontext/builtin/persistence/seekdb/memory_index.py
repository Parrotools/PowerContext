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

"""seekdb single-statement hybrid candidate retrieval over both native indexes."""

from __future__ import annotations

from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection
from sqlalchemy.sql import bindparam

from powercontext.artifacts import ArtifactRef
from powercontext.builtin.artifacts.memory import (
    CapabilityNotSupportedError,
    EmbeddingProfile,
    MemoryChannelHit,
    MemoryProjection,
    MemorySearchChannels,
    MemorySearchRequest,
)
from powercontext.builtin.artifacts.memory.canonical import validate_embedding
from powercontext.builtin.persistence.memory_index import memory_channel_hits
from powercontext.builtin.persistence.oceanbase.memory_index import (
    OceanBaseMemoryFTSIndex,
    OceanBaseMemoryVectorIndex,
)
from powercontext.builtin.persistence.tags import memory_tag_parameters, memory_tag_sql

_SEEKDB_HYBRID_SEARCH_SQL = """
SELECT * FROM (
    SELECT 'fts' AS channel,
           h.memory_artifact_id,
           h.head_revision,
           h.entry_id,
           h.entry_version_id,
           v.text,
           NULL AS distance
    FROM pc_memory_entry_heads AS h
    JOIN pc_memory_entry_versions AS v
      ON v.scope_id = h.scope_id
     AND v.memory_artifact_id = h.memory_artifact_id
     AND v.entry_version_id = h.entry_version_id
    WHERE h.scope_id = :scope_id
      AND h.memory_artifact_id IN :memory_artifact_ids
      AND MATCH(h.searchable_text) AGAINST(:analyzed_query){tag_h}
    ORDER BY MATCH(h.searchable_text) AGAINST(:analyzed_query) DESC,
             h.memory_artifact_id,
             h.entry_id,
             h.entry_version_id
    LIMIT :candidate_limit
) fts_channel
UNION ALL
SELECT * FROM (
    SELECT 'vector' AS channel,
           m.memory_artifact_id,
           m.head_revision,
           m.entry_id,
           m.entry_version_id,
           v.text,
           l2_distance(m.embedding, :query_vector) AS distance
    FROM pc_memory_vector_entries AS m
    JOIN pc_memory_entry_versions AS v
      ON v.scope_id = m.scope_id
     AND v.memory_artifact_id = m.memory_artifact_id
     AND v.entry_version_id = m.entry_version_id
    WHERE m.scope_id = :scope_id
      AND m.memory_artifact_id IN :memory_artifact_ids{tag_m}
    ORDER BY l2_distance(m.embedding, :query_vector) APPROXIMATE
    LIMIT :candidate_limit
) vector_channel
"""


class SeekDBMemoryIndex:
    """One candidate statement for hybrid mode; single channels stay native."""

    def __init__(self, fts_index: OceanBaseMemoryFTSIndex, vector_index: OceanBaseMemoryVectorIndex, /) -> None:
        self._fts = fts_index
        self._vector = vector_index
        self.profile: EmbeddingProfile = vector_index.profile
        self.capabilities = vector_index.capabilities.model_copy(update={"fts": True, "hybrid": True})
        self.tables = (*fts_index.tables, *vector_index.tables)
        self._hybrid_sql = text(_SEEKDB_HYBRID_SEARCH_SQL.replace("{tag_h}", "").replace("{tag_m}", "")).bindparams(
            bindparam("memory_artifact_ids", expanding=True),
            bindparam("query_vector", type_=vector_index.table.c.embedding.type),
        )
        self._tagged_hybrid_sql = text(
            _SEEKDB_HYBRID_SEARCH_SQL.replace("{tag_h}", memory_tag_sql("h")).replace("{tag_m}", memory_tag_sql("m"))
        ).bindparams(
            bindparam("memory_artifact_ids", expanding=True),
            bindparam("tag_keys", expanding=True),
            bindparam("tag_hashes", expanding=True),
            bindparam("query_vector", type_=vector_index.table.c.embedding.type),
        )

    async def initialize(self, connection: AsyncConnection, /) -> None:
        await self._fts.initialize(connection)
        await self._vector.initialize(connection)

    async def replace(
        self,
        connection: AsyncConnection,
        scope_id: str,
        memory_ref: ArtifactRef,
        projections: tuple[MemoryProjection, ...],
        /,
    ) -> None:
        await self._fts.replace(connection, scope_id, memory_ref, projections)
        await self._vector.replace(connection, scope_id, memory_ref, projections)

    async def delete(
        self,
        connection: AsyncConnection,
        scope_id: str,
        memory_ref: ArtifactRef,
        entry_ids: tuple[str, ...],
        /,
    ) -> None:
        await self._fts.delete(connection, scope_id, memory_ref, entry_ids)
        await self._vector.delete(connection, scope_id, memory_ref, entry_ids)

    async def upsert(
        self,
        connection: AsyncConnection,
        scope_id: str,
        memory_ref: ArtifactRef,
        projections: tuple[MemoryProjection, ...],
        /,
    ) -> None:
        await self._fts.upsert(connection, scope_id, memory_ref, projections)
        await self._vector.upsert(connection, scope_id, memory_ref, projections)

    async def search(
        self,
        connection: AsyncConnection,
        scope_id: str,
        request: MemorySearchRequest,
        /,
    ) -> MemorySearchChannels:
        if request.mode != "hybrid":
            fts_channels = await self._fts.search(connection, scope_id, request)
            vector_channels = await self._vector.search(connection, scope_id, request)
            return MemorySearchChannels(fts=fts_channels.fts, vector=vector_channels.vector)
        if request.embedding_profile != self.profile or request.query_vector is None:
            raise CapabilityNotSupportedError("embedding-profile")
        if not await self._vector.vector_complete(connection, scope_id, request.memories, self.profile):
            raise CapabilityNotSupportedError("vector")
        tagged = request.tag_filter is not None
        statement = self._tagged_hybrid_sql if tagged else self._hybrid_sql
        parameters: dict[str, Any] = {
            "scope_id": scope_id,
            "memory_artifact_ids": tuple(memory.artifact_id for memory in request.memories),
            "analyzed_query": request.analyzed_query,
            "query_vector": validate_embedding(
                request.query_vector,
                dimension=self.profile.dimension,
            ),
            "candidate_limit": request.candidate_limit,
            **memory_tag_parameters(request.tag_filter),
        }
        rows = (await connection.execute(statement, parameters)).mappings()
        fts: tuple[MemoryChannelHit, ...] = ()
        vector: tuple[MemoryChannelHit, ...] = ()
        for row in rows:
            channel = str(row["channel"])
            if channel == "fts":
                fts += memory_channel_hits([row], request.memories)
            else:
                vector += memory_channel_hits([row], request.memories)
        return MemorySearchChannels(fts=fts, vector=vector)

    async def vector_complete(
        self,
        connection: AsyncConnection,
        scope_id: str,
        memories: tuple[ArtifactRef, ...],
        profile: EmbeddingProfile,
        /,
    ) -> bool:
        return await self._vector.vector_complete(connection, scope_id, memories, profile)

    async def hydrate(
        self,
        connection: AsyncConnection,
        scope_id: str,
        projections: tuple[MemoryProjection, ...],
        /,
    ) -> tuple[MemoryProjection, ...]:
        return await self._vector.hydrate(connection, scope_id, projections)


__all__ = ["SeekDBMemoryIndex"]
