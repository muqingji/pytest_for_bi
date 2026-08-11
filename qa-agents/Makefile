PYTHON ?= ../.venv/bin/python
PYTEST ?= ../.venv/bin/pytest
PYTHONPATH := src
PILOT_INPUT := eval/workflows/pilot-001-detail-drill-message-i18n/input
PILOT_ORACLE := eval/workflows/pilot-001-detail-drill-message-i18n/oracle
PILOT_RUN := runs/pilot-001

.PHONY: test pilot pilot-full pilot-automation collect-pilot evaluate-pilot compile-workflow-center sync-workflow-center init-autopilot reconcile-autopilot prepare-multica-pilot prepare-multica-alignment-pilot report-multica-alignment-pilot prepare-g01-pilot record-g01-pilot run-n24-pilot prepare-multica-test-design-pilot prepare-multica-oracle-review-pilot run-n04-pilot prepare-multica-test-design-correction-pilot prepare-multica-oracle-review-correction-pilot run-n04-correction-pilot run-n25-after-g02-pilot prepare-multica-split-review-pilot run-n26-after-a11-pilot run-n15-after-n26-pilot prepare-autonomous-test-data-pilot prepare-server-automation-pilot run-n07-env-precheck-pilot run-n16-env-fix-pilot land-automation-candidates-pilot run-n08-automation-pilot run-server-quality-pilot run-server-full-pilot prepare-multica-selection-advice-pilot prepare-human-correction-pilot open-human-correction-pilot sync-human-correction-pilot prepare-multica-human-correction-pilot prepare-g02-pilot open-g02-pilot sync-g02-pilot

G01_DIR := $(PILOT_RUN)/g01
G01_DECISION_INPUT ?= $(G01_DIR)/g01-decision-input.json
G02_DIR := $(PILOT_RUN)/g02
HUMAN_CORRECTION_DIR := $(PILOT_RUN)/human-correction
WORKFLOW_CENTER_CONFIG := multica/workflow-center-config.json
WORKFLOW_CENTER_SPEC ?= runs/confidence-20260811-01/workflow-center-spec.json
WORKFLOW_CENTER_OUTPUT ?= runs/confidence-20260811-01/workflow-center
AUTOPILOT_REQUEST ?=
AUTOPILOT_REGISTRY ?= runs/autopilot-registry
AUTOPILOT_OUTPUT ?= runs/autopilot
AUTOPILOT_ARTIFACT_ROOT ?=
TEST_DATA_NAMESPACE ?= qa-pilot-data-plan-112
TEST_DATA_STAGE ?= $(PILOT_RUN)/test-data

test:
	PYTHONPATH=$(PYTHONPATH) $(PYTEST) -q tests

pilot:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents run --input $(PILOT_INPUT) --output $(PILOT_RUN) --run-id pilot-001 --stop-after N04

pilot-full:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents run --input $(PILOT_INPUT) --output $(PILOT_RUN) --run-id pilot-001 --stop-after N15 --approve-g01 --approve-g02

pilot-automation:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents run --input $(PILOT_INPUT) --output $(PILOT_RUN) --run-id pilot-001 --stop-after G03 --approve-g01 --approve-g02

collect-pilot:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents collect --input $(PILOT_INPUT) --output $(PILOT_INPUT)/source-material.json

evaluate-pilot:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents evaluate --run $(PILOT_RUN) --oracle $(PILOT_ORACLE) --output $(PILOT_RUN)/evaluation.json

compile-workflow-center:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents compile-workflow-center --spec $(WORKFLOW_CENTER_SPEC) --output $(WORKFLOW_CENTER_OUTPUT)

sync-workflow-center:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents sync-workflow-center --spec $(WORKFLOW_CENTER_SPEC) --config $(WORKFLOW_CENTER_CONFIG) --output $(WORKFLOW_CENTER_OUTPUT)

init-autopilot:
	@test -n "$(AUTOPILOT_REQUEST)" || (echo "set AUTOPILOT_REQUEST to a requirement request JSON"; exit 2)
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents init-autopilot --request $(AUTOPILOT_REQUEST) --config $(WORKFLOW_CENTER_CONFIG) --registry $(AUTOPILOT_REGISTRY) --output $(AUTOPILOT_OUTPUT)

reconcile-autopilot:
	@test -n "$(AUTOPILOT_ARTIFACT_ROOT)" || (echo "set AUTOPILOT_ARTIFACT_ROOT to the accepted Artifact root"; exit 2)
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents reconcile-autopilot --spec $(WORKFLOW_CENTER_SPEC) --artifact-root $(AUTOPILOT_ARTIFACT_ROOT) --output $(AUTOPILOT_OUTPUT)

