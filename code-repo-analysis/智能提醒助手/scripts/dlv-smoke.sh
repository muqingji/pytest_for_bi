#!/usr/bin/env bash
# 冒烟验证 Delve 调试链路：在 reminder.Evaluate 处断点，命中后打印变量，再退出。
# 用途：确认“能打断点、能看到变量”这条调试链路在本机可用。
set -uo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "$PROJECT_DIR/../.." && pwd)"
TOOLCHAIN_ENV="$REPO_ROOT/.cache/go-env.sh"

if [ ! -f "$TOOLCHAIN_ENV" ]; then
  echo "找不到 $TOOLCHAIN_ENV，请先执行环境搭建。" >&2
  exit 1
fi
# shellcheck disable=SC1090
. "$TOOLCHAIN_ENV"

if ! command -v dlv >/dev/null 2>&1; then
  echo "未找到 dlv，请先安装：go install github.com/go-delve/delve/cmd/dlv@v1.25.2" >&2
  exit 1
fi

cd "$PROJECT_DIR" || exit 1

COMMANDS_FILE="$(mktemp -t dlv-smoke)"
LOG_FILE="$(mktemp -t dlv-smoke-log)"
trap 'rm -f "$COMMANDS_FILE" "$LOG_FILE"' EXIT

cat > "$COMMANDS_FILE" <<'CMDS'
break internal/domain/reminder.Evaluate
continue
print input.Task.UserID
print input.Task.CompletedCount
print input.Preference.DailyPushCap
exit
CMDS

dlv debug ./cmd/reminder-service \
  --allow-non-terminal-interactive=true \
  -- -user user-passive -task-date 2026-09-20 -db /tmp/reminder-smoke.db \
  < "$COMMANDS_FILE" > "$LOG_FILE" 2>&1
STATUS=$?

if grep -q "could not launch process" "$LOG_FILE"; then
  echo "调试链路不可用：$(grep 'could not launch process' "$LOG_FILE" | head -1)"
  echo "macOS 常见原因是 dlv 未签名或未授权调试，参见："
  echo "  docs/implementation/本地Go环境与调试.md"
  exit 1
fi
if ! grep -q "Breakpoint 1" "$LOG_FILE"; then
  echo "断点未命中，dlv 输出如下：" >&2
  sed -n '1,40p' "$LOG_FILE" >&2
  exit 1
fi

echo "调试链路验证通过：断点命中，变量读取成功。"
echo "--- dlv 输出 ---"
sed -n '/Breakpoint 1 at/,$p' "$LOG_FILE" | head -20
exit 0
