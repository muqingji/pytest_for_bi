"""Command line entry point for local workflow development and evaluation."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
import tempfile

from .evaluation import evaluate_run
from .errors import ContractError, InputError, QaAgentError, SecurityPolicyError
from .gates import (
    prepare_scope_review_request,
    record_scope_review_decision,
    scope_review_decision_template,
)
from .g02_review import (
    open_multica_test_case_review,
    prepare_test_case_review_request,
    sync_multica_test_case_review,
)
from .human_correction import (
    open_multica_human_correction,
    prepare_human_correction_request,
    sync_multica_human_correction,
)
from .multica import (
    fetch_multica_run_messages,
    ingest_multica_output,
    prepare_multica_alignment_input,
    prepare_multica_inputs,
    prepare_multica_oracle_review_input,
    prepare_multica_split_review_input,
    prepare_multica_test_design_correction_input,
    prepare_multica_test_design_input,
)
from .stage_two_nodes import (
    run_n15_after_n26,
    run_n25_after_g02,
    run_n26_after_a11,
)
from .change_set import normalize_change_set
from .reporting import (
    render_evaluation_html,
    render_evaluation_text,
    render_multica_alignment_markdown,
    render_scope_review_markdown,
)
from .security import SecurityPolicy
from .risk import run_risk_strategy_after_g01
from .source_collector import ReadOnlyGitCollector, RepositoryRegistry
from .storage import ArtifactStore
from .test_case_gate import run_n04_after_a09
from .workflow import PhaseOneWorkflow


def _load_json_input(path: Path, label: str) -> object:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise InputError(f"Required {label} input is missing: {path}") from error
    except OSError as error:
        raise InputError(f"Required {label} input cannot be read: {path}") from error
    except json.JSONDecodeError as error:
        raise ContractError(f"Required {label} input is not valid JSON: {path}") from error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="qa-agents")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run the deterministic-first Phase 1 workflow")
    run_parser.add_argument("--input", type=Path, required=True)
    run_parser.add_argument("--output", type=Path, required=True)
    run_parser.add_argument("--run-id")
    run_parser.add_argument("--stop-after", choices=["N04", "N15", "G03"])
    run_parser.add_argument("--approve-g01", action="store_true")
    run_parser.add_argument("--approve-g02", action="store_true")
    run_parser.add_argument("--approve-g03", action="store_true")

    collect_parser = subparsers.add_parser(
        "collect", help="Collect frozen source material from registered remote repositories"
    )
    collect_parser.add_argument("--input", type=Path, required=True)
    collect_parser.add_argument("--output", type=Path, required=True)
    collect_parser.add_argument("--max-bytes", type=int, default=5_000_000)

    evaluate_parser = subparsers.add_parser("evaluate", help="Evaluate a frozen run using Oracle data")
    evaluate_parser.add_argument("--run", type=Path, required=True)
    evaluate_parser.add_argument("--oracle", type=Path, required=True)
    evaluate_parser.add_argument("--output", type=Path)

    multica_parser = subparsers.add_parser(
        "prepare-multica", help="Prepare least-privilege Multica Agent input bundles"
    )
    multica_parser.add_argument("--input", type=Path, required=True)
    multica_parser.add_argument("--output", type=Path, required=True)
    multica_parser.add_argument("--run-id", required=True)

    alignment_parser = subparsers.add_parser(
        "prepare-multica-alignment", help="Prepare A06 input from validated Stage 1 artifacts"
    )
    alignment_parser.add_argument("--artifacts", type=Path, required=True)
    alignment_parser.add_argument("--output", type=Path, required=True)

    test_design_parser = subparsers.add_parser(
        "prepare-multica-test-design",
        help="Prepare A08 input from approved G01 and deterministic N24",
    )
    test_design_parser.add_argument("--requirement-artifact", type=Path, required=True)
    test_design_parser.add_argument("--technical-artifact", type=Path, required=True)
    test_design_parser.add_argument("--alignment-artifact", type=Path, required=True)
    test_design_parser.add_argument("--n24-artifact", type=Path, required=True)
    test_design_parser.add_argument("--g01-request", type=Path, required=True)
    test_design_parser.add_argument("--g01-decision", type=Path, required=True)
    test_design_parser.add_argument("--g01-policy", type=Path, required=True)
    test_design_parser.add_argument("--output", type=Path, required=True)

    test_design_correction_parser = subparsers.add_parser(
        "prepare-multica-test-design-correction",
        help="Prepare a hash-bound A08 correction input after N04 routes to A08",
    )
    test_design_correction_parser.add_argument(
        "--previous-test-design-artifact", type=Path, required=True
    )
    test_design_correction_parser.add_argument(
        "--previous-test-design-bundle", type=Path, required=True
    )
    test_design_correction_parser.add_argument(
        "--oracle-review-artifact", type=Path, required=True
    )
    test_design_correction_parser.add_argument("--n04-artifact", type=Path, required=True)
    test_design_correction_parser.add_argument("--output", type=Path, required=True)

    human_test_design_correction_parser = subparsers.add_parser(
        "prepare-multica-human-test-design-correction",
        help="Prepare A08 recovery input from an approved human correction decision",
    )
    human_test_design_correction_parser.add_argument(
        "--previous-test-design-artifact", type=Path, required=True
    )
    human_test_design_correction_parser.add_argument(
        "--previous-test-design-bundle", type=Path, required=True
    )
    human_test_design_correction_parser.add_argument(
        "--oracle-review-artifact", type=Path, required=True
    )
    human_test_design_correction_parser.add_argument(
        "--n04-artifact", type=Path, required=True
    )
    human_test_design_correction_parser.add_argument(
        "--human-request", type=Path, required=True
    )
    human_test_design_correction_parser.add_argument(
        "--human-decision", type=Path, required=True
    )
    human_test_design_correction_parser.add_argument(
        "--human-policy", type=Path, required=True
    )
    human_test_design_correction_parser.add_argument("--output", type=Path, required=True)

    oracle_review_parser = subparsers.add_parser(
        "prepare-multica-oracle-review",
        help="Prepare A09 input from an accepted A08 Artifact and generic Oracle rules",
    )
    oracle_review_parser.add_argument("--test-design-artifact", type=Path, required=True)
    oracle_review_parser.add_argument("--test-design-bundle", type=Path, required=True)
    oracle_review_parser.add_argument("--oracle-rules", type=Path, required=True)
    oracle_review_parser.add_argument("--output", type=Path, required=True)

    ingest_parser = subparsers.add_parser(
        "ingest-multica", help="Validate and persist one Multica Agent output"
    )
    ingest_parser.add_argument("--bundle", type=Path, required=True)
    ingest_parser.add_argument("--response", type=Path, required=True)
    ingest_parser.add_argument("--output", type=Path, required=True)
    ingest_parser.add_argument("--task-id", required=True)
    ingest_parser.add_argument("--issue-id", required=True)
    ingest_parser.add_argument("--attachment-id", required=True)
    ingest_parser.add_argument("--model-provider", required=True)
    ingest_parser.add_argument("--model", required=True)
    ingest_parser.add_argument("--prompt-version", required=True)

    validate_candidate_parser = subparsers.add_parser(
        "validate-multica-candidate",
        help="Validate one Multica candidate without accepting it into the main chain",
    )
    validate_candidate_parser.add_argument("--bundle", type=Path, required=True)
    validate_candidate_parser.add_argument("--response", type=Path, required=True)
    validate_candidate_parser.add_argument("--task-id", required=True)
    validate_candidate_parser.add_argument("--issue-id", required=True)
    validate_candidate_parser.add_argument("--attachment-id", required=True)
    validate_candidate_parser.add_argument("--model-provider", required=True)
    validate_candidate_parser.add_argument("--model", required=True)
    validate_candidate_parser.add_argument("--prompt-version", required=True)
    validate_candidate_parser.add_argument(
        "--expect-reject",
        action="store_true",
        help="Exit 0 only when the candidate is rejected by contract or tool-trace gates",
    )
    validate_candidate_parser.add_argument(
        "--scratch-output",
        type=Path,
        help="Optional temporary directory used only for a dry-run accept attempt",
    )

    fetch_parser = subparsers.add_parser(
        "fetch-multica", help="Fetch one Multica task message stream into the run store"
    )
    fetch_parser.add_argument("--workspace-id", required=True)
    fetch_parser.add_argument("--task-id", required=True)
    fetch_parser.add_argument("--output", type=Path, required=True)

    alignment_report_parser = subparsers.add_parser(
        "report-multica-alignment", help="Render a deterministic G01 review report from A06"
    )
    alignment_report_parser.add_argument("--artifact", type=Path, required=True)
    alignment_report_parser.add_argument("--bundle", type=Path, required=True)
    alignment_report_parser.add_argument("--output", type=Path, required=True)

    g01_parser = subparsers.add_parser(
        "prepare-g01", help="Prepare a content-addressed G01 human review request"
    )
    g01_parser.add_argument("--requirement-artifact", type=Path, required=True)
    g01_parser.add_argument("--technical-artifact", type=Path, required=True)
    g01_parser.add_argument("--alignment-artifact", type=Path, required=True)
    g01_parser.add_argument("--policy", type=Path, required=True)
    g01_parser.add_argument("--output", type=Path, required=True)

    g01_decision_parser = subparsers.add_parser(
        "record-g01-decision", help="Validate and record an externally authored G01 decision"
    )
    g01_decision_parser.add_argument("--request", type=Path, required=True)
    g01_decision_parser.add_argument("--decision", type=Path, required=True)
    g01_decision_parser.add_argument("--policy", type=Path, required=True)
    g01_decision_parser.add_argument("--output", type=Path, required=True)

    g02_parser = subparsers.add_parser(
        "prepare-g02", help="Prepare a content-addressed G02 Test Case IR review request"
    )
    g02_parser.add_argument("--test-design-artifact", type=Path, required=True)
    g02_parser.add_argument("--oracle-review-artifact", type=Path, required=True)
    g02_parser.add_argument("--n04-artifact", type=Path, required=True)
    g02_parser.add_argument("--policy", type=Path, required=True)
    g02_parser.add_argument("--output", type=Path, required=True)

    g02_open_parser = subparsers.add_parser(
        "open-g02-multica", help="Create and pause on a Multica G02 review issue"
    )
    g02_open_parser.add_argument("--request", type=Path, required=True)
    g02_open_parser.add_argument("--policy", type=Path, required=True)
    g02_open_parser.add_argument("--output", type=Path, required=True)

    g02_sync_parser = subparsers.add_parser(
        "sync-g02-multica", help="Compile a Multica G02 status into a workflow outcome"
    )
    g02_sync_parser.add_argument("--request", type=Path, required=True)
    g02_sync_parser.add_argument("--n04-artifact", type=Path, required=True)
    g02_sync_parser.add_argument("--policy", type=Path, required=True)
    g02_sync_parser.add_argument("--output", type=Path, required=True)

    human_correction_parser = subparsers.add_parser(
        "prepare-human-correction",
        help="Prepare a content-addressed human Test Case IR correction request",
    )
    human_correction_parser.add_argument("--test-design-artifact", type=Path, required=True)
    human_correction_parser.add_argument("--oracle-review-artifact", type=Path, required=True)
    human_correction_parser.add_argument("--n04-artifact", type=Path, required=True)
    human_correction_parser.add_argument("--policy", type=Path, required=True)
    human_correction_parser.add_argument("--output", type=Path, required=True)

    human_correction_open_parser = subparsers.add_parser(
        "open-human-correction-multica",
        help="Create and pause on a Multica human correction Issue",
    )
    human_correction_open_parser.add_argument("--request", type=Path, required=True)
    human_correction_open_parser.add_argument("--policy", type=Path, required=True)
    human_correction_open_parser.add_argument("--output", type=Path, required=True)

    human_correction_sync_parser = subparsers.add_parser(
        "sync-human-correction-multica",
        help="Compile a Multica human correction status into a workflow outcome",
    )
    human_correction_sync_parser.add_argument("--request", type=Path, required=True)
    human_correction_sync_parser.add_argument("--n04-artifact", type=Path, required=True)
    human_correction_sync_parser.add_argument("--policy", type=Path, required=True)
    human_correction_sync_parser.add_argument("--output", type=Path, required=True)
    human_correction_sync_parser.add_argument("--run-manifest", type=Path)
    human_correction_sync_parser.add_argument("--workspace-manifest", type=Path)

    n24_parser = subparsers.add_parser(
        "run-n24-after-g01", help="Run deterministic N24 after a validated G01 approval"
    )
    n24_parser.add_argument("--workflow-input", type=Path, required=True)
    n24_parser.add_argument("--source-snapshot", type=Path, required=True)
    n24_parser.add_argument("--alignment-artifact", type=Path, required=True)
    n24_parser.add_argument("--g01-request", type=Path, required=True)
    n24_parser.add_argument("--g01-decision", type=Path, required=True)
    n24_parser.add_argument("--risk-policy", type=Path, required=True)
    n24_parser.add_argument("--g01-policy", type=Path, required=True)
    n24_parser.add_argument("--output", type=Path, required=True)

    n04_parser = subparsers.add_parser(
        "run-n04-after-a09",
        help="Run deterministic Test Case IR validation after an accepted A09 review",
    )
    n04_parser.add_argument("--test-design-artifact", type=Path, required=True)
    n04_parser.add_argument("--oracle-review-artifact", type=Path, required=True)
    n04_parser.add_argument("--oracle-review-bundle", type=Path, required=True)
    n04_parser.add_argument("--output", type=Path, required=True)
    n04_parser.add_argument("--correction-attempt", type=int, default=1)
    n04_parser.add_argument("--max-correction-attempts", type=int, default=2)

    split_review_parser = subparsers.add_parser(
        "prepare-multica-split-review",
        help="Prepare A11 input from accepted A08 and N25 compiled cases",
    )
    split_review_parser.add_argument("--test-design-artifact", type=Path, required=True)
    split_review_parser.add_argument("--test-design-bundle", type=Path, required=True)
    split_review_parser.add_argument("--compiled-artifact", type=Path, required=True)
    split_review_parser.add_argument("--oracle-rules", type=Path, required=True)
    split_review_parser.add_argument("--output", type=Path, required=True)

    n25_parser = subparsers.add_parser(
        "run-n25-after-g02",
        help="Run deterministic N25 compilation after a validated G02 approval",
    )
    n25_parser.add_argument("--a08-artifact", type=Path, required=True)
    n25_parser.add_argument("--g02-request", type=Path, required=True)
    n25_parser.add_argument("--g02-outcome", type=Path, required=True)
    n25_parser.add_argument("--output", type=Path, required=True)

    n26_parser = subparsers.add_parser(
        "run-n26-after-a11",
        help="Run deterministic N26 selection after an approved A11 review",
    )
    n26_parser.add_argument("--compiled-artifact", type=Path, required=True)
    n26_parser.add_argument("--split-review-artifact", type=Path, required=True)
    n26_parser.add_argument("--split-review-bundle", type=Path, required=True)
    n26_parser.add_argument("--output", type=Path, required=True)
    n26_parser.add_argument("--asset-catalog", type=Path)

    n15_parser = subparsers.add_parser(
        "run-n15-after-n26",
        help="Run deterministic N15 execution-plan compilation after N26 selection",
    )
    n15_parser.add_argument("--selection-artifact", type=Path, required=True)
    n15_parser.add_argument("--compiled-artifact", type=Path, required=True)
    n15_parser.add_argument("--output", type=Path, required=True)
    n15_parser.add_argument("--asset-catalog", type=Path)
    return parser


def _run(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "run":
        result = PhaseOneWorkflow().run(
            args.input,
            args.output,
            run_id=args.run_id,
            stop_after=args.stop_after,
            approve_g01=args.approve_g01,
            approve_g02=args.approve_g02,
            approve_g03=args.approve_g03,
        )
        print(json.dumps(result.summary, ensure_ascii=False, indent=2))
        return 0 if result.status not in {"failed_fatal", "blocked_input"} else 2

    if args.command == "collect":
        project_root = Path(__file__).resolve().parents[2]
        with (args.input / "workflow-input.json").open(encoding="utf-8") as file:
            workflow_input = json.load(file)
        with (args.input / "source-snapshot.json").open(encoding="utf-8") as file:
            source_snapshot = json.load(file)
        security = SecurityPolicy()
        security.validate_workflow_input(workflow_input)
        security.validate_snapshot(source_snapshot)
        registry = RepositoryRegistry.from_file(
            project_root / "policies" / "repository-registry.json"
        )
        material = ReadOnlyGitCollector(registry, max_bytes=args.max_bytes).collect(
            source_snapshot, workflow_input
        )
        security.assert_no_secret_values(material)
        ArtifactStore(args.output.parent).write_json(args.output.name, material)
        print(json.dumps({"output": str(args.output), "status": "completed"}, ensure_ascii=False))
        return 0

    if args.command == "prepare-multica":
        manifest = prepare_multica_inputs(
            args.input,
            args.output,
            workflow_run_id=args.run_id,
        )
        print(json.dumps(manifest, ensure_ascii=False, indent=2))
        return 0

    if args.command == "prepare-multica-alignment":
        bundle = prepare_multica_alignment_input(args.artifacts, args.output)
        print(json.dumps(bundle, ensure_ascii=False, indent=2))
        return 0

    if args.command == "prepare-multica-test-design":
        bundle = prepare_multica_test_design_input(
            args.requirement_artifact,
            args.technical_artifact,
            args.alignment_artifact,
            args.n24_artifact,
            args.g01_request,
            args.g01_decision,
            args.g01_policy,
            args.output,
        )
        print(json.dumps(bundle, ensure_ascii=False, indent=2))
        return 0

    if args.command == "prepare-multica-test-design-correction":
        bundle = prepare_multica_test_design_correction_input(
            args.previous_test_design_artifact,
            args.previous_test_design_bundle,
            args.oracle_review_artifact,
            args.n04_artifact,
            args.output,
        )
        print(json.dumps(bundle, ensure_ascii=False, indent=2))
        return 0

    if args.command == "prepare-multica-human-test-design-correction":
        bundle = prepare_multica_test_design_correction_input(
            args.previous_test_design_artifact,
            args.previous_test_design_bundle,
            args.oracle_review_artifact,
            args.n04_artifact,
            args.output,
            human_correction_request_path=args.human_request,
            human_correction_decision_path=args.human_decision,
            human_correction_policy_path=args.human_policy,
        )
        print(json.dumps(bundle, ensure_ascii=False, indent=2))
        return 0

    if args.command == "prepare-multica-oracle-review":
        bundle = prepare_multica_oracle_review_input(
            args.test_design_artifact,
            args.test_design_bundle,
            args.oracle_rules,
            args.output,
        )
        print(json.dumps(bundle, ensure_ascii=False, indent=2))
        return 0


    if args.command == "ingest-multica":
        artifact = ingest_multica_output(
            args.bundle,
            args.response.read_text(encoding="utf-8"),
            args.output,
            task_id=args.task_id,
            issue_id=args.issue_id,
            attachment_id=args.attachment_id,
            model_provider=args.model_provider,
            model_snapshot=args.model,
            prompt_version=args.prompt_version,
        )
        print(json.dumps(artifact, ensure_ascii=False, indent=2))
        return 0

    if args.command == "validate-multica-candidate":
        scratch = args.scratch_output
        if scratch is None:
            temp_dir = tempfile.TemporaryDirectory(prefix="qa-agents-candidate-")
            scratch = Path(temp_dir.name)
        else:
            temp_dir = None
            scratch.mkdir(parents=True, exist_ok=True)
        try:
            artifact = ingest_multica_output(
                args.bundle,
                args.response.read_text(encoding="utf-8"),
                scratch,
                task_id=args.task_id,
                issue_id=args.issue_id,
                attachment_id=args.attachment_id,
                model_provider=args.model_provider,
                model_snapshot=args.model,
                prompt_version=args.prompt_version,
            )
        except (ContractError, SecurityPolicyError) as error:
            report = {
                "accepted": False,
                "reason_code": error.reason_code,
                "message": str(error),
                "task_id": args.task_id,
                "issue_id": args.issue_id,
                "attachment_id": args.attachment_id,
                "prompt_version": args.prompt_version,
            }
            print(json.dumps(report, ensure_ascii=False, indent=2))
            if temp_dir is not None:
                temp_dir.cleanup()
            return 0 if args.expect_reject else 2
        report = {
            "accepted": True,
            "artifact_id": artifact.get("artifact_id"),
            "artifact_hash": artifact.get("artifact_hash"),
            "status": artifact.get("status"),
            "task_id": args.task_id,
            "issue_id": args.issue_id,
            "attachment_id": args.attachment_id,
            "prompt_version": args.prompt_version,
            "scratch_output": str(scratch),
        }
        print(json.dumps(report, ensure_ascii=False, indent=2))
        if temp_dir is not None:
            temp_dir.cleanup()
        return 2 if args.expect_reject else 0

    if args.command == "fetch-multica":
        messages = fetch_multica_run_messages(
            args.workspace_id,
            args.task_id,
            args.output,
        )
        print(
            json.dumps(
                {"output": str(args.output), "message_count": len(messages)},
                ensure_ascii=False,
                indent=2,
            )
        )
        return 0

    if args.command == "run-n04-after-a09":
        artifact = run_n04_after_a09(
            args.test_design_artifact,
            args.oracle_review_artifact,
            args.oracle_review_bundle,
            args.output,
            correction_attempt=args.correction_attempt,
            max_correction_attempts=args.max_correction_attempts,
        )
        print(json.dumps(artifact, ensure_ascii=False, indent=2))
        return 0

    if args.command == "prepare-multica-split-review":
        bundle = prepare_multica_split_review_input(
            args.test_design_artifact,
            args.test_design_bundle,
            args.compiled_artifact,
            args.oracle_rules,
            args.output,
        )
        print(json.dumps(bundle, ensure_ascii=False, indent=2))
        return 0

    if args.command == "run-n25-after-g02":
        artifact = run_n25_after_g02(
            args.a08_artifact,
            args.g02_request,
            args.g02_outcome,
            args.output,
        )
        print(json.dumps(artifact, ensure_ascii=False, indent=2))
        return 0

    if args.command == "run-n26-after-a11":
        artifact = run_n26_after_a11(
            args.compiled_artifact,
            args.split_review_artifact,
            args.split_review_bundle,
            args.output,
            asset_catalog_path=args.asset_catalog,
        )
        print(json.dumps(artifact, ensure_ascii=False, indent=2))
        return 0

    if args.command == "run-n15-after-n26":
        artifact = run_n15_after_n26(
            args.selection_artifact,
            args.compiled_artifact,
            args.output,
            asset_catalog_path=args.asset_catalog,
        )
        print(json.dumps(artifact, ensure_ascii=False, indent=2))
        return 0

    if args.command == "report-multica-alignment":
        artifact = json.loads(args.artifact.read_text(encoding="utf-8"))
        bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
        report = render_multica_alignment_markdown(artifact, bundle)
        ArtifactStore(args.output.parent).write_text(args.output.name, report)
        print(json.dumps({"output": str(args.output), "status": artifact["status"]}, ensure_ascii=False))
        return 0

    if args.command == "prepare-g01":
        policy = _load_json_input(args.policy, "g01_policy")
        request = prepare_scope_review_request(
            args.requirement_artifact,
            args.technical_artifact,
            args.alignment_artifact,
            args.output,
            policy=policy,
        )
        ArtifactStore(args.output).write_text(
            "g01-review-request.md", render_scope_review_markdown(request)
        )
        ArtifactStore(args.output).write_json(
            "g01-decision-template.json", scope_review_decision_template(request)
        )
        print(
            json.dumps(
                {
                    "output": str(args.output),
                    "status": request["status"],
                    "issue_count": request["issue_count"],
                    "request_hash": request["request_hash"],
                },
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "record-g01-decision":
        decision = record_scope_review_decision(
            args.request, args.decision, args.policy, args.output
        )
        outcome = json.loads(
            (args.output / "g01-review-outcome.json").read_text(encoding="utf-8")
        )
        print(
            json.dumps(
                {
                    "output": str(args.output),
                    "decision": decision["decision"],
                    "decision_hash": decision["decision_hash"],
                    "action": outcome["action"],
                    "next_node": outcome["next_node"],
                },
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "prepare-g02":
        request = prepare_test_case_review_request(
            args.test_design_artifact,
            args.oracle_review_artifact,
            args.n04_artifact,
            args.policy,
            args.output,
        )
        print(
            json.dumps(
                {
                    "output": str(args.output),
                    "status": request["status"],
                    "request_hash": request["request_hash"],
                    "review_key": request["review_key"],
                    "approver": request["review_policy"]["allowed_actor_ids"][0],
                },
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "open-g02-multica":
        state = open_multica_test_case_review(
            args.request, args.policy, args.output
        )
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return 0

    if args.command == "sync-g02-multica":
        result = sync_multica_test_case_review(
            args.request,
            args.n04_artifact,
            args.policy,
            args.output,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "prepare-human-correction":
        request = prepare_human_correction_request(
            args.test_design_artifact,
            args.oracle_review_artifact,
            args.n04_artifact,
            args.policy,
            args.output,
        )
        print(
            json.dumps(
                {
                    "output": str(args.output),
                    "status": request["status"],
                    "request_hash": request["request_hash"],
                    "directive_count": len(request["directives"]),
                    "approver": request["policy"]["allowed_actor_ids"][0],
                },
                ensure_ascii=False,
            )
        )
        return 0

    if args.command == "open-human-correction-multica":
        state = open_multica_human_correction(
            args.request, args.policy, args.output
        )
        print(json.dumps(state, ensure_ascii=False, indent=2))
        return 0

    if args.command == "sync-human-correction-multica":
        result = sync_multica_human_correction(
            args.request,
            args.n04_artifact,
            args.policy,
            args.output,
            run_manifest_path=args.run_manifest,
            workspace_manifest_path=args.workspace_manifest,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    if args.command == "run-n24-after-g01":
        paths = {
            "workflow_input": args.workflow_input,
            "source_snapshot": args.source_snapshot,
            "alignment": args.alignment_artifact,
            "request": args.g01_request,
            "decision": args.g01_decision,
            "risk_policy": args.risk_policy,
            "g01_policy": args.g01_policy,
        }
        values = {key: _load_json_input(path, key) for key, path in paths.items()}
        SecurityPolicy().validate_snapshot(values["source_snapshot"])
        artifact = run_risk_strategy_after_g01(
            values["workflow_input"],
            normalize_change_set(values["source_snapshot"]),
            values["alignment"],
            values["request"],
            values["decision"],
            values["risk_policy"],
            values["g01_policy"],
            args.output,
        )
        print(json.dumps(artifact, ensure_ascii=False, indent=2))
        return 0

    evaluation = evaluate_run(args.run, args.oracle)
    if args.output:
        store = ArtifactStore(args.output.parent)
        store.write_json(args.output.name, evaluation)
        store.write_text(f"{args.output.stem}.txt", render_evaluation_text(evaluation))
        store.write_text(f"{args.output.stem}.html", render_evaluation_html(evaluation))
    print(json.dumps(evaluation, ensure_ascii=False, indent=2))
    return 0 if evaluation["passed"] else 1


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and turn expected domain failures into orchestrator-readable output."""

    try:
        return _run(argv)
    except QaAgentError as error:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "reason_code": error.reason_code,
                    "retryable": error.retryable,
                    "message": str(error),
                },
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
