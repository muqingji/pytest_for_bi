from __future__ import annotations

import json
from pathlib import Path

import pytest

from qa_agents.env_inventory import (
    enrich_plan_with_inventory,
    resolve_variables_from_inventory,
    validate_inventory_snapshot,
)
from qa_agents.errors import ContractError, SecurityPolicyError


INVENTORY = {
    "schema_version": "bi-environment-inventory/1.0",
    "environment": "112",
    "provenance": {
        "captured_at": "2026-08-20T00:00:00+08:00",
        "probe_refs": "env-112-inventory-v1",
    },
    "variables": {"schema_id": "BI_inv0001"},
    "schemas": [
        {
            "schema_id": "BI_inv0001",
            "schema_name": "销售订单统计",
            "schema_object": "biz_sales_order",
            "describe_api_name": "SalesOrderObj",
            "fields": [
                {
                    "field_id": "BI_fld0001",
                    "field_name": "金额",
                    "db_field_name": "amount",
                    "field_type": "Number",
                },
                {
                    "field_id": "BI_fld0002",
                    "field_name": "日期",
                    "db_field_name": "create_time",
                    "field_type": "Date",
                },
            ],
        }
    ],
}


def test_validate_inventory_snapshot_rejects_secrets() -> None:
    bad = json.loads(json.dumps(INVENTORY))
    bad["variables"]["token"] = "AKIA..."
    with pytest.raises(SecurityPolicyError, match="secret"):
        validate_inventory_snapshot(bad)


def test_validate_inventory_snapshot_requires_provenance() -> None:
    bad = json.loads(json.dumps(INVENTORY))
    bad["provenance"] = {}
    with pytest.raises(ContractError, match="provenance"):
        validate_inventory_snapshot(bad)


def test_resolve_variables_from_inventory_resolves_exact_and_field_variables() -> None:
    variables = {
        "schema_id": "{{ schema_id }}",
        "schema_object": "{{ schema_object }}",
        "amount_field_id": "{{ amount_field_id }}",
        "amount_db_field": "{{ amount_db_field }}",
        "amount_field_type": "{{ amount_field_type }}",
        "unknown_var": "{{ unknown_var }}",
    }
    resolved, modes = resolve_variables_from_inventory(variables, INVENTORY)
    assert resolved["schema_id"] == "BI_inv0001"
    assert resolved["schema_object"] == "biz_sales_order"
    assert resolved["amount_field_id"] == "BI_fld0001"
    assert resolved["amount_db_field"] == "amount"
    assert resolved["amount_field_type"] == "Number"
    assert modes["schema_id"] == "inventory"
    assert modes["amount_field_id"] == "inventory"
    assert modes["unknown_var"] == "runtime_required"


def test_enrich_plan_with_inventory_renders_resources_and_reports_modes() -> None:
    plan = {
        "schema_version": "test-data-plan/1.0",
        "environment": "112",
        "namespace": "qa-autonomous-data-003",
        "planning_mode": "autonomous",
        "case_plans": [
            {
                "case_id": "CASE-INV-001",
                "required_scene": "",
                "variables": {
                    "schema_id": "{{ schema_id }}",
                    "amount_field_id": "{{ amount_field_id }}",
                },
                "resources": [
                    {
                        "resource_key": "fixture",
                        "resource_type": "aggregate_metric",
                        "lifecycle_mode": "create",
                        "setup": {
                            "request": {
                                "api": "fs_bi_stat.agg_rule.add_new_agg_rule",
                                "json": {"schemaId": "{{ schema_id }}", "fieldId": "{{ amount_field_id }}"},
                            }
                        },
                        "readiness": [],
                        "cleanup": {},
                        "residue_checks": [],
                    }
                ],
            }
        ],
    }
    enriched = enrich_plan_with_inventory(plan, INVENTORY)
    case_plan = enriched["case_plans"][0]
    assert case_plan["variables"]["schema_id"] == "BI_inv0001"
    setup_json = case_plan["resources"][0]["setup"]["request"]["json"]
    assert setup_json == {"schemaId": "BI_inv0001", "fieldId": "BI_fld0001"}
    resolution = enriched["inventory_resolution"]
    assert resolution["environment"] == "112"
    assert resolution["runtime_required"] == []
    modes = resolution["case_resolutions"][0]["modes"]
    assert modes["schema_id"] == "inventory"
    assert modes["amount_field_id"] == "inventory"
