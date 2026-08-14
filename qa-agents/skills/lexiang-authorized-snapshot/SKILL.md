---
name: lexiang-authorized-snapshot
description: Query current Lexiang BI knowledge in real time by fuzzy keyword and retrieve only explicitly selected documents. Use for BI feature notes, FAQs, operating knowledge, and historical product context; never bulk-capture category bodies.
---

# Lexiang Real-Time Knowledge

Verify `authorized-product-browser-session`, then run `scripts/realtime_query.js search KEYWORD`. The search reads current category indexes and returns only ranked document ID, title, summary, update time, category and source URL.

Run `scripts/realtime_query.js detail DOCUMENT_ID` only after a search result is selected for the active requirement. Bind conclusions to returned URL, document ID, update time, retrieval time and content hash. Never enumerate all bodies or persist a full-category corpus.
