from copy import deepcopy
from pathlib import Path

from qa_agents.agents import BackendAutomationAgent, BackendAutomationReviewAgent
from qa_agents.agents.base import AgentContext
from qa_agents.automation import AutomationPolicy, check_automation_generation
from qa_agents.contracts import ArtifactStatus
from qa_agents.security import SecurityPolicy


ROOT = Path(__file__).resolve().parents[1]


def backend_case() -> dict:
    return {
        "id": "CASE-001-BACKEND",
        "parent_case_id": "CASE-001",
        "intent_ids": ["INTENT-001"],
        "title": "无权限请求返回 403",
        "layer": "backend",
        "risk": "high",
        "priority": "P1",
        "source_refs": [
            {"type": "requirement", "id": "REQ-1", "location": "section-1"}
        ],
        "preconditions": ["使用无权限账号"],
        "test_data": {
            "request": {"method": "GET", "path": "/api/report"},
            "resource_requirements": [{
                "resource_key": "chart",
                "resource_type": "stat_chart",
                "resource_id_variable": "chart_view_id",
                "retention_mode": "retain",
            }],
        },
        "steps": [{
            "name": "请求报表接口",
            "request": {
                "protocol": "http",
                "api": "fs_bi_stat.stat_base.detail_data_query",
                "json": {},
            },
        }],
        "expected": [
            {
                "id": "EXP-01",
                "description": "接口拒绝请求",
                "oracle": {
                    "type": "deterministic",
                    "observation_point": "response.status",
                    "matcher": "equals:403",
                    "source_ref": "REQ-1:section-1",
                },
            }
        ],
        "cleanup": [],
        "execution_policy": {
            "allowed_modes": ["automated"],
            "required_evidence": ["request_response"],
        },
        "automation_candidate": True,
    }


def context() -> AgentContext:
    return AgentContext("run-1", "new_requirement", "snapshot-1", ("input/cases.json",))


def target() -> dict:
    return {
        "repository_id": "pytest_for_bi",
        "access_class": "approved_automation_repository",
        "timeout_seconds": 300,
        "network": False,
        "secrets": [],
    }


def test_backend_generation_review_and_n05_check_are_separate() -> None:
    security = SecurityPolicy()
    case = backend_case()
    generation = BackendAutomationAgent().run(
        context(), {"cases": [case], "target": target()}, security
    )
    assert generation.status == ArtifactStatus.COMPLETED
    assert f"'id': '{case['id']}'" in generation.payload["code_candidates"][0]["content"]
    assert generation.payload["manifest"]["target_repository"]["write_mode"] == (
        "artifact_only_candidate"
    )
    assert generation.payload["manifest"]["input_bindings"] == {}

    review = BackendAutomationReviewAgent().run(
        context(), {"cases": [case], "generation": generation.payload}, security
    )
    assert review.producer.runtime == "automation-review-runtime"
    assert review.payload["approved"] is True
    assert review.payload["generator_hidden_reasoning_accessed"] is False

    policy = AutomationPolicy.from_file(ROOT / "policies" / "automation-target-policy.json")
    code_check = check_automation_generation(generation.payload, policy)
    assert code_check["passed"] is True
    assert code_check["fatal_security_violation"] is False


def test_n05_rejects_business_repository_and_tampered_candidate() -> None:
    generation = BackendAutomationAgent().run(
        context(), {"cases": [backend_case()], "target": target()}, SecurityPolicy()
    ).payload
    policy = AutomationPolicy.from_file(ROOT / "policies" / "automation-target-policy.json")

    business_target = deepcopy(generation)
    business_target["manifest"]["target_repository"]["repository_id"] = "fs-bi"
    result = check_automation_generation(business_target, policy)
    assert result["passed"] is False
    assert result["fatal_security_violation"] is True
    assert {item["issue_code"] for item in result["issues"]} == {
        "target_repository_not_approved"
    }

    tampered = deepcopy(generation)
    tampered["code_candidates"][0]["content"] += "\n# changed after generation\n"
    result = check_automation_generation(tampered, policy)
    assert result["passed"] is False
    assert result["fatal_security_violation"] is False
    assert {item["issue_code"] for item in result["issues"]} == {
        "candidate_hash_mismatch"
    }
    assert result["repair_routes"] == ["A14"]


