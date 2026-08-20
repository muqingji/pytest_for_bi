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
        "test_data": {"request": {"method": "GET", "path": "/api/report"}},
        "steps": [{
            "name": "请求报表接口",
            "request": {"protocol": "http", "api": "report.query", "json": {}},
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

