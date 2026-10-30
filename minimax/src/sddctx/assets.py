"""工程资料收集与解析:从 specs/ 与 sample-project/ 收集规格、代码、测试资产。"""

from __future__ import annotations

import ast
import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from sddctx.analyzer import analyze_text

SPEC_ENTRY_PATTERN = re.compile(r"^- (SPEC-\d{3}-\d+):\s*(.+)$", re.MULTILINE)


@dataclass(frozen=True)
class RawAsset:
    """导入前的一条待入库资产。"""

    kind: str                      # spec_file | spec_entry | code | test
    path: str                      # 相对 minimax/ 的 POSIX 路径
    title: str | None
    symbol: str | None
    content: str
    content_hash: str
    extra_searchable: str = ""
    parent_path: str | None = None  # spec_entry 指回规格文件


@dataclass
class ImportReport:
    files_seen: int = 0
    assets: list[RawAsset] = field(default_factory=list)

    @property
    def counts(self) -> dict[str, int]:
        result: dict[str, int] = {}
        for asset in self.assets:
            result[asset.kind] = result.get(asset.kind, 0) + 1
        return result


def sha256_of(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _relativize(path: Path, home: Path) -> str:
    return path.relative_to(home).as_posix()


def _python_symbols(source: str) -> list[str]:
    """提取 Python 文件顶层 class/def 名,作为符号信息参与检索与定位。"""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    names: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            names.append(node.name)
    return names


def collect_assets(home: Path, specs_dir: Path, project_dir: Path) -> ImportReport:
    """收集规格(含条目拆分)、代码与测试资产。"""
    report = ImportReport()

    # -- 规格 ---------------------------------------------------------------
    for spec_file in sorted(specs_dir.glob("*.md")):
        content = spec_file.read_text(encoding="utf-8")
        rel = _relativize(spec_file, home)
        report.files_seen += 1
        title = content.splitlines()[0].lstrip("# ").strip() if content.splitlines() else spec_file.name
        report.assets.append(
            RawAsset(
                kind="spec_file",
                path=rel,
                title=title,
                symbol=None,
                content=content,
                content_hash=sha256_of(content),
            )
        )
        for match in SPEC_ENTRY_PATTERN.finditer(content):
            entry_id, entry_text = match.group(1), match.group(2).strip()
            report.assets.append(
                RawAsset(
                    kind="spec_entry",
                    path=f"{rel}#{entry_id}",
                    title=entry_id,
                    symbol=entry_id,
                    content=entry_text,
                    content_hash=sha256_of(entry_text),
                    parent_path=rel,
                )
            )

    # -- 代码与测试 ----------------------------------------------------------
    for base, kind in ((project_dir / "src", "code"), (project_dir / "tests", "test")):
        if not base.is_dir():
            continue
        for code_file in sorted(base.rglob("*.py")):
            if "__pycache__" in code_file.parts:
                continue
            content = code_file.read_text(encoding="utf-8")
            rel = _relativize(code_file, home)
            report.files_seen += 1
            symbols = _python_symbols(content)
            title = None
            if kind == "code":
                docstring = ast.get_docstring(ast.parse(content)) if symbols or content.strip() else None
                title = docstring.splitlines()[0].strip() if docstring else None
            report.assets.append(
                RawAsset(
                    kind=kind,
                    path=rel,
                    title=title,
                    symbol=", ".join(symbols) if symbols else None,
                    content=content,
                    content_hash=sha256_of(content),
                )
            )
    return report


def spec_entry_terms(entry_text: str) -> str:
    return analyze_text(entry_text)
