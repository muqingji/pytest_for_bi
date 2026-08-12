# Lexiang Read-Only API

Observed same-origin API patterns:

```text
GET /api/v1/teams/{team_id}/docs?filter=node&parent_id={category_id}&order=weight,-edited_at&limit=100&page={page}
GET /api/v1/teams/{team_id}/docs/{doc_id}?lazy_load=1&increment=1
```

Useful response fields are `target.id`, `target.title`, `target.summary`, `target.content`, `target.md_content`, and edit metadata. Response shapes may vary; the collector normalizes arrays from common `data/list/items/targets` envelopes and fails closed when no page identifiers are found.

The requests must execute inside an already authenticated `lexiangla.com` page. Authentication data is never returned to the collector.
