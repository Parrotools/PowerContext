"""dev 命令:构建上下文 → 调用 MiniMax 完成代码修改 → 留档全过程。

流程对应赛题 2.1 的第 3 步:把上下文提供给使用 MiniMax 的开发助手,
完成代码修改。产物:
- run_dir/context.md / context.json — 提供给模型的上下文
- run_dir/minimax-request.json / minimax-response.* — MiniMax 交互留档
- run_dir/before/ — 修改前代码快照
- run_dir/applied-files.json — 实际写入的文件与哈希
- run_dir/devlog.md — 人工可读的开发过程记录(任务→上下文→请求→响应→修改)
"""

from __future__ import annotations

import hashlib
import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sddctx.config import Settings
from sddctx.context_builder import build_context
from sddctx.minimax_client import ChatResult, MiniMaxClient, MiniMaxError, write_chat_log

FILE_BLOCK_PATTERN = re.compile(
    r"===\s*FILE:\s*(?P<path>[^\n=]+?)\s*===\s*\n```[a-zA-Z0-9_+-]*\n(?P<body>.*?)\n```",
    re.DOTALL,
)

APPLY_ROOT = "sample-project"  # dev 只允许修改业务工程内的文件

SYSTEM_PROMPT = """你是资深 Python 开发助手,在规格驱动开发(SDD)流程中负责按规格修改代码。

规则:
1. 只实现用户给出的任务与规格条目要求的行为,不做无关重构。
2. 遵守给出的全部规格约束(类型、边界、兼容性、排序等)。
3. 保持既有公共接口向后兼容;新参数必须有默认值。
4. 输出方式:对每个需要修改或新建的文件,输出一个完整文件块,格式严格为:

=== FILE: 相对路径 ===
```python
<文件完整新内容>
```

路径必须以 sample-project/ 开头。必须输出文件完整内容(不是片段、不是 diff)。
不要输出解释性文字以外的其他文件块;最后可以加一行简短说明。
"""


@dataclass
class AppliedFile:
    path: str
    bytes_written: int
    sha256: str
    existed_before: bool


@dataclass
class DevRunResult:
    run_dir: Path
    applied: list[AppliedFile] = field(default_factory=list)
    model: str = ""
    usage: dict = field(default_factory=dict)

    @property
    def summary(self) -> str:
        files = ", ".join(item.path for item in self.applied) or "(无)"
        return f"模型 {self.model};修改文件: {files};产物目录: {self.run_dir}"


def parse_file_blocks(content: str) -> list[tuple[str, str]]:
    """从模型输出中解析 FILE 块。"""
    blocks: list[tuple[str, str]] = []
    for match in FILE_BLOCK_PATTERN.finditer(content):
        path = match.group("path").strip().replace("\\", "/")
        body = match.group("body")
        blocks.append((path, body))
    return blocks


def _validate_path(path: str) -> str:
    normalized = path.strip()
    if not normalized.startswith(APPLY_ROOT + "/"):
        raise MiniMaxError(f"拒绝写入业务工程之外的路径: {normalized}(必须以 {APPLY_ROOT}/ 开头)")
    parts = Path(normalized).parts
    if any(part in ("..", "") for part in parts) or Path(normalized).is_absolute():
        raise MiniMaxError(f"非法路径: {normalized}")
    return normalized


def apply_blocks(
    home: Path,
    blocks: list[tuple[str, str]],
    before_dir: Path,
) -> list[AppliedFile]:
    """把模型给出的文件写入业务工程;写前先快照原始内容到 before_dir。"""
    applied: list[AppliedFile] = []
    for raw_path, body in blocks:
        rel = _validate_path(raw_path)
        target = home / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        snapshot = before_dir / Path(rel).relative_to(APPLY_ROOT)
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            existed_before = True
            if not snapshot.exists():
                shutil.copy2(target, snapshot)
        else:
            existed_before = False
            snapshot.write_text("", encoding="utf-8")  # 占位:表示“新增文件”
        content = body if body.endswith("\n") else body + "\n"
        target.write_text(content, encoding="utf-8")
        applied.append(
            AppliedFile(
                path=rel,
                bytes_written=len(content.encode("utf-8")),
                sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
                existed_before=existed_before,
            )
        )
    return applied


def _user_prompt(task: str, context_markdown: str) -> str:
    return (
        f"# 开发任务\n\n{task}\n\n"
        "# 开发上下文(来自 sddctx,含规格条目、相关代码、验证测试与任务状态)\n\n"
        f"{context_markdown}\n\n"
        "请按系统提示的 FILE 块格式,输出需要修改文件的完整新内容。"
    )


