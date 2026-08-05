---
name: sync-fs-bi-api
description: "Safely update generated BI OpenAPI IDL and Python API classes from the fs-bi business repository. Use when asked to fetch, refresh, regenerate, or synchronize fs-bi HTTP contracts or FsBiApi callers. Treat the business repository as immutable: never edit, commit, push, reset, clean, or checkout a business working tree."
---

# Sync FS BI API

Run the bundled deterministic script from the pytest repository root:

```bash
python3 .codex/skills/sync-fs-bi-api/scripts/sync_fs_bi_api.py
```

Pass `--ref <branch-or-tag>` when a non-default revision is requested. The default is `master`.

## Safety contract

- Use only `git clone --mirror`, `git fetch`, `git rev-parse`, and `git archive` against the business source.
- Never run write operations in `/Users/liushanshan/code/server/fs-bi` or another business working tree.
- Never push, commit, merge, rebase, reset, clean, or modify the remote repository.
- Extract the selected commit into a temporary directory and scan that snapshot.
- Write only generated IDL/API files in the current pytest repository.
- Stop on a dirty or invalid mirror instead of attempting repair with destructive commands.
- Do not invent CRM gateway prefixes. Emit callable modules only when the generator contains a route backed by source-code evidence.

## Verification

The script must complete generation, Python compilation, focused generator tests, and route checks. Report:

- resolved remote commit;
- generated module and endpoint counts;
- files changed in the pytest repository;
- test results;
- any module excluded because no code-backed external gateway route exists.

If SSH access fails, report the authentication/network error. Do not fall back to modifying an existing business working tree.
