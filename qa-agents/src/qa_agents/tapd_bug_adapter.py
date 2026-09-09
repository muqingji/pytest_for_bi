"""TAPD Bug registration adapter backed by the tapd-cli Skill."""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path
from typing import Any

from .contracts import ArtifactEnvelope, ArtifactStatus, EvidenceRef, Producer, content_hash
from .errors import ContractError, InputError
from .storage import ArtifactStore


def _load_local_env() -> None:
    """Load the repo-local secret file without overriding explicit env vars."""
    env_path = Path(__file__).resolve().parents[2] / ".env.local"
    if not env_path.is_file():
        return
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _load(path: Path) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ContractError(f"Invalid JSON: {path}") from exc
    if not isinstance(value, dict):
        raise ContractError(f"Expected JSON object: {path}")
    return value


def _workspace(config: dict[str, Any], story_url: str) -> str:
    configured = str(config.get("workspace_id", config.get("workspaceid", ""))).strip()
    import re
    found = re.search(r"(?:tapd_fe/|workspaceid[=/])([0-9]{6,})", story_url or "")
    if configured and found and configured != found.group(1):
        raise ContractError("Configured workspace_id conflicts with TAPD story URL")
    value = configured or (found.group(1) if found else "") or os.environ.get("TAPD_WORKSPACE_IDS", "").split(",")[0].strip()
    if not value:
        raise InputError("TAPD workspace_id is required")
    if not value.isdigit():
        raise ContractError("TAPD workspace_id must be numeric")
    return value