prepare-multica-pilot:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents prepare-multica --input $(PILOT_INPUT) --output $(PILOT_RUN)/multica-inputs --run-id multica-pilot-001

prepare-multica-alignment-pilot:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents prepare-multica-alignment --artifacts $(PILOT_RUN)/multica-stage1/artifacts --output $(PILOT_RUN)/multica-inputs

report-multica-alignment-pilot:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents report-multica-alignment --artifact $(PILOT_RUN)/multica-stage2/artifacts/a06-alignment-result.json --bundle $(PILOT_RUN)/multica-inputs/a06-input.json --output $(PILOT_RUN)/multica-alignment-report.md

prepare-g01-pilot:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents prepare-g01 --requirement-artifact $(PILOT_RUN)/multica-stage1/artifacts/a02-requirement-analysis.json --technical-artifact $(PILOT_RUN)/multica-stage1/artifacts/a03-technical-testability-analysis.json --alignment-artifact $(PILOT_RUN)/multica-stage2/artifacts/a06-alignment-result.json --policy policies/g01-review-policy.json --output $(PILOT_RUN)/g01

record-g01-pilot:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents record-g01-decision --request $(G01_DIR)/g01-review-request.json --decision $(G01_DECISION_INPUT) --policy policies/g01-review-policy.json --output $(G01_DIR)

run-n24-pilot:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents run-n24-after-g01 --workflow-input $(PILOT_INPUT)/workflow-input.json --source-snapshot $(PILOT_INPUT)/source-snapshot.json --alignment-artifact $(PILOT_RUN)/multica-stage2/artifacts/a06-alignment-result.json --g01-request $(G01_DIR)/g01-review-request.json --g01-decision $(G01_DIR)/g01-review-decision.json --risk-policy policies/risk-policy.json --g01-policy policies/g01-review-policy.json --output $(PILOT_RUN)/multica-stage3

prepare-multica-test-design-pilot:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents prepare-multica-test-design --requirement-artifact $(PILOT_RUN)/multica-stage1/artifacts/a02-requirement-analysis.json --technical-artifact $(PILOT_RUN)/multica-stage1/artifacts/a03-technical-testability-analysis.json --alignment-artifact $(PILOT_RUN)/multica-stage2/artifacts/a06-alignment-result.json --n24-artifact $(PILOT_RUN)/multica-stage3/artifacts/n24-test-strategy.json --g01-request $(G01_DIR)/g01-review-request.json --g01-decision $(G01_DIR)/g01-review-decision.json --g01-policy policies/g01-review-policy.json --output $(PILOT_RUN)/multica-inputs

prepare-multica-oracle-review-pilot:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents prepare-multica-oracle-review --test-design-artifact $(PILOT_RUN)/multica-stage4/artifacts/a08-test-design-ir.json --test-design-bundle $(PILOT_RUN)/multica-inputs/a08-input.json --oracle-rules policies/oracle-rule-library.json --output $(PILOT_RUN)/multica-inputs

run-n04-pilot:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents run-n04-after-a09 --test-design-artifact $(PILOT_RUN)/multica-stage4/artifacts/a08-test-design-ir.json --oracle-review-artifact $(PILOT_RUN)/multica-stage5/artifacts/a09-oracle-coverage-review.json --oracle-review-bundle $(PILOT_RUN)/multica-inputs/a09-input.json --output $(PILOT_RUN)/multica-stage6

prepare-multica-test-design-correction-pilot:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents prepare-multica-test-design-correction --previous-test-design-artifact $(PILOT_RUN)/multica-stage4/artifacts/a08-test-design-ir.json --previous-test-design-bundle $(PILOT_RUN)/multica-inputs/a08-input.json --oracle-review-artifact $(PILOT_RUN)/multica-stage5/artifacts/a09-oracle-coverage-review.json --n04-artifact $(PILOT_RUN)/multica-stage6/artifacts/n04-test-case-ir-validation.json --output $(PILOT_RUN)/multica-inputs/a08-correction-01-v2

prepare-multica-oracle-review-correction-pilot:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents prepare-multica-oracle-review --test-design-artifact $(PILOT_RUN)/multica-stage7/artifacts/a08-test-design-ir.json --test-design-bundle $(PILOT_RUN)/multica-inputs/a08-correction-01/a08-input.json --oracle-rules policies/oracle-rule-library.json --output $(PILOT_RUN)/multica-inputs/a09-correction-01

