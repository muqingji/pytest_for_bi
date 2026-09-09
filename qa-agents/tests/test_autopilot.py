import json
from pathlib import Path

import pytest

from qa_agents.autopilot import (
    SERVER_NODE_DEFINITIONS,
    SERVER_STAGE_CARD_DEFINITIONS,
    _advance_frontier,
    _approval_items,
    _artifact_state,
    _artifact_summary,
    initialize_autopilot,
    reconcile_autopilot,
)
from qa_agents.contracts import ArtifactEnvelope, ArtifactStatus, Producer, content_hash
from qa_agents.errors import ContractError


def test_inconclusive_artifact_is_waiting_not_completed() -> None:
    artifact = {"status": "inconclusive", "payload": {"decision": "inconclusive"}}
    assert _artifact_state(artifact) == "waiting_human"


def test_needs_human_with_only_agent_routes_is_automatic_return() -> None:
    artifact = {
        "status": "needs_human",
        "payload": {"issues": [{"route_to": "A08"}, {"route_to": "A08"}]},
        "blocking_questions": [],
    }
    assert _artifact_state(artifact) == "blocked"


def test_needs_human_with_human_route_waits_for_human() -> None:
    artifact = {
        "status": "needs_human",
        "payload": {"issues": [{"route_to": "human"}]},
        "blocking_questions": [],
    }
    assert _artifact_state(artifact) == "waiting_human"


def test_needs_human_with_exhausted_budget_routes_to_human_gate() -> None:
    artifact = {
        "status": "needs_human",
        "payload": {"next_node": "human", "issues": [{"route_to": "A08"}]},
        "blocking_questions": [],
    }
    assert _artifact_state(artifact) == "waiting_human"


def test_artifact_summary_n11_shows_server_gate_counts() -> None:
    artifact = {
        "artifact_id": "n11-quality-decision",
        "status": "blocked",
        "payload": {
            "decision": "blocked",
            "metrics": {"executed": 7, "passed": 0, "failed": 7},
        },
    }
    assert _artifact_summary(artifact) == "服务端不准出：执行 7，通过 0，失败 7"


def test_artifact_summary_needs_human_lists_blocking_issues() -> None:
    artifact = {
        "artifact_id": "a09-oracle-coverage-review",
        "payload": {
            "status": "needs_human",
            "issues": [
                {"id": "A09-ISSUE-007", "issue_code": "ORACLE_EXPECTED_REFERENCE_UNRESOLVABLE"},
                {"id": "A09-ISSUE-008", "issue_code": "LOCALE_NAME_PRECEDENCE_FIXTURE_CONFLICT"},
            ]
        },
    }
    summary = _artifact_summary(artifact)
    assert "2 个阻塞问题" in summary
    assert "A09-ISSUE-007" in summary
    assert "A09-ISSUE-008" in summary


def test_artifact_summary_falls_back_to_status_without_issues() -> None:
    artifact = {"artifact_id": "a09-oracle-coverage-review", "payload": {"status": "needs_human"}}
    assert _artifact_summary(artifact) == "needs_human"


def test_approval_items_carry_issue_message_and_recommendation() -> None:
    artifact = {
        "status": "needs_human",
        "payload": {
            "next_node": "human",
            "issues": [
                {
                    "id": "A09-ISSUE-007",
                    "issue_code": "ORACLE_EXPECTED_REFERENCE_UNRESOLVABLE",
                    "category": "oracle",
                    "human_title": "预期结果写错了",
                    "plain_summary": "预期结果指向不存在的字段，用例无法校验。",
                    "case_id": "TC-E2E-001",
                    "expected_id": "EXP-E2E-001-01",
                    "message": "expected_value 指向不存在的 test_data 路径，无法解析。",
                    "recommendation": "改为可直接解析的结构化期望矩阵。",
                    "route_to": "A08",
                }
            ],
        },
        "blocking_questions": [],
    }
    items = _approval_items(artifact)
    assert len(items) == 1
    assert items[0]["summary"] == "预期结果指向不存在的字段，用例无法校验。"
    assert items[0]["issue_code"] == "ORACLE_EXPECTED_REFERENCE_UNRESOLVABLE"
    assert items[0]["human_title"] == "预期结果写错了"
    assert items[0]["plain_summary"] == "预期结果指向不存在的字段，用例无法校验。"
    assert items[0]["case_id"] == "TC-E2E-001"
    assert items[0]["expected_id"] == "EXP-E2E-001-01"
    assert items[0]["recommendation"] == "改为可直接解析的结构化期望矩阵。"


