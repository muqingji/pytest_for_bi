from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path
from copy import deepcopy

import pytest

from framework.config.environment import load_cases
from qa_agents.data_planning import compile_resource_plan, extract_test_data_intents
from qa_agents.test_data import bind_plan_to_case, validate_test_data_plan


SCHEMA_ID = "BI_e672ff1046fb773b76bc2b56"
AMOUNT_FIELD_ID = "BI_d9d45d8381de9e094fe1973acf408d92"
ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize(
    ("variant", "locale", "field_name", "ratio_type"),
    [
        ("ordinary", "zh-CN", "收入", "0"),
        ("ordinary", "en", "Revenue", "0"),
        ("comparison", "zh-CN", "收入同比", "1"),
        ("comparison", "en", "Revenue YoY", "1"),
    ],
)
def test_pc_002_contract_read_only_variants(
    environment, case_runner, variant, locale, field_name, ratio_type
) -> None:
    if environment.name != "112":
        pytest.skip("PC-002 contract automation runs only with --env=112")
    fields = case_runner.http_api.call(
        "fs_bi_stat.stat_schema.get_fields_by_schema_id", body={"schemaId": SCHEMA_ID}
    )
    assert fields.status_code == 200
    assert AMOUNT_FIELD_ID in str(fields.body)
    _assert_detail_error(case_runner, AMOUNT_FIELD_ID, field_name, locale, ratio_type)


@pytest.mark.parametrize(
    ("variant", "locale", "field_name", "case_id"),
    [
        ("aggregate", "zh-CN", "成交额", "CASE-AUTO-RESULT-FILTER-DETAIL-112"),
        ("aggregate", "en", "Deal Amount", "CASE-AUTO-RESULT-FILTER-DETAIL-112"),
        ("calculated", "zh-CN", "利润率", "CASE-AUTO-CALCULATED-RESULT-FILTER-112"),
        ("calculated", "en", "Profit Margin", "CASE-AUTO-CALCULATED-RESULT-FILTER-112"),
    ],
)
def test_pc_002_contract_managed_variants(
    environment, case_runner, variant, locale, field_name, case_id
) -> None:
    if environment.name != "112":
        pytest.skip("PC-002 contract automation runs only with --env=112")
    source_case = next(item for item in load_cases("112") if item["id"] == case_id)
    case = deepcopy(source_case)
    catalog = json.loads(
        (ROOT / "qa-agents/knowledge/bi-data-capability-catalog.json").read_text()
    )
    policy = json.loads((ROOT / "qa-agents/policies/test-data-policy.json").read_text())
    intent = extract_test_data_intents([case], catalog)
    namespace = "qa-pc002-{}-{}".format(
        variant, datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    )
    plan = compile_resource_plan(intent, catalog, environment="112", namespace=namespace)
    assert validate_test_data_plan(plan, policy)["write_authorized"] is True
    executable = bind_plan_to_case(case, plan)
    request = executable["steps"][0]["request"]["json"]
    request["lan"] = locale
    request["filterLists"][0]["filters"][0]["fieldName"] = field_name
    executable["steps"][0]["expect"]["body_contains_values"] = [field_name]
    context = case_runner.execute(executable)
    assert "s307011535" in str(context["test_response"])
    assert field_name in str(context["test_response"])
    assert all(
        item["status"] == "completed"
        for phase in ("setup", "readiness", "test", "cleanup", "residue")
        for item in context["__lifecycle__"][phase]
    )


def _assert_detail_error(case_runner, field_id, field_name, locale, ratio_type) -> None:
    response = case_runner.http_api.call(
        "fs_bi_stat.stat_base.data_query_da655ba1",
        body={
            "id": SCHEMA_ID, "isView": 0, "measureFieldID": field_id,
            "measureFieldIDs": [field_id], "pageNumber": 1, "pageSize": 20,
            "filterLists": [{"filters": [{
                "displayNumber": 1, "fieldId": field_id, "fieldID": field_id,
                "fieldName": field_name, "fieldType": "Number", "operator": 1,
                "operatorLabel": "equals", "value1": "0", "value2": "",
                "aggDimType": "base_agg", "filterConfig": {
                    "showAppointLevelSwitch": 0, "switchStatus": 0,
                    "filterGroupType": 1, "aggrType": "2", "ratioType": ratio_type,
                },
            }]}], "timeZone": "Asia/Shanghai", "lan": locale,
        },
    )
    assert response.status_code == 200
    body = str(response.body)
    assert "s307011535" in body
    assert field_name in body
    assert "dataSet" not in body or "s307011535" in body
