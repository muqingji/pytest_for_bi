#!/bin/bash
# 安装活跃工作流统一监听器（每 30 秒扫描一次，按 workflow_run_id 隔离）。
# 用法：bash qa-agents/scripts/install-sync-timer.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PLIST_SRC="$ROOT/qa-agents/scripts/com.qa.sync-eight-card.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.qa.sync-eight-card.plist"
WATCHDOG_SRC="$ROOT/qa-agents/scripts/com.qa.sync-eight-card-watchdog.plist"
WATCHDOG_DST="$HOME/Library/LaunchAgents/com.qa.sync-eight-card-watchdog.plist"
PYTHON="$ROOT/qa-agents/.venv/bin/python"
mkdir -p "$HOME/Library/LaunchAgents"
if [[ ! -x "$PYTHON" ]]; then
  echo "错误：Python 虚拟环境不存在：$PYTHON" >&2
  exit 1
fi
sed -e "s|__ROOT__|$ROOT|g" -e "s|__PYTHON__|$PYTHON|g" "$PLIST_SRC" > "$PLIST_DST"
sed -e "s|__ROOT__|$ROOT|g" -e "s|__PYTHON__|$PYTHON|g" "$WATCHDOG_SRC" > "$WATCHDOG_DST"
# 重载前先确认 multica CLI 存在，避免定时器在 launchd 的最小 PATH 下
# 因找不到 multica 而每次崩溃（旧版本曾以 “skipped” 静默掩盖该错误）。
if ! command -v multica >/dev/null 2>&1; then
  echo "错误：multica CLI 不在 PATH 中，请先安装 multica 再安装定时器" >&2
  exit 1
fi
launchctl bootout gui/$(id -u)/com.qa.sync-eight-card 2>/dev/null || true
launchctl bootout gui/$(id -u)/com.qa.sync-eight-card-watchdog 2>/dev/null || true
launchctl bootstrap gui/$(id -u) "$PLIST_DST"
launchctl bootstrap gui/$(id -u) "$WATCHDOG_DST"
launchctl enable gui/$(id -u)/com.qa.sync-eight-card
launchctl enable gui/$(id -u)/com.qa.sync-eight-card-watchdog
echo "已安装 monitor（30 秒）和 watchdog（60 秒）"
echo "日志：/tmp/qa-sync-eight-card.out.log"
echo "卸载：launchctl bootout gui/$(id -u)/com.qa.sync-eight-card; launchctl bootout gui/$(id -u)/com.qa.sync-eight-card-watchdog"