def test_approval_items_carry_g02_review_items() -> None:
    artifact = {
        "artifact_id": "g02-test-case-ir-review",
        "status": "needs_human",
        "payload": {
            "gate_id": "G02",
            "issues": [],
            "review_summary": {
                "parent_case_count": 2,
                "n04_valid": True,
                "blocking_issue_count": 0,
                "warning_count": 0,
            },
            "review_items": [
                {
                    "case_id": "PC-BE-001",
                    "title": "Backend custom dimension dedicated error",
                    "layer": "backend",
                    "priority": "P0",
                    "risk": "critical",
                    "scenario": "Custom dimension in dimension returns s307011534",
                    "source_refs": ["REQ-001", "REQ-002", "TF-003"],
                    "expected": [{"id": "E-1"}, {"id": "E-2"}],
                },
                {
                    "case_id": "PC-BE-002",
                    "title": "Result-set metric filter dedicated error",
                    "layer": "backend",
                    "priority": "P0",
                    "risk": "critical",
                    "scenario": "Result-set filter returns s307011535",
                    "source_refs": ["REQ-003"],
                    "expected": [{"id": "E-3"}],
                },
            ],
        },
    }
    items = _approval_items(artifact)
    assert len(items) == 1
    assert items[0]["category"] == "用例设计待确认"
    assert items[0]["human_title"] == "没有未冻结的产品口径"
    assert "没有需要你补口径的产品场景" in items[0]["summary"]
    assert "Custom dimension" not in items[0]["summary"]
    assert _artifact_summary(artifact) == "2 条用例没有未冻结口径，待放行"


def test_approval_items_use_review_summary_when_review_items_missing() -> None:
    artifact = {
        "artifact_id": "g02-test-case-ir-review",
        "status": "needs_human",
        "payload": {
            "gate_id": "G02",
            "issues": [],
            "review_summary": {"parent_case_count": 11, "n04_valid": True},
        },
    }
    items = _approval_items(artifact)
    assert len(items) == 1
    assert items[0]["category"] == "用例设计待确认"
    assert items[0]["human_title"] == "没有未冻结的产品口径"
    assert "11 条父用例的错误码、文案和覆盖已经按冻结规则写完" in items[0]["summary"]
    assert _artifact_summary(artifact) == "11 条用例没有未冻结口径，待放行"



def test_approval_items_only_surface_g02_case_design_uncertainty() -> None:
    artifact = {
        "artifact_id": "g02-test-case-ir-review",
        "status": "needs_human",
        "payload": {
            "gate_id": "G02",
            "review_summary": {"parent_case_count": 3, "n04_valid": True},
            "skipped_scenarios": [
                {
                    "id": "SKIP-EMPTY-METRIC-NAME",
                    "reason": "skip_not_applicable",
                    "details": "Empty metric display name must not generate specialized copy.",
                    "rule_ref": "RULE-SINGLE-METRIC",
                }
            ],
            "review_items": [
                {
                    "case_id": "PC-BE-001",
                    "title": "Backend custom dimension dedicated error",
                    "layer": "backend",
                    "scenario": "Custom dimension returns s307011534",
                    "source_refs": ["RULE-CUSTOM-DIMENSION"],
                    "expected": [
                        {
                            "id": "E-1",
                            "oracle": {"type": "deterministic", "matcher": "equals"},
                        }
                    ],
                },
                {
                    "case_id": "PC-BE-006",
                    "title": "Backend permission errors preserve existing behavior",
                    "layer": "backend",
                    "source_refs": ["RULE-PERMISSION-PRIORITY"],
                    "expected": [
                        {
                            "id": "E-BE-006-02",
                            "description": "error_code equals pre-change permission failure",
                            "oracle": {
                                "type": "human_review",
                                "matcher": "manual_confirmation",
                            },
                        }
                    ],
                },
            ],
        },
    }
    items = _approval_items(artifact)
    assert [item["id"] for item in items] == [
        "PC-BE-006:human_review",
        "SKIP-EMPTY-METRIC-NAME",
    ]
    assert items[0]["human_title"] == "没权限时不要改提示"
    assert "原来的权限失败" in items[0]["product_scene"]
    assert "请确认该用例的场景、步骤和预期结果可直接执行" not in items[0]["confirm_action"]
    assert items[1]["human_title"] == "空指标名这轮不测"
    assert "PC-BE-001" not in {item["id"] for item in items}
    assert _artifact_summary(artifact) == "2 个用例设计待确认（没权限时不要改提示、空指标名这轮不测）"


