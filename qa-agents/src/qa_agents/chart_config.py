"""Bind case-specific dimension/measure/filter config onto cloned stat charts.

Live 112 findings (2026-08-25):
- copy_stat_view alone leaves every chart as a clone of the source config
- updateStatView can replace dimensionFields and filterLists reliably
- measureFields can be retargeted only from a replaceable measure shell:
  source chart ``客户统计-指定层级`` (订单产品编号) accepts aggregate-metric
  swaps; source ``客户统计_副本`` (单行文本筛选 employee) rejects them and
  readback becomes empty measureFields
- bare base_agg amount fields do not stick; case-owned aggregate metrics
  (aggDimType=agg) do stick after clearing fieldLocation/viewFieldId
"""

from __future__ import annotations

import copy
from typing import Any, Callable, Mapping

from framework.clients.models import ApiResponse

from .errors import ContractError


def _value(response: ApiResponse) -> dict[str, Any]:
    body = response.body if isinstance(response.body, Mapping) else {}
    result = body.get("Result") if isinstance(body.get("Result"), Mapping) else {}
    if result.get("FailureCode") not in (None, 0):
        raise ContractError(f"chart config API failed: {body}")
    value = body.get("Value")
    return dict(value) if isinstance(value, Mapping) else {}


def _walk(value: Any):
    if isinstance(value, Mapping):
        yield value
        for child in value.values():
            yield from _walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from _walk(child)


def _find_field_dto(runner: Any, schema_id: str, field_id: str) -> dict[str, Any]:
    response = runner.http_api.call(
        "fs_bi_stat.stat_schema.get_fields_by_schema_id",
        body={"schemaId": schema_id},
    )
    for item in _walk(response.body):
        candidate = str(item.get("fieldId") or item.get("fieldID") or "")
        if candidate == field_id:
            return copy.deepcopy(dict(item))
    raise ContractError(
        f"field {field_id!r} not found on schema {schema_id!r} for chart config bind"
    )


def _default_filter_option_ids(
    crm: Mapping[str, Any], chart: Mapping[str, Any], filters: Mapping[str, Any]
) -> list[str]:
    raw = (
        crm.get("defaultFilterOptionIDs")
        or crm.get("defaultFilterOptionIds")
        or chart.get("defaultFilterOptionIDs")
        or chart.get("defaultFilterOptionIds")
        or filters.get("defaultFilterOptionIDs")
        or filters.get("defaultFilterOptionIds")
        or []
    )
    if isinstance(raw, list) and raw:
        return [str(item) for item in raw]
    option_ids: list[str] = []
    for item in _walk(filters):
        candidate = item.get("optionID") or item.get("optionId")
        if candidate and str(candidate) not in option_ids:
            option_ids.append(str(candidate))
    return option_ids


_DIMENSION_FIELD_TYPE_BY_SCHEMA_TYPE = {
    "select_one": "SingleSelectEnum",
    "select_many": "MultiSelectEnum",
    "date_time": "Date",
    "date": "Date",
    "text": "String",
    "string": "String",
    "quote": "String",
    "number": "Number",
    "auto_number": "String",
    "email": "String",
    "phone_number": "String",
    "true_or_false": "String",
    "record_type": "SingleSelectEnum",
    "province": "String",
    "city": "String",
    "country": "String",
    "district": "String",
    "department": "String",
    "employee": "String",
    "formula": "String",
    "dimension": "String",
    "tree_path": "String",
}


def _normalize_dimension_field(field: Mapping[str, Any]) -> dict[str, Any]:
    """Map schema field DTOs onto chart axis fieldTypes accepted by updateStatView.

    Live 112 only accepts Date/String/SingleSelectEnum/MultiSelectEnum/Number on
    dimensionFields. Schema types like select_one/date_time/quote must be coerced.
    """
    axis_field = copy.deepcopy(dict(field))
    field_id = str(axis_field.get("fieldID") or axis_field.get("fieldId") or "")
    if not field_id:
        raise ContractError("dimension field DTO missing fieldId")
    axis_field["fieldID"] = field_id
    axis_field["fieldId"] = field_id
    custom_type = str(axis_field.get("customType") or "")
    schema_type = str(axis_field.get("type") or axis_field.get("fieldType") or "").lower()
    if custom_type == "enum_group" or schema_type in {"select_one", "single_select_enum"}:
        axis_field["fieldType"] = "SingleSelectEnum"
        axis_field["subFieldType"] = "SingleSelectEnum"
    elif schema_type in {"select_many", "multi_select_enum"}:
        axis_field["fieldType"] = "MultiSelectEnum"
        axis_field["subFieldType"] = "MultiSelectEnum"
    else:
        mapped = _DIMENSION_FIELD_TYPE_BY_SCHEMA_TYPE.get(schema_type)
        if mapped:
            axis_field["fieldType"] = mapped
            if mapped.endswith("Enum"):
                axis_field["subFieldType"] = mapped
            elif "subFieldType" not in axis_field or axis_field.get("subFieldType") in (None, ""):
                axis_field["subFieldType"] = ""
        elif not axis_field.get("fieldType"):
            # Last resort so updateStatView does not reject bare schema DTOs.
            axis_field["fieldType"] = "String"
            axis_field.setdefault("subFieldType", "")
    return axis_field


