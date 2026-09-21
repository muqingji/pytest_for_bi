"""测试环境自检：用桩服务证明整条用例管线可用。

自检通过只说明「用例文件 → HTTP 请求 → 字段断言 → 报告附件」是通的，
不构成任何业务结论；业务结论只能来自 tests/subjects/ 下对真实服务的执行。
"""

from __future__ import annotations

import allure
import pytest

from tests.common.api_client import ApiClient
from tests.common.case_loader import load_subject
from tests.common.subject_runner import decorate, execute

SUBJECT = load_subject("evaluate_stub", subdir="_harness")


@pytest.mark.harness
@pytest.mark.parametrize("api_case", SUBJECT.cases, ids=SUBJECT.case_ids)
def test_pipeline_selftest(stub_client: ApiClient, stub_base_url: str, api_case: dict) -> None:
    decorate(SUBJECT, api_case, epic="测试环境自检")
    allure.dynamic.parameter("base_url", stub_base_url)
    execute(stub_client, SUBJECT, api_case)
