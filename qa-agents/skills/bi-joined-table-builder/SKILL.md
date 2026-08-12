---
name: bi-joined-table-builder
description: Compile a retained BI joined-table asset from Case semantics and current 112 data-source metadata.
---

# BI joined-table builder

Status: verified on 112. Save, `queryArgDetail`, `queryLwtArg`, and field-detail operations
are registered. Folder identity is bound to live CRM Report evidence; topology may be
discovered from a current `queryArgDetail` response and must pass N27 before saving.

1. Compile a `JoinedTableIntent` into a new `LargeWideTableSaveArgs`; a captured successful request is evidence about the protocol, never a request template.
2. Require the requirement folder, Chinese semantic view name, join purpose, at least two resolved data sources, selected output fields, current identity and timezone. Select customer, sales order or sales record unless the Case requires another subject.
3. Discover every data source, field, relation endpoint and relation key from current metadata. Build `dataSources`, `relations`, `displayFields`, filters, totals and layout from the Case. Never substitute IDs into a captured payload.
4. Choose `joinType` deliberately: `left`, `inner`, `outer` or `vertical`. Record a reason tied to the Case and reject an unsupported topology rather than guessing a relation.
5. Build plaintext `LargeWideTableSaveArgs` with `saveType=0`, empty create-time IDs, the exact requirement-folder `categoryID`, `lwtArgs`, `queryLwtArg`, permissions and Chinese semantic names. Keep `queryLwtArg.id` and `lwtArgs.lwtId` empty for create.
6. Validate before save: data-source IDs are unique and live; every output/filter field belongs to a selected source; relation endpoints exist; relation keys have compatible types; the relation graph is connected unless vertical union is intended; permissions use the current identity; no captured ID or credential is present.
7. Execute `POST /FHH/EM1HBIDEV/lwt/m/save` through the controlled transport. The Agent emits plaintext intent and DTO only. `fx-encrypt`, `__bodykey`, `__fs_salt`, `x-fs-token`, cookies and trace headers are executor-owned.
8. Extract `viewID`, call `queryArgDetail`, and verify folder, name, data sources, relation graph, output fields, filters, join type, permissions and configuration hash. Register the retained asset only after query readiness succeeds.
9. Do not retry an ambiguous save until folder/name/configuration-hash discovery proves the asset is absent. Retain successful assets; do not delete them.
10. Historical compatibility uses an existing joined table discovered through a
read-only operation. Bind its live readback, normalized configuration SHA-256,
observed creation evidence, requirement baseline and evidence level. A newly saved
joined table is never historical evidence.

The compiler output must include placement and relation decisions with Case-based reasons so A14 can generate assertions against the actual constructed topology.