def test_n05_rejects_command_injection_and_unapproved_runtime_call() -> None:
    generation = BackendAutomationAgent().run(
        context(), {"cases": [backend_case()], "target": target()}, SecurityPolicy()
    ).payload
    policy = AutomationPolicy.from_file(ROOT / "policies" / "automation-target-policy.json")

    command_injection = deepcopy(generation)
    command_injection["manifest"]["execution"]["command"].append("--pdb")
    result = check_automation_generation(command_injection, policy)
    assert result["fatal_security_violation"] is True
    assert "execution_command_mismatch" in {
        item["issue_code"] for item in result["issues"]
    }

    runtime_escape = deepcopy(generation)
    candidate = runtime_escape["code_candidates"][0]
    candidate["content"] += "\ncase_runner.shell('whoami')\n"
    from qa_agents.contracts import content_hash

    candidate["content_hash"] = content_hash(candidate["content"])
    runtime_escape["manifest"]["candidate_files"][0]["content_hash"] = candidate[
        "content_hash"
    ]
    result = check_automation_generation(runtime_escape, policy)
    assert result["fatal_security_violation"] is True
    assert "unapproved_runtime_call" in {
        item["issue_code"] for item in result["issues"]
    }


def test_manual_oracle_is_not_generated_as_automation() -> None:
    case = backend_case()
    case["expected"][0]["oracle"]["matcher"] = "manual_confirmation"
    case["execution_policy"]["allowed_modes"] = ["manual"]
    generation = BackendAutomationAgent().run(
        context(), {"cases": [case], "target": target()}, SecurityPolicy()
    )
    assert generation.status == ArtifactStatus.NOT_APPLICABLE
    assert generation.reason_code == "no_machine_executable_integration_or_functional_case"
    assert generation.payload["manifest"] is None


def test_n05_allows_truthful_network_and_112_secrets_declaration() -> None:
    """A backend integration Manifest that declares network plus the policy
    allowlisted 112 credential names must pass N05 (business repo writes remain
    the only forbidden permission)."""

    generation = BackendAutomationAgent().run(
        context(),
        {
            "cases": [backend_case()],
            "target": {
                "repository_id": "pytest_for_bi",
                "access_class": "approved_automation_repository",
                "timeout_seconds": 300,
                "network": True,
                "secrets": [
                    "FXIAOKE_112_ENTERPRISE_ACCOUNT",
                    "FXIAOKE_112_USERNAME",
                    "FXIAOKE_112_PASSWORD",
                ],
            },
        },
        SecurityPolicy(),
    ).payload
    policy = AutomationPolicy.from_file(ROOT / "policies" / "automation-target-policy.json")
    code_check = check_automation_generation(generation, policy)
    assert code_check["passed"] is True
    assert code_check["fatal_security_violation"] is False


def test_n05_rejects_non_executable_skeleton_candidate() -> None:
    """N05 必须拦下纯文本骨架：A14 曾生成 steps/cleanup 为字符串、expected 无
    oracle、assert_oracles 签名错误的候选，N08 运行必然失败。"""
    from qa_agents.contracts import content_hash

    generation = BackendAutomationAgent().run(
        context(), {"cases": [backend_case()], "target": target()}, SecurityPolicy()
    ).payload
    policy = AutomationPolicy.from_file(ROOT / "policies" / "automation-target-policy.json")
    skeleton = (
        'CASE_SPEC = {"id": "TC-BE-001-BACKEND", "steps": ["对 A/B/C 调用真实接口"], '
        '"expected": [{"id": "EXP-1", "expected_value": "s307011534"}], '
        '"cleanup": ["删除统计图和自定义维度。"]}\n'
        "def test_tc_be_001_backend(case_runner):\n"
        "    case_runner.execute(CASE_SPEC)\n"
        "    case_runner.assert_oracles(CASE_SPEC)\n"
    )
    candidate = generation["code_candidates"][0]
    candidate["content"] = skeleton
    candidate["content_hash"] = content_hash(skeleton)
    generation["manifest"]["candidate_files"][0]["content_hash"] = candidate["content_hash"]
    result = check_automation_generation(generation, policy)
    assert result["passed"] is False
    codes = {item["issue_code"] for item in result["issues"]}
    assert "execution_step_not_structured" in codes
    assert "executable_oracle_missing" in codes
    assert "assert_oracles_signature_invalid" in codes
    assert result["fatal_security_violation"] is False