run-n04-correction-pilot:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents run-n04-after-a09 --test-design-artifact $(PILOT_RUN)/multica-stage7/artifacts/a08-test-design-ir.json --oracle-review-artifact $(PILOT_RUN)/multica-stage8/artifacts/a09-oracle-coverage-review.json --oracle-review-bundle $(PILOT_RUN)/multica-inputs/a09-correction-01/a09-input.json --output $(PILOT_RUN)/multica-stage9 --correction-attempt 2 --max-correction-attempts 2

prepare-human-correction-pilot:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents prepare-human-correction --test-design-artifact $(PILOT_RUN)/multica-stage7/artifacts/a08-test-design-ir.json --oracle-review-artifact $(PILOT_RUN)/multica-stage8/artifacts/a09-oracle-coverage-review.json --n04-artifact $(PILOT_RUN)/multica-stage9/artifacts/n04-test-case-ir-validation.json --policy policies/human-correction-policy.json --output $(HUMAN_CORRECTION_DIR)

open-human-correction-pilot:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents open-human-correction-multica --request $(HUMAN_CORRECTION_DIR)/human-correction-request.json --policy policies/human-correction-policy.json --output $(HUMAN_CORRECTION_DIR)

sync-human-correction-pilot:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents sync-human-correction-multica --request $(HUMAN_CORRECTION_DIR)/human-correction-request.json --n04-artifact $(PILOT_RUN)/multica-stage9/artifacts/n04-test-case-ir-validation.json --policy policies/human-correction-policy.json --output $(HUMAN_CORRECTION_DIR) --run-manifest $(PILOT_RUN)/multica-run-manifest.json --workspace-manifest multica/workspace-manifest.json

prepare-multica-human-correction-pilot:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents prepare-multica-human-test-design-correction --previous-test-design-artifact $(PILOT_RUN)/multica-stage7/artifacts/a08-test-design-ir.json --previous-test-design-bundle $(PILOT_RUN)/multica-inputs/a08-correction-01/a08-input.json --oracle-review-artifact $(PILOT_RUN)/multica-stage8/artifacts/a09-oracle-coverage-review.json --n04-artifact $(PILOT_RUN)/multica-stage9/artifacts/n04-test-case-ir-validation.json --human-request $(HUMAN_CORRECTION_DIR)/human-correction-request.json --human-decision $(HUMAN_CORRECTION_DIR)/human-correction-decision.json --human-policy policies/human-correction-policy.json --output $(PILOT_RUN)/multica-inputs/a08-human-correction-01

prepare-g02-pilot:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents prepare-g02 --test-design-artifact $(PILOT_RUN)/multica-stage7/artifacts/a08-test-design-ir.json --oracle-review-artifact $(PILOT_RUN)/multica-stage8/artifacts/a09-oracle-coverage-review.json --n04-artifact $(PILOT_RUN)/multica-stage9/artifacts/n04-test-case-ir-validation.json --policy policies/g02-review-policy.json --output $(G02_DIR)

open-g02-pilot:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents open-g02-multica --request $(G02_DIR)/g02-review-request.json --policy policies/g02-review-policy.json --output $(G02_DIR)

sync-g02-pilot:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents sync-g02-multica --request $(G02_DIR)/g02-review-request.json --n04-artifact $(PILOT_RUN)/multica-stage9/artifacts/n04-test-case-ir-validation.json --policy policies/g02-review-policy.json --output $(G02_DIR)


# Human recovery continuum after QAA-19 authorization.
# A accepted A08 Multica run must emit binding fields as final text and pass tool-trace audit.

HUMAN_A08_BUNDLE=$(PILOT_RUN)/multica-inputs/a08-human-correction-01/a08-input.json
HUMAN_A08_RESPONSE=$(PILOT_RUN)/multica-outputs/a08-human-correction-01-run-messages.json
HUMAN_A08_STAGE=$(PILOT_RUN)/multica-stage10
HUMAN_A09_INPUT=$(PILOT_RUN)/multica-inputs/a09-human-correction-01
HUMAN_A09_STAGE=$(PILOT_RUN)/multica-stage11
HUMAN_N04_STAGE=$(PILOT_RUN)/multica-stage12

validate-human-a08-candidate-pilot:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents validate-multica-candidate --bundle $(HUMAN_A08_BUNDLE) --response $(HUMAN_A08_RESPONSE) --task-id ef5825a9-71c1-4938-ba70-23939896fa9a --issue-id 1cd41070-3051-49bb-82e2-020e7f6281f4 --attachment-id 019fea88-f67f-7c78-850c-b2f91497c919 --model-provider codex --model gpt-5.6-sol --prompt-version 1.3.0 --expect-reject