def test_frontier_advances_past_skipped_g03_to_n07() -> None:
    nodes = [
        {"node_id": "G03", "stage": 18, "state": "skipped"},
        {"node_id": "N07", "stage": 19, "state": "not_started"},
        {"node_id": "N08", "stage": 20, "state": "not_started"},
    ]

    _advance_frontier(nodes)

    assert nodes[1]["state"] == "queued"
    assert nodes[2]["state"] == "not_started"


def test_frontier_queues_all_parallel_nodes_and_stops_on_blocker() -> None:
    nodes = [
        {"node_id": "A02", "stage": 3, "state": "not_started"},
        {"node_id": "A03", "stage": 3, "state": "not_started"},
        {"node_id": "A06", "stage": 4, "state": "not_started"},
    ]
    _advance_frontier(nodes)
    assert [item["state"] for item in nodes] == ["queued", "queued", "not_started"]

    nodes[0]["state"] = "completed"
    nodes[1]["state"] = "blocked"
    _advance_frontier(nodes)
    assert nodes[2]["state"] == "not_started"


def _write(path: Path, value: dict) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
    return path


def _request(path: Path, run_id: str = "REQ-1-r001") -> Path:
    return _write(
        path,
        {
            "schema_version": "autopilot-request/1.0",
            "workflow_id": "REQ-1",
            "requirement_id": "REQ-1",
            "workflow_run_id": run_id,
            "workflow_definition_version": "server-requirement/1.0",
            "source_snapshot_id": "snapshot-1",
            "title": "服务端接口优化",
            "human_owner_member_id": "member-qa",
        },
    )


def _config(path: Path) -> Path:
    return _write(
        path,
        {
            "schema_version": "multica-workflow-center/1.0",
            "workspace_id": "workspace-1",
            "workflow_project_id": "project-workflow",
            "internal_project_id": "project-internal",
            "workflow_lead_id": "agent-lead",
            "properties": {},
        },
    )


class FakeMultica:
    def __init__(self) -> None:
        self.calls: list[list[str]] = []
        self.number = 0

    def __call__(self, command: list[str], _stdin: str | None) -> dict:
        self.calls.append(command)
        self.number += 1
        if command[1:3] == ["autopilot", "create"]:
            return {
                "id": f"autopilot-{self.number}",
                "assignee_id": command[command.index("--agent") + 1],
                "project_id": command[command.index("--project") + 1],
                "execution_mode": "run_only",
                "status": "active",
            }
        if command[1:3] == ["issue", "metadata"]:
            return {"id": command[4]}
        project_id = command[command.index("--project") + 1]
        return {
            "id": f"issue-{self.number}",
            "identifier": f"QAA-{self.number}",
            "project_id": project_id,
        }


def test_autopilot_reuses_requirement_parent_and_run_idempotently(tmp_path: Path) -> None:
    request = _request(tmp_path / "request.json")
    config = _config(tmp_path / "config.json")
    multica = FakeMultica()

    first = initialize_autopilot(
        request, config, tmp_path / "registry", tmp_path / "run-1", runner=multica
    )
    repeated = initialize_autopilot(
        request, config, tmp_path / "registry", tmp_path / "run-1-repeat", runner=multica
    )

    assert first["parent_reused"] is False
    assert first["run_reused"] is False
    assert repeated["parent_reused"] is True
    assert repeated["run_reused"] is True
    assert repeated["parent_issue"] == first["parent_issue"]
    assert repeated["run_issue"] == first["run_issue"]
    assert len(multica.calls) == 3
    assert repeated["autopilot"] == first["autopilot"]
    assert repeated["autopilot_reused"] is True

    second_request = _request(tmp_path / "request-2.json", "REQ-1-r002")
    second = initialize_autopilot(
        second_request,
        config,
        tmp_path / "registry",
        tmp_path / "run-2",
        runner=multica,
    )
    assert second["parent_issue"] == first["parent_issue"]
    assert second["run_issue"] != first["run_issue"]
    assert len(multica.calls) == 4
    registry = json.loads((tmp_path / "registry/autopilot-registry.json").read_text())
    assert len(registry["workflows"]["REQ-1"]["runs"]) == 2
    assert registry["workflows"]["REQ-1"]["runs"][0]["status"] == "superseded"