def test_n05_rejects_json_style_literals_in_case_spec() -> None:
    """N05 门禁必须与 pytest 运行时语义一致：候选文件是纯 Python 源码，
    JSON 风格 true/false/null（裸名）导入时会抛 NameError，必须在 N05 拦截，
    而不是放行后让 N08 在运行时以 infrastructure_error 失败。"""
    from qa_agents.contracts import content_hash

    generation = BackendAutomationAgent().run(
        context(), {"cases": [backend_case()], "target": target()}, SecurityPolicy()
    ).payload
    policy = AutomationPolicy.from_file(ROOT / "policies" / "automation-target-policy.json")
    content = (
        'CASE_SPEC = {"id": "TC-BE-004-BACKEND", "test_level": "integration", '
        '"topic_restriction": false, "dataset": null, "steps": ['
        '{"name": "call", "request": {"api": "fs_bi_stat.stat_base.detail_data_query", "json": {}}}], '
        '"expected": [{"id": "EXP-1", "matcher": "equals", "observation_point": "detail_api.error.code", '
        '"expected_value": "s307011534"}], "cleanup": []}\n'
        "def test_tc_be_004_backend(case_runner):\n"
        "    observations = case_runner.execute(CASE_SPEC)\n"
        '    case_runner.assert_oracles(observations, CASE_SPEC["expected"])\n'
    )
    candidate = generation["code_candidates"][0]
    candidate["content"] = content
    candidate["content_hash"] = content_hash(content)
    generation["manifest"]["candidate_files"][0]["content_hash"] = candidate["content_hash"]
    result = check_automation_generation(generation, policy)
    assert result["passed"] is False
    codes = {item["issue_code"] for item in result["issues"]}
    assert "case_spec_json_literals_not_python" in codes
    assert result["fatal_security_violation"] is False



def test_n05_accepts_constant_helper_case_spec() -> None:
    """A14 用顶部常量/纯函数压缩 CASE_SPEC 时，N05 必须静态展开而不是误拦。

    生成器为避开体积限制会写 ``NS=...`` / ``def q(...): return {...}``，再把名字
    嵌进 CASE_SPEC。文件仍是可 import 的静态 dict；拦成 case_spec_not_literal
    会让已生成的后端用例永远进不了 N08。
    """
    from qa_agents.contracts import content_hash

    generation = BackendAutomationAgent().run(
        context(), {"cases": [backend_case()], "target": target()}, SecurityPolicy()
    ).payload
    policy = AutomationPolicy.from_file(ROOT / "policies" / "automation-target-policy.json")
    content = (
        "NS='qa-ns'\n"
        "API='fs_bi_stat.stat_base.detail_data_query'\n"
        "EX={'status_code': 200}\n"
        "def q(lan, fid='F1'):\n"
        "    return {'id': fid, 'lan': lan}\n"
        "CASE_SPEC = {\n"
        "    'id': 'TC-BE-001-BACKEND',\n"
        "    'test_level': 'integration',\n"
        "    'test_data': {'namespace': NS + '-case'},\n"
        "    'setup': [],\n"
        "    'steps': [{'name': 'query', 'request': {'api': API, 'json': q('zh-CN')}, 'expect': EX}],\n"
        "    'expected': [{'id': 'EXP-1', 'oracle': {'matcher': 'equals',\n"
        "        'observation_point': 'detail_api.error.code', 'expected_value': 's307011534'}}],\n"
        "    'cleanup': [],\n"
        "}\n"
        "def test_tc_be_001_backend(case_runner):\n"
        "    observations = case_runner.execute(CASE_SPEC)\n"
        "    case_runner.assert_oracles(observations, CASE_SPEC['expected'])\n"
    )
    candidate = generation["code_candidates"][0]
    candidate["content"] = content
    candidate["content_hash"] = content_hash(content)
    generation["manifest"]["candidate_files"][0]["content_hash"] = candidate["content_hash"]
    result = check_automation_generation(generation, policy)
    codes = {item["issue_code"] for item in result["issues"]}
    assert "case_spec_not_literal" not in codes
    assert result["passed"] is True, result["issues"]