def _run_cli(args: list[str]) -> dict[str, Any]:
    try:
        proc = subprocess.run(["tapd-cli", *args], text=True, capture_output=True, timeout=60, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(str(exc)) from exc
    raw = proc.stdout.strip() or proc.stderr.strip()
    if proc.returncode != 0:
        raise RuntimeError(raw or f"tapd-cli exited {proc.returncode}")
    try:
        value = json.loads(raw)
        return value if isinstance(value, dict) else {"data": value}
    except json.JSONDecodeError:
        return {"raw": raw}


def _actual_user() -> str:
    """Resolve the human TAPD identity, never the token alias."""
    configured = os.environ.get("TAPD_USER_NAME", "").strip()
    if configured:
        return configured
    try:
        info = _run_cli(["user", "info"])
        data = info.get("data", info)
        if isinstance(data, dict):
            return str(data.get("name") or data.get("display_name") or data.get("username") or "").strip()
    except RuntimeError:
        pass
    return ""


def _id_url(value: dict[str, Any], workspace: str, bug_id: str) -> tuple[str, str]:
    data = value.get("data", value)
    if isinstance(data, dict) and isinstance(data.get("Bug"), dict):
        data = data["Bug"]
    if isinstance(data, list):
        data = data[0] if data else {}
    if isinstance(data, dict):
        bug_id = str(data.get("id") or data.get("bug_id") or bug_id)
        url = str(data.get("url") or data.get("link") or "")
    else:
        url = ""
    if not url and bug_id:
        url = f"https://www.tapd.cn/tapd_fe/{workspace}/bug/detail/{bug_id}"
    return bug_id, url


def register_tapd_bugs(review_artifact: Path, repository_config: Path, output_dir: Path, *, dry_run: bool = False) -> dict[str, Any]:
    _load_local_env()
    review = _load(review_artifact)
    payload = review.get("payload", {})
    if review.get("artifact_id") != "tapd-bug-review-request":
        raise ContractError("Expected tapd-bug-review-request Artifact")
    config = _load(repository_config)
    workspace = _workspace(config, str(payload.get("tapd_story_url", "")))
    story_id = str(payload.get("tapd_story_id", "")).strip()
    if not story_id:
        raise InputError("TAPD story_id is required for Bug association")
    reporter = _actual_user()
    if not reporter:
        raise InputError("Unable to resolve actual TAPD user; set TAPD_USER_NAME")
    iteration_id = str(payload.get("iteration_id", "")).strip()
    version = str(payload.get("version_report") or payload.get("story_version") or payload.get("version") or "").strip()
    if not iteration_id and not dry_run:
        try:
            story = _run_cli(["story", "list", f"workspaceid={workspace}", f"id={story_id}", "fields=id,iteration_id"])
            data = story.get("data", story)
            if isinstance(data, dict):
                rows = data.get("Story") or data.get("stories") or [data]
                if isinstance(rows, list) and rows:
                    iteration_id = str(rows[0].get("iteration_id") or "").strip()
        except RuntimeError:
            pass
    candidates = payload.get("bug_candidates", [])
    if not isinstance(candidates, list) or not candidates:
        raise ContractError("Bug review has no candidates")
    state_path = output_dir / "tapd-bug-adapter-state.json"
    state = _load(state_path) if state_path.exists() else {"schema_version": "tapd-bug-adapter-state/1.0", "entries": {}}
    entries = state.setdefault("entries", {})
    results, errors = [], []
    try:
        if not dry_run:
            fields = _run_cli(["bug", "fields", f"workspaceid={workspace}", "all_options=1"])
        else:
            fields = {"dry_run": True}
    except RuntimeError as exc:
        errors.append({"stage": "fields", "error": str(exc)})
        fields = {}
    for item in candidates:
        key = content_hash({"workflow_run_id": payload.get("workflow_run_id"), "candidate_id": item.get("id"), "fingerprint": item.get("fingerprint", "")})
        if key in entries and entries[key].get("status") == "created":
            results.append(entries[key]); continue
        trace_id = item.get("trace_id") or item.get("evidence", {}).get("trace_id") or ""
        description = "\n\n".join([
            "访问路径：https://www.ceshi112.com/XV/Home/Index#bi/list",
            "账户信息：租户 91863；账号/密码：请见本次执行凭证（敏感信息不写入代码）",
            "终端型号：",
            "前提条件：已登录 112 环境并打开可查看明细的统计图",
            "复现步骤：\n1、进入统计图查看明细页面\n2、执行结果集筛选查看明细请求\n3、观察接口响应中的错误参数",
            "实际结果：" + item["actual_problem"] + (f"；TraceID：{trace_id}" if trace_id else ""),
            "预期结果：" + item["expected_behavior"],
            "重现规律：可复现；每次在 112 环境按上述步骤执行均稳定出现该问题。",
            "备注说明：Case " + item["case_id"] + "；真实测试数据：" + "; ".join(f"{d['real_name']} (ID:{d.get('id') or '-'})" for d in item["test_data"]),
        ])
        # TAPD accepts the story association on bug creation; keeping it in the
        # same request makes the operation retryable without a second mutation.
        title = item.get("short_title") or item["bug_explanation"].split("：", 1)[-1][:80]
        args = ["bug", "add", f"workspaceid={workspace}", f"story_id={story_id}", f"title=【qa-agent】{title}", "priority_label=medium", "severity=serious", "custom_field_22=新功能", "platform=Server", "testphase=业务测试", f"current_owner={reporter}", f"reporter={reporter}", "custom_field_one=ceshi112", f"iteration_id={iteration_id}" if iteration_id else "", f"version_report={version}" if version else "", f"description={description}"]
        args = [arg for arg in args if arg]
        result = {"candidate_id": item.get("id"), "idempotency_key": key, "status": "planned" if dry_run else "failed"}
        if not dry_run and not errors:
            try:
                created = _run_cli(args)
                bug_id, url = _id_url(created, workspace, str(item.get("id", "")))
                # TAPD expects the URL's globally unique story id for the
                # relation endpoint; the short display id is not sufficient.
                story_relation_id = str(payload.get("tapd_story_global_id") or payload.get("tapd_story_url", "").rstrip("/").split("/")[-1])
                if story_relation_id:
                    _run_cli(["story", "link-bug", f"workspaceid={workspace}", f"story-id={story_relation_id}", f"bug-id={bug_id}"])
                    related = _run_cli(["bug", "related-stories", f"workspaceid={workspace}", f"bug-id={bug_id}"])
                    related_text = json.dumps(related, ensure_ascii=False)
                    if story_relation_id not in related_text:
                        raise RuntimeError("TAPD Bug created but demand relation was not confirmed")
                result.update({"status": "created", "tapd_bug_id": bug_id, "tapd_bug_url": url, "response": created})
            except RuntimeError as exc:
                result["error"] = str(exc); errors.append(result.copy())
        entries[key] = result; results.append(result)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    status = ArtifactStatus.COMPLETED if not errors and all(r["status"] in {"created", "planned"} for r in results) else ArtifactStatus.BLOCKED
    payload_out = {"schema_version": "tapd-bug-adapter-result/1.0", "workflow_run_id": payload.get("workflow_run_id"), "tapd_story_id": payload.get("tapd_story_id"), "workspace_id": workspace, "results": results, "errors": errors, "dry_run": dry_run, "retryable": bool(errors)}
    artifact = ArtifactEnvelope(workflow_run_id=str(payload.get("workflow_run_id", "")), workflow_mode=review.get("workflow_mode", "new_requirement"), artifact_id="tapd-bug-adapter-result", source_snapshot_id=str(payload.get("source_snapshot_id", "")), producer=Producer("TAPD_BUG_ADAPTER", profile_version="tapd-cli/0.2.3"), payload=payload_out, status=status, reason_code=None if status is ArtifactStatus.COMPLETED else "tapd_bug_registration_failed", evidence_refs=(EvidenceRef("artifact", "tapd-bug-review-request", review_artifact.name, review.get("artifact_hash")),))
    store = ArtifactStore(output_dir); store.write_artifact(artifact)
    return artifact.to_dict()
