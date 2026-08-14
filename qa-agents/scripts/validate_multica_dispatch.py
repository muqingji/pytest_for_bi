#!/usr/bin/env python3
"""Fail closed when a Multica Agent instruction does not match its input mode."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import subprocess


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--agent-id", required=True)
    args = parser.parse_args()
    bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
    completed = subprocess.run(
        ["multica", "agent", "get", args.agent_id, "--output", "json"],
        check=True,
        capture_output=True,
        text=True,
    )
    agent = json.loads(completed.stdout)
    profile = str(bundle.get("profile_id", ""))
    version = str(bundle.get("profile_version", ""))
    instructions = str(agent.get("instructions", ""))
    errors = []
    if not profile or profile not in instructions:
        errors.append(f"instructions do not declare profile {profile}")
    if not version or f"v{version}" not in instructions:
        errors.append(f"instructions do not declare profile version v{version}")
    correction = version.startswith("1.2") or version.startswith("1.3")
    if correction and "correction_resolutions" not in instructions:
        errors.append("correction instructions do not require correction_resolutions")
    result = {
        "status": "blocked" if errors else "passed",
        "agent_id": args.agent_id,
        "profile_id": profile,
        "profile_version": version,
        "errors": errors,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 2 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
