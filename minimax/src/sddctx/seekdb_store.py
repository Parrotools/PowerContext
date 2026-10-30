"""嵌入式 seekdb 存储层:工程资料(规格/代码/测试)的唯一持久化与检索入口。

seekdb 以进程内嵌入实例运行(pylibseekdb),通过 SQLAlchemy 异步引擎以
MySQL 兼容方言访问;全文检索使用 seekdb 原生 FULLTEXT 索引
(MATCH ... AGAINST),中文按 Analyzer v1 预分词后入库。
"""

from __future__ import annotations

import contextlib
import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from pyobvector import AsyncOceanBaseDialect
from sqlalchemy import Table, Column, String, Integer, Text, MetaData, text
from sqlalchemy.dialects import registry as dialect_registry
from sqlalchemy.engine import URL
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from sddctx.analyzer import analyze_text


class SddCtxSeekDBDialect(AsyncOceanBaseDialect):
    """OceanBase 兼容方言,按 seekdb 的连接行为调整关闭逻辑。"""

    def do_close(self, dbapi_connection: DBAPIConnection) -> None:
        # seekdb 在 COM_QUIT 期间会重置 unix socket,SQLAlchemy 的 terminate
        # 路径能处理该重置并回落到关闭传输层。
        self.do_terminate(dbapi_connection)

_DIALECT_DRIVER = "sddctx+aseekdb"

_METADATA = MetaData()
SDD_ASSETS = Table(
    "sdd_assets",
    _METADATA,
    Column("asset_id", String(320), primary_key=True),
    Column("kind", String(32), nullable=False),          # spec_file | spec_entry | code | test
    Column("path", String(512), nullable=False),         # 相对 minimax/ 的路径(spec_entry 带条目锚点)
    Column("title", String(512)),
    Column("symbol", String(512)),                       # 代码/测试的顶层符号;规格条目的条目编号
    Column("content", Text, nullable=False),
    Column("content_hash", String(64), nullable=False),
    Column("version", Integer, nullable=False, default=1),
    Column("imported_at", String(64), nullable=False),
    Column("searchable_text", Text, nullable=False),
)

_CREATE_FTS_SQL = "CREATE FULLTEXT INDEX ix_sdd_assets_fts ON sdd_assets (searchable_text) WITH PARSER SPACE"
_FTS_INDEX_EXISTS_SQL = text(
    """
    SELECT COUNT(*) AS n
    FROM information_schema.statistics
    WHERE table_schema = DATABASE()
      AND table_name = 'sdd_assets'
      AND index_name = 'ix_sdd_assets_fts'
    """
)

_INSERT_SQL = text(
    """
    INSERT INTO sdd_assets
        (asset_id, kind, path, title, symbol, content, content_hash,
         version, imported_at, searchable_text)
    VALUES
        (:asset_id, :kind, :path, :title, :symbol, :content, :content_hash,
         :version, :imported_at, :searchable_text)
    """
)

_UPDATE_SQL = text(
    """
    UPDATE sdd_assets
    SET kind = :kind, path = :path, title = :title, symbol = :symbol,
        content = :content, content_hash = :content_hash,
        version = version + 1, imported_at = :imported_at,
        searchable_text = :searchable_text
    WHERE asset_id = :asset_id
    """
)

_SELECT_HASH_SQL = text("SELECT content_hash FROM sdd_assets WHERE asset_id = :asset_id")

_SEARCH_SQL = text(
    """
    SELECT asset_id, kind, path, title, symbol, content, content_hash,
           version, imported_at,
           MATCH(searchable_text) AGAINST(:query) AS score
    FROM sdd_assets
    WHERE MATCH(searchable_text) AGAINST(:query)
      AND kind IN :kinds
    ORDER BY score DESC, asset_id
    LIMIT :limit
    """
)

_ALL_SQL = text(
    """
    SELECT asset_id, kind, path, title, symbol, content, content_hash,
           version, imported_at
    FROM sdd_assets
    WHERE kind IN :kinds
    ORDER BY path, symbol
    LIMIT :limit
    """
)


class Asset(BaseModel):
    asset_id: str
    kind: str
    path: str
    title: str | None = None
    symbol: str | None = None
    content: str
    content_hash: str = ""
    version: int = 1
    imported_at: str = ""


class SearchHit(BaseModel):
    asset: Asset
    score: float
    matched_query: str


class QueryTrace(BaseModel):
    """一次数据库查询的审计记录,写入 records/db-query-log.md。"""

    executed_at: str
    purpose: str
    sql: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    hit_count: int = 0
    hit_ids: list[str] = Field(default_factory=list)
    duration_ms: float = 0.0


