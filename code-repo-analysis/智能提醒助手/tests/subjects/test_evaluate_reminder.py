"""业务主体：提醒评估接口（POST /internal/v1/reminders/evaluate）。"""

from __future__ import annotations

import allure
import pytest

from tests.common.api_client import ApiClient
from tests.common.case_loader import load_subject
from tests.common.case_runner import render_diff, run_case
from tests.common.report import attach_case, attach_diffs, attach_exchange

SUBJECT = load_subject("evaluate_reminder")

SEVERITY = {"P0": allure.severity_level.CRITICAL, "P1": allure.severity_level.NORMAL, "P2": allure.severity_level.MINOR}


def _decorate(case: dict) -> None:
    allure.dynamic.epic("智能提醒助手")
    allure.dynamic.feature(f"业务主体 {SUBJECT.subject}")
    allure.dynamic.story(SUBJECT.description)
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


@pytest.mark.subject
@pytest.mark.parametrize("api_case", SUBJECT.cases, ids=SUBJECT.case_ids)
def test_evaluate_reminder(api_client: ApiClient, api_case: dict) -> None:
    _decorate(api_case)
    attach_case(api_case)

    if api_case.get("pending"):
        pytest.skip(f"待确认预期值：{api_case.get('pending_reason', '未说明原因')}")

    with allure.step("执行用例步骤"):
        results = run_case(api_client, SUBJECT.endpoint, api_case)

    for index, result in enumerate(results, start=1):
        with allure.step(f"步骤 {index}：{result.name}"):
            attach_exchange(result.response)
            attach_diffs(result.diffs)

    assert all(result.passed for result in results), render_diff(api_case, results)
