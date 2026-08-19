#!/usr/bin/env bash
# 修复 Codex "brew upgrade --cask codex: Cask not installed" 问题
# 根因：Codex 是 npm 全局安装，但 codex update 误判为 brew，导致更新走错分支。
set -uo pipefail

echo "==> 当前 codex 版本: $(codex --version 2>/dev/null || echo '未检测到 codex')"

if brew list --cask codex >/dev/null 2>&1; then
    echo "==> 检测到 brew cask 安装，使用 brew 更新"
    brew upgrade --cask codex
    rc=$?
else
    echo "==> 检测到 npm 安装（或未装 brew cask），使用 npm 更新"
    npm install -g @openai/codex@latest --no-audit --no-fund
    rc=$?
    if [ "$rc" -ne 0 ]; then
        echo "==> npm 直接安装失败，尝试 sudo 重试（会提示输入密码）"
        sudo npm install -g @openai/codex@latest --no-audit --no-fund
        rc=$?
    fi
fi

if [ "$rc" -ne 0 ]; then
    echo "==> 更新失败，请手动执行: npm install -g @openai/codex@latest"
    exit "$rc"
fi

echo "==> 更新完成，新版本: $(codex --version)"
echo "==> 提示：后续更新请继续用 npm；若希望 codex update 生效，可改用 brew install --cask codex 统一管理"
