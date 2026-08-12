---
name: fxiaoke-help-snapshot
description: Recursively capture approved help.fxiaoke.com product-manual trees as evidence-bound JSON snapshots. Use when K01 needs anonymous official product documentation with same-origin link discovery and per-page hashes.
---

# Fxiaoke Help Snapshot

Run `scripts/capture_help.py URL --output PATH`. Follow only `https://help.fxiaoke.com/` links beneath the approved root path. Remove script/style/navigation text, deduplicate canonical URLs, and record failures explicitly.

This Skill is read-only. A partial crawl is not publishable. It never submits forms, follows authentication redirects, or accesses external hosts.
