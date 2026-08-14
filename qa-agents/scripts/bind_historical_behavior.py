#!/usr/bin/env python3
"""Seal and bind a historical behavior packet into one A08 input bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from qa_agents.contracts import content_hash
from qa_agents.historical_behavior import validate_historical_behavior_packet


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--packet", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    bundle = json.loads(args.bundle.read_text(encoding="utf-8"))
    packet = json.loads(args.packet.read_text(encoding="utf-8"))
    packet["packet_hash"] = content_hash(packet)
    validate_historical_behavior_packet(packet)
    bundle["allowed_inputs"]["historical_behavior_packet"] = packet
    bundle["bundle_hash"] = content_hash(
        {key: value for key, value in bundle.items() if key != "bundle_hash"}
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(bundle, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"bundle_hash": bundle["bundle_hash"], "packet_hash": packet["packet_hash"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
