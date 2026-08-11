from __future__ import annotations

import json
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
EVIDENCE_PATH = (
    ROOT / "qa-agents/runs/pilot-001/retained-test-data-112-20260811-01.json"
)


def _variants() -> list[dict]:
    evidence = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    return list(evidence["request_scoped_variants"])


@pytest.mark.parametrize("variant", _variants(), ids=lambda item: item["variant"])
def test_retained_result_filter_variants_are_readable_in_112(
    environment, case_runner, variant: dict
) -> None:
    """Read-only replay against resources explicitly retained by the user."""

    if environment.name != "112":
        pytest.skip("retained BI resources exist only in 112")
    schema_id = "BI_e672ff1046fb773b76bc2b56"
    field_id = variant["field_id"]
    field_name = variant["field_name"]
    case = {
        "id": f"CASE-BE-002-{variant['variant']}",
        "name": f"112 retained {variant['variant']} result-set filter",
        "environment": "112",
        "steps": [
            {
                "name": "只读调用查看明细接口",
                "request": {
                    "protocol": "http",
                    "api": "fs_bi_stat.stat_base.data_query_da655ba1",
                    "json": {
                        "id": schema_id,
                        "isView": 0,
                        "measureFieldID": field_id,
                        "measureFieldIDs": [field_id],
                        "pageNumber": 1,
                        "pageSize": 20,
                        "filterLists": [
                            {
                                "filters": [
                                    {
                                        "displayNumber": 1,
                                        "fieldId": field_id,
                                        "fieldID": field_id,
                                        "fieldName": field_name,
                                        "fieldType": "Number",
                                        "operator": 1,
                                        "operatorLabel": "等于",
                                        "value1": "0",
                                        "value2": "",
                                        "aggDimType": "agg",
                                        "filterConfig": {
                                            "showAppointLevelSwitch": 0,
                                            "switchStatus": 0,
                                            "filterGroupType": variant["filter_group_type"],
                                            "aggrType": variant["aggr_type"],
                                            "ratioType": variant["ratio_type"],
                                        },
                                    }
                                ]
                            }
                        ],
                        "timeZone": "Asia/Shanghai",
                        "lan": "zh-CN",
                    },
                },
                "expect": {
                    "status_code": 200,
                },
            }
        ],
        "cleanup": [],
    }

    context = case_runner.execute(case)

    assert context["__lifecycle__"]["setup"] == []
    assert context["__lifecycle__"]["cleanup"] == []
    assert context["__lifecycle__"]["test"][0]["status"] == "completed"
    assert "s307011535" in str(context["test_response"])
    assert field_name in str(context["test_response"])