def test_n05_still_rejects_dynamic_case_spec_helpers() -> None:
    from qa_agents.contracts import content_hash

    generation = BackendAutomationAgent().run(
        context(), {"cases": [backend_case()], "target": target()}, SecurityPolicy()
    ).payload
    policy = AutomationPolicy.from_file(ROOT / "policies" / "automation-target-policy.json")
    content = (
        "import os\n"
        "CASE_SPEC = {'id': os.getenv('CASE'), 'steps': [], 'expected': [], 'cleanup': []}\n"
        "def test_x(case_runner):\n"
        "    observations = case_runner.execute(CASE_SPEC)\n"
        "    case_runner.assert_oracles(observations, CASE_SPEC['expected'])\n"
    )
    candidate = generation["code_candidates"][0]
    candidate["content"] = content
    candidate["content_hash"] = content_hash(content)
    generation["manifest"]["candidate_files"][0]["content_hash"] = candidate["content_hash"]
    result = check_automation_generation(generation, policy)
    codes = {item["issue_code"] for item in result["issues"]}
    assert "case_spec_not_literal" in codes
    assert result["passed"] is False


def test_n05_accepts_not_equals_and_not_one_of_oracles() -> None:
    """A08 批准的 not_equals / not_one_of 必须能过 N05，否则已生成后端用例会被卡死。"""
    from qa_agents.contracts import content_hash

    generation = BackendAutomationAgent().run(
        context(), {"cases": [backend_case()], "target": target()}, SecurityPolicy()
    ).payload
    policy = AutomationPolicy.from_file(ROOT / "policies" / "automation-target-policy.json")
    content = (
        "CASE_SPEC = {\n"
        "    'id': 'TC-BE-001-BACKEND',\n"
        "    'test_level': 'integration',\n"
        "    'setup': [],\n"
        "    'steps': [{'name': 'query', 'request': {'api': 'fs_bi_stat.stat_base.detail_data_query', 'json': {}}}],\n"
        "    'expected': [\n"
        "        {'id': 'E-BE-003-05', 'oracle': {'matcher': 'not_equals',\n"
        "            'observation_point': 'detail_api.response.error_code', 'expected_value': 's307011536'}},\n"
        "        {'id': 'E-BE-006-01', 'oracle': {'matcher': 'not_one_of',\n"
        "            'observation_point': 'detail_api.response.error_code',\n"
        "            'expected_value': ['s307011534', 's307011535']}},\n"
        "        {'id': 'E-BE-007-01', 'oracle': {'matcher': 'one_of',\n"
        "            'observation_point': 'detail_api.response.error_code',\n"
        "            'expected_value': ['s307011534', 's307011535']}},\n"
        "    ],\n"
        "    'cleanup': [],\n"
        "}\n"
        "def test_tc_be_001_backend(case_runner):\n"
        "    observations = case_runner.execute(CASE_SPEC)\n"
        "    case_runner.assert_oracles(observations, CASE_SPEC['expected'])\n"
    )
    candidate = generation["code_candidates"][0]
    candidate["content"] = content
    candidate["content_hash"] = content_hash(content)
    generation["manifest"]["candidate_files"][0]["content_hash"] = candidate["content_hash"]
    result = check_automation_generation(generation, policy)
    codes = {item["issue_code"] for item in result["issues"]}
    assert "oracle_matcher_not_supported" not in codes
    assert result["passed"] is True


