from __future__ import annotations

import pytest

from framework.config.environment import load_cases


def test_result_set_filter_detail_with_owned_metric_in_112(environment, case_runner) -> None:
    if environment.name != "112":
        pytest.skip("real test-data lifecycle runs only with --env=112")
    case = next(
        item
        for item in load_cases("112")
        if item["id"] == "CASE-FUNC-RESULT-FILTER-DETAIL-112"
    )

    context = case_runner.execute(case)

    assert context["__lifecycle__"]["setup"][0]["status"] == "completed"
    assert context["__lifecycle__"]["readiness"][0]["status"] == "completed"
    assert context["__lifecycle__"]["test"][0]["status"] == "completed"
    assert context["__lifecycle__"]["cleanup"][0]["status"] == "completed"
    assert "s307011535" in str(context["test_response"])
    assert context["metric_name"] in str(context["test_response"])
