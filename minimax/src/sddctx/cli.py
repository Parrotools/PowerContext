"""sddctx 命令行入口。

调用入口一览(CLI 即模块的明确调用入口,输入输出见各子命令 help):
    sddctx import     导入规格/代码/测试资料到 seekdb
    sddctx context    按任务构建开发上下文(规格条目/代码/测试/任务状态)
    sddctx dev        将上下文提供给 MiniMax 开发助手,完成代码修改
    sddctx verify     运行目标功能测试与回归测试,结果写入 PowerContext
    sddctx status     查看/更新任务看板(PowerContext)
    sddctx resume     重启模块后读取任务状态并继续使用
    sddctx diff       生成 MiniMax 修改前后代码差异
    sddctx reset      清空本地数据(seekdb 目录),恢复业务工程初始状态
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from sddctx import __version__
from sddctx.config import Settings, redact
from sddctx.context_builder import build_context
from sddctx.importer import run_import
from sddctx.runner import run_verify
from sddctx.task_state import TaskBoard, TaskStateClient, TaskStateError, VerificationRecord

DEFAULT_TARGET_TESTS = "tests/test_order_query_filter.py"


def _settings() -> Settings:
    return Settings.load()


def cmd_import(args: argparse.Namespace) -> int:
    settings = _settings()
    result, _report = run_import(settings)
    from sddctx.importer import format_import_result  # noqa: PLC0415

    print(format_import_result(result, settings.db_query_log))
    return 0


def _check_required_sources(context, task_def: dict) -> tuple[bool, list[str]]:
    """对照 task.json 的必要来源清单核对上下文输出,返回(是否全部命中, 报告行)。"""
    entries = {item.path for item in context.spec_entries}
    files = {item.path for item in context.spec_files}
    code_paths = {item.path for item in context.code}
    test_paths = {item.path for item in context.tests}
    lines: list[str] = []
    all_ok = True

    def _covered(required: str, direct: set[str], fallback: set[str]) -> tuple[bool, str]:
        if required in direct:
            return True, "条目命中"
        parent = required.split("#")[0]
        if "#" in required and parent in fallback:
            return True, "所在规格文档已纳入上下文"
        return False, "未命中"

    for required in task_def.get("required_spec_sources", []):
        ok, how = _covered(required, entries, files)
        all_ok &= ok
        lines.append(f"  {'✔' if ok else '✘'} 规格 {required}({how})")
    for required in task_def.get("required_code_sources", []):
        ok = required in code_paths
        all_ok &= ok
        lines.append(f"  {'✔' if ok else '✘'} 代码 {required}")
    for required in task_def.get("required_test_sources", []):
        ok = required in test_paths
        all_ok &= ok
        lines.append(f"  {'✔' if ok else '✘'} 测试 {required}")
    return all_ok, lines


def cmd_context(args: argparse.Namespace) -> int:
    settings = _settings()
    context = build_context(settings, args.task, use_state=not args.no_state)
    output_text = context.to_markdown()
    if args.out:
        out_path = Path(args.out)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(output_text, encoding="utf-8")
    if args.check:
        task_def = json.loads(Path(args.check).read_text(encoding="utf-8"))
        all_ok, lines = _check_required_sources(context, task_def)
        report = ["# 上下文必要来源核对", f"- 任务: {args.task}", f"- 清单: {args.check}", ""] + lines
        report.append(f"\n结论:{'必要来源全部包含 ✔' if all_ok else '存在缺失 ✘'}")
        report_text = "\n".join(report)
        print(report_text)
        if args.out:
            check_path = Path(str(args.out)).with_suffix(".check.md")
            check_path.write_text(report_text, encoding="utf-8")
        return 0 if all_ok else 1
    if args.json:
        print(json.dumps(context.to_json(include_content=True), ensure_ascii=False, indent=2))
    else:
        if args.out:
            print(f"上下文已写入 {args.out}")
        print(output_text)
    return 0


def cmd_dev(args: argparse.Namespace) -> int:
    settings = _settings()
    from sddctx.agent import MiniMaxError, run_dev  # noqa: PLC0415

    try:
        result = run_dev(settings, args.task, args.task_id, Path(args.run_dir) if args.run_dir else None)
    except MiniMaxError as error:
        print(f"[dev 失败] {error}", file=sys.stderr)
        return 2
    print(result.summary)
    print(f"代码差异已生成: {result.run_dir / 'code.diff.md'}")
    print(f"下一步: 运行 `sddctx verify --task-id {args.task_id} --phase after` 验证修改。")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    settings = _settings()
    targets = [part.strip() for part in args.target_tests.split(",") if part.strip()]
    outcome = run_verify(settings, args.task_id, targets, args.phase, skip_regression=args.skip_regression)
    print(outcome.summary)
    return 0 if outcome.accepted else 1


def cmd_status(args: argparse.Namespace) -> int:
    settings = _settings()
    state = TaskStateClient(settings)
    if args.set_board:
        payload = json.loads(Path(args.set_board).read_text(encoding="utf-8"))
        board = TaskBoard.model_validate(payload)
        citation = state.remember_board(board)
        print(f"任务看板已写入 PowerContext: {json.dumps(citation, ensure_ascii=False)}")
        return 0
    if args.complete is not None or args.pending is not None:
        board = state.load_board(args.task_id)
        if board is None:
            board = TaskBoard(
                task_id=args.task_id or "task-001",
                objective=args.objective or "(未填写目标;可用 --objective 指定或 --set-board 覆盖)",
            )
        for item in args.complete or []:
            if item not in board.completed:
                board.completed.append(item)
            if item in board.pending:
                board.pending.remove(item)
        for item in args.pending or []:
            if item not in board.pending and item not in board.completed:
                board.pending.append(item)
        citation = state.remember_board(board)
        print(f"任务看板已更新并写入 PowerContext: {json.dumps(citation, ensure_ascii=False)}")
    board = state.load_board(args.task_id)
    if board is None:
        print(f"(任务 {args.task_id or '(最新)'} 暂无已保存的看板)")
        return 0
    print(json.dumps(board.model_dump(mode="json"), ensure_ascii=False, indent=2))
    return 0


def cmd_resume(args: argparse.Namespace) -> int:
    """重启复用验收点:新进程读取 PowerContext 状态并用于后续处理。"""
    settings = _settings()
    state = TaskStateClient(settings)
    try:
        board = state.load_board(args.task_id)
        verifications = state.load_verifications(args.task_id)
        dev_runs = state.load_dev_runs(args.task_id)
    except TaskStateError as error:
        print(f"[resume 失败] {error}", file=sys.stderr)
        return 2
    print("# 任务恢复(重启后从 PowerContext 读取)")
    if board is None:
        print(f"(任务 {args.task_id or '(最新)'} 无已保存状态)")
        return 1
    print(f"- 任务编号: {board.task_id}")
    print(f"- 目标: {board.objective}")
    print("- 已完成:")
    for item in board.completed:
        print(f"  ✔ {item}")
    print("- 待办:")
    for item in board.pending:
        print(f"  ▶ {item}")
    print("- 已有验证结果(来自 PowerContext Memory):")
    for record in verifications:
        print(f"  [{record.phase}] {'通过' if record.passed else '未通过'} — {record.detail or record.command}(日志: {record.log_path})")
    if dev_runs:
        print("- MiniMax 开发记录(来自 PowerContext Memory):")
        for run in dev_runs:
            files = ", ".join(item.get("path", "?") for item in run.get("applied_files", [])) or "(无)"
            print(f"  [{run.get('executed_at', '?')}] 模型 {run.get('model', '?')} 修改 {files}(日志: {run.get('devlog_file', '?')})")
    # 复用:把恢复的状态用于构建当前上下文
    context = build_context(settings, board.objective, use_state=True)
    context_path = settings.records_dir / "resume-context.md"
    context_path.write_text(context.to_markdown(), encoding="utf-8")
    print(f"- 已基于恢复的状态重建开发上下文: {context_path}")
    remaining = ", ".join(board.pending) if board.pending else "(无)"
    print(f"- 后续处理建议: 剩余待办 → {remaining}")
    return 0


def cmd_diff(args: argparse.Namespace) -> int:
    settings = _settings()
    from sddctx.agent import write_diff  # noqa: PLC0415

    diff_path = write_diff(Path(args.run_dir), settings)
    print(f"代码差异已写入: {diff_path}")
    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    settings = _settings()
    if not args.force:
        answer = input(f"将删除 seekdb 数据目录 {settings.seekdb_path} 与记录目录 {settings.records_dir} 的生成内容,继续? [y/N] ")
        if answer.strip().lower() != "y":
            print("已取消。")
            return 0
    shutil.rmtree(settings.seekdb_path, ignore_errors=True)
    for generated in (
        settings.db_query_log,
        settings.powercontext_log,
        settings.records_dir / "resume-context.md",
    ):
        generated.unlink(missing_ok=True)
    for sub in ("minimax", "verify", "spec-update-demo"):
        shutil.rmtree(settings.records_dir / sub, ignore_errors=True)
    print("已重置:seekdb 数据目录与生成记录已清空;规格与业务工程保持初始状态。")
    print("提示:业务工程若有修改,可用 `git checkout -- minimax/sample-project` 恢复;")
    print("PowerContext Server 的状态如需一并清空,先停服后 `rm -rf .sddctx-data/powercontext` 再重启。")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    """体检:依次检查 seekdb、库内资产、PowerContext、MiniMax 配置与业务工程测试收集。"""
    settings = _settings()
    results: list[tuple[str, str, str]] = []  # (状态, 项目, 说明)

    # 1. seekdb 可用性
    try:
        from sddctx.seekdb_store import AssetStore  # noqa: PLC0415
        import asyncio  # noqa: PLC0415

        async def _probe() -> int:
            async with AssetStore(settings.seekdb_path) as store:
                return await store.count()

        count = asyncio.run(_probe())
        results.append(("ok" if count else "warn", "seekdb", f"可用;库内资产 {count} 条" + ("" if count else "(尚未导入,先运行 sddctx import)")))
    except Exception as error:  # noqa: BLE001
        results.append(("fail", "seekdb", f"不可用:{error}"))

    # 2. PowerContext Server
    try:
        import httpx  # noqa: PLC0415

        response = httpx.get(settings.powercontext_url.rstrip("/") + "/health/ready", timeout=5)
        ok = response.status_code == 200
        results.append(("ok" if ok else "fail", "PowerContext Server", f"{settings.powercontext_url} → HTTP {response.status_code}"))
    except Exception as error:  # noqa: BLE001
        results.append(("warn", "PowerContext Server", f"不可达({settings.powercontext_url}):{error};状态保存/复用将不可用"))
        results.append(("skip", "PowerContext scope", "依赖 Server"))
    else:
        try:
            state = TaskStateClient(settings)
            scope_id = state.ensure_scope()
            results.append(("ok", "PowerContext scope", f"就绪(scope_id={scope_id})"))
        except TaskStateError as error:
            results.append(("fail", "PowerContext scope", str(error)))

    # 3. MiniMax 配置
    if settings.minimax_api_key:
        results.append(("ok", "MiniMax API Key", f"已配置({redact(settings.minimax_api_key)})"))
    else:
        results.append(("warn", "MiniMax API Key", "未配置;仅影响 sddctx dev 步骤"))
    results.append(("ok", "MiniMax 接入点/模型", f"{settings.minimax_base_url} / {settings.minimax_model}"))

    # 4. 业务工程测试可收集
    try:
        import subprocess  # noqa: PLC0415
        import sys as _sys  # noqa: PLC0415

        probe = subprocess.run(
            [_sys.executable, "-m", "pytest", "tests", "--collect-only", "-q"],
            cwd=settings.sample_project_dir,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            env={**dict(__import__("os").environ), "PYTHONPATH": str(settings.sample_project_dir / "src")},
        )
        # -q 聚合输出形如 "tests/test_pricing.py: 5";逐行累加数量,兜底数 "::" 行
        collected = 0
        for line in probe.stdout.splitlines():
            line = line.strip()
            if "::" in line:
                collected += 1
            elif line and ":" in line and line.rsplit(":", 1)[1].strip().isdigit():
                collected += int(line.rsplit(":", 1)[1].strip())
        results.append(("ok" if probe.returncode == 0 else "fail", "业务工程测试", f"可收集 {collected} 个用例(exit={probe.returncode})"))
    except Exception as error:  # noqa: BLE001
        results.append(("fail", "业务工程测试", str(error)))

    symbols = {"ok": "✔", "warn": "▲", "fail": "✘", "skip": "—"}
    failed = 0
    print("# sddctx 体检")
    for status, item, detail in results:
        print(f"{symbols[status]} {item}: {detail}")
        if status == "fail":
            failed += 1
    print(f"\n结论:{'存在 ' + str(failed) + ' 项失败,请先修复' if failed else '可以运行验证样例(warn 项按说明处理)'}")
    return 1 if failed else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="sddctx", description="SDD 上下文管理系统(见 minimax/README.md)")
    parser.add_argument("--version", action="version", version=f"sddctx {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("import", help="导入规格/代码/测试资料到 seekdb")
    p.set_defaults(func=cmd_import)

    p = sub.add_parser("context", help="按任务构建开发上下文")
    p.add_argument("--task", required=True, help="开发任务的自然语言描述")
    p.add_argument("--out", help="同时写入 markdown 文件")
    p.add_argument("--json", action="store_true", help="以 JSON 输出(含检索审计)")
    p.add_argument("--check", metavar="TASK_JSON", help="对照任务清单 JSON 核对必要规格/代码/测试来源(便于评审核对)")
    p.add_argument("--no-state", action="store_true", help="不读取 PowerContext 任务状态")
    p.set_defaults(func=cmd_context)

    p = sub.add_parser("dev", help="调用 MiniMax 完成代码修改(需要 SDDCTX_MINIMAX_API_KEY)")
    p.add_argument("--task", required=True, help="开发任务的自然语言描述")
    p.add_argument("--task-id", default="task-001", help="任务编号(用于状态保存)")
    p.add_argument("--run-dir", help="运行产物目录(默认 records/minimax/<task>-<时间戳>)")
    p.set_defaults(func=cmd_dev)

    p = sub.add_parser("verify", help="运行目标/回归测试并保存验证结果")
    p.add_argument("--task-id", default="task-001")
    p.add_argument("--phase", choices=("before", "after"), required=True)
    p.add_argument("--target-tests", default=DEFAULT_TARGET_TESTS, help="逗号分隔的目标测试路径")
    p.add_argument("--skip-regression", action="store_true", help="跳过回归测试(仅 before 阶段调试用)")
    p.set_defaults(func=cmd_verify)

    p = sub.add_parser("status", help="查看/更新任务看板(PowerContext)")
    p.add_argument("--task-id", default=None)
    p.add_argument("--set-board", help="从 JSON 文件写入完整看板")
    p.add_argument("--objective", help="首次创建看板时的任务目标")
    p.add_argument("--complete", nargs="*", help="标记完成的事项")
    p.add_argument("--pending", nargs="*", help="新增待办事项")
    p.set_defaults(func=cmd_status)

    p = sub.add_parser("resume", help="重启后从 PowerContext 恢复任务状态")
    p.add_argument("--task-id", default=None)
    p.set_defaults(func=cmd_resume)

    p = sub.add_parser("diff", help="生成 MiniMax 修改前后的代码差异")
    p.add_argument("--run-dir", required=True)
    p.set_defaults(func=cmd_diff)

    p = sub.add_parser("reset", help="清空 seekdb 数据与生成记录")
    p.add_argument("--force", action="store_true")
    p.set_defaults(func=cmd_reset)

    p = sub.add_parser("doctor", help="体检:seekdb/PowerContext/MiniMax/业务工程就绪检查")
    p.set_defaults(func=cmd_doctor)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