def test_precreated_stage_issues_are_reused_for_same_run(tmp_path: Path) -> None:
    request = _request(tmp_path / "request.json")
    config = json.loads(_config(tmp_path / "config.json").read_text())
    config["precreate_nodes"] = True
    config_path = _write(tmp_path / "config.json", config)
    multica = FakeMultica()

    initialize_autopilot(
        request, config_path, tmp_path / "registry", tmp_path / "first", runner=multica
    )
    call_count = len(multica.calls)
    initialize_autopilot(
        request, config_path, tmp_path / "registry", tmp_path / "second", runner=multica
    )

    assert len(multica.calls) == call_count
    first = json.loads((tmp_path / "first/workflow-center-spec.json").read_text())
    second = json.loads((tmp_path / "second/workflow-center-spec.json").read_text())
    assert all("issue_id" not in item for item in first["nodes"])
    assert all("issue_id" not in item for item in second["nodes"])
    card_calls = {
        command[command.index("--title") + 1].split()[1]: command
        for command in multica.calls
        if command[1:3] == ["issue", "create"]
        and command[command.index("--title") + 1].startswith("[REQ-1-r001]")
        and "服务端 QA Run" not in command[command.index("--title") + 1]
        and command[command.index("--title") + 1].split()[1].startswith("C")
    }
    assert set(card_calls) == {item[0] for item in SERVER_STAGE_CARD_DEFINITIONS}
    assert len(card_calls) == 8
    assert all("--assignee-id" not in command for command in card_calls.values())
    assert len({item["stage_issue_id"] for item in first["nodes"]}) == 8
    assert len(first["nodes"]) == len(SERVER_NODE_DEFINITIONS)
    assert all(item.get("stage_card_id") for item in first["nodes"])


def test_reconcile_refreshes_replaced_node_and_stage_bindings(tmp_path: Path) -> None:
    request = _request(tmp_path / "request.json")
    config = json.loads(_config(tmp_path / "config.json").read_text())
    config["precreate_nodes"] = True
    config_path = _write(tmp_path / "config.json", config)
    initialize_autopilot(request, config_path, tmp_path / "registry", tmp_path / "initial", runner=FakeMultica())

    registry_path = tmp_path / "registry/autopilot-registry.json"
    registry = json.loads(registry_path.read_text())
    run = registry["workflows"]["REQ-1"]["runs"][0]
    run["node_issues"]["A03"] = {"id": "replacement-node", "identifier": "QAA-999"}
    run["stage_issues"]["C1"] = {"id": "replacement-stage", "identifier": "QAA-998"}
    registry["registry_hash"] = content_hash({k: v for k, v in registry.items() if k != "registry_hash"})
    registry_path.write_text(json.dumps(registry), encoding="utf-8")

    result = reconcile_autopilot(
        tmp_path / "initial/workflow-center-spec.json", [], tmp_path / "reconciled"
    )
    spec = json.loads(Path(result["spec_path"]).read_text())
    node = next(item for item in spec["nodes"] if item["node_id"] == "A03")
    assert node["issue_identifier"] == "QAA-999"
    assert node["stage_issue_identifier"] == "QAA-998"
    card = next(item for item in spec["stage_cards"] if item["stage_card_id"] == "C1")
    assert card["issue_identifier"] == "QAA-998"
def test_autopilot_creates_parent_in_center_and_run_in_internal_project(tmp_path: Path) -> None:
    multica = FakeMultica()
    initialize_autopilot(
        _request(tmp_path / "request.json"),
        _config(tmp_path / "config.json"),
        tmp_path / "registry",
        tmp_path / "run",
        runner=multica,
    )

    parent, autopilot, run = multica.calls
    assert parent[parent.index("--project") + 1] == "project-internal"
    assert "--parent" not in parent
    assert run[run.index("--project") + 1] == "project-internal"
    assert run[run.index("--parent") + 1] == "issue-1"
    assert autopilot[1:3] == ["autopilot", "create"]
    assert autopilot[autopilot.index("--mode") + 1] == "run_only"


def test_autopilot_initializes_complete_server_quality_dag(tmp_path: Path) -> None:
    initialize_autopilot(
        _request(tmp_path / "request.json"),
        _config(tmp_path / "config.json"),
        tmp_path / "registry",
        tmp_path / "run",
        runner=FakeMultica(),
    )

    spec = json.loads((tmp_path / "run/workflow-center-spec.json").read_text())
    nodes = {item["node_id"]: item for item in spec["nodes"]}
    assert {
        "A14", "A15", "A18-BE", "A18-CT", "N05", "G03", "N07", "N08",
        "N10", "N17", "N18", "N09", "N20", "N11", "N19", "N12", "N13", "N23",
    } <= set(nodes)
    assert nodes["A14"]["stage"] == nodes["A15"]["stage"]
    assert nodes["N08"]["stage"] == nodes["N17"]["stage"]
    assert nodes["N17"]["label"] == "未执行用例收口"
    assert nodes["N11"]["label"] == "服务端准出判定"
    assert nodes["N23"]["stage"] > nodes["N12"]["stage"]


