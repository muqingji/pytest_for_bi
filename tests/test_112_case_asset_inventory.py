from __future__ import annotations

import json
from pathlib import Path

import pytest

from qa_agents.asset_discovery import discover_catalog, walk_values
from qa_agents.chart_builder import canonical_hash


OUTPUT = Path(__file__).resolve().parents[1] / "generated/112-case-asset-inventory.json"
CUSTOM_DIMENSION_ID = "BI_02293bb8fb184b56b0502f25cf06e3d5"


def _query(case_runner, category_id, page, page_size):
    return case_runner.http_client.post(
        "/FHH/EM1HBICRM/rptCategoryController/getCategoryAndRpt",
        json_body={"categoryID": category_id, "keyWord": "", "type": 1,
                   "listRange": 2, "pageNumber": page, "pageSize": page_size,
                   "showFullPathCategory": 1, "timeZone": "Asia/Shanghai"},
    ).body


def _chart(case_runner, view_id):
    return case_runner.http_api.call(
        "fs_bi_stat.stat_edit.get_chart_config",
        body={"id": view_id, "isView": 1, "type": "edit", "querySource": "UNKNOWN",
              "cacheTime": 0, "refresh": 1},
    ).body


def _filters(case_runner, view_id):
    return case_runner.http_api.call(
        "fs_bi_stat.stat_edit.get_filters_result", body={"id": view_id, "isView": 1}
    ).body


def _metric_type(metric):
    source_type = str(metric.get("type", "")).lower()
    if source_type == "formula":
        return "calculated"
    if source_type in {"count", "sum", "max", "min", "average", "count_distinct"}:
        return "aggregate"
    if str(metric.get("ratioType", "0")) != "0" or str(metric.get("aggrType")) in {"7", "8", "9", "10"}:
        return "comparison"
    if metric.get("formula") or metric.get("isCalc"):
        return "calculated"
    if str(metric.get("isPredefined")) == "2":
        return "aggregate"
    return "ordinary"


def test_inventory_live_case_assets_in_112(environment, case_runner):
    if environment.name != "112":
        pytest.skip("112 only")
    catalog = discover_catalog(lambda category, page, size: _query(
        case_runner, category, page, size
    ))
    charts = [item for item in catalog if int(item.get("isCategory", -1)) == 2]
    result_set_assets = []
    custom_dimension_assets = []
    schema_fields = {}
    for item in charts:
        view_id = str(item["itemID"])
        chart_body = _chart(case_runner, view_id)
        if chart_body.get("Result", {}).get("FailureCode") != 0:
            continue
        value = chart_body.get("Value") or {}
        chart_text = json.dumps(value, ensure_ascii=False, sort_keys=True)
        if CUSTOM_DIMENSION_ID in chart_text:
            custom_dimension_assets.append({
                "resource_id": view_id, "display_name": value.get("viewName"),
                "configuration_hash": canonical_hash(value),
            })
        filter_body = _filters(case_runner, view_id)
        result_filters = [node for node in walk_values(filter_body)
                          if node.get("filterGroupType") == 1 or (
                              isinstance(node.get("filterConfig"), dict)
                              and node["filterConfig"].get("filterGroupType") == 1)]
        if not result_filters:
            continue
        metrics = value.get("measureFields") or []
        by_id = {str(metric.get("fieldId") or metric.get("fieldID")): metric for metric in metrics}
        schema_id = str(value.get("schemaId") or "")
        if schema_id and schema_id not in schema_fields:
            response = case_runner.http_api.call(
                "fs_bi_stat.stat_schema.get_fields_by_schema_id", body={"schemaId": schema_id}
            ).body
            schema_fields[schema_id] = {
                "by_id": {str(node.get("fieldId") or node.get("fieldID")): dict(node)
                          for node in walk_values(response) if node.get("fieldId") or node.get("fieldID")},
                "response_hash": canonical_hash(response),
            }
        matched = []
        for filter_item in result_filters:
            field_id = str(filter_item.get("fieldId") or filter_item.get("fieldID") or "")
            metric = schema_fields.get(schema_id, {}).get("by_id", {}).get(
                field_id, by_id.get(field_id, filter_item)
            )
            if field_id:
                matched.append({"field_id": field_id,
                                "field_name": filter_item.get("fieldName") or metric.get("fieldName"),
                                "metric_type": _metric_type(metric)})
        result_set_assets.append({
            "resource_id": view_id, "display_name": value.get("viewName"),
            "schema_id": value.get("schemaId"), "matched_metrics": matched,
            "chart_configuration_hash": canonical_hash(value),
            "filter_configuration_hash": canonical_hash(filter_body),
            "schema_fields_response_hash": schema_fields.get(schema_id, {}).get("response_hash"),
        })
    payload = {
        "schema_version": "case-asset-inventory/1.0", "environment": "112",
        "catalog_entry_count": len(catalog), "chart_count": len(charts),
        "custom_dimension_id": CUSTOM_DIMENSION_ID,
        "custom_dimension_assets": custom_dimension_assets,
        "result_set_filter_assets": result_set_assets,
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    assert result_set_assets, "full catalog contains no result-set filter chart"
