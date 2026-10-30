"""seekdb 存储层集成测试:临时目录中的真实嵌入式 seekdb。

注意:嵌入式实例与连接池绑定创建它的事件循环,因此每个用例都在单次
asyncio.run 内完成 open → 操作 → close。
"""

import asyncio

import pytest

from sddctx.seekdb_store import AssetStore, QueryTraceSink


def run_with_store(tmp_path, scenario):
    """在单事件循环内打开临时 AssetStore,执行 scenario(store) 后关闭。"""

    async def _main():
        store = AssetStore(tmp_path / "seekdb", QueryTraceSink(None))
        await store.open()
        try:
            return await scenario(store)
        finally:
            await store.close()

    return asyncio.run(_main())


def test_upsert_and_search_cjk(tmp_path):
    async def scenario(store):
        await store.upsert_asset(
            kind="spec_entry",
            path="specs/SPEC-003-订单查询规格.md#SPEC-003-1",
            content="订单查询接口 customer_orders 支持最小金额筛选参数 min_total(Decimal 类型)。",
            title="SPEC-003-1",
            symbol="SPEC-003-1",
            content_hash="h1",
        )
        await store.upsert_asset(
            kind="spec_entry",
            path="specs/SPEC-002-折扣规则.md#SPEC-002-1",
            content="折扣百分比必须在 0 到 50 之间,超出范围抛出 ValueError。",
            title="SPEC-002-1",
            symbol="SPEC-002-1",
            content_hash="h2",
        )
        return await store.search("订单查询 最小金额 筛选", kinds=("spec_entry",), limit=5)

    hits = run_with_store(tmp_path, scenario)
    assert hits, "CJK 全文检索应有命中"
    assert hits[0].asset.symbol == "SPEC-003-1"  # 相关性排序命中目标条目


def test_version_bumps_on_content_change_only(tmp_path):
    async def scenario(store):
        first = await store.upsert_asset(
            kind="spec_entry", path="specs/a.md#E-1", content="版本一",
            title="E-1", symbol="E-1", content_hash="hash-v1",
        )
        second = await store.upsert_asset(
            kind="spec_entry", path="specs/a.md#E-1", content="版本一",
            title="E-1", symbol="E-1", content_hash="hash-v1",
        )
        third = await store.upsert_asset(
            kind="spec_entry", path="specs/a.md#E-1", content="版本二",
            title="E-1", symbol="E-1", content_hash="hash-v2",
        )
        return first.version, second.version, third.version

    v1, v2, v3 = run_with_store(tmp_path, scenario)
    assert (v1, v2, v3) == (1, 1, 2)  # 未变化不升版本,变化才升


def test_kind_filter(tmp_path):
    async def scenario(store):
        await store.upsert_asset(kind="spec_entry", path="specs/a.md#E-1", content="订单查询 参数",
                                 title="E-1", symbol="E-1", content_hash="h1")
        await store.upsert_asset(kind="code", path="src/checkout/repository.py", content="订单查询 for_customer",
                                 title=None, symbol=None, content_hash="h2")
        spec_hits = await store.search("订单查询", kinds=("spec_entry",), limit=5)
        code_hits = await store.search("订单查询", kinds=("code",), limit=5)
        return spec_hits, code_hits

    spec_hits, code_hits = run_with_store(tmp_path, scenario)
    assert {hit.asset.kind for hit in spec_hits} == {"spec_entry"}
    assert {hit.asset.kind for hit in code_hits} == {"code"}


def test_search_traces_recorded(tmp_path):
    async def scenario():
        sink = QueryTraceSink(tmp_path / "log.md")
        async with AssetStore(tmp_path / "seekdb", sink) as store:
            await store.upsert_asset(kind="spec_entry", path="specs/a.md#E-1", content="订单查询 参数",
                                     title="E-1", symbol="E-1", content_hash="h1")
            await store.search("订单查询", kinds=("spec_entry",), limit=5)
        return sink.traces

    traces = asyncio.run(scenario())
    assert any(trace.purpose.startswith("upsert") for trace in traces)
    assert any(trace.purpose == "context-selection" for trace in traces)
    log_text = (tmp_path / "log.md").read_text(encoding="utf-8")
    assert "seekdb 查询记录" in log_text