def _normalize_filter_field(field: Mapping[str, Any]) -> dict[str, Any]:
    """Build a chart filter entry from a schema field/metric DTO.

    Aggregate metrics are marked with aggDimType=agg so BI treats them as
    result-set capable filter fields. Operator 0 + empty values matches the
    live readback observed after successful 112 binds.
    """
    item = copy.deepcopy(dict(field))
    field_id = str(item.get("fieldID") or item.get("fieldId") or "")
    if not field_id:
        raise ContractError("filter field DTO missing fieldId")
    item["fieldID"] = field_id
    item["fieldId"] = field_id
    item.setdefault("displayNumber", 1)
    item.setdefault("isLock", 0)
    item.setdefault("operator", 0)
    item.setdefault("value1", "")
    item.setdefault("value2", "")
    item.setdefault("operatorLabel", "")
    item.setdefault("dateRangeID", "")
    item.setdefault("parentID", "")
    item.setdefault("subFieldType", item.get("subFieldType") or "")
    if str(item.get("aggDimType") or "") == "agg" or str(item.get("type") or "").lower() in {
        "number",
        "agg",
    }:
        item.setdefault("fieldType", "Number")
        item.setdefault("type", "number")
        item.setdefault("aggDimType", "agg")
        item.setdefault("dbObjName", "agg_data")
        item.setdefault(
            "ui",
            {
                "format": "Number",
                "justLeafNodeSelect": 0,
                "type": "UI_Input",
                "isShowDisplayName": False,
            },
        )
        item.setdefault("operateMenu", ["filterGroup", "filterDetail"])
    return item


def _normalize_measure_field(
    base_measure: Mapping[str, Any], field: Mapping[str, Any]
) -> dict[str, Any]:
    """Retarget the chart measure shell onto a case-owned aggregate metric.

    The server allocates fieldLocation/viewFieldId; sending empty values is
    required so the new fieldID is accepted.
    """
    if not base_measure:
        raise ContractError("chart has no measure shell to retarget")
    item = copy.deepcopy(dict(base_measure))
    field_id = str(field.get("fieldID") or field.get("fieldId") or "")
    if not field_id:
        raise ContractError("measure field DTO missing fieldId")

    item["fieldID"] = field_id
    item["fieldId"] = field_id
    for key in (
        "fieldName",
        "dbFieldName",
        "type",
        "udfFieldId",
        "objectDescribeApiName",
        "aggDimType",
    ):
        if field.get(key) is not None:
            item[key] = copy.deepcopy(field[key])

    item["type"] = str(field.get("type") or item.get("type") or "number")
    item["fieldType"] = "Number"
    item["dbObjName"] = str(field.get("dbObjName") or item.get("dbObjName") or "agg_data")
    item["subFieldType"] = ""
    describe = field.get("describeApiNames") or []
    if isinstance(describe, list) and describe:
        item["crmObjName"] = str(describe[0])
    elif str(field.get("objectDescribeApiName") or "") == "biz_account":
        item["crmObjName"] = "AccountObj"
    item["objShowName"] = str(item.get("objShowName") or "客户")
    item["legendName"] = str(field.get("fieldName") or item.get("legendName") or "")
    item["formatStr"] = str(item.get("formatStr") or "#,##0")
    item["aggrType"] = "2"
    item["checkFieldAggregateType"] = "2"
    item["aggrTypeMap"] = {"2": "求和"}
    item["checkFieldAggregateTypeMap"] = {"2": "求和"}
    item["operateMenu"] = ["filter", "filterGroup", "aggr", "order"]
    item["ui"] = {
        "type": "UI_Input",
        "justLeafNodeSelect": 0,
        "format": "Number",
        "isShowDisplayName": False,
    }
    item["measureConfig"] = {
        "measureIcon": 0,
        "baseOnSortFieldProportionType": 0,
        "proportionType": 0,
        "isInTotalList": 0,
        "isRanking": False,
        "rankPartition": "global",
        "description": "",
    }
    # Critical for sticky replace on 112.
    item["fieldLocation"] = ""
    item["viewFieldId"] = ""
    item["yAxisIndex"] = int(item.get("yAxisIndex") or 1)
    item["isPredefined"] = item.get("isPredefined", 2)
    item["isDetail"] = item.get("isDetail", 1)
    item["isShowLegend"] = item.get("isShowLegend", 1)
    item["isShowValue"] = item.get("isShowValue", 1)
    item["orderType"] = item.get("orderType", 0)
    item["ratioType"] = str(item.get("ratioType") or "0")
    item["analysisType"] = str(item.get("analysisType") or "0")
    item["parentID"] = item.get("parentID") or ""
    item["formula"] = item.get("formula") or ""
    item["isVisible"] = item.get("isVisible", 1)
    item["status"] = item.get("status", 1)
    return item