def test_reconcile_refreshes_stale_n11_label(tmp_path: Path) -> None:
    initialize_autopilot(
        _request(tmp_path / "request.json"),
        _config(tmp_path / "config.json"),
        tmp_path / "registry",
        tmp_path / "run",
        runner=FakeMultica(),
    )
    spec_path = tmp_path / "run/workflow-center-spec.json"
    spec = json.loads(spec_path.read_text())
    for node in spec["nodes"]:
        if node["node_id"] == "N11":
            node["label"] = "确定性质量决策"
            node["stage_card_title"] = "证据归一与质量决策"
    for card in spec["stage_cards"]:
        if card["stage_card_id"] == "C7":
            card["title"] = "证据归一与质量决策"
    spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
    reconcile_autopilot(spec_path, [tmp_path / "artifacts"], tmp_path / "reconciled")
    out = json.loads((tmp_path / "reconciled/workflow-center-spec.json").read_text())
    nodes = {item["node_id"]: item for item in out["nodes"]}
    cards = {item["stage_card_id"]: item for item in out["stage_cards"]}
    assert nodes["N11"]["label"] == "服务端准出判定"
    assert nodes["N11"]["stage_card_title"] == "证据归一与准出判定"
    assert cards["C7"]["title"] == "证据归一与准出判定"


def test_reconcile_derives_nodes_and_human_actions_from_artifacts(tmp_path: Path) -> None:
    multica = FakeMultica()
    initialize_autopilot(
        _request(tmp_path / "request.json"),
        _config(tmp_path / "config.json"),
        tmp_path / "registry",
        tmp_path / "initial",
        runner=multica,
    )
    artifacts = tmp_path / "artifacts"
    for component, artifact_id, status, payload in (
        (
            "N01",
            "n01-source-extraction-manifest",
            ArtifactStatus.COMPLETED,
            {"summary": "输入已冻结"},
        ),
        (
            "A02",
            "a02-requirement-analysis",
            ArtifactStatus.COMPLETED_WITH_GAPS,
            {"summary": "识别 2 个开放问题"},
        ),
        (
            "A03",
            "a03-technical-testability-analysis",
            ArtifactStatus.NEEDS_HUMAN,
            {"status": "needs_human", "blocking_items": [{"id": "BI-001", "summary": "文案待确认"}]},
        ),
        (
            "G01",
            "g01-scope-review",
            ArtifactStatus.NEEDS_HUMAN,
            {"decision": "pending", "issues": [{"id": "I1"}, {"id": "I2"}]},
        ),
    ):
        envelope = ArtifactEnvelope(
            workflow_run_id="REQ-1-r001",
            workflow_mode="new_requirement",
            artifact_id=artifact_id,
            source_snapshot_id="snapshot-1",
            producer=Producer(component),
            payload=payload,
            status=status,
        )
        _write(artifacts / f"{artifact_id}.json", envelope.to_dict())

    result = reconcile_autopilot(
        tmp_path / "initial/workflow-center-spec.json",
        [artifacts],
        tmp_path / "reconciled",
    )

    assert result["changed"] is True
    assert result["revision"] == 2
    assert result["artifact_node_count"] == 4
    assert result["open_action_count"] == 1
    spec = json.loads((tmp_path / "reconciled/workflow-center-spec.json").read_text())
    nodes = {item["node_id"]: item for item in spec["nodes"]}
    assert nodes["INPUT-FREEZE"]["state"] == "completed"
    assert nodes["A02"]["state"] == "completed"
    assert nodes["A03"]["state"] == "completed"
    assert nodes["G01"]["state"] == "waiting_human"
    assert spec["actions"][0]["item_count"] == 2
    approval_items = spec["actions"][0]["approval_items"]
    assert [item["id"] for item in approval_items] == ["I1", "I2"]
    assert spec["actions"][0]["item_count"] == len(approval_items)
    assert all(item["summary"] for item in approval_items)
    assert nodes["G01"]["approval_items"] == approval_items

    unchanged = reconcile_autopilot(
        tmp_path / "reconciled/workflow-center-spec.json",
        [artifacts],
        tmp_path / "reconciled-again",
    )
    assert unchanged["changed"] is False
    assert unchanged["revision"] == 2


