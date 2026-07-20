from __future__ import annotations

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