def run_dev(settings: Settings, task: str, task_id: str, run_dir: Path | None = None) -> DevRunResult:
    if not task.strip():
        raise MiniMaxError("任务描述不能为空")
    if run_dir is None:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        run_dir = settings.records_dir / "minimax" / f"{task_id or 'run'}-{stamp}"
    run_dir.mkdir(parents=True, exist_ok=True)

    context = build_context(settings, task, use_state=True)
    (run_dir / "context.md").write_text(context.to_markdown(), encoding="utf-8")
    (run_dir / "context.json").write_text(
        json.dumps(context.to_json(include_content=True), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    client = MiniMaxClient(settings)
    result: ChatResult = client.chat(SYSTEM_PROMPT, _user_prompt(task, context.to_markdown()))
    write_chat_log(run_dir, result, settings)

    blocks = parse_file_blocks(result.content)
    if not blocks:
        raise MiniMaxError(
            "MiniMax 输出中没有可解析的 FILE 块。请检查 minimax-response.md,"
            "或重试(提示词要求 === FILE: path === 围栏块)。"
        )
    before_dir = run_dir / "before"
    applied = apply_blocks(settings.home, blocks, before_dir)

    (run_dir / "applied-files.json").write_text(
        json.dumps(
            {
                "task": task,
                "task_id": task_id,
                "applied_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "model": result.model,
                "files": [item.__dict__ for item in applied],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    devlog = [
        f"# MiniMax 开发记录 — {task_id or 'run'}",
        "",
        f"- 时间: {datetime.now(timezone.utc).isoformat(timespec='seconds')}",
        f"- 任务: {task}",
        f"- 模型: {result.model}(base_url: {settings.minimax_base_url})",
        f"- usage: {json.dumps(result.usage, ensure_ascii=False)}",
        "",
        "## 1. 提供给模型的上下文",
        "",
        "见 `context.md`(与 `sddctx context` 输出一致:规格条目、代码、测试、任务状态,均含真实来源)。",
        "",
        "## 2. MiniMax 请求",
        "",
        "见 `minimax-request.json`(API Key 已脱敏;system 提示词要求 FILE 块输出格式)。",
        "",
        "## 3. MiniMax 响应",
        "",
        "见 `minimax-response.md` / `minimax-response.json`(原文留档)。",
        "",
        "## 4. 代码修改过程",
        "",
        f"- 解析到 {len(blocks)} 个 FILE 块,全部写入业务工程:",
        "",
    ]
    for item in applied:
        action = "修改" if item.existed_before else "新建"
        devlog.append(f"  - {action} `{item.path}`({item.bytes_written} 字节,sha256 {item.sha256[:12]}…)")
    devlog += [
        "",
        "修改前快照: `before/`;修改后与快照的差异: `sddctx diff --run-dir <本目录>`。",
        "",
    ]
    (run_dir / "devlog.md").write_text("\n".join(devlog), encoding="utf-8")

    # 把开发过程写入 PowerContext(状态链:任务→上下文→修改→验证)
    try:
        from sddctx.task_state import TaskStateClient  # noqa: PLC0415

        TaskStateClient(settings).remember_dev_run(
            {
                "task_id": task_id,
                "task": task,
                "model": result.model,
                "base_url": settings.minimax_base_url,
                "run_dir": str(run_dir),
                "context_file": str(run_dir / "context.md"),
                "devlog_file": str(run_dir / "devlog.md"),
                "usage": result.usage,
                "applied_files": [
                    {"path": item.path, "sha256": item.sha256, "existed_before": item.existed_before}
                    for item in applied
                ],
            }
        )
    except Exception as error:  # noqa: BLE001 - PowerContext 不可达不阻塞修改
        print(f"[warn] 开发记录写入 PowerContext 失败: {error}")

    write_diff(run_dir, settings)  # 生成 code.diff.md,产物与入口无关、始终完整

    return DevRunResult(run_dir=run_dir, applied=applied, model=result.model, usage=result.usage)


def write_diff(run_dir: Path, settings: Settings) -> Path:
    """对比 before/ 快照与当前业务工程,生成统一 diff。"""
    import difflib  # noqa: PLC0415

    before_dir = run_dir / "before"
    if not before_dir.is_dir():
        raise FileNotFoundError(f"{before_dir} 不存在(该目录由 sddctx dev 创建)")
    lines = [f"# 代码差异 — {run_dir.name}", ""]
    changed = 0
    for snapshot in sorted(before_dir.rglob("*")):
        if snapshot.is_dir():
            continue
        rel = snapshot.relative_to(before_dir)
        target = settings.sample_project_dir / rel
        before_text = snapshot.read_text(encoding="utf-8") if snapshot.exists() and snapshot.stat().st_size else ""
        after_text = target.read_text(encoding="utf-8") if target.exists() else ""
        if before_text == after_text and target.exists():
            continue
        changed += 1
        lines.append(f"## {rel.as_posix()}")
        lines.append("")
        lines.append("```diff")
        lines.extend(
            difflib.unified_diff(
                before_text.splitlines(),
                after_text.splitlines(),
                fromfile=f"a/{APPLY_ROOT}/{rel.as_posix()}",
                tofile=f"b/{APPLY_ROOT}/{rel.as_posix()}",
                lineterm="",
            )
        )
        lines.append("```")
        lines.append("")
    if not changed:
        lines.append("(业务工程与快照一致,无差异)")
    diff_path = run_dir / "code.diff.md"
    diff_path.write_text("\n".join(lines), encoding="utf-8")
    return diff_path


__all__ = ["AppliedFile", "DevRunResult", "MiniMaxError", "apply_blocks", "parse_file_blocks", "run_dev", "write_diff"]
