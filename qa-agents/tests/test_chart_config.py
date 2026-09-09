from __future__ import annotations

import pytest

from framework.clients.models import ApiResponse
from qa_agents.chart_config import (
    _resolve_field_dto,
    bind_stat_chart_config,
)
from qa_agents.errors import ContractError


SCHEMA = "BI_5be1351956fc11448cdde39e"
NATIVE_DATE = "BI_sales_order_create_time"
NATIVE_SELECT = "BI_sales_order_status"
FOREIGN_DATE = "BI_f6b5bbe13117f9e4e2f96790b31115a9"

SCHEMA_FIELDS = [
    {
        "fieldId": NATIVE_DATE,
        "fieldName": "创建时间",
        "type": "date_time",
        "dbFieldName": "create_time",
        "dbObjName": "biz_sales_order",
    },
    {
        "fieldId": NATIVE_SELECT,
        "fieldName": "订单状态",
        "type": "select_one",
        "dbFieldName": "status",
        "dbObjName": "biz_sales_order",
    },
    {
        "fieldId": "BI_amount",
        "fieldName": "订单金额",
        "type": "number",
        "dbFieldName": "amount",
        "dbObjName": "biz_sales_order",
    },
]


class FakeRunner:
    def __init__(self, fields: list[dict] | None = None) -> None:
        self.fields = list(fields or SCHEMA_FIELDS)
        self.last_update: dict | None = None
        self.http_api = self
        self.http_client = self

    def call(self, operation: str, body=None):
        if operation == "fs_bi_stat.stat_schema.get_fields_by_schema_id":
            return ApiResponse(
                200,
                {"Result": {"FailureCode": 0}, "Value": {"fields": self.fields}},
            )
        if operation == "fs_bi_stat.stat_edit.get_chart_config":
            if self.last_update:
                axis = self.last_update.get("axisData") or {}
                return ApiResponse(
                    200,
                    {
                        "Result": {"FailureCode": 0},
                        "Value": {
                            "schemaId": SCHEMA,
                            "chartType": "bar",
                            "dimensionFields": axis.get("dimensionFields") or [],
                            "measureFields": axis.get("measureFieldList") or [],
                            "defaultFilterOptionIDs": ["opt-1"],
                        },
                    },
                )
            return ApiResponse(
                200,
                {
                    "Result": {"FailureCode": 0},
                    "Value": {
                        "schemaId": SCHEMA,
                        "chartType": "bar",
                        "dimensionFields": [
                            {"fieldId": "BI_old_dim", "fieldName": "old"}
                        ],
                        "measureFields": [
                            {
                                "fieldId": "BI_old_measure",
                                "fieldName": "oldm",
                                "yAxisIndex": 1,
                            }
                        ],
                        "defaultFilterOptionIDs": ["opt-1"],
                    },
                },
            )
        if operation == "fs_bi_stat.stat_edit.get_filters_result":
            if self.last_update:
                return ApiResponse(
                    200,
                    {
                        "Result": {"FailureCode": 0},
                        "Value": {
                            "filterLists": self.last_update.get("filterLists") or [],
                            "secondaryFilterLists": [],
                            "defaultFilterOptionIDs": ["opt-1"],
                        },
                    },
                )
            return ApiResponse(
                200,
                {
                    "Result": {"FailureCode": 0},
                    "Value": {
                        "filterLists": [
                            {
                                "filters": [
                                    {"fieldId": "BI_old_filter", "fieldName": "oldf"}
                                ]
                            }
                        ],
                        "secondaryFilterLists": [],
                        "defaultFilterOptionIDs": ["opt-1"],
                    },
                },
            )
        if operation == "fs_bi_crm.stat_edit.get_stat_view":
            return ApiResponse(
                200,
                {
                    "Result": {"FailureCode": 0},
                    "Value": {
                        "viewID": "view-1",
                        "defaultFilterOptionIDs": ["opt-1"],
                    },
                },
            )
        raise AssertionError(operation)

    def post(self, path: str, json_body=None):
        assert path.endswith("updateStatView")
        self.last_update = json_body
        return ApiResponse(200, {"Result": {"FailureCode": 0}, "Value": {}})

def test_resolve_exact_field_id_wins() -> None:
    field, used_fallback = _resolve_field_dto(
        SCHEMA,
        NATIVE_SELECT,
        role="filter",
        fields=SCHEMA_FIELDS,
    )
    assert used_fallback is False
    assert field["fieldId"] == NATIVE_SELECT


def test_resolve_missing_filter_falls_back_to_schema_date() -> None:
    field, used_fallback = _resolve_field_dto(
        SCHEMA,
        FOREIGN_DATE,
        role="filter",
        fields=SCHEMA_FIELDS,
    )
    assert used_fallback is True
    assert field["fieldId"] == NATIVE_DATE


def test_resolve_missing_dimension_prefers_select() -> None:
    field, used_fallback = _resolve_field_dto(
        SCHEMA,
        "BI_missing_dim",
        role="dimension",
        fields=SCHEMA_FIELDS,
    )
    assert used_fallback is True
    assert field["fieldId"] == NATIVE_SELECT


def test_resolve_raises_when_no_compatible_native_field() -> None:
    with pytest.raises(ContractError, match="no schema-native filter field"):
        _resolve_field_dto(
            SCHEMA,
            FOREIGN_DATE,
            role="filter",
            fields=[
                {
                    "fieldId": "BI_text",
                    "fieldName": "备注",
                    "type": "text",
                    "dbFieldName": "remark",
                }
            ],
        )


def test_bind_does_not_crash_on_foreign_object_filter() -> None:
    runner = FakeRunner()
    payload = bind_stat_chart_config(
        runner,
        chart_view_id="view-1",
        schema_id=SCHEMA,
        filter_field_id=FOREIGN_DATE,
    )
    assert payload["status"] == "bound"
    assert payload["requested"]["filter_field_id"] == FOREIGN_DATE
    assert payload["resolved"]["filter_field_id"] == NATIVE_DATE
    assert payload["fallbacks"]["filter_field_id"] == FOREIGN_DATE
    filters = (runner.last_update or {}).get("filterLists") or []
    bound_ids = [
        item.get("fieldId") or item.get("fieldID")
        for group in filters
        for item in (group.get("filters") or [])
    ]
    assert NATIVE_DATE in bound_ids
    assert FOREIGN_DATE not in bound_ids


def test_bind_keeps_source_measure_when_metric_not_on_schema() -> None:
    runner = FakeRunner()
    payload = bind_stat_chart_config(
        runner,
        chart_view_id="view-1",
        schema_id=SCHEMA,
        filter_field_id=NATIVE_DATE,
        measure_field_id="BI_missing_metric",
    )
    assert payload["status"] == "bound"
    assert payload["measure_bind_status"] == "skipped_field_not_on_schema"
    assert payload["fallbacks"]["measure_field_id"] == "BI_missing_metric"
    measures = ((runner.last_update or {}).get("axisData") or {}).get("measureFieldList")
    assert measures
    assert (measures[0].get("fieldId") or measures[0].get("fieldID")) == "BI_old_measure"
