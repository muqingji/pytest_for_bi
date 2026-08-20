#!/bin/bash
# 安装 8 卡流程本地同步定时器（每 2 分钟自动跑一次同步，幂等）。
# 用法：bash qa-agents/scripts/install-sync-timer.sh
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PLIST_SRC="$ROOT/qa-agents/scripts/com.qa.sync-eight-card.plist"
PLIST_DST="$HOME/Library/LaunchAgents/com.qa.sync-eight-card.plist"
mkdir -p "$HOME/Library/LaunchAgents"
cp "$PLIST_SRC" "$PLIST_DST"
# 重载前先确认 multica CLI 存在，避免定时器在 launchd 的最小 PATH 下
# 因找不到 multica 而每次崩溃（旧版本曾以 “skipped” 静默掩盖该错误）。
if ! command -v multica >/dev/null 2>&1; then
  echo "错误：multica CLI 不在 PATH 中，请先安装 multica 再安装定时器" >&2
  exit 1
fi
launchctl bootout gui/$(id -u)/com.qa.sync-eight-card 2>/dev/null || true
launchctl bootstrap gui/$(id -u) "$PLIST_DST"
launchctl enable gui/$(id -u)/com.qa.sync-eight-card
echo "已安装并启动 com.qa.sync-eight-card（每 120 秒同步一次）"
echo "日志：/tmp/qa-sync-eight-card.out.log"
echo "卸载：launchctl bootout gui/$(id -u)/com.qa.sync-eight-card && rm -f $PLIST_DST"