prepare-multica-oracle-review-human-pilot:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents prepare-multica-oracle-review --test-design-artifact $(HUMAN_A08_STAGE)/artifacts/a08-test-design-ir.json --test-design-bundle $(HUMAN_A08_BUNDLE) --oracle-rules policies/oracle-rule-library.json --output $(HUMAN_A09_INPUT)

run-n04-human-correction-pilot:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents run-n04-after-a09 --test-design-artifact $(HUMAN_A08_STAGE)/artifacts/a08-test-design-ir.json --oracle-review-artifact $(HUMAN_A09_STAGE)/artifacts/a09-oracle-coverage-review.json --oracle-review-bundle $(HUMAN_A09_INPUT)/a09-input.json --output $(HUMAN_N04_STAGE) --correction-attempt 3 --max-correction-attempts 2

prepare-g02-after-human-pilot:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents prepare-g02 --test-design-artifact $(HUMAN_A08_STAGE)/artifacts/a08-test-design-ir.json --oracle-review-artifact $(HUMAN_A09_STAGE)/artifacts/a09-oracle-coverage-review.json --n04-artifact $(HUMAN_N04_STAGE)/artifacts/n04-test-case-ir-validation.json --policy policies/g02-review-policy.json --output $(G02_DIR)

open-g02-after-human-pilot:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents open-g02-multica --request $(G02_DIR)/g02-review-request.json --policy policies/g02-review-policy.json --output $(G02_DIR)

sync-g02-after-human-pilot:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents sync-g02-multica --request $(G02_DIR)/g02-review-request.json --n04-artifact $(HUMAN_N04_STAGE)/artifacts/n04-test-case-ir-validation.json --policy policies/g02-review-policy.json --output $(G02_DIR)

# Stage-two real chain after G02 approval (N25 -> A11 -> N26 -> N15).
# A11 is an external Multica review: prepare the input, hand it to the A11 Agent
# in the Multica desktop, then ingest the accepted output before N26/N15.

HUMAN_A08_STAGE=$(PILOT_RUN)/multica-stage10
HUMAN_N25_STAGE=$(PILOT_RUN)/multica-stage13
HUMAN_A11_INPUT=$(PILOT_RUN)/multica-inputs/a11-01
HUMAN_A11_STAGE=$(PILOT_RUN)/multica-stage14
HUMAN_N26_STAGE=$(PILOT_RUN)/multica-stage15
HUMAN_N15_STAGE=$(PILOT_RUN)/multica-stage16

run-n25-after-g02-pilot:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents run-n25-after-g02 --a08-artifact $(HUMAN_A08_STAGE)/artifacts/a08-test-design-ir.json --g02-request $(G02_DIR)/g02-review-request.json --g02-outcome $(G02_DIR)/g02-review-outcome.json --output $(HUMAN_N25_STAGE) --run-manifest $(PILOT_RUN)/multica-run-manifest.json

prepare-multica-split-review-pilot:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents prepare-multica-split-review --test-design-artifact $(HUMAN_A08_STAGE)/artifacts/a08-test-design-ir.json --test-design-bundle $(PILOT_RUN)/multica-inputs/a08-human-correction-01/a08-input.json --compiled-artifact $(HUMAN_N25_STAGE)/artifacts/n25-compiled-test-cases.json --oracle-rules policies/oracle-rule-library.json --output $(HUMAN_A11_INPUT)

run-n26-after-a11-pilot:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents run-n26-after-a11 --compiled-artifact $(HUMAN_N25_STAGE)/artifacts/n25-compiled-test-cases.json --split-review-artifact $(HUMAN_A11_STAGE)/artifacts/a11-split-coverage-review.json --split-review-bundle $(HUMAN_A11_INPUT)/a11-input.json --output $(HUMAN_N26_STAGE) --selection-policy policies/selection-policy.json --run-manifest $(PILOT_RUN)/multica-run-manifest.json

prepare-multica-selection-advice-pilot:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents prepare-multica-selection-advice --selection-artifact $(HUMAN_N26_STAGE)/artifacts/n26-test-selection.json --compiled-artifact $(HUMAN_N25_STAGE)/artifacts/n25-compiled-test-cases.json --output $(PILOT_RUN)/multica-inputs/a12-input --selection-policy policies/selection-policy.json

run-n15-after-n26-pilot:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents run-n15-after-n26 --selection-artifact $(HUMAN_N26_STAGE)/artifacts/n26-test-selection.json --compiled-artifact $(HUMAN_N25_STAGE)/artifacts/n25-compiled-test-cases.json --output $(HUMAN_N15_STAGE) --run-manifest $(PILOT_RUN)/multica-run-manifest.json

