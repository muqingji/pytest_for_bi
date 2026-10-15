#!/usr/bin/env python3
"""Regression: section 6 is a Java walk step, and calls stay on the implementation."""

from __future__ import annotations

import importlib.util
from pathlib import Path


def _load():
    path = Path(__file__).with_name("validate_report.py")
    spec = importlib.util.spec_from_file_location("validate_report", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def main() -> int:
    module = _load()
    impl = "impl/ApprovalDefinitionApprovalActionImpl.java"
    iface = "web/ApprovalDefinitionAction.java"
    bad = module.code_mapping_errors(
        "svc",
        {
            "repo": "fs-crm-workflow",
            "file": impl,
            "symbol": "ApprovalDefinitionApprovalActionImpl.getDefinition",
            "declaration_file": iface,
            "calls": [],
        },
        "这里调用 approvalDefinitionService.getWorkflow。",
        "1. 起点文件，为什么从这里读，下一步跨服务。\n",
        impl,
    )
    if not any("without source.calls" in item or "declaration file" in item for item in bad):
        raise SystemExit(f"bug pattern was not rejected: {bad}")
    if not any("Java walk step" in item for item in bad):
        raise SystemExit(f"old narrative was not rejected: {bad}")
    good_detail = (
        f"接口文件 {iface} 第 49 行没有 approvalDefinitionService.getWorkflow。"
        f"第 191 行调用 approvalDefinitionService.getWorkflow。文件 {impl}。"
    )
    good_section = (
        "### 步骤 1\n"
        "1、这一步是干什么的：获取审批定义详情。这个接口只声明入口，没有方法体。\n"
        f"2、文件绝对路径：`/repo/{iface}`\n"
        "3、（方法：getDefinition，接口：ApprovalDefinitionAction）\n"
        "### 步骤 2\n"
        "1、这一步是干什么的：组装审批定义详情。实现里读取流程定义。\n"
        f"2、文件绝对路径：`/repo/{impl}`\n"
        "3、（方法：getDefinition，接口：ApprovalDefinitionAction）\n"
    )
    good = module.code_mapping_errors(
        "svc",
        {
            "repo": "fs-crm-workflow",
            "file": impl,
            "symbol": "ApprovalDefinitionApprovalActionImpl.getDefinition",
            "declaration_file": iface,
            "declaration_line": 49,
            "calls": [{"symbol": "approvalDefinitionService.getWorkflow", "file": impl, "line": 191}],
        },
        good_detail,
        good_section,
        good_detail,
    )
    if good:
        raise SystemExit(f"correct walk step was rejected: {good}")
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
