"""上下文构建:根据开发任务从 seekdb 检索并选择规格条目、代码与测试,形成开发上下文。

选择方法(可解释、确定性):
1. 任务文本经 Analyzer v1 分词后,在 seekdb 原生 FULLTEXT 索引上按
   spec_entry / code / test 三类分别检索(MATCH ... AGAINST 相关性打分);
2. 从任务文本抽取代码标识符(snake_case / CamelCase),对路径、符号或正文
   命中标识符的资产加成;
3. 类别内按总分排序取 Top-N,过滤零分资产;
4. 叠加 PowerContext 中保存的任务状态(已完成/待办/验证结果)作为上下文
   的第四部分。

输出 markdown(供人/Agent 阅读)与 JSON(供程序消费)两种形态,所有条目
都带真实来源(kind/path/version/score)。
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone

from sddctx.analyzer import extract_identifiers
from sddctx.config import Settings
from sddctx.seekdb_store import Asset, AssetStore, QueryTraceSink, SearchHit
from sddctx.task_state import TaskBoard, TaskStateError, load_board

KIND_LABELS = {
    "spec_file": "规格文档",
    "spec_entry": "规格条目",
    "code": "代码",
    "test": "测试",
}

MAX_CONTENT_CHARS = 4000


@dataclass
class SelectedItem:
    kind: str
    path: str
    title: str | None
    symbol: str | None
    version: int
    score: float
    content: str
    reasons: list[str] = field(default_factory=list)

    def to_json(self, include_content: bool = True) -> dict:
        payload = {
            "kind": self.kind,
            "source": self.path,
            "title": self.title,
            "symbol": self.symbol,
            "version": self.version,
            "score": round(self.score, 4),
            "reasons": self.reasons,
        }
        if include_content:
            payload["content"] = self.content
        return payload


@dataclass
class BuiltContext:
    task: str
    generated_at: str
    spec_entries: list[SelectedItem]
    spec_files: list[SelectedItem]
    code: list[SelectedItem]
    tests: list[SelectedItem]
    board: TaskBoard | None
    board_error: str | None
    db_queries: list[dict]

    def to_markdown(self) -> str:
        lines = [f"# 开发上下文 — {self.task}", ""]
        lines.append(f"- 生成时间: {self.generated_at}")
        lines.append("")

        lines.append("## 一、适用的规格条目")
        if self.spec_entries:
            for item in self.spec_entries:
                lines.append(f"- [{item.symbol}] {item.content}")
                lines.append(f"  来源: `{item.path}`(版本 {item.version},score {item.score:.3f})")
        else:
            lines.append("- (无命中)")
        lines.append("")
        if self.spec_files:
            lines.append("### 相关规格文档(全文)")
            for item in self.spec_files:
                lines.append(f"#### `{item.path}` — {item.title}(版本 {item.version})")
                lines.append("")
                lines.append("```markdown")
                lines.append(_clip(item.content, 2500))
                lines.append("```")
                lines.append("")

        lines.append("## 二、需要关注的代码")
        if self.code:
            for item in self.code:
                lines.append(f"### `{item.path}`" + (f" — 符号: {item.symbol}" if item.symbol else ""))
                lines.append(f"来源: `{item.path}`(版本 {item.version},score {item.score:.3f})")
                lines.append("")
                lines.append("```python")
                lines.append(_clip(item.content))
                lines.append("```")
                lines.append("")
        else:
            lines.append("(无命中)")
            lines.append("")

        lines.append("## 三、验证测试")
        if self.tests:
            for item in self.tests:
                lines.append(f"### `{item.path}`" + (f" — 符号: {item.symbol}" if item.symbol else ""))
                lines.append(f"来源: `{item.path}`(版本 {item.version},score {item.score:.3f})")
                lines.append("")
                lines.append("```python")
                lines.append(_clip(item.content))
                lines.append("```")
                lines.append("")
        else:
            lines.append("(无命中)")
            lines.append("")

        lines.append("## 四、任务状态(PowerContext)")
        if self.board is not None:
            lines.append(f"- 任务编号: {self.board.task_id}")
            lines.append(f"- 目标: {self.board.objective}")
            lines.append(f"- 已完成: {json.dumps(self.board.completed, ensure_ascii=False)}")
            lines.append(f"- 待办: {json.dumps(self.board.pending, ensure_ascii=False)}")
            lines.append(f"- 已有验证结果: {json.dumps(self.board.verification, ensure_ascii=False)}")
            lines.append(f"- 最近更新: {self.board.updated_at}")
        elif self.board_error:
            lines.append(f"- (未能读取任务状态: {self.board_error})")
        else:
            lines.append("- (暂无已保存的任务状态)")
        lines.append("")
        return "\n".join(lines)

    def to_json(self, include_content: bool = False) -> dict:
        return {
            "task": self.task,
            "generated_at": self.generated_at,
            "sections": {
                "spec_entries": [i.to_json(include_content) for i in self.spec_entries],
                "spec_files": [i.to_json(include_content) for i in self.spec_files],
                "code": [i.to_json(include_content) for i in self.code],
                "tests": [i.to_json(include_content) for i in self.tests],
                "task_state": (
                    self.board.model_dump() if self.board is not None else {"error": self.board_error}
                ),
            },
            "db_queries": self.db_queries,
        }


def _clip(content: str, limit: int = MAX_CONTENT_CHARS) -> str:
    if len(content) <= limit:
        return content
    return content[:limit] + f"\n…(截断,共 {len(content)} 字符,完整内容见来源文件)"


def _identifier_bonus(hit: SearchHit, identifiers: list[str]) -> tuple[float, list[str]]:
    bonus = 0.0
    reasons: list[str] = []
    haystack = "\n".join(
        part for part in (hit.asset.path, hit.asset.symbol or "", hit.asset.title or "", hit.asset.content) if part
    ).casefold()
    for identifier in identifiers:
        if identifier.casefold() in haystack:
            bonus += 1.0
            reasons.append(f"标识符命中 {identifier}")
    return min(bonus, 3.0), reasons


async def _select(
    store: AssetStore,
    task: str,
    *,
    kind: str,
    limit: int,
    identifiers: list[str],
    purpose: str,
) -> list[SelectedItem]:
    hits = await store.search(task, kinds=(kind,), limit=limit * 3, purpose=purpose)
    scored: list[tuple[float, SearchHit, list[str]]] = []
    for hit in hits:
        bonus, reasons = _identifier_bonus(hit, identifiers)
        total = hit.score + bonus
        if total <= 0:
            continue
        reasons = [f"全文检索 score={hit.score:.3f}"] + reasons
        scored.append((total, hit, reasons))
    scored.sort(key=lambda entry: (-entry[0], entry[1].asset.asset_id))
    return [
        SelectedItem(
            kind=hit.asset.kind,
            path=hit.asset.path,
            title=hit.asset.title,
            symbol=hit.asset.symbol,
            version=hit.asset.version,
            score=total,
            content=hit.asset.content,
            reasons=reasons,
        )
        for total, hit, reasons in scored[:limit]
    ]


async def _build_async(settings: Settings, task: str, *, use_state: bool) -> BuiltContext:
    sink = QueryTraceSink(settings.db_query_log)
    identifiers = extract_identifiers(task)
    async with AssetStore(settings.seekdb_path, sink) as store:
        spec_entries = await _select(store, task, kind="spec_entry", limit=8, identifiers=identifiers, purpose="context-selection:spec_entry")
        spec_files = await _select(store, task, kind="spec_file", limit=3, identifiers=identifiers, purpose="context-selection:spec_file")
        code = await _select(store, task, kind="code", limit=6, identifiers=identifiers, purpose="context-selection:code")
        tests = await _select(store, task, kind="test", limit=6, identifiers=identifiers, purpose="context-selection:test")

        board: TaskBoard | None = None
        board_error: str | None = None
        if use_state:
            try:
                board = await load_board(settings, task_id=None)
            except TaskStateError as error:
                board_error = str(error)

    return BuiltContext(
        task=task,
        generated_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        spec_entries=spec_entries,
        spec_files=spec_files,
        code=code,
        tests=tests,
        board=board,
        board_error=board_error,
        db_queries=[trace.model_dump() for trace in sink.traces],
    )


def build_context(settings: Settings, task: str, *, use_state: bool = True) -> BuiltContext:
    return asyncio.run(_build_async(settings, task, use_state=use_state))


def assets_present(settings: Settings) -> tuple[bool, int]:
    """检查库内是否已有资产(未导入时给出友好提示)。"""

    async def _count() -> int:
        async with AssetStore(settings.seekdb_path) as store:
            return await store.count()

    try:
        return True, asyncio.run(_count())
    except Exception:  # noqa: BLE001 - 探测失败一律按未导入处理
        return False, 0
