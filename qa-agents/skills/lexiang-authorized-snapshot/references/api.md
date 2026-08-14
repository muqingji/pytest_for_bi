# Lexiang Read-Only API

Current same-origin API patterns:

```text
GET /api/v1/docs?filter=category&category_id={category_id}&limit=100&page={page}
GET /api/v1/docs/{node_id}?lazy_load=1&increment=1
```

Search reads only index fields: node ID, target ID, title, summary and edit metadata. Detail reads one explicitly selected node. Do not enumerate category bodies.

The requests must execute inside an already authenticated `lexiangla.com` page. Authentication data is never returned to the collector.
