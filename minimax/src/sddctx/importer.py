"""导入命令:把规格、代码、测试资料写入 seekdb(内容变化自动升版本)。"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path

from sddctx.assets import ImportReport, collect_assets
from sddctx.config import Settings
from sddctx.seekdb_store import AssetStore, QueryTraceSink


@dataclass
class ImportResult:
    files_seen: int
    assets_upserted: int
    counts: dict[str, int]
    total_assets_in_db: int


async def _run_import(settings: Settings) -> tuple[ImportResult, ImportReport]:
    report = collect_assets(settings.home, settings.specs_dir, settings.sample_project_dir)
    sink = QueryTraceSink(settings.db_query_log)
    async with AssetStore(settings.seekdb_path, sink) as store:
        for asset in report.assets:
            await store.upsert_asset(
                kind=asset.kind,
                path=asset.path,
                content=asset.content,
                title=asset.title,
                symbol=asset.symbol,
                content_hash=asset.content_hash,
                extra_searchable=asset.extra_searchable,
            )
        total = await store.count()
    return ImportResult(
        files_seen=report.files_seen,
        assets_upserted=len(report.assets),
        counts=report.counts,
        total_assets_in_db=total,
    ), report


def run_import(settings: Settings) -> tuple[ImportResult, ImportReport]:
    return asyncio.run(_run_import(settings))


def format_import_result(result: ImportResult, db_log: Path) -> str:
    lines = [
        f"导入完成:扫描 {result.files_seen} 个文件,写入 {result.assets_upserted} 条资产。",
        "  分类: " + ", ".join(f"{kind}×{count}" for kind, count in sorted(result.counts.items())),
        f"  库内资产总数: {result.total_assets_in_db}",
        f"  导入/查询审计已追加到: {db_log}",
    ]
    return "\n".join(lines)
