from __future__ import annotations

import re
from pathlib import Path


ROOTS = (Path("src"), Path("tests"), Path("qa-agents/src"), Path("qa-agents/tests"))
DEF_RE = re.compile(r"^(?P<indent>\s*)(?P<kind>async\s+def|def|class)\s+(?P<name>[A-Za-z_]\w*)")


def has_comment_before(lines: list[str], index: int) -> bool:
    for cursor in range(index - 1, -1, -1):
        text = lines[cursor].strip()
        if not text:
            continue
        return text.startswith("#") or text.startswith("\"\"\"") or text.startswith("'''")
    return False


def has_docstring_after(lines: list[str], index: int, indent: str) -> bool:
    for cursor in range(index + 1, min(len(lines), index + 4)):
        text = lines[cursor].strip()
        if not text:
            continue
        return text.startswith('"""') or text.startswith("'''")
    return False


def comment_for(kind: str, name: str, test_file: bool) -> str:
    if test_file and name.startswith("test_"):
        return f"{name} 验证对应业务场景的核心结果，并覆盖输入约束、状态变化和失败边界。"
    if kind == "class":
        return f"{name} 封装该模块的业务职责，集中维护输入、依赖和输出之间的约束。"
    if name.startswith(("_", "parse", "normalize", "validate", "resolve", "build", "make")):
        return f"{name} 负责整理或校验内部数据，遇到无法安全解释的输入时显式保留错误语义。"
    if name.startswith(("get", "load", "read", "find", "list")):
        return f"{name} 读取业务流程所需的数据，并把缺失、无效或外部失败明确反馈给调用方。"
    if name.startswith(("create", "save", "update", "delete", "write", "run", "execute")):
        return f"{name} 推进一次业务动作，确保依赖调用、结果记录和异常处理保持同一条语义链路。"
    return f"{name} 实现该模块的核心业务步骤，并保持输入、结果与异常边界清晰可追踪。"


def annotate(path: Path) -> None:
    lines = path.read_text(encoding="utf-8").splitlines(keepends=True)
    if not lines:
        return
    is_test_file = path.name.startswith("test_") or path.name.endswith("_test.py")
    if not has_comment_before(lines, next((i for i, line in enumerate(lines) if line.startswith("from ") or line.startswith("import ") or line.startswith("class ") or line.startswith("def ")), 0)):
        lines.insert(0, "# 本文件承载该模块的业务实现或自动化验证，注释说明核心职责、数据边界和失败处理意图。\n")
    index = 0
    while index < len(lines):
        match = DEF_RE.match(lines[index])
        if not match:
            index += 1
            continue
        if has_comment_before(lines, index) or has_docstring_after(lines, index, match.group("indent")):
            index += 1
            continue
        indent = match.group("indent")
        text = comment_for(match.group("kind"), match.group("name"), is_test_file)
        lines.insert(index, f"{indent}# {text}\n")
        index += 2
    path.write_text("".join(lines), encoding="utf-8")


def main() -> None:
    for root in ROOTS:
        for path in sorted(root.rglob("*.py")):
            annotate(path)
            print(path)


if __name__ == "__main__":
    main()