def test_reconcile_refreshes_summary_when_completed_artifact_changes(tmp_path: Path) -> None:
    initialize_autopilot(
        _request(tmp_path / "request.json"),
        _config(tmp_path / "config.json"),
        tmp_path / "registry",
        tmp_path / "initial",
        runner=FakeMultica(),
    )
    artifacts = tmp_path / "artifacts"

    def write_n27(summary: str) -> None:
        envelope = ArtifactEnvelope(
            workflow_run_id="REQ-1-r001",
            workflow_mode="new_requirement",
            artifact_id="n27-test-data-plan-validation",
            source_snapshot_id="snapshot-1",
            producer=Producer("N27"),
            payload={"summary": summary, "valid": True},
            status=ArtifactStatus.COMPLETED,
        )
        _write(
            artifacts / "n27-test-data-plan-validation.json",
            envelope.to_dict(),
        )

    write_n27("old validation summary")
    first = reconcile_autopilot(
        tmp_path / "initial/workflow-center-spec.json",
        [artifacts],
        tmp_path / "first",
    )
    write_n27("new validation summary")
    reconcile_autopilot(
        Path(first["spec_path"]),
        [artifacts],
        tmp_path / "second",
    )
    spec = json.loads((tmp_path / "second/workflow-center-spec.json").read_text())
    n27 = next(item for item in spec["nodes"] if item["node_id"] == "N27")
    assert n27["result_summary"] == "new validation summary"


def test_reconcile_routes_blocked_a09_to_waiting_human_when_n04_routes_human(
    tmp_path: Path,
) -> None:
    multica = FakeMultica()
    initialize_autopilot(
        _request(tmp_path / "request.json"),
        _config(tmp_path / "config.json"),
        tmp_path / "registry",
        tmp_path / "initial",
        runner=multica,
    )
    artifacts = tmp_path / "artifacts"
    n04_payload = {
        "schema_version": "test-case-ir-validation/1.0",
        "valid": False,
        "next_node": "human",
        "issues": [
            {"id": "A09-ISSUE-007", "origin": "A09", "severity": "blocking"},
            {"id": "A09-ISSUE-008", "origin": "A09", "severity": "blocking"},
        ],
        "correction_attempt": 2,
        "max_correction_attempts": 2,
    }
    a09_payload = {
        "schema_version": "oracle-coverage-review/1.0",
        "approved": False,
        "issues": [
            {
                "id": "A09-ISSUE-007",
                "severity": "blocking",
                "route_to": "A08",
                "case_id": "TC-E2E-001",
                "recommendation": "改 expected_value",
            },
            {
                "id": "A09-ISSUE-008",
                "severity": "blocking",
                "route_to": "A08",
                "case_id": "TC-BE-002",
                "recommendation": "按 locale 拆分数据行",
            },
        ],
    }
    for component, artifact_id, status, payload in (
        (
            "N04",
            "n04-test-case-ir-validation",
            ArtifactStatus.NEEDS_HUMAN,
            n04_payload,
        ),
        (
            "A09",
            "a09-oracle-coverage-review",
            ArtifactStatus.NEEDS_HUMAN,
            a09_payload,
        ),
    ):
        envelope = ArtifactEnvelope(
            workflow_run_id="REQ-1-r001",
            workflow_mode="new_requirement",
            artifact_id=artifact_id,
            source_snapshot_id="snapshot-1",
            producer=Producer(component),
            payload=payload,
            status=status,
        )
        _write(artifacts / f"{artifact_id}.json", envelope.to_dict())

    result = reconcile_autopilot(
        tmp_path / "initial/workflow-center-spec.json",
        [artifacts],
        tmp_path / "reconciled",
    )

    assert result["changed"] is True
    spec = json.loads((tmp_path / "reconciled/workflow-center-spec.json").read_text())
    nodes = {item["node_id"]: item for item in spec["nodes"]}
    assert nodes["N04"]["state"] == "waiting_human"
    assert nodes["A09"]["state"] == "waiting_human"
    assert nodes["A09"]["result_summary"] == "阻塞问题已路由人工处置，等待定向修正或终止决策"
    gate_ids = {action["gate_id"] for action in spec["actions"]}
    assert "N04" in gate_ids and "A09" in gate_ids
    assert result["open_action_count"] == 2


