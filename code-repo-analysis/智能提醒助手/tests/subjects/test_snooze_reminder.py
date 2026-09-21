"""业务主体：延后提醒（POST /internal/v1/reminders/{decision_id}/snooze）。

用例数据见 tests/cases/snooze_reminder.json，本文件只声明主体与运行方式。
"""

from __future__ import annotations

import pytest

from tests.common.api_client import ApiClient
from tests.common.case_loader import load_subject
from tests.common.subject_runner import decorate, execute

SUBJECT = load_subject("snooze_reminder")


@pytest.mark.subject
@pytest.mark.parametrize("api_case", SUBJECT.cases, ids=SUBJECT.case_ids)
def test_snooze_reminder(api_client: ApiClient, api_case: dict) -> None:
    decorate(SUBJECT, api_case, epic="智能提醒助手")
    execute(api_client, SUBJECT, api_case)
