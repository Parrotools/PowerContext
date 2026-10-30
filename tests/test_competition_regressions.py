import json
from typing import cast

import pytest

from powercontext.builtin.runtime.context_pack import ContextPack, ContextPackDelta, ContextPackError
from powercontext.sources import ConnectorRunSession
from powercontext.sources.pi_session import PiSessionConnector, PiSessionInput, parse_pi_session


def test_pi_requires_explicit_parent():
    data = b'{"type":"session","version":3,"id":"s"}\n{"id":"a","type":"message"}\n'
    with pytest.raises(ValueError, match="parentId"):
        parse_pi_session(PiSessionInput(content=data))


@pytest.mark.anyio
@pytest.mark.parametrize(
    "checkpoint",
    [
        {"version": 1, "session_id": "other", "events": {}},
        {"version": 1, "session_id": "s", "events": {"a": "bad"}},
        {"version": 2, "session_id": "s", "events": {}},
    ],
)
async def test_pi_rejects_bad_checkpoint_before_submission(tmp_path, checkpoint):
    path = tmp_path / "session.jsonl"
    path.write_text(
        '{"type":"session","version":3,"id":"s"}\n'
        '{"id":"a","parentId":null,"type":"message",'
        '"message":{"role":"user","content":"hello"}}\n'
    )

    class Session:
        def __init__(self):
            self.checkpoint = checkpoint

        async def submit(self, *args):
            pytest.fail("invalid checkpoint submitted an event")

    session = Session()
    with pytest.raises(ValueError, match="checkpoint"):
        await PiSessionConnector(path).run(cast(ConnectorRunSession, session))


def test_pack_and_delta_reject_invalid_wire_encodings():
    pack = ContextPack.build((b"a",))
    assert ContextPack.from_bytes(pack.to_bytes()) == pack
    delta = ContextPackDelta.between(pack, ContextPack.build((b"a", b"b")))
    assert ContextPackDelta.from_bytes(delta.to_bytes()) == delta
    for wire, cls in [(pack.to_bytes(), ContextPack), (delta.to_bytes(), ContextPackDelta)]:
        with pytest.raises(ContextPackError):
            cls.from_bytes(wire.decode().encode("utf-16"))
    payload = json.loads(delta.to_bytes())
    payload["appended"] = ["YR=="]
    with pytest.raises(ContextPackError, match="base64"):
        ContextPackDelta.from_bytes(json.dumps(payload).encode())
    payload["appended"] = []
    payload["base_digest"] = "sha256:+" + "0" * 63
    with pytest.raises(ContextPackError, match="digest"):
        ContextPackDelta.from_bytes(json.dumps(payload).encode())


@pytest.mark.anyio
async def test_pdf_neighbors_stay_within_document_revision():
    from types import SimpleNamespace

    from powercontext.artifacts import ArtifactRef
    from powercontext.sources import SourceRef
    from powercontext.sources.pdf_pages import pdf_page_source_id, search_pdf_pages

    ref = ArtifactRef(family="memory", artifact_id="m", revision=1)

    def record(sha, page, text):
        entry = SimpleNamespace(
            entry_id=f"{sha[0]}{page}",
            entry_version_id="v",
            text=f"doc\n{text}",
            sources=(SourceRef(source_type="pdf-page", source_id=pdf_page_source_id("doc", sha, page)),),
        )
        return SimpleNamespace(entry=entry, memory_ref=ref, state="active")

    records = [
        record("a" * 64, 1, "unicorn revenue unicorn"),
        record("a" * 64, 2, "neighbor"),
        record("b" * 64, 2, "other revision"),
    ]

    class Memory:
        async def list(self):
            return SimpleNamespace(entries=records)

    found = await search_pdf_pages(Memory(), "unicorn revenue", limit=2)
    assert [citation.entry_id for citation in found] == ["a1", "a2"]


@pytest.mark.anyio
async def test_lifecycle_registration_retry_reconciles_and_preserves_citation(monkeypatch):
    from powercontext.artifacts import ArtifactRef
    from powercontext.builtin.artifacts.memory import MemoryEntryInput
    from powercontext.builtin.persistence.sqlite import SQLiteConfig
    from powercontext.builtin.runtime import BuiltinConfig, CaptureSource, RememberMemoryRequest, open_builtin_runtime
    from powercontext.builtin.runtime.source_lifecycle import SourceLifecycleError, SourceLifecycleEvent
    from powercontext.builtin.scope import ScopeDraft

    async with open_builtin_runtime(BuiltinConfig(database=SQLiteConfig())) as runtime:
        assert runtime.scopes is not None
        scope = await runtime.scopes.create(ScopeDraft(title="test", summary="test", idempotency_key="test"))
        lifecycle = runtime.lifecycle.for_scope(scope.scope_id)
        receipt = await runtime.sources.for_scope(scope.scope_id).capture(
            CaptureSource(source_id="root", content="root", metadata={})
        )
        await lifecycle.register_source("root", receipt.source_ref, revision=1)
        await lifecycle.apply(
            SourceLifecycleEvent(node_id="root", revision=1, sequence=1, available=False, reason="off")
        )
        created = await runtime.memory.for_scope(scope.scope_id).remember(
            RememberMemoryRequest(entries=(MemoryEntryInput(kind="fact", text="fact"),))
        )
        assert created.entry is not None
        citation = created.entry.citation
        original = lifecycle._reconcile

        async def fail(nodes):
            raise RuntimeError("interrupted")

        monkeypatch.setattr(lifecycle, "_reconcile", fail)
        with pytest.raises(RuntimeError, match="interrupted"):
            await lifecycle.register_memory("derived", citation, parents=("root",), policy="all")
        monkeypatch.setattr(lifecycle, "_reconcile", original)
        await lifecycle.register_memory("derived", citation, parents=("root",), policy="all")
        page = await runtime.memory.for_scope(scope.scope_id).list(include_inactive=True)
        assert page.entries[0].state != "active"
        revision = page.memory_ref
        await lifecycle.register_memory("derived", citation, parents=("root",), policy="all")
        assert (await runtime.memory.for_scope(scope.scope_id).list(include_inactive=True)).memory_ref == revision
        assert await lifecycle.resolve("derived", purpose="audit") == citation
        with pytest.raises(SourceLifecycleError, match="topic-memory"):
            await lifecycle.register_topic(
                "wrong", ArtifactRef(family="memory", artifact_id="m", revision=1), parents=("root",), policy="all"
            )


