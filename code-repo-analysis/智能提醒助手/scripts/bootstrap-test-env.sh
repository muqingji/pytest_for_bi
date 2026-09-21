#!/usr/bin/env bash
# 在本项目包内创建独立的 pytest 运行环境（不写系统目录，不与仓库根 .venv 共享）。
# 用法： bash scripts/bootstrap-test-env.sh [--force]
set -euo pipefail

PACKAGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_DIR="$PACKAGE_DIR/.testenv"
REQUIREMENTS="$PACKAGE_DIR/requirements-test.txt"

pick_python() {
  for candidate in "${PYTHON_BIN:-}" python3.11 python3.12 python3.13 python3; do
    [ -n "$candidate" ] || continue
    if command -v "$candidate" >/dev/null 2>&1; then
      echo "$candidate"
      return 0
    fi
  done
  echo "找不到可用的 Python 解释器（需要 3.9+）" >&2
  return 1
}

PYTHON="$(pick_python)"
echo "使用 Python: $($PYTHON --version 2>&1)（$PYTHON）"

if [ "${1:-}" = "--force" ] && [ -d "$VENV_DIR" ]; then
  rm -rf "$VENV_DIR"
fi

if [ ! -d "$VENV_DIR" ]; then
  "$PYTHON" -m venv "$VENV_DIR"
  echo "已创建虚拟环境: $VENV_DIR"
fi

"$VENV_DIR/bin/python" -m pip install --quiet --upgrade pip
"$VENV_DIR/bin/python" -m pip install --quiet -r "$REQUIREMENTS"

echo "--- 已安装依赖 ---"
"$VENV_DIR/bin/python" -m pip list | grep -Ei "pytest|allure|requests" || true
echo "--- 环境就绪 ---"
echo "Python: $("$VENV_DIR/bin/python" --version 2>&1)"
echo "环境目录: $VENV_DIR"
