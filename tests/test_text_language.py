from __future__ import annotations

import pytest

from framework.core.text_language import (
    TextLanguage,
    assert_texts_in_language,
    detect_text_language,
    is_text_in_language,
)
from tests.test_translation_language import _case_for_translation_language


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("统计图_区域", TextLanguage.CHINESE),
        ("BI 图表配置 2", TextLanguage.MIXED),
        ("Dashboard configuration 2", TextLanguage.ENGLISH),
        ("123-_", TextLanguage.UNKNOWN),
        ("", TextLanguage.UNKNOWN),
    ],
)
def test_detect_text_language(value: str, expected: TextLanguage) -> None:
    assert detect_text_language(value) is expected


def test_language_match_accepts_mixed_identifiers_only_for_chinese() -> None:
    assert is_text_in_language("BI 图表配置 2", "zh-CN")
    assert not is_text_in_language("BI 图表配置 2", "en")
    assert is_text_in_language("Dashboard 2", "en")


def test_assert_texts_in_language_reports_missing_and_mismatched_names() -> None:
    with pytest.raises(AssertionError, match="没有采集到"):
        assert_texts_in_language([], "zh-CN")
    with pytest.raises(AssertionError, match="识别为 zh-CN"):
        assert_texts_in_language(["统计图"], "en")


@pytest.mark.parametrize("translation_language", ["zh-CN", "en"])
def test_translation_target_language_is_explicit(
    translation_language: str,
) -> None:
    case = {
        "steps": [
            {"request": {"body": {"language": "en"}}},
            {"request": {"json": {"argMap": {"language": "en"}}}},
        ]
    }

    prepared_case = _case_for_translation_language(case, translation_language)

    assert prepared_case["steps"][0]["request"]["body"]["language"] == translation_language
    assert (
        prepared_case["steps"][1]["request"]["json"]["argMap"]["language"]
        == translation_language
    )
    assert case["steps"][0]["request"]["body"]["language"] == "en"
