"""翻译工作台的四种语言组合专项测试。

这个文件只负责组织测试流程：加载 Case、切换个人语言、设置目标翻译语言、
调用 CaseRunner 执行真实接口，以及对 CaseRunner 采集的字段执行语言断言。
分类接口和翻译接口的具体请求拼装、发送及响应字段采集位于
``framework.core.runner.CaseRunner`` 中。
"""

from __future__ import annotations

import os
from contextlib import nullcontext
from copy import deepcopy
from pathlib import Path
from time import sleep, time_ns
from typing import Any

import pytest

from framework.config.environment import load_cases
from framework.core.text_language import assert_texts_in_language

try:
    # Allure 只负责记录测试标题、步骤和附件。未安装 Allure 时仍允许普通 pytest 运行。
    import allure
except ImportError:
    allure = None


# JSON 数据通过 workflow 标识归属于本专项，避免混入通用接口测试。
_WORKFLOW = "translation_language"

# 接口使用语言代码，测试步骤和错误消息使用便于阅读的中文名称。
_LANGUAGE_LABELS = {"zh-CN": "中文", "en": "英文"}

# 语言切换接口成功不代表所有后端服务立即生效，因此每个主体固定等待 5 秒。
_LANGUAGE_SWITCH_WAIT_SECONDS = 5

# Accept-Language 表示当前个人界面语言，影响响应中的 needTransName。
# 它和请求体中的 language（目标翻译语言）是两个不同概念。
_ACCEPT_LANGUAGE = {
    "zh-CN": "zh-CN,zh-TW;q=0.9,en;q=0.8",
    "en": "en,zh-CN;q=0.9,zh-TW;q=0.8",
}


@pytest.fixture(scope="session")
def translation_language_cases(pytestconfig: pytest.Config) -> dict[str, Any]:
    """加载一次专项数据，并拆分为语言切换 Case 和翻译 Case。

    session 作用域表示整个 pytest 进程只加载一次数据。返回值结构为：
    ``{"switches": {"zh-CN": case, "en": case}, "translations": [...]}``。
    四个测试主体会共同读取该结构，但真正执行前都会深拷贝单条 Case。
    """
    # 个人语言是同一账号的全局状态，并行主体会互相覆盖，所以必须串行执行。
    if hasattr(pytestconfig, "workerinput"):
        raise RuntimeError(
            "翻译工作台专项必须串行执行；请移除 pytest -n 参数或使用 -n 0"
        )
    # 命令行 --env 优先，其次读取 TEST_ENV，最后使用 test 环境。
    environment = pytestconfig.getoption("--env") or os.getenv("TEST_ENV", "test")
    if environment != "112":
        # 这些 Case 的分类值、rowKey 和 translateKey 都来自 112 环境。
        pytest.skip("Translation language workflow only runs in the 112 environment")

    # load_cases 会加载 test_data 下所有 *.112.json，再用 workflow 过滤本专项数据。
    cases = [case for case in load_cases(environment) if case.get("workflow") == _WORKFLOW]

    # 将两条语言切换 Case 按请求体 language 建立索引，后面可直接按语言取用。
    switches = {
        case["steps"][0]["request"]["json"]["language"]: case
        for case in cases
        if case.get("subject_id") == "pass_api_set_app_language"
    }
    # 两个 translation_workbench*.112.json 文件中的 12 + 16 条 Case 都进入该列表。
    translations = [
        case
        for case in cases
        if Path(case["__source__"]).name.startswith("translation_workbench")
    ]
    # 尽早校验数据完整性，避免执行到第三个主体才发现缺少切换 Case。
    if set(switches) != {"zh-CN", "en"}:
        raise AssertionError("pass_api.112.json 必须同时定义 zh-CN 和 en 两条语言切换 case")
    if not translations:
        raise AssertionError("没有加载到 translation_workbench.112.json 翻译 case")
    return {"switches": switches, "translations": translations}


def _allure_step(name: str):
    """创建 Allure 步骤；没有安装 Allure 时返回空上下文。"""
    return allure.step(name) if allure else nullcontext()


def _allure_title(name: str):
    """设置 Allure 测试标题；没有安装 Allure 时保持测试函数不变。"""
    return allure.title(name) if allure else lambda function: function


