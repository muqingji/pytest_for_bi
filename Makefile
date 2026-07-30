PYTHON ?= python3

.PHONY: install test allure serve-allure sync-idl sync-fs-bi-http sync-fs-bi-remote

install:
	$(PYTHON) -m pip install -r requirements.txt

test:
	$(PYTHON) -m pytest --alluredir=allure-results

allure:
	allure generate allure-results -o allure-report --clean

serve-allure:
	allure serve allure-results

sync-idl:
	$(PYTHON) scripts/sync_idl.py --idl-dir idl

sync-fs-bi-http:
	$(PYTHON) scripts/sync_fs_bi_http_api.py --source /Users/liushanshan/code/server/fs-bi

sync-fs-bi-remote:
	$(PYTHON) .codex/skills/sync-fs-bi-api/scripts/sync_fs_bi_api.py