class QueryTraceSink:
    """收集查询审计并追加写入记录文件(数据库查询记录)。"""

    def __init__(self, log_path: Path | None) -> None:
        self._log_path = log_path
        self.traces: list[QueryTrace] = []

    def record(self, trace: QueryTrace) -> None:
        self.traces.append(trace)
        if self._log_path is None:
            return
        self._log_path.parent.mkdir(parents=True, exist_ok=True)
        header_needed = not self._log_path.exists()
        with self._log_path.open("a", encoding="utf-8") as handle:
            if header_needed:
                handle.write("# seekdb 查询记录\n\n由 sddctx 自动追加,每条记录含时间、用途、SQL、参数与命中。\n\n")
            handle.write(f"## {trace.executed_at} — {trace.purpose}\n\n")
            handle.write("```sql\n")
            handle.write(_squash(trace.sql))
            handle.write("\n```\n\n")
            handle.write(f"- 参数: `{trace.parameters}`\n")
            handle.write(f"- 命中数: {trace.hit_count};命中: `{trace.hit_ids}`;耗时: {trace.duration_ms} ms\n\n")


def _squash(sql: str, limit: int = 400) -> str:
    collapsed = " ".join(sql.split())
    return collapsed if len(collapsed) <= limit else collapsed[:limit] + " …"


class SeekDBUnavailableError(RuntimeError):
    """pylibseekdb 不可用(未安装或平台不支持)。"""