def _case_for_translation_language(
    case: dict[str, Any], translation_language: str
) -> dict[str, Any]:
    """复制一条翻译 Case，并把请求体语言改成当前目标翻译语言。

    ``translation_language`` 控制 translateValue，不代表当前用户的个人语言。
    同一条原始 Case 会被四个主体复用，因此必须先深拷贝，不能原地修改数据。
    """
    prepared = deepcopy(case)

    # 当前数据通常只有一个步骤，但遍历全部步骤可兼容以后增加的多步骤 Case。
    for step in prepared["steps"]:
        request = step.get("request", {})

        # test_case 模板会被加载器标准化为 json；普通翻译 Case 仍使用 body。
        body = request.get("json", request.get("body"))
        if not isinstance(body, dict):
            continue

        # sub_query_optimize 等接口把 language 放在请求体顶层。
        if "language" in body:
            body["language"] = translation_language

        # 分类接口把 language 放在 argMap 中，需要单独同步。
        arg_map = body.get("argMap")
        if isinstance(arg_map, dict) and "language" in arg_map:
            arg_map["language"] = translation_language
    return prepared


def _case_for_personal_language_switch(
    case_runner,
    case: dict[str, Any],
    personal_language: str,
) -> dict[str, Any]:
    """构造个人语言切换请求，同时保留自动登录得到的会话。

    页面切换语言时，请求发出前 Cookie 和 Accept-Language 仍表示“当前语言”，
    请求体中的 language 才是“准备切换到的语言”。接口成功后，调用方再把
    共享客户端更新成新的个人语言。
    """
    prepared = deepcopy(case)

    # 从自动登录会话中读取当前 lang Cookie；可能存在同名但不同域的 Cookie。
    existing_languages = [
        cookie.value
        for cookie in case_runner.http_client.cookies.jar
        if cookie.name == "lang" and cookie.value in _LANGUAGE_LABELS
    ]
    # 首次登录没有 lang Cookie 时，用目标语言的另一种语言模拟切换前状态。
    current_language = existing_languages[-1] if existing_languages else (
        "en" if personal_language == "zh-CN" else "zh-CN"
    )
    # set_cookie 会尽量保留原 Cookie 的 domain/path，不破坏登录会话。
    case_runner.http_client.set_cookie("lang", current_language)

    request = prepared["steps"][0]["request"]
    base_url = case_runner.environment.get("http.base_url", "").rstrip("/")

    # 每次切换使用唯一 trace ID，避免缓存并方便在服务端日志中定位请求。
    trace_suffix = str(time_ns())
    request["params"] = {
        **(request.get("params") or {}),
        "traceId": f"FSW-pytest-{trace_suffix}",
    }
    # 这些请求头模拟页面的语言切换请求；认证 Cookie 由共享 HttpClient 自动携带。
    request["headers"] = {
        **(request.get("headers") or {}),
        "Accept-Language": _ACCEPT_LANGUAGE[current_language],
        "Origin": base_url,
        "Referer": f"{base_url}/XV/UI/manage",
        "X-Trace-Id": f"pytest-language-switch-{trace_suffix}",
    }
    return prepared


def _assert_result_languages(
    context: dict[str, Any],
    personal_language: str,
    translation_language: str,
) -> None:
    """检查分组、原始名称和翻译名称，并一次性汇总全部字段错误。

    CaseRunner 返回的 context 中：
    - matched_folder_names：query_optimize 实际返回的可展开分组名称；
    - matched_names：最终词条的 needTransName；
    - matched_translate_values：最终词条的 translateValue。

    每项断言独立捕获异常，因此分组失败后，名称和名称翻译仍会继续检查。
    """
    personal_language_label = _LANGUAGE_LABELS[personal_language]
    translation_language_label = _LANGUAGE_LABELS[translation_language]
    failures = []

    # 只有接口真实返回了分组行才检查分组；平铺词条不会产生该列表内容。
    folder_names = context.get("matched_folder_names", [])
    if folder_names:
        try:
            with _allure_step(f"分组名称断言：全部为{personal_language_label}"):
                assert_texts_in_language(
                    folder_names,
                    personal_language,
                    field_name="分组名称（needTransName）",
                )
        except AssertionError as error:
            failures.append(str(error))
    # needTransName 是当前个人语言下显示的原始“名称”。
    try:
        with _allure_step(f"名称断言：全部为{personal_language_label}"):
            assert_texts_in_language(
                context.get("matched_names", []),
                personal_language,
                field_name="名称（needTransName）",
            )
    except AssertionError as error:
        failures.append(str(error))
    # translateValue 是翻译结果，只受目标翻译语言控制。
    try:
        with _allure_step(f"名称翻译断言：全部为{translation_language_label}"):
            assert_texts_in_language(
                context.get("matched_translate_values", []),
                translation_language,
                field_name="名称翻译（translateValue）",
            )
    except AssertionError as error:
        failures.append(str(error))
    # 用中文分号连接三类错误，文本报告会再拆分成独立的可读错误行。
    if failures:
        raise AssertionError("；".join(failures))


