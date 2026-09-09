#!/usr/bin/env python3
"""CLI for the registry-driven active workflow monitor."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import time

from qa_agents.workflow_monitor import (
    check_heartbeat,
    discover_workflows,
    monitor_once,
    register_workflow,
    resume_workflow,
    watchdog_status,
)


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser()
    result.add_argument("--registry", type=Path, required=True)
    subparsers = result.add_subparsers(dest="command", required=True)
    register = subparsers.add_parser("register")
    register.add_argument("--config", type=Path, required=True)
    register.add_argument("--artifact-root", type=Path, required=True)
    register.add_argument("--spec", type=Path, required=True)
    scan = subparsers.add_parser("scan")
    scan.add_argument("--watch", action="store_true")
    scan.add_argument("--interval", type=int, default=30)
    scan.add_argument("--no-discover", action="store_true")
    watchdog = subparsers.add_parser("watchdog")
    watchdog.add_argument("--max-age", type=int, default=90)
    watchdog.add_argument("--kickstart-label")
    resume = subparsers.add_parser("resume")
    resume.add_argument("--run-id", required=True)
    resume.add_argument("--acknowledge-accuracy-violation", action="store_true")
    return result


def main() -> int:
    args = parser().parse_args()
    repo_root = Path(__file__).resolve().parents[2]
    if args.command == "register":
        value = register_workflow(
            args.registry, args.config, args.artifact_root, args.spec, repo_root
        )
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return 0
    if args.command == "resume":
        value = resume_workflow(
            args.registry,
            args.run_id,
            acknowledge_accuracy_violation=args.acknowledge_accuracy_violation,
        )
        print(json.dumps(value, ensure_ascii=False, indent=2))
        return 0
    if args.command == "watchdog":
        value = watchdog_status(args.registry, max_age_seconds=args.max_age)
        if value.get("status") == "unhealthy" and args.kickstart_label:
            import subprocess
            completed = subprocess.run(
                ["launchctl", "kickstart", "-k", f"gui/{__import__('os').getuid()}/{args.kickstart_label}"],
                text=True, capture_output=True, check=False,
            )
            value["recovery"] = {"action": "kickstart", "returncode": completed.returncode}
        if value.get("status") == "unhealthy":
            print(json.dumps(value, ensure_ascii=False))
            return 2
        print(json.dumps(value, ensure_ascii=False))
        return 0
    sync_script = repo_root / "qa-agents/scripts/sync_eight_card_progress.py"
    while True:
        discovery = {"registered": [], "rejected": []}
        if not args.no_discover:
            discovery = discover_workflows(args.registry, repo_root)
        value = monitor_once(args.registry, repo_root, sync_script)
        value["discovery"] = discovery
        print(json.dumps(value, ensure_ascii=False))
        if not args.watch:
            return 0
        time.sleep(max(10, args.interval))


if __name__ == "__main__":
    raise SystemExit(main())