@pytest.mark.anyio
async def test_lifecycle_registers_captured_noncontent_source():
    from powercontext.builtin.persistence.sqlite import SQLiteConfig
    from powercontext.builtin.runtime import BuiltinConfig, SubmitSourceObservation, open_builtin_runtime
    from powercontext.builtin.scope import ScopeDraft
    from powercontext.sources import SourceDefinitionRegistry, manifest_for_definition, project_source_for_transport
    from powercontext.sources.csv_rows import CSV_ROW_SOURCE_DEFINITION, CSVDocumentInput, parse_csv_document

    rows = parse_csv_document(CSVDocumentInput(document_id="doc", primary_key="id", content=b"id,name\n1,A\n"))
    registry = SourceDefinitionRegistry((CSV_ROW_SOURCE_DEFINITION,))
    observation = project_source_for_transport(registry, await registry.resolve(rows[0]))
    async with open_builtin_runtime(BuiltinConfig(database=SQLiteConfig())) as runtime:
        assert runtime.scopes is not None
        scope = await runtime.scopes.create(ScopeDraft(title="test", summary="test", idempotency_key="csv"))
        await runtime.ingestion.register(manifest_for_definition(CSV_ROW_SOURCE_DEFINITION))
        receipt = await runtime.ingestion.submit(
            SubmitSourceObservation(scope_id=scope.scope_id, observation=observation)
        )
        lifecycle = runtime.lifecycle.for_scope(scope.scope_id)
        await lifecycle.register_source("csv", receipt.source_ref, revision=1)
        assert await lifecycle.resolve("csv", purpose="generation") == receipt.source_ref


@pytest.mark.anyio
async def test_lifecycle_event_replay_finishes_interrupted_graph_persistence(monkeypatch):
    from powercontext.builtin.artifacts.memory import MemoryEntryInput
    from powercontext.builtin.persistence.sqlite import SQLiteConfig
    from powercontext.builtin.runtime import BuiltinConfig, CaptureSource, RememberMemoryRequest, open_builtin_runtime
    from powercontext.builtin.runtime.source_lifecycle import SourceLifecycleError, SourceLifecycleEvent
    from powercontext.builtin.scope import ScopeDraft

    async with open_builtin_runtime(BuiltinConfig(database=SQLiteConfig())) as runtime:
        assert runtime.scopes is not None
        scope = await runtime.scopes.create(ScopeDraft(title="test", summary="test", idempotency_key="replay"))
        lifecycle = runtime.lifecycle.for_scope(scope.scope_id)
        source = await runtime.sources.for_scope(scope.scope_id).capture(
            CaptureSource(source_id="root", content="root", metadata={})
        )
        await lifecycle.register_source("root", source.source_ref, revision=1)
        created = await runtime.memory.for_scope(scope.scope_id).remember(
            RememberMemoryRequest(entries=(MemoryEntryInput(kind="fact", text="fact"),))
        )
        assert created.entry is not None
        citation = created.entry.citation
        await lifecycle.register_memory("child", citation, parents=("root",), policy="all")
        original = lifecycle._save_node

        async def fail_descendant(node_id, node):
            if node_id == "child":
                message = "interrupted descendant persistence"
                raise RuntimeError(message)
            await original(node_id, node)

        event = SourceLifecycleEvent(node_id="root", revision=1, sequence=1, available=False, reason="off")
        monkeypatch.setattr(lifecycle, "_save_node", fail_descendant)
        with pytest.raises(RuntimeError, match="interrupted descendant"):
            await lifecycle.apply(event)
        monkeypatch.setattr(lifecycle, "_save_node", original)
        await lifecycle.apply(event)
        with pytest.raises(SourceLifecycleError, match="not available"):
            await runtime.lifecycle.for_scope(scope.scope_id).resolve("child", purpose="generation")
        page = await runtime.memory.for_scope(scope.scope_id).list(include_inactive=True)
        assert page.entries[0].state != "active"
        await lifecycle.apply(event)
        assert (
            await runtime.memory.for_scope(scope.scope_id).list(include_inactive=True)
        ).memory_ref == page.memory_ref
        assert await lifecycle.resolve("child", purpose="audit") == citation
