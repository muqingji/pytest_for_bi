#!/usr/bin/env bash
# 把仓库内的本地 Go 工具链接入当前 shell。
# 用法： source scripts/go-env.sh
# 说明： 工具链安装在仓库根目录的 .cache/ 下，不写系统目录，因此无需 sudo。
set -u

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPO_ROOT="$(cd "$PROJECT_DIR/../.." && pwd)"
TOOLCHAIN_ENV="$REPO_ROOT/.cache/go-env.sh"

if [ ! -f "$TOOLCHAIN_ENV" ]; then
  echo "找不到本地 Go 工具链环境文件：$TOOLCHAIN_ENV" >&2
  echo "请先重新执行环境搭建，或改用系统已安装的 go。" >&2
  return 1 2>/dev/null || exit 1
fi

# shellcheck disable=SC1090
. "$TOOLCHAIN_ENV"

echo "Go      : $(go version)"
echo "GOROOT  : $GOROOT"
echo "GOPATH  : $GOPATH"
echo "GOPROXY : $GOPROXY"
if command -v dlv >/dev/null 2>&1; then
  echo "Delve   : $(dlv version | sed -n 2p | tr -s ' ')"
else
  echo "Delve   : 未安装（调试需要 dlv）"
fi