def _retain_measure_fields(chart: Mapping[str, Any]) -> list[dict[str, Any]]:
    measure_fields: list[dict[str, Any]] = []
    for measure in chart.get("measureFields") or []:
        item = copy.deepcopy(dict(measure))
        if "yAxisIndex" not in item:
            item["yAxisIndex"] = 1
        if "fieldID" not in item and item.get("fieldId"):
            item["fieldID"] = item["fieldId"]
        if "fieldId" not in item and item.get("fieldID"):
            item["fieldId"] = item["fieldID"]
        measure_fields.append(item)
    return measure_fields


def build_update_stat_view_body(
    runner: Any,
    view_id: str,
    *,
    dimension_field: Mapping[str, Any] | None = None,
    filter_field: Mapping[str, Any] | None = None,
    measure_field: Mapping[str, Any] | None = None,
    keep_source_filters: bool = False,
) -> dict[str, Any]:
    """Assemble CRM updateStatView body from current chart + optional overrides."""
    chart = _value(
        runner.http_api.call(
            "fs_bi_stat.stat_edit.get_chart_config",
            body={
                "id": view_id,
                "isView": 1,
                "type": "edit",
                "querySource": "UNKNOWN",
                "cacheTime": 0,
                "refresh": 1,
            },
        )
    )
    filters = _value(
        runner.http_api.call(
            "fs_bi_stat.stat_edit.get_filters_result",
            body={"id": view_id, "isView": 1},
        )
    )
    crm = _value(
        runner.http_api.call(
            "fs_bi_crm.stat_edit.get_stat_view",
            body={"id": view_id},
        )
    )
    base = copy.deepcopy(crm)
    base.update(
        {
            "viewID": view_id,
            "schemaID": chart.get("schemaId"),
            "chartUserDefined": chart.get("userDefined"),
            "templateID": chart.get("templateId", ""),
            "topNum": chart.get("topNum", 0),
            "isShowDimension": chart.get("isShowDimension", 0),
            "timeZone": chart.get("timeZone"),
            "ratioDateFieldId": chart.get("ratioDateFieldId"),
            "authType": chart.get("authType"),
            "updateTime": chart.get("updateTime"),
            "currentTime": chart.get("currentTime"),
        }
    )
    dimension_fields = list(chart.get("dimensionFields") or [])
    if dimension_field is not None:
        dimension_fields = [_normalize_dimension_field(dimension_field)]
    if measure_field is not None:
        shell = list(chart.get("measureFields") or [])
        if not shell:
            raise ContractError(
                f"chart {view_id!r} has empty measureFields; cannot retarget measure"
            )
        measure_fields = [_normalize_measure_field(shell[0], measure_field)]
    else:
        measure_fields = _retain_measure_fields(chart)
    if filter_field is not None and not keep_source_filters:
        filter_lists = [{"filters": [_normalize_filter_field(filter_field)]}]
    else:
        filter_lists = list(filters.get("filterLists") or [])
    option_ids = _default_filter_option_ids(crm, chart, filters)
    if not option_ids:
        raise ContractError(
            f"chart {view_id!r} is missing defaultFilterOptionIDs required by updateStatView"
        )
    return {
        "axisData": {
            "chartType": chart.get("chartType"),
            "dimensionFields": dimension_fields,
            "measureFieldList": measure_fields,
            "dimensionAttrFields": chart.get("dimensionAttrFields") or [],
            "schemaId": chart.get("schemaId"),
            "topNum": chart.get("topNum", 0),
            "isShowDimension": chart.get("isShowDimension", 0),
        },
        "filterLists": filter_lists,
        "secondaryFilterLists": filters.get("secondaryFilterLists") or [],
        "defaultFilterOptionIDs": option_ids,
        "statLayoutInfo": chart.get("layout"),
        "statMobileLayoutInfo": chart.get("mobileLayout"),
        "statViewBaseInfo": base,
        "drillRouteFieldLists": [],
        "drillDownPath": chart.get("drillDownPath", "-1"),
    }


def _summarize_fields(items: list[Mapping[str, Any]] | None) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for item in items or []:
        rows.append(
            {
                "field_id": str(item.get("fieldId") or item.get("fieldID") or ""),
                "field_name": str(item.get("fieldName") or item.get("dbFieldName") or ""),
            }
        )
    return rows


