# 112 Backend Quality Gate Report

Decision: **NOT READY**

The required terminal condition (`13/13 ready` and all tests passing) is not met. The latest full run produced 36 passed and 13 failed from 49 collected atoms. JUnit evidence is `backend-13-cases-junit-rerun.xml`.

## Confirmed 112 defects

1. PC-003 four-node multi-relation: the frozen contract requires `s307011536`; 112 returns the old generic `s307050002` when the newly created topology is visible. Immediate metadata topology visibility is also non-deterministic across sequential creates.
2. PC-004 What relation: a real metric based on `base_crmfeedrelation` returns system error `s207050405`; the frozen contract requires `s307011537`. WhatList returns the required code and the non-dynamic baseline does not return it.

## Missing controlled prerequisites

1. A configured 112 limited/no-permission identity is required for `all_four_without_permission`. Only one identity profile is currently available.
2. Allowlisted, environment-isolated fault hooks are required for parameter, timeout, and metadata error priority tests. Public-environment destructive injection is prohibited.
3. Immutable pre-change chart and pivot fixture IDs plus frozen configuration hashes are required for PC-006 and PC-007. A newly created asset cannot prove historical compatibility.

## Data lifecycle

Every created custom dimension or aggregate metric uses a unique `qa-*` namespace. Cleanup runs in `finally`, and the active custom-dimension list or schema field list is checked for absence after deletion. No test changes or writes were made to the fs-bi business repository.

## Required next external actions

1. Deploy the PC-003 and PC-004 contract behavior to 112, then rerun the generated suite.
2. Add a limited/no-permission 112 identity profile without exposing credentials in repository files or reports.
3. Provide an allowlisted test-only fault injection facility, isolated to the test namespace.
4. Register at least one pre-change chart and one pre-change pivot asset with stable IDs and frozen hashes.
