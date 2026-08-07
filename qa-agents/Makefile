PYTHON ?= ../.venv/bin/python
PYTEST ?= ../.venv/bin/pytest
PYTHONPATH := src
PILOT_INPUT := eval/workflows/pilot-001-detail-drill-message-i18n/input
PILOT_ORACLE := eval/workflows/pilot-001-detail-drill-message-i18n/oracle
PILOT_RUN := runs/pilot-001

.PHONY: test pilot pilot-full pilot-automation collect-pilot evaluate-pilot prepare-multica-pilot prepare-multica-alignment-pilot report-multica-alignment-pilot prepare-g01-pilot record-g01-pilot run-n24-pilot prepare-multica-test-design-pilot prepare-multica-oracle-review-pilot run-n04-pilot prepare-multica-test-design-correction-pilot prepare-multica-oracle-review-correction-pilot run-n04-correction-pilot

G01_DIR := $(PILOT_RUN)/g01
G01_DECISION_INPUT ?= $(G01_DIR)/g01-decision-input.json

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
