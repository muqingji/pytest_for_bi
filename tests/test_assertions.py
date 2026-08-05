from __future__ import annotations

import pytest

from framework.clients.models import ApiResponse
from framework.core.assertions import assert_response, get_by_path


def test_assert_response_supports_partial_body_paths_and_schema() -> None:
    response = ApiResponse(status_code=200, body={"code": 0, "data": {"users": [{"id": 7, "name": "Ada"}]}})
    assert_response(
        response,
        {
            "status_code": 200,
            "body": {"code": 0},
            "json_path": {"data.users[0].name": "Ada"},
            "schema": {"type": "object", "required": ["code", "data"]},
        },
    )
    assert get_by_path(response.body, "data.users[0].id") == 7


def test_assert_response_reports_mismatched_values() -> None:
    with pytest.raises(AssertionError, match="expected 1"):
        assert_response(ApiResponse(status_code=200, body={"code": 0}), {"body": {"code": 1}})


def test_assert_response_finds_key_in_serialized_json_field_value() -> None:
    expected_key = "Bi.Custom.Realtime.StatName.BI_1.Label"
    response = ApiResponse(
        status_code=200,
        body={"Value": '{"items":[{"translateKey":"' + expected_key + '"}]}'},
    )

    assert_response(response, {"body_contains_keys": [expected_key]})
