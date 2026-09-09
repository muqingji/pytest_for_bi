#!/usr/bin/env python3
"""Regenerate the deterministic server automation bundle for one workflow run."""

from __future__ import annotations

import argparse
from pathlib import Path

from qa_agents.server_automation import prepare_server_automation


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--artifact-dir", type=Path, required=True)
    parser.add_argument("--target", type=Path, required=True)
    parser.add_argument("--automation-policy", type=Path, required=True)
    parser.add_argument("--skill-registry", type=Path)
    args = parser.parse_args()
    artifacts = args.artifact_dir / "artifacts"
    prepare_server_automation(
        artifacts / "n15-execution-plan.json",
        artifacts / "n25-compiled-test-cases.json",
        args.automation_policy,
        args.target,
        args.artifact_dir,
        test_data_validation_path=artifacts / "n27-test-data-plan-validation.json",
        test_data_resource_plan_path=artifacts / "a22-test-data-plan.json",
        skill_registry_path=args.skill_registry,
    )


if __name__ == "__main__":
    main()
