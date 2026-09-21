"""测试环境自检：断言比较器和用例加载器本身的行为。

比较器是整个业务测试的判定核心，它出错会让业务用例静默全绿，所以单独自检。
"""

from __future__ import annotations

import pytest

from tests.common.case_loader import CaseSchemaError, load_subject
from tests.common.expectation import compare_body


@pytest.mark.harness
def test_subset_mode_ignores_extra_fields_but_exact_mode_locks_them() -> None:
    expected = {"status": "CREATED"}
    actual = {"status": "CREATED", "strategy_version": "v1"}
    assert compare_body(expected, actual, "subset") == []
    assert compare_body(expected, actual, "exact") == ["$ 出现预期外字段：['strategy_version']"]


@pytest.mark.harness
def test_type_mismatch_and_missing_field_are_reported() -> None:
    diffs = compare_body({"should_remind": True, "decision_id": "d-1"}, {"should_remind": 1}, "subset")
    assert "$.should_remind 期望 True，实际 1" in diffs
    assert any(diff.startswith("$.decision_id 缺失") for diff in diffs)


@pytest.mark.harness
def test_wildcards_accept_any_value_and_regex() -> None:
    diffs = compare_body(
        {"request_id": "$any", "decision_id": {"$regex": "^decision-[0-9a-f]{32}$"}},
        {"request_id": "8f2c1a9e", "decision_id": "decision-" + "a" * 32},
        "subset",
    )
    assert diffs == []


@pytest.mark.harness
def test_wildcards_reject_wrong_shape() -> None:
    diffs = compare_body(
        {"request_id": "$any", "decision_id": {"$regex": "^decision-[0-9a-f]{32}$"}},
        {"request_id": None, "decision_id": "decision-short"},
        "subset",
    )
    assert "$.request_id 期望任意非空值，实际为 null" in diffs
    assert any("期望匹配正则" in diff for diff in diffs)


@pytest.mark.harness
def test_array_length_is_asserted() -> None:
    assert compare_body({"events": [1, 2]}, {"events": [1]}, "subset") == ["$.events 数组长度期望 2，实际 1"]


@pytest.mark.harness
def test_case_loader_rejects_duplicate_ids(tmp_path, monkeypatch) -> None:
    from tests.common import settings as settings_module

    cases_dir = tmp_path / "cases"
    cases_dir.mkdir()
    (cases_dir / "dup.json").write_text(
        """
        {
          "subject": "dup",
          "endpoint": {"method": "POST", "path": "/x"},
          "cases": [
            {"id": "A", "name": "1", "request": {"body": {}}, "expected": {"status_code": 200, "body": {}}},
            {"id": "A", "name": "2", "request": {"body": {}}, "expected": {"status_code": 200, "body": {}}}
          ]
        }
        """,
        encoding="utf-8",
    )
    monkeypatch.setattr(settings_module, "CASES_DIR", cases_dir)
    monkeypatch.setattr("tests.common.case_loader.CASES_DIR", cases_dir)
    with pytest.raises(CaseSchemaError, match="用例 id 重复"):
        load_subject("dup")


@pytest.mark.harness
def test_case_loader_rejects_unknown_match_mode() -> None:
    subject = load_subject("evaluate_stub", subdir="_harness")
    assert subject.case_ids[0] == "STUB-001"
    assert subject.endpoint.method == "POST"
