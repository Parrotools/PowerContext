"""MiniMax 输出解析与补丁应用的安全测试(不发起网络请求)。"""

from pathlib import Path

import pytest

from sddctx.agent import apply_blocks, parse_file_blocks
from sddctx.minimax_client import MiniMaxError


def test_parse_standard_blocks():
    content = (
        "说明文字\n"
        "=== FILE: sample-project/src/checkout/repository.py ===\n"
        "```python\nprint('hi')\n```\n"
        "=== FILE: sample-project/tests/new_test.py ===\n"
        "```python\nassert True\n```\n"
        "结束"
    )
    blocks = parse_file_blocks(content)
    assert [path for path, _ in blocks] == [
        "sample-project/src/checkout/repository.py",
        "sample-project/tests/new_test.py",
    ]
    assert blocks[0][1] == "print('hi')"


def test_parse_language_tagged_fence():
    content = "=== FILE: sample-project/a.py ===\n```python\nx = 1\n```\n"
    assert parse_file_blocks(content) == [("sample-project/a.py", "x = 1")]


def test_parse_no_blocks_returns_empty():
    assert parse_file_blocks("抱歉,我无法修改。") == []


def test_apply_writes_and_snapshots_before(tmp_path: Path):
    target = tmp_path / "sample-project" / "src" / "mod.py"
    target.parent.mkdir(parents=True)
    target.write_text("OLD = 1\n", encoding="utf-8")
    before_dir = tmp_path / "before"
    applied = apply_blocks(
        tmp_path,
        [("sample-project/src/mod.py", "NEW = 2\n")],
        before_dir,
    )
    assert target.read_text(encoding="utf-8") == "NEW = 2\n"
    assert (before_dir / "src" / "mod.py").read_text(encoding="utf-8") == "OLD = 1\n"
    assert applied[0].existed_before is True


def test_apply_new_file_creates_placeholder_snapshot(tmp_path: Path):
    applied = apply_blocks(tmp_path, [("sample-project/new.py", "X = 1")], tmp_path / "before")
    assert (tmp_path / "sample-project" / "new.py").read_text(encoding="utf-8") == "X = 1\n"
    assert applied[0].existed_before is False


def test_apply_rejects_outside_root(tmp_path: Path):
    with pytest.raises(MiniMaxError):
        apply_blocks(tmp_path, [("specs/SPEC-003.md", "hacked")], tmp_path / "before")


def test_apply_rejects_traversal(tmp_path: Path):
    with pytest.raises(MiniMaxError):
        apply_blocks(tmp_path, [("sample-project/../evil.py", "hacked")], tmp_path / "before")


def test_apply_rejects_absolute(tmp_path: Path):
    with pytest.raises(MiniMaxError):
        apply_blocks(tmp_path, [("/etc/passwd", "hacked")], tmp_path / "before")
