PYTHON ?= python3

.PHONY: install test allure serve-allure interface-test interface-report print-interface-report interface-html-report publish-interface-report sync-idl sync-fs-bi-http sync-fs-bi-remote

INTERFACE_REPORT_ROOT ?= reports/interface-automation
INTERFACE_RESULTS_DIR ?= $(INTERFACE_REPORT_ROOT)/allure-results
INTERFACE_HTML_DIR ?= $(INTERFACE_REPORT_ROOT)/allure-report
INTERFACE_TEXT_REPORT ?= $(INTERFACE_REPORT_ROOT)/report.txt
INTERFACE_REPORT_MAX_CHARS ?= 6000
INTERFACE_REPORT_URL ?= https://oss.firstshare.cn/reports/interface-automation/current/

install:
	$(PYTHON) -m pip install -r requirements.txt

test:
	$(PYTHON) -m pytest --alluredir=allure-results

allure:
	allure generate allure-results -o allure-report --clean

serve-allure:
	allure serve allure-results

interface-test:
	mkdir -p $(INTERFACE_REPORT_ROOT)
	PYTHONPATH=.:src .venv/bin/pytest --env=112 tests/test_translation_language.py --alluredir=$(INTERFACE_RESULTS_DIR) --clean-alluredir

interface-report:
	@mkdir -p $(INTERFACE_REPORT_ROOT)
	@PYTHONPATH=.:src .venv/bin/pytest -q --tb=short --env=112 tests/test_translation_language.py --alluredir=$(INTERFACE_RESULTS_DIR) --clean-alluredir; \
	pytest_status=$$?; \
	$(PYTHON) scripts/print_allure_report.py $(INTERFACE_RESULTS_DIR) --output $(INTERFACE_TEXT_REPORT) --max-attachment-chars $(INTERFACE_REPORT_MAX_CHARS); \
	report_status=$$?; \
	test $$report_status -eq 0 || exit $$report_status; \
	exit $$pytest_status

print-interface-report:
	@$(PYTHON) scripts/print_allure_report.py $(INTERFACE_RESULTS_DIR) --output $(INTERFACE_TEXT_REPORT) --max-attachment-chars $(INTERFACE_REPORT_MAX_CHARS)

interface-html-report: interface-test
	@command -v allure >/dev/null || { echo "allure CLI is required to generate HTML"; exit 1; }
	allure generate $(INTERFACE_RESULTS_DIR) -o $(INTERFACE_HTML_DIR) --clean
	@echo "Interface automation report: $(INTERFACE_HTML_DIR)/index.html"

publish-interface-report: interface-html-report
	@test -n "$(OSS_REPORT_DEPLOY_TARGET)" || { echo "Set OSS_REPORT_DEPLOY_TARGET, for example user@host:/var/www/reports/interface-automation/current/"; exit 1; }
	rsync -az --delete $(INTERFACE_HTML_DIR)/ $(OSS_REPORT_DEPLOY_TARGET)
	@echo "Published interface automation report: $(INTERFACE_REPORT_URL)"

sync-idl:
	$(PYTHON) scripts/sync_idl.py --idl-dir idl

sync-fs-bi-http:
	$(PYTHON) scripts/sync_fs_bi_http_api.py --source /Users/liushanshan/code/server/fs-bi

sync-fs-bi-remote:
	$(PYTHON) .codex/skills/sync-fs-bi-api/scripts/sync_fs_bi_api.py
