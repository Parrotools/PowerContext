"""verify 命令:运行目标功能测试与回归测试,记录命令、退出码、代码版本,并存入 PowerContext。

- --phase before:目标测试应失败(目标行为未实现);全部通过视为异常并明确报告。
- --phase after:目标测试必须全部通过,且回归测试(全量测试)也必须全部通过。
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from sddctx.config import Settings
from sddctx.task_state import TaskStateClient, VerificationRecord


@dataclass
class TestRun:
    command: str
    exit_code: int
    duration_s: float
    summary: str
    failed_nodes: list[str] = field(default_factory=list)
    passed: bool = False
    log_path: str = ""


def _git_head(home: Path) -> str:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=home,
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (OSError, subprocess.TimeoutExpired):
        pass
    return "unknown(not-a-git-worktree)"


def _sample_project_version(settings: Settings) -> str:
    """业务工程源码指纹:让测试日志能对应到具体代码版本。"""
    digest = hashlib.sha256()
    for base in ("src", "tests"):
        directory = settings.sample_project_dir / base
        if not directory.is_dir():
            continue
        for file in sorted(directory.rglob("*.py")):
            if "__pycache__" in file.parts:
                continue
            digest.update(str(file.relative_to(settings.sample_project_dir)).encode())
            digest.update(file.read_bytes())
    return digest.hexdigest()[:16]


def run_pytest(test_paths: list[str], cwd: Path, log_path: Path, env_extra: dict | None = None) -> TestRun:
    """运行 pytest 并完整留档(命令、退出码、输出)。

    自动把 sample-project/src 注入 PYTHONPATH,保证测试只依赖交付的代码,
    不会以“缺少依赖”类环境错误充当功能失败。
    """
    project_src = str((cwd / "src").resolve())
    existing_pythonpath = __import__("os").environ.get("PYTHONPATH", "")
    pythonpath = project_src if not existing_pythonpath else f"{project_src}{__import__('os').pathsep}{existing_pythonpath}"
    command = [sys.executable, "-m", "pytest", *test_paths]
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    process = subprocess.run(
        command,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=900,
        check=False,
        env={**dict(__import__("os").environ), "PYTHONPATH": pythonpath, **(env_extra or {})},
    )
    duration = time.monotonic() - started
    output = process.stdout + ("\n[stderr]\n" + process.stderr if process.stderr.strip() else "")
    log_path.write_text(
        "# pytest 运行记录\n\n"
        f"- 时间: {datetime.now(timezone.utc).isoformat(timespec='seconds')}\n"
        f"- 命令: `{subprocess.list2cmdline(command)}`\n"
        f"- 工作目录: {cwd}\n"
        f"- 退出码: {process.returncode}\n\n"
        f"```\n{output}\n```\n",
        encoding="utf-8",
    )
    failed_nodes = [
        line.split()[1] for line in process.stdout.splitlines() if line.startswith("FAILED ")
    ]
    short = next(
        (line for line in process.stdout.splitlines() if " passed" in line or " failed" in line or " no tests ran" in line),
        "",
    )
    return TestRun(
        command=subprocess.list2cmdline(command),
        exit_code=process.returncode,
        duration_s=round(duration, 2),
        summary=short.strip() or f"exit={process.returncode}",
        failed_nodes=failed_nodes,
        passed=process.returncode == 0,
        log_path=str(log_path),
    )


@dataclass
class VerifyOutcome:
    phase: str
    target: TestRun
    regression: TestRun | None
    accepted: bool
    reason: str
    code_version: str

    @property
    def summary(self) -> str:
        lines = [
            f"[{self.phase}] 目标测试: {'通过' if self.target.passed else '未通过'} — {self.target.summary}",
            f"       (命令: {self.target.command};退出码 {self.target.exit_code};日志: {self.target.log_path})",
        ]
        if self.regression is not None:
            lines += [
                f"[{self.phase}] 回归测试: {'通过' if self.regression.passed else '未通过'} — {self.regression.summary}",
                f"       (命令: {self.regression.command};退出码 {self.regression.exit_code};日志: {self.regression.log_path})",
            ]
        lines.append(f"[{self.phase}] 验收判定: {'✔ 通过' if self.accepted else '✘ 未通过'} — {self.reason}")
        lines.append(f"[{self.phase}] 代码版本: git {self.code_version}")
        return "\n".join(lines)


def run_verify(
    settings: Settings,
    task_id: str,
    target_tests: list[str],
    phase: str,
    *,
    skip_regression: bool = False,
) -> VerifyOutcome:
    if phase not in ("before", "after"):
        raise ValueError(f"phase 必须是 before/after,收到 {phase}")
    code_version = _git_head(settings.home)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    verify_dir = settings.records_dir / "verify"
    project_dir = settings.sample_project_dir

    target = run_pytest(target_tests, project_dir, verify_dir / f"target-{phase}-{stamp}.log")
    regression: TestRun | None = None
    if not skip_regression:
        regression = run_pytest(["tests"], project_dir, verify_dir / f"regression-{phase}-{stamp}.log")

    if phase == "before":
        if target.passed:
            accepted = False
            reason = "修改前目标测试不应全部通过——请确认目标行为确实尚未实现。"
        else:
            accepted = True
            reason = f"目标测试按预期失败(行为未实现),失败节点: {', '.join(target.failed_nodes) or '见日志'}"
    else:
        if not target.passed:
            accepted = False
            reason = f"修改后目标测试未全部通过: {', '.join(target.failed_nodes) or '见日志'}"
        elif regression is not None and not regression.passed:
            accepted = False
            reason = f"回归测试未全部通过: {', '.join(regression.failed_nodes) or '见日志'}"
        else:
            accepted = True
            reason = "目标测试与回归测试全部通过。"

    outcome = VerifyOutcome(
        phase=phase,
        target=target,
        regression=regression,
        accepted=accepted,
        reason=reason,
        code_version=code_version,
    )

    # 写入 PowerContext(验证结果),供重启后复用
    state = TaskStateClient(settings)
    try:
        state.remember_verification(
            VerificationRecord(
                task_id=task_id,
                phase=phase,
                command=target.command,
                exit_code=target.exit_code,
                passed=target.passed,
                log_path=target.log_path,
                code_version=f"{code_version}+fp:{_sample_project_version(settings)}",
                detail=reason,
            )
        )
        if regression is not None:
            state.remember_verification(
                VerificationRecord(
                    task_id=task_id,
                    phase=f"{phase}-regression",
                    command=regression.command,
                    exit_code=regression.exit_code,
                    passed=regression.passed,
                    log_path=regression.log_path,
                    code_version=code_version,
                    detail=regression.summary,
                )
            )
    except Exception as error:  # noqa: BLE001 - PowerContext 不可达时不阻塞测试结论
        print(f"[warn] 验证结果写入 PowerContext 失败: {error}")

    (verify_dir / f"summary-{phase}-{stamp}.json").write_text(
        json.dumps(
            {
                "phase": phase,
                "accepted": outcome.accepted,
                "reason": reason,
                "code_version": code_version,
                "target": target.__dict__,
                "regression": regression.__dict__ if regression else None,
            },
            ensure_ascii=False,
            indent=2,
            default=str,
        ),
        encoding="utf-8",
    )
    return outcome


__all__ = ["TestRun", "VerifyOutcome", "run_pytest", "run_verify"]