def test_n05_rejects_placeholder_setup_body_missing_contract_fields() -> None:
    """N05 必须拦下 setup 阶段仅含 namespace/variant 的占位 body：112 业务校验
    会拒绝这类请求，放行只会让 N08 以 infrastructure_error 失败。"""
    from qa_agents.contracts import content_hash

    generation = BackendAutomationAgent().run(
        context(), {"cases": [backend_case()], "target": target()}, SecurityPolicy()
    ).payload
    policy = AutomationPolicy.from_file(ROOT / "policies" / "automation-target-policy.json")
    content = (
        'CASE_SPEC = {"id": "TC-BE-001-BACKEND", "test_level": "integration", '
        '"test_data": {"resource_requirements": ['
        '{"resource_key": "cd_field", "resource_type": "custom_dimension", '
        '"setup_operation": "fs_bi_stat.custom_dimension.create_custom_dimension", '
        '"required_body_keys": ["topologyDescribeId", "customType", "dimensionName", '
        '"dimensionConfig", "describeApiName", "sourceField"]}]}, '
        '"setup": [{"name": "create", "request": {"api": '
        '"fs_bi_stat.custom_dimension.create_custom_dimension", '
        '"json": {"namespace": "qa-a22-pilot-001-source-v1", "variants": ["baseline"]}}}], '
        '"steps": [{"name": "query", "request": {"api": '
        '"fs_bi_stat.custom_dimension.get_custom_dimension", "json": {}}}], '
        '"expected": [{"id": "EXP-1", "matcher": "equals", "observation_point": "detail_api.error.code", '
        '"expected_value": "s307011534"}], "cleanup": []}\n'
        "def test_tc_be_001_backend(case_runner):\n"
        "    observations = case_runner.execute(CASE_SPEC)\n"
        '    case_runner.assert_oracles(observations, CASE_SPEC["expected"])\n'
    )
    candidate = generation["code_candidates"][0]
    candidate["content"] = content
    candidate["content_hash"] = content_hash(content)
    generation["manifest"]["candidate_files"][0]["content_hash"] = candidate["content_hash"]
    result = check_automation_generation(generation, policy)
    assert result["passed"] is False
    codes = {item["issue_code"] for item in result["issues"]}
    assert "setup_body_missing_contract_fields" in codes
    assert result["fatal_security_violation"] is False


def test_n05_allows_setup_body_with_verified_contract_keys() -> None:
    """完整携带 required_body_keys 的 setup body 不再被占位校验拦截。"""
    from qa_agents.contracts import content_hash

    generation = BackendAutomationAgent().run(
        context(), {"cases": [backend_case()], "target": target()}, SecurityPolicy()
    ).payload
    policy = AutomationPolicy.from_file(ROOT / "policies" / "automation-target-policy.json")
    content = (
        'CASE_SPEC = {"id": "TC-BE-001-BACKEND", "test_level": "integration", '
        '"test_data": {"resource_requirements": ['
        '{"resource_key": "cd_field", "resource_type": "custom_dimension", '
        '"setup_operation": "fs_bi_stat.custom_dimension.create_custom_dimension", '
        '"required_body_keys": ["topologyDescribeId", "customType", "dimensionName", '
        '"dimensionConfig", "describeApiName", "sourceField"]}]}, '
        '"setup": [{"name": "create", "request": {"api": '
        '"fs_bi_stat.custom_dimension.create_custom_dimension", '
        '"json": {"topologyDescribeId": "BI_5bcebcdc3060e20001e79977", '
        '"customType": "enum_group", "dimensionName": "qa-a22-pilot-001-source-v1-baseline", '
        '"description": "auto", "dimensionConfig": "{}", "describeApiName": "AccountObj", '
        '"sourceField": {"fieldId": "BI_5bcebcddcab2980001ee22b3", "apiName": "account_level"}}}], '
        '"steps": [{"name": "query", "request": {"api": '
        '"fs_bi_stat.custom_dimension.get_custom_dimension", "json": {}}}], '
        '"expected": [{"id": "EXP-1", "matcher": "equals", "observation_point": "detail_api.error.code", '
        '"expected_value": "s307011534"}], "cleanup": []}\n'
        "def test_tc_be_001_backend(case_runner):\n"
        "    observations = case_runner.execute(CASE_SPEC)\n"
        '    case_runner.assert_oracles(observations, CASE_SPEC["expected"])\n'
    )
    candidate = generation["code_candidates"][0]
    candidate["content"] = content
    candidate["content_hash"] = content_hash(content)
    generation["manifest"]["candidate_files"][0]["content_hash"] = candidate["content_hash"]
    result = check_automation_generation(generation, policy)
    codes = {item["issue_code"] for item in result["issues"]}
    assert "setup_body_missing_contract_fields" not in codes


