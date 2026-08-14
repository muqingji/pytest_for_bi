"""Fail-closed compiler for retained statistical chart setup plans."""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Mapping

from .errors import ContractError

_HASH = re.compile(r"sha256:[0-9a-f]{64}")


def canonical_hash(value: object) -> str:
    raw = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode()).hexdigest()


def compile_chart_resource(
    *, requirement_name: str, view_name: str, namespace: str,
    category_id: str, folder_query_operation: str, folder_response_hash: str,
    schema_id: str, axis_data: Mapping[str, Any], layout: Mapping[str, Any],
    identity: Mapping[str, Any], filters: list[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Compile CreateStatViewArg without inventing directory or field metadata."""
    if not requirement_name or not view_name or not namespace:
        raise ContractError("chart semantic names and namespace are required")
    if not category_id or not folder_query_operation or not _HASH.fullmatch(folder_response_hash):
        raise ContractError("chart requires live folder operation, category id and response hash")
    if not schema_id or not axis_data.get("measureFieldList"):
        raise ContractError("chart requires live schema and at least one measure")
    if axis_data.get("chartType") not in {"line", "bar", "pie", "table", "funnel", "doubley",
                                          "card", "gauge", "maphot", "mapbubble", "stackbar",
                                          "stackline", "heatmap", "pivottable", "scatter",
                                          "worldbubble", "cvrfunnel", "worldhot", "radar",
                                          "treemap", "butterfly"}:
        raise ContractError("chartType is not a source-backed ChartTypeEnum value")
    if any(item.get("yAxisIndex") not in {1, 2} for item in axis_data["measureFieldList"]):
        raise ContractError("every chart measure requires a source-backed yAxisIndex")
    template_id = str(identity.get("templateID", ""))
    if not template_id:
        raise ContractError("formal CRM chart creation requires a live templateID")
    body = {
        "axisData": dict(axis_data), "filterLists": list(filters or []),
        "defaultFilterOptionIDs": [], "statLayoutInfo": dict(layout),
        "drillRouteFieldLists": [], "drillDownPath": "-1",
        "statViewBaseInfo": {
            "categoryID": category_id, "description": f"需求：{requirement_name}",
            "viewName": view_name, "viewID": "", "schemaID": schema_id,
            "templateID": template_id, "chartUserDefined": 1,
            "timeZone": identity.get("timeZone"),
            "userOwnerList": identity.get("userOwnerList", []),
        },
    }
    if "permType" in identity:
        body["statViewBaseInfo"]["permType"] = identity["permType"]
    if not body["statViewBaseInfo"]["timeZone"]:
        raise ContractError("chart timezone must come from current session")
    if body["statViewBaseInfo"].get("permType") == 1 and not body["statViewBaseInfo"]["userOwnerList"]:
        raise ContractError("private chart permission requires live owner metadata")
    config_hash = canonical_hash(body)
    return {
        "resource_key": "stat_chart", "resource_type": "stat_chart",
        "resource_id_variable": "chart_view_id", "retention_mode": "retain",
        "ownership_namespace": namespace, "display_name": view_name,
        "source_field_type": "chart_clone",
        "source_field_type": "chart", "asset_folder_name": requirement_name,
        "folder_binding": {"folder_name": requirement_name, "category_id": category_id,
                           "folder_query_operation": folder_query_operation,
                           "folder_response_hash": folder_response_hash},
        "configuration_hash": config_hash,
        "setup": {"request": {"api": "fs_bi_crm.stat_create.create_stat_view",
                               "json": body},
                  "extract": {"chart_view_id": "viewID"}},
        "readiness": [{"request": {"api": "fs_bi_stat.stat_edit.get_chart_config",
                                      "json": {"id": "{{ chart_view_id }}", "isView": 1,
                                               "type": "edit", "querySource": "UNKNOWN",
                                               "cacheTime": 0, "refresh": 1}}}],
    }


def compile_chart_clone_resource(
    *, requirement_name: str, view_name: str, namespace: str, category_id: str,
    folder_query_operation: str, folder_response_hash: str, source_view_id: str,
    source_config_hash: str,
) -> dict[str, Any]:
    """Compile the verified CRM copy/move/rename lifecycle for a complete chart."""
    if not all((requirement_name, view_name, namespace, category_id, source_view_id)):
        raise ContractError("chart clone semantic names, category and source view are required")
    if not _HASH.fullmatch(folder_response_hash) or not _HASH.fullmatch(source_config_hash):
        raise ContractError("chart clone requires live folder and source configuration hashes")
    return {
        "resource_key": "stat_chart", "resource_type": "stat_chart",
        "resource_id_variable": "chart_view_id", "retention_mode": "retain",
        "ownership_namespace": namespace, "display_name": view_name,
        "asset_folder_name": requirement_name,
        "folder_binding": {"folder_name": requirement_name, "category_id": category_id,
                           "folder_query_operation": folder_query_operation,
                           "folder_response_hash": folder_response_hash},
        "source_provenance": {"source_view_id": source_view_id,
                              "source_config_hash": source_config_hash},
        "configuration_hash": canonical_hash({"source": source_config_hash,
                                                "category_id": category_id,
                                                "view_name": view_name}),
        "setup": {"request": {"api": "fs_bi_crm.stat_create.copy_stat_view",
                               "json": {"statViewBaseInfo": {"viewID": source_view_id,
                                                              "isChange": 0}}},
                  "extract": {"chart_view_id": "viewID"}},
        "post_setup": [
            {"request": {"api": "fs_bi_crm.rpt_view_display.rename_rpt_view",
                         "json": {"viewID": "{{ chart_view_id }}", "viewName": view_name,
                                  "description": f"需求：{requirement_name}", "isCategory": 2}}},
            {"request": {"api": "fs_bi_crm.stat_edit.get_stat_view",
                         "json": {"id": "{{ chart_view_id }}"}},
             "extract": {"chart_origin_category_id": "Value.categoryID"}},
            {"request": {"api": "fs_bi_crm.rpt_view_display.move_rpt_view",
                         "json": {"targetCategoryID": category_id,
                                  "originCategoryID": "{{ chart_origin_category_id }}",
                                  "viewID": "{{ chart_view_id }}", "isCategory": 2}},
             "condition": {"left": "{{ chart_origin_category_id }}",
                           "operator": "not_equals", "right": category_id}},
        ],
        "readiness": [
            {"request": {"api": "fs_bi_crm.stat_edit.get_stat_view",
                         "json": {"id": "{{ chart_view_id }}"}}},
            {"request": {"api": "fs_bi_stat.stat_edit.get_chart_config",
                         "json": {"id": "{{ chart_view_id }}", "isView": 1,
                                  "type": "edit", "querySource": "UNKNOWN",
                                  "cacheTime": 0, "refresh": 1}}},
        ],
    }
