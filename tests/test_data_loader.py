from __future__ import annotations

from pathlib import Path

import pytest

from framework.config.environment import EnvironmentConfig, load_cases


def test_load_cases_only_loads_requested_environment(tmp_path) -> None:
    (tmp_path / "users.test.json").write_text('[{"id": "test_case", "steps": [{}]}]', encoding="utf-8")
    (tmp_path / "users.prod.json").write_text('[{"id": "prod_case", "steps": [{}]}]', encoding="utf-8")
    cases = load_cases("test", tmp_path)
    assert [case["id"] for case in cases] == ["test_case"]
    assert cases[0]["__source__"].endswith("users.test.json")


def test_environment_expands_variables_and_local_overrides(tmp_path, monkeypatch) -> None:
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    (config_dir / "environment.test.json").write_text(
        '{"http": {"base_url": "${TEST_URL}", "headers": {"X-Base": "1"}}}', encoding="utf-8"
    )
    (config_dir / "environment.test.local.json").write_text(
        '{"http": {"headers": {"Authorization": "Bearer local"}}}', encoding="utf-8"
    )
    monkeypatch.setenv("TEST_URL", "https://api.test")
    environment = EnvironmentConfig.load("test", tmp_path)
    assert environment.get("http.base_url") == "https://api.test"
    assert environment.get("http.headers") == {"X-Base": "1", "Authorization": "Bearer local"}


def test_load_cases_expands_subject_instances_and_filters_priority(tmp_path) -> None:
    (tmp_path / "bi.112.json").write_text(
        """{
          "test_case": {"id": "bi_category", "api": "bi.query", "tags": ["bi"]},
          "cases": [
            {"id": "english", "priority": "P0", "req": {"body": {"language": "en"}}, "resp": {"status_code": 200}},
            {"id": "chinese", "priority": "P2", "req": {"body": {"language": "zh-CN"}}, "resp": {"status_code": 200}}
          ]
        }""",
        encoding="utf-8",
    )

    cases = load_cases("112", tmp_path, priorities={"P0", "P1"})

    assert len(cases) == 1
    assert cases[0]["id"] == "bi_category::english"
    assert cases[0]["subject_id"] == "bi_category"
    assert cases[0]["case_id"] == "english"
    assert cases[0]["priority"] == "P0"
    assert cases[0]["steps"] == [
        {
            "name": "english",
            "request": {
                "protocol": "http",
                "api": "bi.query",
                "json": {"language": "en"},
            },
            "expect": {"status_code": 200},
        }
    ]


def test_subject_case_requires_req_resp_and_priority(tmp_path) -> None:
    (tmp_path / "invalid.112.json").write_text(
        '{"test_case":{"id":"subject","api":"bi.query"},"cases":[{"id":"missing_fields"}]}',
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="priority, req, resp"):
        load_cases("112", tmp_path)


def test_pass_api_language_cases_are_independent_and_restore_english() -> None:
    data_dir = Path(__file__).resolve().parents[1] / "test_data"

    cases = [case for case in load_cases("112", data_dir) if case.get("subject_id") == "pass_api_set_app_language"]

    assert [case["case_id"] for case in cases] == ["switch_to_chinese", "switch_to_english"]
    assert [case["steps"][0]["request"]["json"]["language"] for case in cases] == ["zh-CN", "en"]
    assert all(case["steps"][0]["request"]["api"] == "pass_api.set_app_language" for case in cases)
