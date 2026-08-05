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


def test_translation_summary_lists_scenarios_paths_and_readable_failures(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "failed-fields-attachment.json",
        [{"needTransName": "Dashboard", "translateValue": ""}],
    )
    _write_json(
        tmp_path / "passed-fields-attachment.json",
        [{"needTransName": "指标", "translateValue": "Metric"}],
    )
    _write_json(
        tmp_path / "failed-folder-attachment.json",
        [{"needTransName": "Report folder", "rowKey": "folder-1"}],
    )
    _write_json(
        tmp_path / "passed-folder-attachment.json",
        [{"needTransName": "指标文件夹", "rowKey": "folder-2"}],
    )
    _write_json(
        tmp_path / "translation-result.json",
        {
            "name": "主体二：个人语言为中文，翻译成英文",
            "status": "failed",
            "start": 1000,
            "stop": 1200,
            "steps": [
                {
                    "name": "前置步骤：个人语言切换成中文",
                    "status": "passed",
                },
                {
                    "name": "翻译 case 01：图表配置-报表列表-统计图",
                    "status": "failed",
                    "statusDetails": {
                        "message": (
                            "AssertionError: 名称（needTransName）字段应为 zh-CN: "
                            "'Dashboard'（识别为 en）；名称翻译（translateValue）字段应为 "
                            "en: ''（识别为 unknown）"
                        )
                    },
                    "steps": [
                        {
                            "name": "查询统计图翻译项",
                            "status": "passed",
                            "attachments": [
                                {
                                    "name": "命中的文件夹名称字段",
                                    "source": "failed-folder-attachment.json",
                                    "type": "application/json",
                                }
                            ],
                            "steps": [
                                {
                                    "name": "采集最终词条：统计图_区域 > Dashboard",
                                    "status": "passed",
                                    "attachments": [
                                        {
                                            "name": "命中的名称与名称翻译字段",
                                            "source": "failed-fields-attachment.json",
                                            "type": "application/json",
                                        }
                                    ],
                                }
                            ],
                        }
                    ],
                },
                {
                    "name": "翻译 case 02：主题指标-指标名称",
                    "status": "passed",
                    "steps": [
                        {
                            "name": "检查命中字段",
                            "status": "passed",
                            "attachments": [
                                {
                                    "name": "命中的文件夹名称字段",
                                    "source": "passed-folder-attachment.json",
                                    "type": "application/json",
                                },
                                {
                                    "name": "命中的名称与名称翻译字段",
                                    "source": "passed-fields-attachment.json",
                                    "type": "application/json",
                                }
                            ],
                        }
                    ],
                },
            ],
        },
    )

    renderer = LocalReportRenderer(tmp_path)
    report = renderer.render_summary(renderer.load_results())

    assert "翻译路径 Case: 2 条  |  通过: 1  |  失败: 1" in report
    assert "场景 1: 主体二：个人语言为中文，翻译成英文" in report
    assert (
        "[01] [FAIL] 图表配置 > 报表列表 > 统计图 > 统计图_区域 > Dashboard"
        in report
    )
    assert "[FAIL] 分组名称（needTransName）：期望中文，实际值='Report folder'，识别为英文" in report
    assert "名称（needTransName）：期望中文，实际值='Dashboard'，识别为英文" in report
    assert "名称翻译（translateValue）：期望英文，实际值=''，识别为空值或无法识别" in report
    assert "[02] [PASS] 主题指标 > 指标名称" in report
    assert "[PASS] 分组名称（needTransName）：期望中文，实际值='指标文件夹'，识别为中文" in report
    assert "[PASS] 名称（needTransName）：期望中文，实际值='指标'，识别为中文" in report
    assert "[PASS] 名称翻译（translateValue）：期望英文，实际值='Metric'，识别为英文" in report
    assert '"status"' not in report


def test_translation_summary_does_not_report_setup_errors_as_success(tmp_path: Path) -> None:
    _write_json(
        tmp_path / "translation-setup-error-result.json",
        {
            "name": "主体三：个人语言为英文，翻译成中文",
            "status": "broken",
            "start": 1000,
            "stop": 1100,
            "statusDetails": {"message": "login failed"},
        },
    )

    report = LocalReportRenderer(tmp_path).render_summary(
        LocalReportRenderer(tmp_path).load_results()
    )

    assert "测试主体: 1 个  |  通过: 0  |  失败: 0  |  异常: 1" in report
    assert "主体在执行翻译 Case 前失败" in report
    assert "共有 1 个测试主体未通过，其中 0 条翻译路径 Case 未通过" in report
    assert "全部翻译路径 Case 通过" not in report


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