def test_n05_rejects_unverified_setup_expectation_and_extract_path() -> None:
    from qa_agents.contracts import content_hash

    generation = BackendAutomationAgent().run(
        context(), {"cases": [backend_case()], "target": target()}, SecurityPolicy()
    ).payload
    policy = AutomationPolicy.from_file(ROOT / "policies" / "automation-target-policy.json")
    content = (
        'CASE_SPEC = {"id": "CASE-001-BACKEND", "test_level": "integration", '
        '"test_data": {}, "setup": [{"request": {"api": '
        '"fs_bi_stat.custom_dimension.create_custom_dimension", "json": {'
        '"topologyDescribeId": "id", "customType": "enum_group", '
        '"dimensionName": "name", "dimensionConfig": "{}", '
        '"describeApiName": "AccountObj", "sourceField": {}}}, '
        '"extract": {"field_id": "$.data.fieldId"}, "expect": {"status": "success"}}], '
        '"readiness": [], "steps": [{"request": {"api": '
        '"fs_bi_stat.stat_base.detail_data_query", "json": {}}}], '
        '"expected": [{"id": "EXP-1", "oracle": {"matcher": "equals", '
        '"observation_point": "response.code", "expected_value": "OK"}}], '
        '"cleanup": [], "residue_checks": []}\n'
        "def test_case(case_runner):\n"
        "    observations = case_runner.execute(CASE_SPEC)\n"
        '    case_runner.assert_oracles(observations, CASE_SPEC["expected"])\n'
    )
    candidate = generation["code_candidates"][0]
    candidate["content"] = content
    candidate["content_hash"] = content_hash(content)
    generation["manifest"]["candidate_files"][0]["content_hash"] = candidate["content_hash"]

    result = check_automation_generation(generation, policy)

    codes = {item["issue_code"] for item in result["issues"]}
    assert "response_expectation_unsupported" in codes
    assert "setup_extract_contract_mismatch" in codes


def test_n05_rejects_cleanup_for_retained_resources() -> None:
    from qa_agents.contracts import content_hash

    generation = BackendAutomationAgent().run(
        context(), {"cases": [backend_case()], "target": target()}, SecurityPolicy()
    ).payload
    policy = AutomationPolicy.from_file(ROOT / "policies" / "automation-target-policy.json")
    content = (
        'CASE_SPEC = {"id": "CASE-001-BACKEND", "test_level": "integration", '
        '"test_data": {"resource_requirements": [{"resource_key": "chart", '
        '"resource_type": "stat_chart", "setup_operation": '
        '"fs_bi_crm.stat_create.copy_stat_view", "resource_id_variable": '
        '"chart_view_id", "retention_mode": "retain", '
        '"required_body_keys": ["statViewBaseInfo"]}]}, '
        '"setup": [{"request": {"api": "fs_bi_crm.stat_create.copy_stat_view", '
        '"json": {"statViewBaseInfo": {"viewID": "BI_source", "isChange": 0}}}, '
        '"extract": {"chart_view_id": "Value.viewID"}, '
        '"expect": {"status_code": 200}}], "readiness": [], "steps": [], '
        '"expected": [{"id": "EXP-1", "oracle": {"matcher": "equals", '
        '"observation_point": "response.code", "expected_value": "OK"}}], '
        '"cleanup": [{"name": "bad_cleanup", "when_variable": "chart_view_id", '
        '"request": {"api": "fs_bi_crm.rpt_view_display.move_rpt_view", '
        '"json": {"viewID": "{{chart_view_id}}"}}}]}\n'
        "def test_case(case_runner):\n"
        "    observations = case_runner.execute(CASE_SPEC)\n"
        '    case_runner.assert_oracles(observations, CASE_SPEC["expected"])\n'
    )
    candidate = generation["code_candidates"][0]
    candidate["content"] = content
    candidate["content_hash"] = content_hash(content)
    generation["manifest"]["candidate_files"][0]["content_hash"] = candidate["content_hash"]

    result = check_automation_generation(generation, policy)

    assert result["passed"] is False
    assert "retained_resource_cleanup_forbidden" in {
        item["issue_code"] for item in result["issues"]
    }