def test_a06_needs_human_merges_into_g01_without_second_action(tmp_path: Path) -> None:
    multica = FakeMultica()
    initialize_autopilot(
        _request(tmp_path / "request.json"),
        _config(tmp_path / "config.json"),
        tmp_path / "registry",
        tmp_path / "initial",
        runner=multica,
    )
    artifacts = tmp_path / "artifacts"
    for component, artifact_id, status, payload in (
        (
            "N01",
            "n01-source-extraction-manifest",
            ArtifactStatus.COMPLETED,
            {"summary": "输入已冻结"},
        ),
        (
            "A02",
            "a02-requirement-analysis",
            ArtifactStatus.COMPLETED_WITH_GAPS,
            {"summary": "识别 2 个开放问题"},
        ),
        (
            "A06",
            "a06-alignment-result",
            ArtifactStatus.NEEDS_HUMAN,
            {"status": "needs_human", "findings": [{"id": "FIND-001", "severity": "high", "type": "conflict", "summary": "实现与需求冲突"}]},
        ),
        (
            "G01",
            "g01-scope-review",
            ArtifactStatus.NEEDS_HUMAN,
            {
                "status": "needs_human",
                "issues": [
                    {
                        "issue_id": "A02:AMB-001",
                        "category": "需求待确认",
                        "plain_summary": "需求文档里没有写清楚：提示优先级未规定",
                        "confirm_action": "请确认或补充需求口径。",
                        "severity": "high",
                        "route_to": "A02",
                        "requirement_ids": ["REQ-001"],
                        "detail": {"id": "AMB-001"},
                    }
                ],
            },
        ),
    ):
        envelope = ArtifactEnvelope(
            workflow_run_id="REQ-1-r001",
            workflow_mode="new_requirement",
            artifact_id=artifact_id,
            source_snapshot_id="snapshot-1",
            producer=Producer(component),
            payload=payload,
            status=status,
        )
        _write(artifacts / f"{artifact_id}.json", envelope.to_dict())

    result = reconcile_autopilot(
        tmp_path / "initial/workflow-center-spec.json",
        [artifacts],
        tmp_path / "reconciled",
    )

    spec = json.loads((tmp_path / "reconciled/workflow-center-spec.json").read_text())
    nodes = {item["node_id"]: item for item in spec["nodes"]}
    # Stage 1 分析节点不再单独等待人工，问题并入 G01 一次审批
    assert nodes["A06"]["state"] == "completed"
    assert nodes["G01"]["state"] == "waiting_human"
    assert result["open_action_count"] == 1
    assert spec["actions"][0]["gate_id"] == "G01"
    approval = spec["actions"][0]["approval_items"][0]
    assert approval["id"] == "A02:AMB-001"
    assert approval["category"] == "需求待确认"
    assert approval["confirm_action"].startswith("请确认")
    assert approval["summary"].startswith("需求文档里没有写清楚")


def test_autopilot_rejects_tampered_registry(tmp_path: Path) -> None:
    multica = FakeMultica()
    request = _request(tmp_path / "request.json")
    config = _config(tmp_path / "config.json")
    initialize_autopilot(
        request, config, tmp_path / "registry", tmp_path / "run", runner=multica
    )
    registry_path = tmp_path / "registry/autopilot-registry.json"
    registry = json.loads(registry_path.read_text())
    registry["revision"] = 99
    _write(registry_path, registry)

    with pytest.raises(ContractError, match="registry hash is invalid"):
        initialize_autopilot(
            request, config, tmp_path / "registry", tmp_path / "run-2", runner=multica
        )


def test_artifact_summary_needs_human_lists_unresolved_requirements() -> None:
    artifact = {
        "artifact_id": "a22-test-data-plan",
        "payload": {
            "status": "needs_human",
            "unresolved_requirements": [
                {"requirement_id": "UR-01", "reason_code": "chart_create_op_unverified"},
                {"requirement_id": "UR-02", "reason_code": "relation_topology_params_unconfirmed"},
                {"requirement_id": "UR-03", "reason_code": "permission_fixture_unverified"},
                {"requirement_id": "UR-04", "reason_code": "historical_fixture_seed_unverified"},
                {"requirement_id": "UR-05", "reason_code": "fault_injection_capability_unconfirmed"},
            ],
        },
    }
    summary = _artifact_summary(artifact)
    assert "5 个未决数据需求需人工确认" in summary
    assert "UR-01" in summary


def test_approval_items_carry_a22_unresolved_requirements() -> None:
    artifact = {
        "artifact_id": "a22-test-data-plan",
        "payload": {
            "status": "needs_human",
            "unresolved_requirements": [
                {
                    "requirement_id": "UR-01",
                    "reason_code": "chart_create_op_unverified",
                    "requirement": "stat_chart 创建接口及参数未验证，图表 setup_operation 需人工确认",
                }
            ],
        },
    }
    items = _approval_items(artifact)
    assert len(items) == 1
    assert items[0]["id"] == "UR-01"
    assert items[0]["title"] == "未决数据需求"
    assert "stat_chart 创建接口及参数未验证" in items[0]["summary"]
    assert items[0]["category"] == "test_data_pending_human"