def bind_stat_chart_config(
    runner: Any,
    *,
    chart_view_id: str,
    schema_id: str,
    dimension_field_id: str = "",
    filter_field_id: str = "",
    measure_field_id: str = "",
) -> dict[str, Any]:
    """Differentiate a cloned chart with case-owned dimension/measure/filter."""
    view_id = str(chart_view_id or "").strip()
    schema = str(schema_id or "").strip()
    if not view_id:
        raise ContractError("bind_stat_chart_config requires chart_view_id")
    if not schema:
        raise ContractError("bind_stat_chart_config requires schema_id")
    dim_id = str(dimension_field_id or "").strip()
    filter_id = str(filter_field_id or "").strip()
    measure_id = str(measure_field_id or "").strip()
    if not dim_id and not filter_id and not measure_id:
        return {
            "status": "skipped",
            "reason": "no_dimension_measure_or_filter_binding",
            "chart_view_id": view_id,
        }

    dimension_field = _find_field_dto(runner, schema, dim_id) if dim_id else None
    filter_field = _find_field_dto(runner, schema, filter_id) if filter_id else None
    measure_field = _find_field_dto(runner, schema, measure_id) if measure_id else None
    body = build_update_stat_view_body(
        runner,
        view_id,
        dimension_field=dimension_field,
        filter_field=filter_field,
        measure_field=measure_field,
    )
    updated = runner.http_client.post(
        "/FHH/EM1HBICRM/statEditController/updateStatView",
        json_body=body,
    )
    updated_body = updated.body if isinstance(updated.body, Mapping) else {}
    result = updated_body.get("Result") if isinstance(updated_body.get("Result"), Mapping) else {}
    if result.get("FailureCode") not in (None, 0):
        raise ContractError(f"updateStatView failed for {view_id}: {updated_body}")

    chart = _value(
        runner.http_api.call(
            "fs_bi_stat.stat_edit.get_chart_config",
            body={
                "id": view_id,
                "isView": 1,
                "type": "edit",
                "querySource": "UNKNOWN",
                "cacheTime": 0,
                "refresh": 1,
            },
        )
    )
    filters = _value(
        runner.http_api.call(
            "fs_bi_stat.stat_edit.get_filters_result",
            body={"id": view_id, "isView": 1},
        )
    )
    dims = _summarize_fields(list(chart.get("dimensionFields") or []))
    measures = _summarize_fields(list(chart.get("measureFields") or []))
    filter_rows: list[dict[str, str]] = []
    for group in filters.get("filterLists") or []:
        if not isinstance(group, Mapping):
            continue
        filter_rows.extend(_summarize_fields(list(group.get("filters") or [])))

    if measure_id:
        actual_measure_ids = [row["field_id"] for row in measures]
        if measure_id not in actual_measure_ids:
            raise ContractError(
                "measure bind did not stick on updateStatView readback: "
                f"wanted {measure_id!r}, got {measures!r}. "
                "Source chart measure shell may not support field retarget "
                "(use 客户统计-指定层级 / replaceable measure source)."
            )

    measure_status = "replaced" if measure_id else "source_retained"
    return {
        "status": "bound",
        "chart_view_id": view_id,
        "schema_id": schema,
        "chart_type": chart.get("chartType"),
        "dimensions": dims,
        "measures": measures,
        "filters": filter_rows,
        "measure_bind_status": measure_status,
        "requested": {
            "dimension_field_id": dim_id,
            "measure_field_id": measure_id,
            "filter_field_id": filter_id,
        },
    }


def bind_stat_chart_config_action(
    runner: Any, step: Mapping[str, Any], context: dict[str, Any]
) -> ApiResponse:
    inputs = step.get("inputs") if isinstance(step.get("inputs"), Mapping) else {}
    payload = bind_stat_chart_config(
        runner,
        chart_view_id=str(inputs.get("chart_view_id") or context.get("chart_view_id") or ""),
        schema_id=str(inputs.get("schema_id") or context.get("schema_id") or ""),
        dimension_field_id=str(
            inputs.get("dimension_field_id") or context.get("dimension_field_id") or ""
        ),
        filter_field_id=str(
            inputs.get("filter_field_id") or context.get("filter_field_id") or ""
        ),
        measure_field_id=str(
            inputs.get("measure_field_id") or context.get("measure_field_id") or ""
        ),
    )
    context["chart_config_bind"] = payload
    return ApiResponse(status_code=200, body={"Result": {"FailureCode": 0}, "Value": payload})


def chart_action_handlers() -> dict[str, Callable[..., Any]]:
    return {"bind_stat_chart_config": bind_stat_chart_config_action}
