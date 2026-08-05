from __future__ import annotations

import pytest

from framework.core.text_language import (
    TextLanguage,
    assert_texts_in_language,
    detect_text_language,
    is_text_in_language,
)
from tests.translation_workbench.test_translation_language import (
    _assert_result_languages,
    _case_for_personal_language_switch,
    _case_for_translation_language,
    _run_language_subject,
)


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


@pytest.mark.parametrize(
    ("personal_language", "translation_language", "name", "translate_value"),
    [
        ("en", "en", "Dashboard", "Dashboard translation"),
        ("en", "zh-CN", "Dashboard", "数据驾驶舱翻译"),
        ("zh-CN", "en", "数据驾驶舱", "Dashboard translation"),
        ("zh-CN", "zh-CN", "数据驾驶舱", "数据驾驶舱翻译"),
    ],
)
def test_result_language_assertions_cover_personal_and_translation_matrix(
    personal_language: str,
    translation_language: str,
    name: str,
    translate_value: str,
) -> None:
    _assert_result_languages(
        {
            "matched_names": [name],
            "matched_translate_values": [translate_value],
        },
        personal_language,
        translation_language,
    )


def test_result_language_assertion_rejects_wrong_translation_language() -> None:
    with pytest.raises(AssertionError, match="名称翻译.*字段应为 en"):
        _assert_result_languages(
            {
                "matched_names": ["Dashboard"],
                "matched_translate_values": ["数据驾驶舱翻译"],
            },
            "en",
            "en",
        )


def test_result_language_assertion_reports_name_and_translation_failures() -> None:
    with pytest.raises(AssertionError) as captured:
        _assert_result_languages(
            {
                "matched_names": ["中文名称"],
                "matched_translate_values": ["中文翻译"],
            },
            "en",
            "en",
        )

    message = str(captured.value)
    assert "名称（needTransName）字段应为 en" in message
    assert "名称翻译（translateValue）字段应为 en" in message


def test_result_language_assertion_checks_returned_folder_against_personal_language() -> None:
    with pytest.raises(AssertionError, match="分组名称.*字段应为 en"):
        _assert_result_languages(
            {
                "matched_folder_names": ["统计图_区域"],
                "matched_names": ["Dashboard"],
                "matched_translate_values": ["中文翻译"],
            },
            "en",
            "zh-CN",
        )


def test_result_language_assertion_skips_folder_when_api_returned_no_folder_row() -> None:
    _assert_result_languages(
        {
            "matched_folder_names": [],
            "matched_names": ["Dashboard"],
            "matched_translate_values": ["中文翻译"],
        },
        "en",
        "zh-CN",
    )


@pytest.mark.parametrize("translate_value", ["", None])
def test_result_language_assertion_rejects_empty_translation_value(translate_value) -> None:
    with pytest.raises(AssertionError, match="名称翻译.*识别为 unknown"):
        _assert_result_languages(
            {
                "matched_names": ["Dashboard"],
                "matched_translate_values": [translate_value],
            },
            "en",
            "en",
        )


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


def test_language_subject_switches_once_and_waits_before_translation() -> None:
    events = []
    switch_case = {
        "id": "switch-en",
        "steps": [{"request": {"json": {"language": "en"}}}],
    }
    translation_case = {
        "id": "translation-case",
        "name": "翻译 Case",
        "steps": [{"request": {"body": {"language": "en"}}}],
    }

    class FakeHttpClient:
        class Cookies:
            jar = []

        cookies = Cookies()
        default_headers = {}

        def set_cookie(self, name, value) -> None:
            events.append(("cookie", name, value))

    class FakeRunner:
        class Environment:
            @staticmethod
            def get(name, default=None):
                return "https://crm.example.test" if name == "http.base_url" else default

        environment = Environment()
        http_client = FakeHttpClient()

        def run(self, case):
            if case["id"] == switch_case["id"]:
                request = case["steps"][0]["request"]
                events.append(
                    (
                        "switch",
                        case["id"],
                        request["headers"]["Accept-Language"],
                        request["headers"]["Origin"],
                        request["headers"]["Referer"],
                        request["params"]["traceId"].startswith("FSW-pytest-"),
                    )
                )
                return {}
            events.append(
                (
                    "translation",
                    case["steps"][0]["request"]["body"]["language"],
                    self.http_client.default_headers["Accept-Language"],
                )
            )
            return {
                "matched_names": ["Dashboard"],
                "matched_translate_values": ["中文翻译"],
            }

    _run_language_subject(
        FakeRunner(),
        {"switches": {"en": switch_case}, "translations": [translation_case]},
        "en",
        "zh-CN",
        wait_for_language_switch=lambda seconds: events.append(("wait", seconds)),
    )

    assert events == [
        ("cookie", "lang", "zh-CN"),
        (
            "switch",
            "switch-en",
            "zh-CN,zh-TW;q=0.9,en;q=0.8",
            "https://crm.example.test",
            "https://crm.example.test/XV/UI/manage",
            True,
        ),
        ("cookie", "lang", "en"),
        ("wait", 5),
        ("translation", "zh-CN", "en,zh-CN;q=0.9,zh-TW;q=0.8"),
    ]


def test_personal_language_switch_uses_existing_session_language() -> None:
    class Cookie:
        name = "lang"
        value = "en"

    class HttpClient:
        class Cookies:
            jar = [Cookie()]

        cookies = Cookies()

        @staticmethod
        def set_cookie(name, value):
            assert (name, value) == ("lang", "en")

    class Environment:
        @staticmethod
        def get(name, default=None):
            return "https://crm.example.test" if name == "http.base_url" else default

    class Runner:
        http_client = HttpClient()
        environment = Environment()

    prepared = _case_for_personal_language_switch(
        Runner(),
        {"steps": [{"request": {"json": {"language": "zh-CN"}}}]},
        "zh-CN",
    )

    headers = prepared["steps"][0]["request"]["headers"]
    assert headers["Accept-Language"] == "en,zh-CN;q=0.9,zh-TW;q=0.8"