def test_reconcile_clears_ghost_completed_nodes_when_artifact_disappears(tmp_path: Path) -> None:
    initialize_autopilot(
        _request(tmp_path / "request.json"),
        _config(tmp_path / "config.json"),
        tmp_path / "registry",
        tmp_path / "initial",
        runner=FakeMultica(),
    )
    artifacts = tmp_path / "artifacts"
    n17 = ArtifactEnvelope(
        workflow_run_id="REQ-1-r001",
        workflow_mode="new_requirement",
        artifact_id="n17-manual-execution",
        source_snapshot_id="snapshot-1",
        producer=Producer("N17"),
        payload={
            "pending_count": 1,
            "next_node": "N17",
            "tasks": [
                {
                    "case_id": "CASE-AUTO",
                    "title": "未执行用例",
                    "status": "pending",
                    "summary": "自动化未执行",
                }
            ],
        },
        status=ArtifactStatus.BLOCKED,
        reason_code="unexecuted_cases_pending",
    )
    n11 = ArtifactEnvelope(
        workflow_run_id="REQ-1-r001",
        workflow_mode="new_requirement",
        artifact_id="n11-quality-decision",
        source_snapshot_id="snapshot-1",
        producer=Producer("N11"),
        payload={"decision": "inconclusive"},
        status=ArtifactStatus.INCONCLUSIVE,
    )
    _write(artifacts / "n17-manual-execution.json", n17.to_dict())
    _write(artifacts / "n11-quality-decision.json", n11.to_dict())

    first = reconcile_autopilot(
        tmp_path / "initial/workflow-center-spec.json",
        [artifacts],
        tmp_path / "reconciled",
    )
    spec = json.loads((tmp_path / "reconciled/workflow-center-spec.json").read_text())
    nodes = {item["node_id"]: item for item in spec["nodes"]}
    assert first["changed"] is True
    assert nodes["N17"]["state"] == "blocked"
    assert nodes["N11"]["state"] == "waiting_human"

    (artifacts / "n11-quality-decision.json").unlink()
    second = reconcile_autopilot(
        tmp_path / "reconciled/workflow-center-spec.json",
        [artifacts],
        tmp_path / "reconciled-again",
    )
    spec = json.loads((tmp_path / "reconciled-again/workflow-center-spec.json").read_text())
    nodes = {item["node_id"]: item for item in spec["nodes"]}
    assert second["changed"] is True
    assert nodes["N17"]["state"] == "blocked"
    assert nodes["N11"]["state"] == "not_started"
    assert "artifact_id" not in nodes["N11"]

    assert not spec["actions"] or all(item.get("gate_id") != "N17" for item in spec["actions"])


def test_unexecuted_n17_is_blocked_without_approval_action(tmp_path: Path) -> None:
    initialize_autopilot(
        _request(tmp_path / "request.json"),
        _config(tmp_path / "config.json"),
        tmp_path / "registry",
        tmp_path / "initial",
        runner=FakeMultica(),
    )
    artifacts = tmp_path / "artifacts"
    n17 = ArtifactEnvelope(
        workflow_run_id="REQ-1-r001",
        workflow_mode="new_requirement",
        artifact_id="n17-manual-execution",
        source_snapshot_id="snapshot-1",
        producer=Producer("N17"),
        payload={
            "pending_count": 1,
            "next_node": "N17",
            "summary": "1 条用例尚未执行，不能结束质量流程",
            "tasks": [
                {
                    "case_id": "PC-CT-001-CONTRACT",
                    "title": "契约用例",
                    "status": "pending",
                    "reason_code": "automation_not_executed",
                    "summary": "自动化未生成或未执行",
                }
            ],
        },
        status=ArtifactStatus.BLOCKED,
        reason_code="unexecuted_cases_pending",
    )
    _write(artifacts / "n17-manual-execution.json", n17.to_dict())
    reconcile_autopilot(
        tmp_path / "initial/workflow-center-spec.json",
        [artifacts],
        tmp_path / "reconciled",
    )
    spec = json.loads((tmp_path / "reconciled/workflow-center-spec.json").read_text())
    nodes = {item["node_id"]: item for item in spec["nodes"]}
    assert nodes["N17"]["state"] == "blocked"
    assert "approval_items" not in nodes["N17"]
    assert all(item.get("gate_id") != "N17" for item in spec["actions"])
