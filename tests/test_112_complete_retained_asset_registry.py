from __future__ import annotations

import json
from pathlib import Path

import pytest


ACCOUNT_SCHEMA_ID = "BI_5bcebcdc3060e20001e79977"
SALES_ORDER_SCHEMA_ID = "BI_5be1351956fc11448cdde39e"
REQUIREMENT_NAME = "统计图查看明细限制原因提示优化"
OUTPUT = Path(__file__).resolve().parents[1] / "generated/retained-test-assets.json"
JOINED_TABLE_EVIDENCE = (
    Path(__file__).resolve().parents[1] / "generated/112-joined-table-create-evidence.json"
)

METRICS = {
    "销售订单三节点关联汇率聚合指标": ("BI_a23fbc479ea07edab8c7fd5fddf90cc7", "mc_exchange_rate", "Number", "三节点"),
    "销售订单四节点多关联汇率聚合指标": ("BI_a23fbc479ea07edab8c7fd5fddf90cc7", "mc_exchange_rate", "Number", "四节点"),
    "销售订单跟进动态单值关联信息编号聚合指标": ("BI_ffe575aa25f8d92833ee2244cfffd7c3", "feed_id", "Number", "What"),
    "销售订单销售记录多值动态关联对象计数指标": ("BI_6488425a35e05a4983a93ecfd1e39e77", "related_object", "String", "WhatList"),
    "销售订单退款金额普通关联聚合指标": ("BI_dee958f43f3fec268fdc41b8203b1a6b", "refunded_amount", "Number", "普通关联"),
    "销售订单退款金额结果集筛选聚合指标": ("BI_dee958f43f3fec268fdc41b8203b1a6b", "refunded_amount", "Number", "结果集筛选"),
}


def _walk(value):
    if isinstance(value, dict):
        yield value
        for nested in value.values():
            yield from _walk(nested)
    elif isinstance(value, list):
        for nested in value:
            yield from _walk(nested)


def test_complete_and_register_retained_assets_in_112(environment, case_runner) -> None:
    if environment.name != "112":
        pytest.skip("retained asset registry runs only with --env=112")

    result_name = "销售订单退款金额结果集筛选聚合指标"
    existing = case_runner.http_api.call(
        "fs_bi_stat.stat_schema.get_fields_by_schema_id",
        body={"schemaId": SALES_ORDER_SCHEMA_ID},
    )
    if result_name not in str(existing.body):
        created = case_runner.http_api.call(
            "fs_bi_stat.agg_rule.add_new_agg_rule",
            body={
                "schemaId": SALES_ORDER_SCHEMA_ID, "schemaObjectName": "biz_sales_order",
                "displayName": result_name,
                "aggObject": {"refObjName": "biz_refund", "refObjShowName": "退款",
                              "refJoinField": "BI_0aa9ba25823fd3c0a736c2851da5e87a"},
                "aggField": {"dbFieldName": "refunded_amount", "fieldName": "退款金额",
                             "fieldType": "Number", "dbObjName": "biz_refund",
                             "fieldId": "BI_dee958f43f3fec268fdc41b8203b1a6b"},
                "aggFieldTime": {"dbFieldName": "refunded_time", "fieldName": "退款日期",
                                 "fieldType": "Date", "dbObjName": "biz_refund",
                                 "fieldId": "BI_ea8d0c37c44510bc922d20774f771b10"},
                "filterLists": [{"filters": [{
                    "fieldId": "BI_dee958f43f3fec268fdc41b8203b1a6b",
                    "fieldID": "BI_dee958f43f3fec268fdc41b8203b1a6b",
                    "dbFieldName": "refunded_amount", "dbObjName": "biz_refund",
                    "fieldName": "退款金额", "fieldType": "Number", "operator": 1,
                    "value1": "0", "filterConfig": {"filterGroupType": 1, "aggrType": "2"},
                }]}],
                "checkFieldAggregateType": 2, "initStatus": 1, "timeZone": "Asia/Shanghai",
            },
        )
        assert created.body.get("Result", {}).get("FailureCode") == 0
        assert created.body.get("Value", {}).get("fieldId")

    dimension_response = case_runner.http_api.call(
        "fs_bi_stat.custom_dimension.find_custom_dimensions",
        body={"topologyDescribeId": ACCOUNT_SCHEMA_ID,
              "keyWord": "客户等级枚举分组自定义维度", "timeZone": "Asia/Shanghai"},
    )
    dimension = next(
        item for item in _walk(dimension_response.body)
        if item.get("dimensionName") == "客户等级枚举分组自定义维度"
    )
    assets = [{
        "requirement_name": REQUIREMENT_NAME, "resource_type": "custom_dimension",
        "display_name": dimension["dimensionName"], "resource_id": dimension["dimensionId"],
        "subject": "客户", "schema_id": ACCOUNT_SCHEMA_ID,
        "source_field_id": dimension.get("sourceDimensionId"),
        "source_field_api_name": "account_level", "source_field_type": "select_one",
        "relation_topology": None, "retention_mode": "retain",
        "purpose": "验证自定义维度在维度、数据范围、下钻字段中的明细限制",
        "readiness": "active",
    }]
    joined_table = json.loads(JOINED_TABLE_EVIDENCE.read_text())
    assert joined_table["readiness"] == "active"
    assets.append({
        **joined_table,
        "subject": "客户/销售订单",
        "schema_id": SALES_ORDER_SCHEMA_ID,
        "source_field_id": None,
        "source_field_api_name": None,
        "source_field_type": None,
        "relation_topology": joined_table["join_type"],
        "purpose": "验证拼表查看明细入口及客户销售订单关联配置",
    })

    metric_response = case_runner.http_api.call(
        "fs_bi_stat.stat_schema.get_fields_by_schema_id",
        body={"schemaId": SALES_ORDER_SCHEMA_ID},
    )
    found = {}
    for item in _walk(metric_response.body):
        name = item.get("displayName") or item.get("fieldName") or item.get("name")
        field_id = item.get("fieldId") or item.get("fieldID")
        if name in METRICS and field_id:
            found[name] = str(field_id)
    assert set(found) == set(METRICS), {"missing": sorted(set(METRICS) - set(found))}
    for name, (source_id, api_name, field_type, topology) in METRICS.items():
        assets.append({
            "requirement_name": REQUIREMENT_NAME, "resource_type": "aggregate_metric",
            "display_name": name, "resource_id": found[name], "subject": "销售订单",
            "schema_id": SALES_ORDER_SCHEMA_ID, "source_field_id": source_id,
            "source_field_api_name": api_name, "source_field_type": field_type,
            "relation_topology": topology, "retention_mode": "retain",
            "purpose": "验证查看明细限制原因和错误码", "readiness": "active",
        })
    OUTPUT.write_text(
        json.dumps({"requirement_name": REQUIREMENT_NAME, "asset_count": len(assets),
                    "assets": assets}, ensure_ascii=False, indent=2) + "\n"
    )
    assert len(assets) == 8
