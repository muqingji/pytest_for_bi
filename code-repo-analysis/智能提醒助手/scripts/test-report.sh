#!/usr/bin/env bash
# 业务测试入口：用包内独立 pytest 环境跑用例，并用 Allure 生成 HTML 报告。
#
# 用法：
#   bash scripts/test-report.sh                 # 只跑业务测试（-m subject）
#   bash scripts/test-report.sh -m harness      # 只跑测试环境自检
#   bash scripts/test-report.sh -k EVAL-001     # 透传 pytest 参数
#
# 报告产物：
#   reports/allure-results   Allure 原始结果（附件、环境信息）
#   reports/allure-report    Allure HTML（allure generate 产物）
set -euo pipefail

PACKAGE_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV_PYTEST="$PACKAGE_DIR/.testenv/bin/pytest"
REPORTS_DIR="$PACKAGE_DIR/reports"
RESULTS_DIR="${ALLURE_RESULTS_DIR:-$REPORTS_DIR/allure-results}"
REPORT_DIR="${ALLURE_REPORT_DIR:-$REPORTS_DIR/allure-report}"

if [ "$#" -gt 0 ]; then
  PYTEST_ARGS=("$@")
else
  PYTEST_ARGS=(-m subject)
fi

resolve_java() {
  if command -v java >/dev/null 2>&1 && java -version >/dev/null 2>&1; then
    return 0
  fi
  local brew_prefix
  brew_prefix="$(brew --prefix openjdk 2>/dev/null || true)"
  for candidate in /usr/local/opt/openjdk/bin /opt/homebrew/opt/openjdk/bin "${brew_prefix:+$brew_prefix/bin}"; do
    [ -n "$candidate" ] || continue
    if [ -x "$candidate/java" ]; then
      export PATH="$candidate:$PATH"
      return 0
    fi
  done
  return 1
}

if [ ! -x "$VENV_PYTEST" ]; then
  echo "未找到包内独立测试环境：$VENV_PYTEST" >&2
  echo "先执行： bash scripts/bootstrap-test-env.sh" >&2
  exit 1
fi

echo "=== 1/2 运行 pytest ==="
echo "用例参数： ${PYTEST_ARGS[*]}"
cd "$PACKAGE_DIR"
set +e
"$VENV_PYTEST" --alluredir="$RESULTS_DIR" --clean-alluredir "${PYTEST_ARGS[@]}"
STATUS=$?
set -e
echo "pytest 退出码： $STATUS（0 通过，1 有用例失败，其他见 pytest 输出）"

echo
echo "=== 2/2 生成 Allure HTML 报告 ==="
if ! command -v allure >/dev/null 2>&1; then
  echo "未找到 allure CLI，已保留原始结果：$RESULTS_DIR" >&2
  echo "安装方式： brew install allure" >&2
  exit "$STATUS"
fi

if ! resolve_java; then
  echo "未找到可用的 Java 运行时，无法生成 HTML；已保留原始结果：$RESULTS_DIR" >&2
  echo "安装方式： brew install openjdk" >&2
  exit "$STATUS"
fi

allure generate "$RESULTS_DIR" --clean --output "$REPORT_DIR" >/dev/null
echo "报告目录： $REPORT_DIR"
echo "本地打开： allure open $REPORT_DIR"
exit "$STATUS"
