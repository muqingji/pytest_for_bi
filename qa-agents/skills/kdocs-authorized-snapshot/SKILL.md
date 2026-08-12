---
name: kdocs-authorized-snapshot
description: Capture approved WPS/KDocs product documents as sanitized, evidence-bound JSON snapshots. Use for 365.kdocs.cn or kdocs.cn sources when K01 needs read-only product knowledge and an authenticated kdocs-cli or visible Chrome session is available.
---

# KDocs Authorized Snapshot

Run `scripts/capture.py URL --output PATH`. It tries authenticated `kdocs-cli` first, then a visible Chrome session through `browser_snapshot.py`. Never print or persist tokens, cookies, authorization headers, or browser profiles.

Accept only approved source URLs. Reject login/SSO pages, empty content, unsupported documents, and permission failures. Record the requested/effective URL, title, capture method, timestamp, content hash and sanitized text.

This Skill is read-only and artifact-only. A successful snapshot is still a K01 candidate; deterministic provenance and freshness validation must pass before publication.