class AssetStore:
    """嵌入式 seekdb 资产存储。生命周期:open() → 查询/写入 → close()。"""

    def __init__(self, db_path: Path, trace_sink: QueryTraceSink | None = None) -> None:
        self._db_path = db_path
        self._trace_sink = trace_sink or QueryTraceSink(None)
        self._engine: AsyncEngine | None = None
        self._instance: Any = None

    # -- 生命周期 -----------------------------------------------------------

    async def open(self) -> None:
        try:
            import pylibseekdb  # noqa: PLC0415
        except ModuleNotFoundError as error:  # pragma: no cover - 依赖缺失场景
            raise SeekDBUnavailableError(
                "需要 pylibseekdb:请先 pip install 'pylibseekdb>=1.4' (Linux/macOS)"
            ) from error
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._instance = await pylibseekdb.aopen(str(self._db_path))
        options = dict(self._instance.connection_options())
        username = str(options.pop("user", "root"))
        password_value = options.pop("password", None)
        host = str(options.pop("host", "localhost"))
        port_value = options.pop("port", None)
        # seekdb 握手省略 autocommit 标志,aiomysql 会误判事务状态;与
        # PowerContext 内嵌路径一致,显式关闭 autocommit 并由 SQLAlchemy 管理事务。
        options["init_command"] = "SET autocommit = 0"
        _register_dialect()
        url = URL.create(
            _DIALECT_DRIVER,
            username=username,
            password=None if password_value is None else str(password_value),
            host=host,
            port=None if port_value is None else int(port_value),
            database="test",
            query={"charset": "utf8mb4"},
        )
        self._engine = create_async_engine(url, connect_args=options, pool_pre_ping=True)
        async with self._engine.begin() as connection:
            await connection.run_sync(_METADATA.create_all, tables=[SDD_ASSETS])
            await self._ensure_fts_index(connection)

    async def close(self) -> None:
        if self._engine is not None:
            await self._engine.dispose()
            self._engine = None
        if self._instance is not None:
            self._instance.close()
            self._instance = None

    async def __aenter__(self) -> "AssetStore":
        await self.open()
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.close()

    @contextlib.asynccontextmanager
    async def _connection(self):
        if self._engine is None:
            raise RuntimeError("AssetStore 未打开,先调用 open()")
        async with self._engine.connect() as connection:
            yield connection

    async def _ensure_fts_index(self, connection: Any) -> None:
        existing = (await connection.execute(_FTS_INDEX_EXISTS_SQL)).scalar()
        if not existing:
            await connection.execute(text(_CREATE_FTS_SQL))

    # -- 写入 ---------------------------------------------------------------

    async def upsert_asset(
        self,
        *,
        kind: str,
        path: str,
        content: str,
        title: str | None = None,
        symbol: str | None = None,
        content_hash: str = "",
        extra_searchable: str = "",
    ) -> Asset:
        """写入或更新一条资产;内容变化时版本自增(规格更新后重新导入可见)。"""
        symbol_suffix = ""
        if symbol:
            # symbol 可能很长(单文件全部顶层符号);主键用哈希后缀保证有界且稳定。
            symbol_suffix = "#" + hashlib.sha256(symbol.encode("utf-8")).hexdigest()[:16]
        asset_id = f"{kind}:{path}{symbol_suffix}"
        searchable = analyze_text(" ".join(part for part in (title or "", symbol or "", path, content, extra_searchable) if part))
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        stored_symbol = symbol[:500] if symbol else None
        async with self._connection() as connection:
            async with connection.begin():
                existing_hash = (
                    await connection.execute(_SELECT_HASH_SQL, {"asset_id": asset_id})
                ).scalar()
                if existing_hash is None:
                    action = "insert"
                    parameters = {
                        "asset_id": asset_id,
                        "kind": kind,
                        "path": path,
                        "title": title,
                        "symbol": stored_symbol,
                        "content": content,
                        "content_hash": content_hash,
                        "version": 1,
                        "imported_at": now,
                        "searchable_text": searchable,
                    }
                    await connection.execute(_INSERT_SQL, parameters)
                elif existing_hash == content_hash:
                    # 内容未变化:保持版本与首次导入时间,不产生空修订。
                    action = "unchanged"
                    row = (
                        await connection.execute(
                            text("SELECT version, content_hash, imported_at FROM sdd_assets WHERE asset_id = :asset_id"),
                            {"asset_id": asset_id},
                        )
                    ).mappings().one()
                    return Asset(
                        asset_id=asset_id,
                        kind=kind,
                        path=path,
                        title=title,
                        symbol=stored_symbol,
                        content=content,
                        content_hash=row["content_hash"],
                        version=int(row["version"]),
                        imported_at=row["imported_at"],
                    )
                else:
                    action = "update"
                    parameters = {
                        "asset_id": asset_id,
                        "kind": kind,
                        "path": path,
                        "title": title,
                        "symbol": stored_symbol,
                        "content": content,
                        "content_hash": content_hash,
                        "imported_at": now,
                        "searchable_text": searchable,
                    }
                    await connection.execute(_UPDATE_SQL, parameters)
                row = (
                    await connection.execute(
                        text("SELECT version, content_hash FROM sdd_assets WHERE asset_id = :asset_id"),
                        {"asset_id": asset_id},
                    )
                ).mappings().one()
        self._trace_sink.record(
            QueryTrace(
                executed_at=now,
                purpose=f"upsert[{action}] {kind} {path}" + (f"#{symbol}" if symbol else ""),
                sql=str(_INSERT_SQL if action == "insert" else _UPDATE_SQL),
                parameters={k: (v if k != "content" else f"<{len(str(v))} chars>") for k, v in parameters.items()},
                hit_count=1,
                hit_ids=[asset_id],
            )
        )
        return Asset(
            asset_id=asset_id,
            kind=kind,
            path=path,
            title=title,
            symbol=symbol,
            content=content,
            content_hash=row["content_hash"],
            version=int(row["version"]),
            imported_at=now,
        )

    # -- 查询 ---------------------------------------------------------------

    async def search(
        self,
        query: str,
        kinds: tuple[str, ...],
        limit: int = 8,
        purpose: str = "context-selection",
    ) -> list[SearchHit]:
        """原生全文检索:MATCH ... AGAINST 相关性打分,数据库内完成过滤与排序。"""
        analyzed = analyze_text(query)
        if not analyzed:
            return []
        parameters = {"query": analyzed, "kinds": tuple(kinds), "limit": limit}
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        started = time.monotonic()
        async with self._connection() as connection:
            rows = (await connection.execute(_SEARCH_SQL, parameters)).mappings().all()
        duration_ms = (time.monotonic() - started) * 1000
        self._trace_sink.record(
            QueryTrace(
                executed_at=now,
                purpose=purpose,
                sql=str(_SEARCH_SQL),
                parameters={"query(analyzed)": analyzed, "kinds": list(kinds), "limit": limit},
                hit_count=len(rows),
                hit_ids=[row["asset_id"] for row in rows],
                duration_ms=round(duration_ms, 2),
            )
        )
        return [
            SearchHit(asset=_row_to_asset(row), score=float(row["score"]), matched_query=analyzed)
            for row in rows
        ]

    async def list_assets(self, kinds: tuple[str, ...], limit: int = 500) -> list[Asset]:
        parameters = {"kinds": tuple(kinds), "limit": limit}
        async with self._connection() as connection:
            rows = (await connection.execute(_ALL_SQL, parameters)).mappings().all()
        return [_row_to_asset(row) for row in rows]

    async def count(self) -> int:
        async with self._connection() as connection:
            return int((await connection.execute(text("SELECT COUNT(*) FROM sdd_assets"))).scalar())

    @property
    def traces(self) -> list[QueryTrace]:
        return self._trace_sink.traces


def _row_to_asset(row: Any) -> Asset:
    return Asset(
        asset_id=row["asset_id"],
        kind=row["kind"],
        path=row["path"],
        title=row["title"],
        symbol=row["symbol"],
        content=row["content"],
        content_hash=row["content_hash"],
        version=int(row["version"]),
        imported_at=row["imported_at"],
    )


_DIALECT_REGISTERED = False


def _register_dialect() -> None:
    """注册 seekdb 方言(键 ``sddctx.aseekdb``,URL driver ``sddctx+aseekdb``)。

    复用 pyobvector 的 OceanBase 异步方言,仅调整连接关闭行为:
    seekdb 在 COM_QUIT 期间会重置 unix socket,terminate 路径更稳。
    """
    global _DIALECT_REGISTERED
    if _DIALECT_REGISTERED:
        return
    dialect_registry.register("sddctx.aseekdb", "sddctx.seekdb_store", "SddCtxSeekDBDialect")
    _DIALECT_REGISTERED = True


__all__ = [
    "Asset",
    "AssetStore",
    "QueryTrace",
    "QueryTraceSink",
    "SearchHit",
    "SeekDBUnavailableError",
]