def test_n05_rejects_unverified_result_filter_operation() -> None:
    from qa_agents.contracts import content_hash

    generation = BackendAutomationAgent().run(
        context(), {"cases": [backend_case()], "target": target()}, SecurityPolicy()
    ).payload
    policy = AutomationPolicy.from_file(ROOT / "policies/automation-target-policy.json")
    content = (
        'CASE_SPEC = {"id": "CASE-RS", "title": "结果集筛选", "test_data": {}, '
        '"setup": [], "readiness": [], "steps": [{"name": "detail", '
        '"request": {"api": "fs_bi_stat.stat_base.detail_data_query", "json": {}}}], '
        '"expected": [{"id": "EXP-1", "oracle": {"matcher": "equals", '
        '"observation_point": "detail_api.error.code", '
        '"expected_value": "s307011535"}}], "cleanup": []}\n'
        "def test_case(case_runner):\n"
        "    observations = case_runner.execute(CASE_SPEC)\n"
        '    case_runner.assert_oracles(observations, CASE_SPEC["expected"])\n'
    )
    candidate = generation["code_candidates"][0]
    candidate["content"] = content
    candidate["content_hash"] = content_hash(content)
    generation["manifest"]["candidate_files"][0]["content_hash"] = candidate[
        "content_hash"
    ]

    result = check_automation_generation(generation, policy)

    assert "execution_contract_mismatch" in {
        item["issue_code"] for item in result["issues"]
    }


def test_n05_rejects_incomplete_verified_execution_body() -> None:
    from qa_agents.contracts import content_hash

    generation = BackendAutomationAgent().run(
        context(), {"cases": [backend_case()], "target": target()}, SecurityPolicy()
    ).payload
    policy = AutomationPolicy.from_file(ROOT / "policies/automation-target-policy.json")
    content = (
        'CASE_SPEC = {"id": "CASE-RS", "title": "结果集筛选", "test_data": {}, '
        '"setup": [], "readiness": [], "steps": [{"name": "detail", '
        '"request": {"api": "fs_bi_stat.stat_base.data_query_da655ba1", '
        '"json": {"id": "schema"}}}], "expected": [{"id": "EXP-1", '
        '"oracle": {"matcher": "equals", '
        '"observation_point": "detail_api.error.code", '
        '"expected_value": "s307011535"}}], "cleanup": []}\n'
        "def test_case(case_runner):\n"
        "    observations = case_runner.execute(CASE_SPEC)\n"
        '    case_runner.assert_oracles(observations, CASE_SPEC["expected"])\n'
    )
    candidate = generation["code_candidates"][0]
    candidate["content"] = content
    candidate["content_hash"] = content_hash(content)
    generation["manifest"]["candidate_files"][0]["content_hash"] = candidate[
        "content_hash"
    ]

    result = check_automation_generation(generation, policy)

    assert "execution_body_missing_contract_fields" in {
        item["issue_code"] for item in result["issues"]
    }


def test_a18_ignores_rejected_cases_for_mapping() -> None:
    """Rejected A14 cases must not block A18 approval of mapped candidates."""
    security = SecurityPolicy()
    mapped = backend_case()
    mapped["id"] = "CASE-MAPPED-BACKEND"
    mapped["expected"][0]["id"] = "EXP-MAPPED"
    rejected = backend_case()
    rejected["id"] = "CASE-REJECTED-BACKEND"
    rejected["expected"][0]["id"] = "EXP-REJECTED"

    generation = BackendAutomationAgent().run(
        context(), {"cases": [mapped], "target": target()}, security
    ).payload
    generation = {
        **generation,
        "rejected_cases": [
            {"case_id": rejected["id"], "reason_code": "execution_step_not_structured"}
        ],
    }
    # Keep mapping only for the generated case.
    review = BackendAutomationReviewAgent().run(
        context(),
        {"cases": [mapped, rejected], "generation": generation},
        security,
    )
    assert review.payload["approved"] is True
    assert review.payload["issues"] == []



