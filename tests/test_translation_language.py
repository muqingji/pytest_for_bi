from __future__ import annotations

import os
from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest

from framework.auth import authenticate_fxiaoke
from framework.config.environment import load_cases

try:
    import allure
except ImportError:
    allure = None


_WORKFLOW = "translation_language"
_LANGUAGE_LABELS = {"zh-CN": "中文", "en": "英文"}


@pytest.fixture(scope="session")
def translation_language_cases(pytestconfig: pytest.Config) -> dict[str, Any]:
    environment = pytestconfig.getoption("--env") or os.getenv("TEST_ENV", "test")
    if environment != "112":
        pytest.skip("Translation language workflow only runs in the 112 environment")

    cases = [case for case in load_cases(environment) if case.get("workflow") == _WORKFLOW]
    switches = {
        case["steps"][0]["request"]["json"]["language"]: case
        for case in cases
        if case.get("subject_id") == "pass_api_set_app_language"
    }
    translations = [
        case
        for case in cases
        if Path(case["__source__"]).name.startswith("translation_workbench")
    ]
    if set(switches) != {"zh-CN", "en"}:
        raise AssertionError("pass_api.112.json 必须同时定义 zh-CN 和 en 两条语言切换 case")
    if not translations:
        raise AssertionError("没有加载到 translation_workbench.112.json 翻译 case")
    return {"switches": switches, "translations": translations}


def _allure_step(name: str):
    return allure.step(name) if allure else nullcontext()


def _allure_title(name: str):
    return allure.title(name) if allure else lambda function: function


def _case_for_translation_language(
    case: dict[str, Any], translation_language: str
) -> dict[str, Any]:
    prepared = deepcopy(case)
    for step in prepared["steps"]:
        request = step.get("request", {})
        body = request.get("json", request.get("body"))
        if not isinstance(body, dict):
            continue
        if "language" in body:
            body["language"] = translation_language
        arg_map = body.get("argMap")
        if isinstance(arg_map, dict) and "language" in arg_map:
            arg_map["language"] = translation_language
    return prepared


def _run_language_subject(
    case_runner,
    workflow_cases: dict[str, Any],
    personal_language: str,
    translation_language: str,
) -> None:
    personal_language_label = _LANGUAGE_LABELS[personal_language]
    translation_language_label = _LANGUAGE_LABELS[translation_language]
    with _allure_step(f"前置步骤：个人语言切换成{personal_language_label}"):
        case_runner.run(workflow_cases["switches"][personal_language])
        with _allure_step("同步 lang Cookie 并刷新登录会话"):
            case_runner.http_client.set_cookie("lang", personal_language)
            authenticate_fxiaoke(case_runner.environment, case_runner.http_client)
            case_runner.http_client.set_cookie("lang", personal_language)

    failures = []
    for index, case in enumerate(workflow_cases["translations"], start=1):
        case_name = case.get("name", case["id"])
        try:
            with _allure_step(f"翻译 case {index:02d}：{case_name}"):
                prepared_case = _case_for_translation_language(case, translation_language)
                case_runner.run(prepared_case)
        except Exception as error:
            failures.append(f"{case_name}: {error}")

    if failures:
        details = "\n".join(f"  {index}. {failure}" for index, failure in enumerate(failures, start=1))
        raise AssertionError(
            f"个人语言为{personal_language_label}、翻译成{translation_language_label}时，"
            f"{len(failures)}/{len(workflow_cases['translations'])} "
            f"条翻译 case 未通过：\n{details}"
        )


@_allure_title("主体一：个人语言为中文，翻译成中文")
def test_personal_language_chinese_translates_to_chinese(
    translation_language_cases: dict[str, Any],
    case_runner,
) -> None:
    _run_language_subject(case_runner, translation_language_cases, "zh-CN", "zh-CN")


@_allure_title("主体二：个人语言为中文，翻译成英文")
def test_personal_language_chinese_translates_to_english(
    translation_language_cases: dict[str, Any],
    case_runner,
) -> None:
    _run_language_subject(case_runner, translation_language_cases, "zh-CN", "en")


@_allure_title("主体三：个人语言为英文，翻译成中文")
def test_personal_language_english_translates_to_chinese(
    translation_language_cases: dict[str, Any],
    case_runner,
) -> None:
    _run_language_subject(case_runner, translation_language_cases, "en", "zh-CN")


@_allure_title("主体四：个人语言为英文，翻译成英文")
def test_personal_language_english_translates_to_english(
    translation_language_cases: dict[str, Any],
    case_runner,
) -> None:
    _run_language_subject(case_runner, translation_language_cases, "en", "en")
