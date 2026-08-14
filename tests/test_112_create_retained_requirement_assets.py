from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.test_112_customer_custom_dimension_lifecycle import (
    ACCOUNT_DESCRIBE_API_NAME,
    ACCOUNT_LEVEL_API_NAME,
    ACCOUNT_SCHEMA_ID,
    _walk,
)
from tests.test_112_dynamic_relation_metric_lifecycle import SCENARIOS


SALES_ORDER_SCHEMA_ID = "BI_5be1351956fc11448cdde39e"
REQUIREMENT_NAME = "统计图查看明细限制原因提示优化"
OUTPUT = Path(__file__).resolve().parents[1] / "generated/retained-test-assets.json"


def _create_metric(case_runner, name, agg_object, agg_field, time_field, filters=None):
    response = case_runner.http_api.call(
        "fs_bi_stat.agg_rule.add_new_agg_rule",
        body={
            "schemaId": SALES_ORDER_SCHEMA_ID,
            "schemaObjectName": "biz_sales_order",
            "displayName": name,
            "aggObject": agg_object,
            "aggField": agg_field,
            "aggFieldTime": time_field,
            "filterLists": filters or [],
            "checkFieldAggregateType": 2,
            "initStatus": 1,
            "timeZone": "Asia/Shanghai",
        },
    )
    assert response.status_code == 200
    assert response.body.get("Result", {}).get("FailureCode") == 0
    return str(response.body["Value"]["fieldId"])


