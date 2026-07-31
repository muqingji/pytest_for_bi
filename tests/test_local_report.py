from __future__ import annotations

import json
from pathlib import Path

from scripts.print_allure_report import LocalReportRenderer, _redact_text


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


def test_local_report_prints_case_steps_attachments_and_summary(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "request-attachment.json",
        {"api": "bi.query", "token": "secret-token", "body": {"language": "en"}},
    )
    _write_json(
        tmp_path / "case-result.json",
        {
            "name": "test_case[translation_chart_stat[P1]]",
            "status": "passed",
            "start": 1000,
            "stop": 1125,
            "parameters": [
                {
                    "name": "api_case",
                    "value": "{'id': 'translation_chart_stat', 'name': '图表配置-统计图', 'priority': 'P1'}",
                }
            ],
            "steps": [
                {
                    "name": "查询统计图翻译项",
                    "status": "passed",
                    "start": 1000,
                    "stop": 1120,
                    "attachments": [{"name": "request", "source": "request-attachment.json"}],
                    "steps": [
                        {
                            "name": "响应断言：HTTP 200",
                            "status": "passed",
                            "start": 1110,
                            "stop": 1120,
                        }
                    ],
                }
            ],
        },
    )

    report = LocalReportRenderer(tmp_path).render(LocalReportRenderer(tmp_path).load_results())

    assert "[PASS] 图表配置-统计图" in report
    assert "ID: translation_chart_stat" in report
    assert "步骤: 查询统计图翻译项 (120ms)" in report
    assert "响应断言：HTTP 200" in report
    assert '"token": "***REDACTED***"' in report
    assert "通过 1 / 失败 0 / 异常 0 / 跳过 0 / 共 1 条" in report


def test_local_report_includes_failure_and_truncates_large_attachment(tmp_path: Path) -> None:
    _write_json(tmp_path / "response-attachment.json", {"body": "x" * 200})
    _write_json(
        tmp_path / "failed-result.json",
        {
            "name": "test_failed",
            "status": "failed",
            "start": 1000,
            "stop": 1050,
            "attachments": [{"name": "response", "source": "response-attachment.json"}],
            "statusDetails": {"message": "expected 200, got 500", "trace": "trace details"},
        },
    )

    renderer = LocalReportRenderer(tmp_path, max_attachment_chars=80)
    report = renderer.render(renderer.load_results())

    assert "[FAIL] test_failed" in report
    assert "expected 200, got 500" in report
    assert "trace details" in report
    assert "已省略" in report
    assert "未通过用例:" in report


def test_local_report_does_not_print_duplicate_attachment_content(tmp_path: Path) -> None:
    _write_json(tmp_path / "first-attachment.json", {"status_code": 200})
    _write_json(tmp_path / "duplicate-attachment.json", {"status_code": 200})
    _write_json(
        tmp_path / "case-result.json",
        {
            "name": "test_case",
            "status": "passed",
            "attachments": [
                {"name": "response", "source": "first-attachment.json"},
                {"name": "response", "source": "duplicate-attachment.json"},
            ],
        },
    )

    renderer = LocalReportRenderer(tmp_path)
    report = renderer.render(renderer.load_results())

    assert report.count('"status_code": 200') == 1


def test_local_report_redacts_secrets_from_plain_failure_text() -> None:
    value = "config={'password': 'plain-secret', 'fs_token': 'token-value'} authorization=Bearer-value"

    redacted = _redact_text(value)

    assert "plain-secret" not in redacted
    assert "token-value" not in redacted
    assert "Bearer-value" not in redacted
    assert redacted.count("***REDACTED***") == 3


def test_local_report_deduplicates_identical_failure_traces(tmp_path: Path) -> None:
    for index in range(2):
        _write_json(
            tmp_path / f"case-{index}-result.json",
            {
                "name": f"test_case_{index}",
                "status": "broken",
                "statusDetails": {"message": "setup failed", "trace": "same trace"},
            },
        )

    renderer = LocalReportRenderer(tmp_path)
    report = renderer.render(renderer.load_results())

    assert report.count("same trace") == 1
    assert "已省略重复内容" in report
