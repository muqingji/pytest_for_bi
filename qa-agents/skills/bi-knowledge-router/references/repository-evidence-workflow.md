# Repository Evidence Workflow

1. Select the repository entry in `qa-agents/knowledge/bi-repository-knowledge-catalog.json` by the Skill's `source_id`.
2. Compare checkout `HEAD` with `verified_commit`. A mismatch is stale and cannot establish current behavior until the profile is refreshed.
3. Read repository guidance and build metadata, then inspect the entry anchors. Follow symbols through callers, implementations, DTOs, error mapping and relevant tests.
4. Distinguish production code from tests, comments, generated files and legacy/dead paths. Confirm cross-service claims in each owning repository.
5. Return repository ID, commit, path and symbol for each fact. Mark inferences and runtime unknowns.
6. Product repositories are immutable: never edit, commit, checkout, reset, clean or push them.