def _run_language_subject(
    case_runner,
    workflow_cases: dict[str, Any],
    personal_language: str,
    translation_language: str,
    *,
    wait_for_language_switch=sleep,
) -> None:
    """运行一种“个人语言 + 目标翻译语言”组合下的全部 28 条 Case。"""
    personal_language_label = _LANGUAGE_LABELS[personal_language]
    translation_language_label = _LANGUAGE_LABELS[translation_language]

    # 一个主体开始时只切换一次个人语言；主体内 28 条 Case 共用切换后的会话。
    with _allure_step(f"前置步骤：个人语言切换成{personal_language_label}"):
        switch_case = _case_for_personal_language_switch(
            case_runner,
            workflow_cases["switches"][personal_language],
            personal_language,
        )
        # 通过 CaseRunner 发送真实 SetAppLanguage 请求，并检查 HTTP/业务状态。
        case_runner.run(switch_case)

        # 接口成功后，同步本地会话状态，后续分类和翻译请求都会携带新语言。
        case_runner.http_client.set_cookie("lang", personal_language)
        case_runner.http_client.default_headers["Accept-Language"] = _ACCEPT_LANGUAGE[
            personal_language
        ]
        # 等待后端语言配置传播完成，再开始读取 needTransName。
        with _allure_step(
            f"等待个人语言切换生效（{_LANGUAGE_SWITCH_WAIT_SECONDS} 秒）"
        ):
            wait_for_language_switch(_LANGUAGE_SWITCH_WAIT_SECONDS)

    # Case 级失败先收集，不在第一条失败时终止，保证一次报告覆盖全部路径。
    failures = []
    for index, case in enumerate(workflow_cases["translations"], start=1):
        case_name = case.get("name", case["id"])
        try:
            # 固定格式的步骤名会被文本报告解析成 Case 编号和分类路径。
            with _allure_step(f"翻译 case {index:02d}：{case_name}"):
                # 先写入本主体的目标翻译语言，再由 CaseRunner 构造并发送整条请求链。
                prepared_case = _case_for_translation_language(case, translation_language)
                result = case_runner.run(prepared_case)

                # CaseRunner 请求和采集全部完成后，统一检查分组及最终词条字段。
                _assert_result_languages(result, personal_language, translation_language)
        except Exception as error:
            # 不只捕获断言错误，也记录请求、响应解析等异常，然后继续下一条 Case。
            failures.append(f"{case_name}: {error}")

    # 28 条全部执行后再让当前主体失败，异常消息中包含每条失败 Case 的原因。
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
    """验证个人语言中文、目标翻译语言中文。"""
    _run_language_subject(case_runner, translation_language_cases, "zh-CN", "zh-CN")


@_allure_title("主体二：个人语言为中文，翻译成英文")
def test_personal_language_chinese_translates_to_english(
    translation_language_cases: dict[str, Any],
    case_runner,
) -> None:
    """验证个人语言中文、目标翻译语言英文。"""
    _run_language_subject(case_runner, translation_language_cases, "zh-CN", "en")


@_allure_title("主体三：个人语言为英文，翻译成中文")
def test_personal_language_english_translates_to_chinese(
    translation_language_cases: dict[str, Any],
    case_runner,
) -> None:
    """验证个人语言英文、目标翻译语言中文。"""
    _run_language_subject(case_runner, translation_language_cases, "en", "zh-CN")


@_allure_title("主体四：个人语言为英文，翻译成英文")
def test_personal_language_english_translates_to_english(
    translation_language_cases: dict[str, Any],
    case_runner,
) -> None:
    """验证个人语言英文、目标翻译语言英文。"""
    _run_language_subject(case_runner, translation_language_cases, "en", "en")
