PYTHON ?= python3

.PHONY: install test allure serve-allure sync-idl

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
