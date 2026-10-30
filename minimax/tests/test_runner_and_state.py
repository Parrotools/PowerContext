"""runner 与 CLI 冒烟测试(不依赖网络;PowerContext 用例在服务不可达时跳过)。"""

import socket
import subprocess
import sys
from pathlib import Path

import httpx

from sddctx.runner import run_pytest
from sddctx.task_state import TaskBoard, TaskStateClient, TaskStateError
from sddctx.config import Settings

POWERCONTEXT_URL = "http://127.0.0.1:8000"


def _server_up() -> bool:
    try:
        host, port = "127.0.0.1", 8000
        with socket.create_connection((host, port), timeout=1):
            httpx.get(f"{POWERCONTEXT_URL}/health/ready", timeout=3)
        return True
    except Exception:  # noqa: BLE001
        return False


def test_run_pytest_injects_pythonpath(tmp_path: Path):
    src = tmp_path / "src" / "pkg"
    src.mkdir(parents=True)
    (src / "mod.py").write_text("VALUE = 1\n", encoding="utf-8")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_ok.py").write_text("from pkg.mod import VALUE\n\ndef test_value():\n    assert VALUE == 1\n", encoding="utf-8")
    run = run_pytest(["tests"], tmp_path, tmp_path / "pytest.log")
    assert run.passed, run.summary
    log = (tmp_path / "pytest.log").read_text(encoding="utf-8")
    assert "退出码: 0" in log


def test_run_pytest_records_failures(tmp_path: Path):
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_fail.py").write_text("def test_bad():\n    assert 1 == 2\n", encoding="utf-8")
    run = run_pytest(["tests"], tmp_path, tmp_path / "pytest.log")
    assert not run.passed
    assert run.failed_nodes == ["tests/test_fail.py::test_bad"]


def test_board_roundtrip_with_powercontext():
    """状态复用:写入看板后,以全新 TaskStateClient(新进程语义)读取。"""
    if not _server_up():
        print("PowerContext Server 未运行,跳过状态复用用例")
        return
    settings = Settings.load()
    writer = TaskStateClient(settings)
    board = TaskBoard(
        task_id="pytest-task",
        objective="测试看板写入与读取",
        completed=["写入看板"],
        pending=["读取看板"],
    )
    writer.remember_board(board)
    reader = TaskStateClient(settings)  # 全新 client,模拟重启
    loaded = reader.load_board("pytest-task")
    assert loaded is not None
    assert loaded.task_id == "pytest-task"
    assert loaded.completed == ["写入看板"]
    assert loaded.pending == ["读取看板"]
