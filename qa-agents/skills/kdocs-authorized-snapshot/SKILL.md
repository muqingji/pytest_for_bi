---
name: kdocs-authorized-snapshot
description: Query the current authorized WPS/KDocs BI whitepaper in real time and retrieve only matching visible sections or slides. Use for current product rules and whitepaper evidence; never archive the full document.
---

# KDocs Real-Time Knowledge

Verify `authorized-product-browser-session`, then run `../lexiang-authorized-snapshot/scripts/realtime_query.js kdocs-search KEYWORD`. Return only matching snippets with document title, live URL and retrieval time. Read additional selected material only when the query identifies a relevant section/slide.

Do not store a full document snapshot. Bind evidence to the live document URL, title, retrieval time and snippet hash. Treat absent matches as insufficient evidence, not as proof that a rule does not exist.
