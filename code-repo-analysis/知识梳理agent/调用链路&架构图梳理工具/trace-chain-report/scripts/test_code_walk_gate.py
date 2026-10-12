#!/usr/bin/env python3
"""Regression: a call must be pinned to the implementation file, not the interface."""

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
        f"1. fs-crm-workflow ApprovalDefinitionApprovalActionImpl.getDefinition\n文件：{impl}\n这里调用 approvalDefinitionService.getWorkflow。\n",
        impl,
    )
    if not any("without source.calls" in item or "declaration file" in item for item in bad):
        raise SystemExit(f"bug pattern was not rejected: {bad}")
    good_detail = (
        f"接口文件 {iface} 第 49 行没有 approvalDefinitionService.getWorkflow。"
        f"第 191 行调用 approvalDefinitionService.getWorkflow。文件 {impl}。"
    )
    good_section = (
        f"1. fs-crm-workflow ApprovalDefinitionAction.getDefinition\n文件：{iface}:49\n这里没有这次调用。\n"
        f"2. fs-crm-workflow ApprovalDefinitionApprovalActionImpl.getDefinition\n文件：{impl}\n"
        "第 191 行调用 approvalDefinitionService.getWorkflow。\n"
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
        raise SystemExit(f"correct call site was rejected: {good}")
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
