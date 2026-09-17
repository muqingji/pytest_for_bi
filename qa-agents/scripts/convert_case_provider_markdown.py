#!/usr/bin/env python3
"""Convert an fs-qa-knowledge Markdown Case table to the provider contract."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from qa_agents.case_provider import CaseProviderAdapter


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--markdown", type=Path, required=True)
    parser.add_argument("--provider-commit", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    provider_input = json.loads(args.input.read_text(encoding="utf-8"))
    markdown = args.markdown.read_text(encoding="utf-8")
    requirement_refs = [
        str(item["id"])
        for item in provider_input["requirements"]
        if isinstance(item, dict) and item.get("id")
    ]
    metadata = {
        "mode": "artifact_only",
        "provider_commit": args.provider_commit,
        "output_contract": "case-provider-output/1.0",
        "side_effects": [],
        "workflow_run_id": provider_input["workflow_run_id"],
        "source_snapshot_id": provider_input["source_snapshot_id"],
        "input_bundle_hash": provider_input["input_hash"],
        "source_format": "markdown_table",
        "source_refs": requirement_refs,
    }
    draft = CaseProviderAdapter().from_markdown_bundle(
        markdown,
        metadata,
        expected_commit=args.provider_commit,
    )
    value = {"metadata": metadata, "candidates": draft["candidates"]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(
        json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps({"output": str(args.output), "candidates": draft["candidate_count"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
