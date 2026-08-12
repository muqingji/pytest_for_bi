#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

from qa_agents.knowledge_packet_builder import build_test_knowledge_packet


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--compiled-cases", type=Path, required=True)
    parser.add_argument("--openapi", type=Path, required=True)
    parser.add_argument("--capability-catalog", type=Path, required=True)
    parser.add_argument("--knowledge-snapshot-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    load = lambda path: json.loads(path.read_text(encoding="utf-8"))
    packet = build_test_knowledge_packet(
        load(args.compiled_cases), load(args.openapi), load(args.capability_catalog),
        knowledge_snapshot_id=args.knowledge_snapshot_id,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(packet, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
