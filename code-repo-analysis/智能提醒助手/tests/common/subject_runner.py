"""业务主体用例的公共执行体：业务测试与测试环境自检共用同一套执行路径。

两条路径共用本模块，保证“环境自检通过”确实等于“业务用例的管道是通的”。
"""

from __future__ import annotations

from typing import Any

import allure
import pytest

from tests.common.api_client import ApiClient
from tests.common.case_loader import SubjectData
from tests.common.case_runner import render_diff, run_case
from tests.common.report import attach_case, attach_diffs, attach_exchange

SEVERITY = {
    "P0": allure.severity_level.CRITICAL,
    "P1": allure.severity_level.NORMAL,
    "P2": allure.severity_level.MINOR,
}


def decorate(subject: SubjectData, case: dict[str, Any], *, epic: str | None = None) -> None:
    """把用例元数据写进 Allure：主体、标题、优先级、验收标准映射。"""
    if epic:
        allure.dynamic.epic(epic)
    allure.dynamic.feature(f"业务主体 {subject.subject}")
    if subject.description:
        allure.dynamic.story(subject.description)
    allure.dynamic.title(f"{case['id']} {case['name']}")
    allure.dynamic.id(case["id"])
    severity = SEVERITY.get(str(case.get("priority", "")))
    if severity:
        allure.dynamic.severity(severity)
    for ac in case.get("ac", []):
        allure.dynamic.label("ac", ac)
    for fr in case.get("fr", []):
        allure.dynamic.label("fr", fr)
    if case.get("scenario"):
        allure.dynamic.label("scenario", str(case["scenario"]))


def execute(api_client: ApiClient, subject: SubjectData, case: dict[str, Any]) -> None:
    """跑一条用例：请求接口 → 字段断言 → 断言差异与请求响应写入报告。"""
    attach_case(case)

    if case.get("pending"):
        pytest.skip(f"待确认预期值：{case.get('pending_reason', '未说明原因')}")

    with allure.step("执行用例步骤"):
        results = run_case(api_client, subject.endpoint, case)

    for index, result in enumerate(results, start=1):
        with allure.step(f"步骤 {index}：{result.name}"):
            attach_exchange(result.response)
            attach_diffs(result.diffs)

    assert all(result.passed for result in results), render_diff(case, results)