def test_n05_allows_bind_stat_chart_config_setup_action() -> None:
    """Copied charts must be rebound; N05 cannot reject the bind action step."""
    from qa_agents.contracts import content_hash

    generation = BackendAutomationAgent().run(
        context(), {"cases": [backend_case()], "target": target()}, SecurityPolicy()
    ).payload
    policy = AutomationPolicy.from_file(ROOT / "policies" / "automation-target-policy.json")
    content = (
        "CASE_SPEC={'id':'PC-BE-001-BACKEND','test_data':{'resource_requirements':["
        "{'resource_type':'stat_chart','resource_id_variable':'chart_view_id',"
        "'retention_mode':'retain'}]},'setup':["
        "{'name':'bind_chart','action':'bind_stat_chart_config',"
        "'inputs':{'chart_view_id':'{{chart_view_id}}',"
        "'schema_id':'BI_5be1351956fc11448cdde39e'},"
        "'expect':{'status_code':200}}],"
        "'steps':[{'name':'call','request':{'api':'fs_bi_stat.stat_base.data_query_da655ba1',"
        "'json':{'id':'{{chart_view_id}}','isView':0,'measureFieldID':'m',"
        "'measureFieldIDs':['m'],'pageNumber':1,'pageSize':20,'filterLists':[],"
        "'timeZone':'Asia/Shanghai','lan':'zh-CN'}},'expect':{'status_code':200}}],"
        "'expected':[{'id':'E1','oracle':{'expected_value':'s307011534','matcher':'equals',"
        "'observation_point':'detail_api.response.error_code','type':'deterministic'}}],"
        "'cleanup':[]}\n"
        "def test_pc_be_001_backend(case_runner):\n"
        "    observations=case_runner.execute(CASE_SPEC)\n"
        "    case_runner.assert_oracles(observations,CASE_SPEC['expected'])\n"
    )
    candidate = generation["code_candidates"][0]
    candidate["content"] = content
    candidate["content_hash"] = content_hash(content)
    generation["manifest"]["candidate_files"][0]["content_hash"] = candidate["content_hash"]
    result = check_automation_generation(generation, policy)
    codes = {item["issue_code"] for item in result["issues"]}
    assert "execution_request_missing" not in codes
    assert "unsupported_step_action" not in codes
    assert result["passed"] is True, result["issues"]


def test_n05_rejects_chart_binding_without_chart_resource() -> None:
    from qa_agents.contracts import content_hash

    case = backend_case()
    case["test_data"].pop("resource_requirements")
    generation = BackendAutomationAgent().run(
        context(), {"cases": [case], "target": target()}, SecurityPolicy()
    ).payload
    policy = AutomationPolicy.from_file(ROOT / "policies" / "automation-target-policy.json")
    content = (
        "CASE_SPEC={'id':'CASE-001-BACKEND','steps':[{'name':'call',"
        "'request':{'api':'fs_bi_stat.stat_base.data_query_da655ba1',"
        "'json':{'id':'{{chart_view_id}}'}},'expect':{'status_code':200}}],"
        "'expected':[],'cleanup':[]}\n"
        "def test_case(case_runner):\n"
        "    observations=case_runner.execute(CASE_SPEC)\n"
        "    case_runner.assert_oracles(observations,CASE_SPEC['expected'])\n"
    )
    candidate = generation["code_candidates"][0]
    candidate["content"] = content
    candidate["content_hash"] = content_hash(content)
    generation["manifest"]["candidate_files"][0]["content_hash"] = candidate["content_hash"]
    result = check_automation_generation(generation, policy)
    assert result["passed"] is False
    assert "chart_binding_missing" in {item["issue_code"] for item in result["issues"]}


def test_n05_rejects_schema_id_bound_as_chart_id() -> None:
    from qa_agents.contracts import content_hash

    generation = BackendAutomationAgent().run(
        context(), {"cases": [backend_case()], "target": target()}, SecurityPolicy()
    ).payload
    policy = AutomationPolicy.from_file(ROOT / "policies" / "automation-target-policy.json")
    content = (
        "CASE_SPEC={'id':'CASE-001-BACKEND','test_data':{'resource_requirements':["
        "{'resource_type':'stat_chart','resource_id_variable':'chart_view_id',"
        "'retention_mode':'retain'}]},'variables':{'chart_view_id':"
        "'BI_e672ff1046fb773b76bc2b56'},'steps':[{'name':'call',"
        "'request':{'api':'fs_bi_stat.stat_base.data_query_da655ba1',"
        "'json':{'id':'{{chart_view_id}}'}},'expect':{'status_code':200}}],"
        "'expected':[],'cleanup':[]}\n"
        "def test_case(case_runner):\n"
        "    observations=case_runner.execute(CASE_SPEC)\n"
        "    case_runner.assert_oracles(observations,CASE_SPEC['expected'])\n"
    )
    candidate = generation["code_candidates"][0]
    candidate["content"] = content
    candidate["content_hash"] = content_hash(content)
    generation["manifest"]["candidate_files"][0]["content_hash"] = candidate["content_hash"]
    result = check_automation_generation(generation, policy)
    assert result["passed"] is False
    assert "chart_id_forgery" in {item["issue_code"] for item in result["issues"]}
