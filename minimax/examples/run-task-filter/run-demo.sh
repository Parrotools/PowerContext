#!/usr/bin/env bash
# 一键验证样例:重置 → 导入 → 上下文 → before 验证 → (可选)MiniMax dev → after 验证 → resume
# 用法:
#   bash examples/run-task-filter/run-demo.sh                # 不含 MiniMax 步骤
#   SDDCTX_MINIMAX_API_KEY=sk-xxx bash examples/run-task-filter/run-demo.sh   # 完整流程
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOME_DIR="$(cd "$HERE/../.." && pwd)"
cd "$HOME_DIR"

TASK="为订单查询增加最小金额筛选条件:customer_orders 支持 min_total 参数,含边界,不影响既有调用"
TASK_ID="task-001"
SDDCTX=".venv/bin/sddctx"

step() { printf '\n========== %s ==========\n' "$1"; }

step "0/7 重置(从空状态开始)"
$SDDCTX reset --force

step "1/7 导入工程资料到 seekdb"
$SDDCTX import

step "2/7 构建开发上下文"
$SDDCTX context --task "$TASK" --out records/context-task-001.md
$SDDCTX context --task "$TASK" --json > records/context-task-001.json
sed -n '1,40p' records/context-task-001.md

step "3/7 修改前验证(目标行为未实现,预期失败)"
$SDDCTX verify --task-id "$TASK_ID" --phase before || true

step "4/7 保存任务进展(PowerContext)"
$SDDCTX status --task-id "$TASK_ID" --objective "$TASK" \
  --complete "导入规格/代码/测试资料到 seekdb" "构建开发上下文并确认规格条目" "修改前运行目标测试并记录失败" \
  --pending "MiniMax 完成代码修改" "修改后运行目标测试与回归测试"

if [[ -n "${SDDCTX_MINIMAX_API_KEY:-}" ]]; then
  step "5/7 MiniMax 完成代码修改"
  $SDDCTX dev --task "$TASK" --task-id "$TASK_ID"
  step "6/7 修改后验证(目标 + 回归)"
  $SDDCTX verify --task-id "$TASK_ID" --phase after
else
  step "5/7 (跳过 MiniMax:未设置 SDDCTX_MINIMAX_API_KEY)"
  step "6/7 (跳过 after 验证:代码尚未修改)"
fi

step "7/7 重启复用:新进程读取 PowerContext 状态并重建上下文"
$SDDCTX resume --task-id "$TASK_ID"

printf '\n完成。产物:records/(MiniMax 开发记录/验证日志/查询与状态记录)。\n'
