#!/usr/bin/env python3
"""Construct differentiated 112 chart test data (dim/measure/filter bind).

Creates case-owned aggregate metrics / custom dimensions / stat charts under a
shared namespace prefix, then binds each chart so 维度 / 指标 / 筛选 differ.

Usage:
  PYTHONPATH=src:qa-agents/src .venv/bin/python qa-agents/scripts/construct_112_diff_charts.py
  PYTHONPATH=src:qa-agents/src .venv/bin/python qa-agents/scripts/construct_112_diff_charts.py --prefix qa-diff-lss-demo
"""
from __future__ import annotations

import argparse
import time
import json
import os
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
os.chdir(ROOT)
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "qa-agents" / "src")]

from framework.api.catalog import HttpApiCatalog
from framework.auth import authenticate_fxiaoke, validate_credential_source
from framework.clients.database import DatabaseClient
from framework.clients.http import HttpClient
from framework.clients.rpc import RpcClient
from framework.config.environment import EnvironmentConfig, project_root
from framework.core.runner import CaseRunner
from qa_agents.chart_config import chart_action_handlers
from qa_agents.data_planning import compile_resource_plan
from qa_agents.test_data import bind_plan_to_case, validate_test_data_plan

OUT_DIR = ROOT / "qa-agents/runs/pilot-001/test-data"
CATALOG = ROOT / "qa-agents/knowledge/bi-data-capability-catalog.json"
POLICY = ROOT / "qa-agents/policies/test-data-policy.json"
A22 = OUT_DIR / "artifacts/a22-test-data-intent.json"
LOG = OUT_DIR / "construct_112_diff_charts.log"


def log(msg: str) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    line = f"{datetime.now().strftime('%H:%M:%S')} {msg}"
    with LOG.open("a", encoding="utf-8") as fh:
        fh.write(line + "\n")
    print(line, flush=True)


def make_runner() -> CaseRunner:
    validate_credential_source("112")
    env = EnvironmentConfig.load("112", root=ROOT)
    http = HttpClient(
        base_url=env.get("http.base_url", ""),
        headers=env.get("http.headers", {}),
        timeout=env.get("http.timeout", 60.0),
        verify=env.get("http.verify", True),
    )
    authenticate_fxiaoke(env, http)
    return CaseRunner(
        env,
        http,
        RpcClient(env.get("rpc", {}), http),
        DatabaseClient(env.get("databases", {})),
        HttpApiCatalog.load(project_root() / "idl" / "http"),
        action_handlers=chart_action_handlers(),
    )


def summarize_chart(runner: CaseRunner, view_id: str) -> dict:
    chart = runner.http_api.call(
        "fs_bi_stat.stat_edit.get_chart_config",
        body={
            "id": view_id,
            "isView": 1,
            "type": "edit",
            "querySource": "UNKNOWN",
            "cacheTime": 0,
            "refresh": 1,
        },
    ).body
    filters = runner.http_api.call(
        "fs_bi_stat.stat_edit.get_filters_result",
        body={"id": view_id, "isView": 1},
    ).body
    crm = runner.http_api.call(
        "fs_bi_crm.stat_edit.get_stat_view", body={"id": view_id}
    ).body
    ch = (chart or {}).get("Value") or {}
    fl = (filters or {}).get("Value") or {}
    cr = (crm or {}).get("Value") or {}
    dims = [
        {
            "name": item.get("fieldName") or item.get("dbFieldName"),
            "id": item.get("fieldId") or item.get("fieldID"),
        }
        for item in ch.get("dimensionFields") or []
    ]
    meas = [
        {
            "name": item.get("fieldName") or item.get("dbFieldName"),
            "id": item.get("fieldId") or item.get("fieldID"),
        }
        for item in ch.get("measureFields") or []
    ]
    filt = []
    for group in fl.get("filterLists") or []:
        for item in group.get("filters") or []:
            filt.append(
                {
                    "name": item.get("fieldName") or item.get("dbFieldName"),
                    "id": item.get("fieldId") or item.get("fieldID"),
                    "aggDimType": item.get("aggDimType"),
                }
            )
    return {
        "view_id": view_id,
        "view_name": ch.get("viewName") or cr.get("viewName"),
        "schema_id": ch.get("schemaId"),
        "category_id": cr.get("categoryID") or cr.get("categoryId"),
        "chart_type": ch.get("chartType"),
        "dimensions": dims,
        "measures": meas,
        "filters": filt,
        "chart_fc": ((chart or {}).get("Result") or {}).get("FailureCode"),
    }


