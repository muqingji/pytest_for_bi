---
name: lexiang-authorized-snapshot
description: Capture approved lexiangla.com feature and FAQ categories through the user's visible authenticated Chrome session. Use when K01 needs a complete sanitized category index and page bodies without exporting browser cookies or credentials.
---

# Lexiang Authorized Snapshot

Run `scripts/capture_category.py URL --output PATH`. The script opens the approved category in visible Chrome, uses the page's authenticated same-origin context, enumerates category pages, fetches each page body, and emits a sanitized JSON snapshot.

Never read or copy browser profile files, cookies, local storage, authorization headers, passwords, or tokens. Reject login redirects, cross-origin results, empty categories and partial page failures. Do not silently publish partial captures.

Each page must retain doc ID, title, source URL, edit metadata when available, sanitized Markdown/text and SHA-256 hash. The category snapshot must contain page counts, failure counts and a manifest hash. K01 receives candidates only; Publisher validation remains mandatory.
