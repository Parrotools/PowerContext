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

"""Native query-plan regression for filtered hybrid retrieval."""

from __future__ import annotations

from contextlib import contextmanager

import pytest
from sqlalchemy import Engine, event

from powercontext.builtin.artifacts.memory import EmbeddingProfile, MemoryEntryInput
from powercontext.builtin.inference import EmbeddingResult
from powercontext.builtin.persistence.seekdb import SeekDBConfig
from powercontext.builtin.runtime import BuiltinConfig, open_builtin_contexts
from powercontext.builtin.tags import MemoryEntryTagTarget, TagFilter

pytest.importorskip("pylibseekdb")


class _Embedding:
    profile = EmbeddingProfile(
        profile_id="hybrid-tag-regression",
        model="deterministic",
        dimension=3,
        distance="l2",
        normalization="unit",
    )

    async def embed(self, texts: tuple[str, ...], /) -> EmbeddingResult:
        return EmbeddingResult(vectors=tuple((1.0, 0.0, 0.0) for _ in texts))


@contextmanager
def _candidate_statements():
    statements = []

    def record(_connection, _cursor, statement, parameters, _context, _executemany):
        if "AGAINST" in statement.upper() and "l2_distance" in statement.lower():
            statements.append((statement, parameters))

    event.listen(Engine, "before_cursor_execute", record)
    try:
        yield statements
    finally:
        event.remove(Engine, "before_cursor_execute", record)


@pytest.mark.anyio
async def test_tagged_hybrid_preserves_both_native_indexes(tmp_path):
    async with open_builtin_contexts(
        BuiltinConfig(database=SeekDBConfig(path=tmp_path / "db")),
        embedding_model=_Embedding(),
    ) as contexts:
        memory = (await contexts.get("tagged-hybrid")).artifacts.memory
        head = await memory.remember(
            memory=None,
            entries=(
                MemoryEntryInput(kind="fact", text="Alpha selected evidence."),
                MemoryEntryInput(kind="fact", text="Alpha excluded evidence."),
            ),
            mode="append",
        )
        assert head is not None
        selected = next(entry for entry in await memory.entries(head) if "selected" in entry.text)
        target = MemoryEntryTagTarget(artifact_id=head.artifact_id, entry_id=selected.entry_id)
        empty = await contexts.records.get_tags("tagged-hybrid", target)
        await contexts.records.replace_tags("tagged-hybrid", target, ("selected", "verified"), expected_etag=empty.etag)
        for match in ("any", "all"):
            with _candidate_statements() as statements:
                result = await memory.search(
                    "alpha",
                    memories=(head,),
                    mode="hybrid",
                    limit=1,
                    tag_filter=TagFilter(tags=("selected", "verified"), match=match),
                )
            assert [hit.entry_id for hit in result.hits] == [selected.entry_id]
            assert len(statements) == 1
            statement, parameters = statements[0]
            async with contexts.database.transaction() as connection:
                rows = await connection.exec_driver_sql(f"EXPLAIN {statement}", parameters)
                plan = "\n".join(str(row[0]) for row in rows)
            assert "TEXT RETRIEVAL SCAN" in plan
            assert "VECTOR INDEX" in plan