def extract_created(context: dict, resources: list[dict], namespace: str) -> list[dict]:
    created = []
    for resource in resources:
        if resource.get("lifecycle_mode") == "existing_read_only":
            continue
        id_var = str(resource.get("resource_id_variable") or "")
        rid = context.get(id_var)
        if not rid:
            continue
        display = str(resource.get("display_name") or resource.get("resource_key") or id_var)
        created.append(
            {
                "resource_type": resource.get("resource_type"),
                "resource_key": resource.get("resource_key"),
                "resource_id_variable": id_var,
                "resource_id": rid,
                "display_name": display,
                "folder_id": resource.get("folder_binding", {}).get("category_id")
                if isinstance(resource.get("folder_binding"), dict)
                else None,
                "namespace": namespace,
            }
        )
    return created


def _fmt_fields(rows: list[dict] | tuple | list) -> str:
    parts = []
    for item in rows or []:
        if isinstance(item, dict):
            name = item.get("name") or ""
            fid = item.get("id") or ""
        elif isinstance(item, (list, tuple)) and len(item) >= 2:
            # signature stores (id, name)
            fid, name = item[0], item[1]
        else:
            continue
        parts.append(f"{name}({fid})" if fid else str(name))
    return "；".join(parts) if parts else "-"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--prefix",
        default="",
        help="namespace prefix; default qa-diff-lss-YYYYMMDDHHMMSS",
    )
    parser.add_argument(
        "--intent",
        default=str(A22),
        help="path to a22 test-data intent json",
    )
    args = parser.parse_args()
    if LOG.exists():
        LOG.write_text("")

    if not Path(args.intent).exists():
        log(f"missing intent: {args.intent}")
        return 2
    raw_intent = json.loads(Path(args.intent).read_text(encoding="utf-8"))
    intent_payload = raw_intent.get("payload") if isinstance(raw_intent.get("payload"), dict) else raw_intent
    intent = {
        "schema_version": intent_payload.get("schema_version") or "test-data-intent/1.0",
        "case_intents": intent_payload.get("case_intents") or [],
        "paused_cases": intent_payload.get("paused_cases") or [],
        "unresolved_requirements": intent_payload.get("unresolved_requirements") or [],
    }
    catalog = json.loads(CATALOG.read_text(encoding="utf-8"))
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    prefix = args.prefix.strip() or f"qa-diff-lss-{datetime.now().strftime('%Y%m%d%H%M%S')}"
    log(f"start prefix={prefix}")

    runner = make_runner()
    case_results = []
    created_assets = []

    case_intents = list(intent.get("case_intents") or [])
    for index, case_intent in enumerate(case_intents, start=1):
        case_id = str(case_intent.get("case_id") or f"CASE-{index}")
        ns = f"{prefix}-{index:02d}"
        log(f"==== [{index}/{len(case_intents)}] {case_id} ns={ns} ====")
        if index > 1:
            time.sleep(1.5)
        single_intent = {
            "schema_version": intent.get("schema_version") or "test-data-intent/1.0",
            "case_intents": [case_intent],
            "paused_cases": [],
            "unresolved_requirements": [],
        }
        context: dict = {}
        chart_summaries: list[dict] = []
        created: list[dict] = []
        errors: list[str] = []
        try:
            plan = compile_resource_plan(
                single_intent, catalog, environment="112", namespace=ns
            )
            validation = validate_test_data_plan(plan, policy)
            if not validation.get("valid"):
                raise RuntimeError(f"plan invalid: {validation}")
            case = {
                "id": case_id,
                "title": case_intent.get("requirement_name") or case_id,
                "name": case_intent.get("requirement_name") or case_id,
                "steps": [],
            }
            bound = bind_plan_to_case(case, plan)
            bound["steps"] = bound.get("steps") or []
            log(
                "setup="
                f"{len(bound.get('setup') or [])} prep={len(bound.get('preparation') or [])} "
                f"actions={[s.get('action') for s in bound.get('setup') or [] if s.get('action')]}"
            )
            context = {
                "config": runner.environment.values,
                "__case_name": bound.get("name", case_id),
                "__lifecycle__": {
                    "environment": "112",
                    "namespace": ns,
                    "setup": [],
                    "readiness": [],
                    "test": [],
                    "cleanup": [],
                    "residue": [],
                },
                **deepcopy(bound.get("variables") or {}),
                "namespace": ns,
            }
            preparation = bound.get("preparation") or []
            if preparation:
                for item in preparation:
                    phase = str(item.get("phase") or "")
                    if phase == "discovery":
                        phase = "readiness"
                    if phase not in {"setup", "readiness"}:
                        continue
                    runner._run_steps([item["step"]], context, phase)
            else:
                runner._run_steps(bound.get("setup") or [], context, "setup")
                runner._run_steps(bound.get("readiness") or [], context, "readiness")

            resources = list((plan["case_plans"][0] or {}).get("resources") or [])
            created = extract_created(context, resources, ns)
            for asset in created:
                if asset["resource_type"] == "stat_chart" and asset.get("resource_id"):
                    summary = summarize_chart(runner, str(asset["resource_id"]))
                    asset["chart_config"] = summary
                    asset["display_name"] = summary.get("view_name") or asset["display_name"]
                    asset["folder_id"] = summary.get("category_id") or asset.get("folder_id")
                    chart_summaries.append(summary)
                    log(
                        f"CHART {summary.get('view_name')} dims={summary.get('dimensions')} "
                        f"meas={summary.get('measures')} filt={summary.get('filters')}"
                    )
            status = "created"
            log(f"STATUS {status} created={len(created)}")
        except Exception as exc:  # noqa: BLE001 - construction report collects failures
            status = "failed"
            errors = [f"{type(exc).__name__}: {exc}"]
            created = []
            chart_summaries = []
            log(f"STATUS failed {errors[0][:300]}")
        created_assets.extend({"case_id": case_id, **asset} for asset in created)
        case_results.append(
            {
                "case_id": case_id,
                "title": case_intent.get("requirement_name") or case_id,
                "namespace": ns,
                "status": status,
                "resources": created,
                "errors": errors,
                "lifecycle": context.get("__lifecycle__") if context else {},
                "chart_summaries": chart_summaries,
            }
        )

    chart_sigs = []
    for asset in created_assets:
        if asset.get("resource_type") != "stat_chart":
            continue
        cfg = asset.get("chart_config") or {}
        sig = (
            tuple((d.get("id"), d.get("name")) for d in cfg.get("dimensions") or []),
            tuple((m.get("id"), m.get("name")) for m in cfg.get("measures") or []),
            tuple((f.get("id"), f.get("name")) for f in cfg.get("filters") or []),
        )
        chart_sigs.append(
            {"case_id": asset["case_id"], "name": cfg.get("view_name"), "sig": sig}
        )
    unique = len({json.dumps(item["sig"], ensure_ascii=False) for item in chart_sigs})
    unique_meas = len({json.dumps(item["sig"][1], ensure_ascii=False) for item in chart_sigs})
    unique_dims = len({json.dumps(item["sig"][0], ensure_ascii=False) for item in chart_sigs})
    unique_filt = len({json.dumps(item["sig"][2], ensure_ascii=False) for item in chart_sigs})
    split_ok = 0
    for item in chart_sigs:
        meas_ids = {row[0] for row in item["sig"][1] if row and row[0]}
        filt_ids = {row[0] for row in item["sig"][2] if row and row[0]}
        if meas_ids and filt_ids and meas_ids.isdisjoint(filt_ids):
            split_ok += 1

    report = {
        "schema_version": "112-demo-test-data-construction/1.0",
        "constructed_at": datetime.now(timezone.utc).isoformat(),
        "environment": "112",
        "enterprise_hint": "91863",
        "demo_namespace_prefix": prefix,
        "differentiation": {
            "mode": "dimension_measure_and_filter_bind",
            "source_view_id": "BI_6a87c6677d22e800077e4f2b",
            "source_view_name": "客户统计-指定层级",
            "measure_bind_status": "case_aggregate_metric",
            "filter_bind_status": "second_metric_or_rotated_native_filter",
            "dimension_bind_status": "custom_or_fallback_native_dim",
            "chart_signature_count": len(chart_sigs),
            "unique_chart_signature_count": unique,
            "unique_dimension_count": unique_dims,
            "unique_measure_count": unique_meas,
            "unique_filter_count": unique_filt,
            "in_chart_measure_filter_split_count": split_ok,
        },
        "how_to_find_in_ui": {
            "schema": "客户统计 BI_5bcebcdc3060e20001e79977",
            "chart_folder_id": "BI_6a7c47e1280b910007abf988",
            "name_prefix": prefix,
            "steps": [
                f"打开客户统计，搜索名称包含 {prefix} 的指标/自定义维度",
                f"打开目录 BI_6a7c47e1280b910007abf988，找统计图名称以 {prefix}- 开头",
                "逐个打开统计图，确认维度 / 指标 / 筛选均按 case 区分，且同图指标≠筛选",
            ],
        },
        "totals": {
            "cases": len(case_results),
            "created_cases": sum(1 for item in case_results if item["status"] == "created"),
            "failed_cases": sum(1 for item in case_results if item["status"] == "failed"),
            "created_assets": len(created_assets),
        },
        "created_assets": created_assets,
        "case_results": case_results,
        "chart_signatures": [
            {
                "case_id": item["case_id"],
                "name": item["name"],
                "dimensions": item["sig"][0],
                "measures": item["sig"][1],
                "filters": item["sig"][2],
            }
            for item in chart_sigs
        ],
    }

    ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    json_path = OUT_DIR / f"112-demo-construction-{ts}.json"
    latest_json = OUT_DIR / "112-demo-construction-latest.json"
    md_path = OUT_DIR / f"112-demo-construction-{ts}.md"
    latest_md = OUT_DIR / "112-demo-construction-latest.md"
    payload = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    json_path.write_text(payload, encoding="utf-8")
    latest_json.write_text(payload, encoding="utf-8")

    lines = [
        "# 112 实测测试数据构造报告（差异化统计图）",
        "",
        f"- 时间：`{report['constructed_at']}`",
        f"- 环境：`112` / 企业 `91863`",
        f"- 命名前缀：`{prefix}`",
        f"- 主题：客户统计 (`BI_5bcebcdc3060e20001e79977`)",
        f"- 统计图目录 ID：`BI_6a7c47e1280b910007abf988`",
        f"- 源图：`BI_6a87c6677d22e800077e4f2b`（客户统计-指定层级）",
        f"- 差异化：维度 + 指标(度量) + 筛选；同图指标/筛选拆分",
        f"- 结果：`{report['totals']['created_cases']}/{report['totals']['cases']}` case 成功，新建资产 `{report['totals']['created_assets']}`",
        f"- 统计图签名去重：`{unique}/{len(chart_sigs)}` unique",
        f"- 指标唯一：`{unique_meas}`；维度唯一：`{unique_dims}`；筛选唯一：`{unique_filt}`",
        f"- 同图指标≠筛选：`{split_ok}/{len(chart_sigs)}`",
        "",
        "## 你在 112 怎么找",
        f"1. 打开 **客户统计**，搜索名称包含 `{prefix}` 的指标/自定义维度",
        f"2. 打开目录 `BI_6a7c47e1280b910007abf988`，找统计图名称以 `{prefix}-` 开头",
        "3. 打开多个统计图对比：**维度**、**指标(度量)**、**筛选条件**；同图内指标应不等于筛选",
        "",
        "## Case 结果",
        "| Case | 状态 | Namespace | 新建资源数 |",
        "|---|---|---|---|",
    ]
    for item in case_results:
        lines.append(
            f"| `{item['case_id']}` | **{item['status']}** | `{item['namespace']}` | {len(item.get('resources') or [])} |"
        )
    lines.extend(
        [
            "",
            "## 统计图差异对照",
            "| Case | 统计图 | 维度 | 度量 | 筛选 |",
            "|---|---|---|---|---|",
        ]
    )
    for item in report["chart_signatures"]:
        lines.append(
            f"| `{item['case_id']}` | `{item['name']}` | {_fmt_fields(item['dimensions'])} | "
            f"{_fmt_fields(item['measures'])} | {_fmt_fields(item['filters'])} |"
        )
    lines.extend(["", "## 新建资产清单", "| Case | 类型 | 名称 | ID |", "|---|---|---|---|"])
    for asset in created_assets:
        lines.append(
            f"| `{asset['case_id']}` | {asset.get('resource_type')} | `{asset.get('display_name')}` | `{asset.get('resource_id')}` |"
        )
    md = "\n".join(lines) + "\n"
    md_path.write_text(md, encoding="utf-8")
    latest_md.write_text(md, encoding="utf-8")
    log(f"WROTE {json_path}")
    log(f"WROTE {md_path}")
    log(f"unique_chart_signatures={unique}/{len(chart_sigs)} split={split_ok}")
    log("DONE")
    return 0 if report["totals"]["failed_cases"] == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