def test_create_retained_requirement_assets_in_112(environment, case_runner) -> None:
    if environment.name != "112":
        pytest.skip("retained asset creation runs only with --env=112")
    assets = []

    fields = case_runner.http_api.call(
        "fs_bi_stat.stat_schema.get_fields_by_schema_id",
        body={"schemaId": ACCOUNT_SCHEMA_ID},
    )
    source_field = next(
        item for item in _walk(fields.body)
        if item.get("dbFieldName") == ACCOUNT_LEVEL_API_NAME and item.get("fieldId")
    )
    option_codes = []
    for item in _walk(source_field.get("ui", {})):
        code = str(item.get("optionCode", ""))
        if code and code not in option_codes:
            option_codes.append(code)
    if len(option_codes) < 2:
        pytest.skip("AccountObj.account_level has fewer than two live enum options; not_ready")
    split = max(1, len(option_codes) // 2)
    dimension_name = "客户等级枚举分组自定义维度"
    dimension = case_runner.http_api.call(
        "fs_bi_stat.custom_dimension.create_custom_dimension",
        body={
            "topologyDescribeId": ACCOUNT_SCHEMA_ID,
            "customType": "enum_group",
            "dimensionName": dimension_name,
            "description": f"需求：{REQUIREMENT_NAME}；基于客户等级枚举字段构造并长期保留",
            "dimensionConfig": json.dumps({
                "groups": [
                    {"name": "客户等级组一", "values": option_codes[:split]},
                    {"name": "客户等级组二", "values": option_codes[split:]},
                ],
                "default_name": "其他客户",
            }, ensure_ascii=False),
            "describeApiName": ACCOUNT_DESCRIBE_API_NAME,
            "sourceField": {
                "fieldId": source_field["fieldId"],
                "apiName": source_field["dbFieldName"],
                "type": source_field["type"],
                "describeApiName": ACCOUNT_DESCRIBE_API_NAME,
            },
        },
    )
    assert dimension.body.get("Result", {}).get("FailureCode") == 0
    dimension_id = str(dimension.body["Value"]["dimensionId"])
    assets.append({
        "requirement_name": REQUIREMENT_NAME, "resource_type": "custom_dimension",
        "display_name": dimension_name, "resource_id": dimension_id,
        "subject": "客户", "schema_id": ACCOUNT_SCHEMA_ID,
        "source_field_id": source_field["fieldId"], "source_field_api_name": "account_level",
        "source_field_type": source_field["type"], "retention_mode": "retain",
        "purpose": "验证自定义维度在维度、数据范围、下钻字段中的明细限制",
    })

    multi_base = {
        "refObjName": "object_sW5Pv__c", "refObjShowName": "销售订单关联主对象",
        "refJoinField": "BI_5274c1636ee87f0ba68f9aefa9ceb8fb",
        "slaveObject": {
            "refObjName": "object_1Lhg5__c", "refObjShowName": "销售订单关联从对象",
            "refJoinField": "BI_f59e3ce2bacf254c6e05c03eeacd9f85",
            "key": "BI_f59e3ce2bacf254c6e05c03eeacd9f85",
        },
    }
    multi_field = {
        "dbFieldName": "mc_exchange_rate", "fieldName": "汇率", "fieldType": "Number",
        "dbObjName": "object_1Lhg5__c", "fieldId": "BI_a23fbc479ea07edab8c7fd5fddf90cc7",
    }
    multi_time = {
        "dbFieldName": "create_time", "fieldName": "创建时间", "fieldType": "Date",
        "dbObjName": "object_1Lhg5__c", "fieldId": "BI_f6b5bbe13117f9e4e2f96790b31115a9",
    }
    for name, filters, topology in (
        ("销售订单三节点关联汇率聚合指标", [], "三节点"),
        ("销售订单四节点多关联汇率聚合指标", [{"filters": [{
            "fieldId": "BI_30a76bf349ea4cb58d7396e63622f074",
            "fieldID": "BI_30a76bf349ea4cb58d7396e63622f074",
            "dbFieldName": "owner", "dbObjName": "object_1Lhg5__c",
            "fieldName": "负责人", "fieldType": "Number", "type": "employee",
            "refObjName": "org_employee_user", "operator": 22, "value1": "",
        }]}], "四节点"),
    ):
        field_id = _create_metric(case_runner, name, multi_base, multi_field, multi_time, filters)
        assets.append({
            "requirement_name": REQUIREMENT_NAME, "resource_type": "aggregate_metric",
            "display_name": name, "resource_id": field_id, "subject": "销售订单",
            "schema_id": SALES_ORDER_SCHEMA_ID, "source_field_id": multi_field["fieldId"],
            "source_field_api_name": "mc_exchange_rate", "source_field_type": "Number",
            "relation_topology": topology, "retention_mode": "retain",
            "purpose": "验证多关联指标查看明细限制",
        })

    relation_names = {
        "what": "销售订单跟进动态单值关联信息编号聚合指标",
        "whatlist": "销售订单销售记录多值动态关联对象计数指标",
        "non_dynamic": "销售订单退款金额普通关联聚合指标",
    }
    for scenario, name in relation_names.items():
        config = SCENARIOS[scenario]
        filters = None
        if scenario == "whatlist":
            filters = [{"filters": [{
                "fieldId": "BI_d7cf7c3f0e12367c1d6acff274853d9f",
                "fieldID": "BI_d7cf7c3f0e12367c1d6acff274853d9f",
                "dbFieldName": "related_api_names", "dbObjName": "active_record",
                "fieldName": "关联业务对象", "fieldType": "String",
                "fieldRelationType": "whatList", "type": "select_many",
                "operator": 26, "value1": '[{"optionCode":"SalesOrderObj"}]',
            }]}]
        field_id = _create_metric(
            case_runner, name, config["agg_object"], config["agg_field"],
            config["time_field"], filters,
        )
        assets.append({
            "requirement_name": REQUIREMENT_NAME, "resource_type": "aggregate_metric",
            "display_name": name, "resource_id": field_id, "subject": "销售订单",
            "schema_id": SALES_ORDER_SCHEMA_ID,
            "source_field_id": config["agg_field"]["fieldId"],
            "source_field_api_name": config["agg_field"]["dbFieldName"],
            "source_field_type": config["agg_field"]["fieldType"],
            "relation_topology": scenario, "retention_mode": "retain",
            "purpose": "验证动态关联与普通关联的明细限制识别",
        })

    result_name = "销售订单金额结果集筛选聚合指标"
    result_id = _create_metric(
        case_runner, result_name,
        {"refObjName": "biz_sales_order", "refObjShowName": "销售订单", "refJoinField": ""},
        {"dbFieldName": "total_amount", "fieldName": "订单金额", "fieldType": "Number",
         "dbObjName": "biz_sales_order", "fieldId": "BI_5bd81fc8c7fa166683a9d44d"},
        {"dbFieldName": "create_time", "fieldName": "创建时间", "fieldType": "Date",
         "dbObjName": "biz_sales_order", "fieldId": "BI_5be1351956fc11448cdde3d1"},
        [{"filters": [{"fieldId": "BI_5bd81fc8c7fa166683a9d44d",
          "fieldID": "BI_5bd81fc8c7fa166683a9d44d", "fieldName": "订单金额",
          "fieldType": "Number", "operator": 1, "value1": "0",
          "filterConfig": {"filterGroupType": 1, "aggrType": "2"}}]}],
    )
    assets.append({
        "requirement_name": REQUIREMENT_NAME, "resource_type": "aggregate_metric",
        "display_name": result_name, "resource_id": result_id, "subject": "销售订单",
        "schema_id": SALES_ORDER_SCHEMA_ID, "source_field_id": "BI_5bd81fc8c7fa166683a9d44d",
        "source_field_api_name": "total_amount", "source_field_type": "Number",
        "retention_mode": "retain", "purpose": "验证结果集筛选指标查看明细限制",
    })

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps({"requirement_name": REQUIREMENT_NAME, "assets": assets}, ensure_ascii=False, indent=2) + "\n")
    assert len(assets) == 7