prepare-autonomous-test-data-pilot:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents prepare-test-data --compiled-cases $(HUMAN_N25_STAGE)/artifacts/n25-compiled-test-cases.json --policy policies/test-data-policy.json --knowledge-sources knowledge/bi-knowledge-sources.json --capability-catalog knowledge/bi-data-capability-catalog.json --environment 112 --namespace $(TEST_DATA_NAMESPACE) --output $(TEST_DATA_STAGE)


# Execution-phase environment gates (design doc section 17): N07 precheck runs
# before any formal Case execution; a blocked precheck is routed to N16, whose
# fix plan must address every failed check before N07 is re-run.
N07_ENV_TARGET := $(PILOT_RUN)/env/target.json
N07_ENV_OBSERVED := $(PILOT_RUN)/env/observed.json
N07_ENV_FIX_PLAN := $(PILOT_RUN)/env/fix-plan.json
AUTOMATION_TARGET := $(PILOT_RUN)/env/automation-target.json
SERVER_AUTOMATION_STAGE := $(PILOT_RUN)/server-automation
N07_STAGE := $(PILOT_RUN)/multica-stage17
N16_STAGE := $(PILOT_RUN)/multica-stage18
N08_STAGE := $(PILOT_RUN)/multica-stage19
SERVER_QUALITY_STAGE := $(PILOT_RUN)/server-quality
SERVER_QUALITY_AUTOMATION_ARGS ?=
N08_GENERATION ?=
N08_REVIEW ?=
N08_CODE_CHECK ?=

prepare-server-automation-pilot:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents prepare-server-automation --execution-plan $(HUMAN_N15_STAGE)/artifacts/n15-execution-plan.json --compiled-cases $(HUMAN_N25_STAGE)/artifacts/n25-compiled-test-cases.json --automation-policy policies/automation-target-policy.json --target $(AUTOMATION_TARGET) --output $(SERVER_AUTOMATION_STAGE)

run-n07-env-precheck-pilot:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents run-n07-env-precheck --target $(N07_ENV_TARGET) --observed $(N07_ENV_OBSERVED) --output $(N07_STAGE) --workflow-run-id multica-pilot-001 --source-snapshot-id pilot-001-source-v1 --workflow-mode new_requirement

run-n16-env-fix-pilot:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents run-n16-env-fix --precheck $(N07_STAGE)/artifacts/n07-environment-precheck.json --fix-plan $(N07_ENV_FIX_PLAN) --output $(N16_STAGE)

LANDING_STAGE := $(PILOT_RUN)/candidate-landing

land-automation-candidates-pilot:
	@test -n "$(N08_GENERATION)" -a -n "$(N08_REVIEW)" -a -n "$(N08_CODE_CHECK)" || (echo "set N08_GENERATION, N08_REVIEW and N08_CODE_CHECK to current hash-bound Artifacts"; exit 2)
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents land-automation-candidates --generation $(N08_GENERATION) --review $(N08_REVIEW) --code-check $(N08_CODE_CHECK) --automation-policy policies/automation-target-policy.json --output $(LANDING_STAGE)

run-n08-automation-pilot:
	@test -n "$(N08_GENERATION)" -a -n "$(N08_REVIEW)" -a -n "$(N08_CODE_CHECK)" || (echo "set N08_GENERATION, N08_REVIEW and N08_CODE_CHECK to current hash-bound Artifacts"; exit 2)
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents run-n08-automation --generation $(N08_GENERATION) --review $(N08_REVIEW) --code-check $(N08_CODE_CHECK) --environment-precheck $(N07_STAGE)/artifacts/n07-environment-precheck.json --automation-policy policies/automation-target-policy.json --execution-policy policies/execution-policy.json --output $(N08_STAGE)

run-server-quality-pilot:
	PYTHONPATH=$(PYTHONPATH) $(PYTHON) -m qa_agents run-server-quality --execution-plan $(HUMAN_N15_STAGE)/artifacts/n15-execution-plan.json --compiled-cases $(HUMAN_N25_STAGE)/artifacts/n25-compiled-test-cases.json --environment-precheck $(N07_STAGE)/artifacts/n07-environment-precheck.json $(SERVER_QUALITY_AUTOMATION_ARGS) --quality-policy policies/quality-policy.json --run-manifest $(PILOT_RUN)/multica-run-manifest.json --output $(SERVER_QUALITY_STAGE)

run-server-full-pilot: prepare-server-automation-pilot run-n07-env-precheck-pilot run-server-quality-pilot
