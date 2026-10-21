# Delivery and Validation Integration Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline and one fresh independent whole-branch review at the end.

**Goal:** Integrate delivery/validation capabilities while preserving the fork history and upstream reliability contracts, then open a PR.

**Architecture:** Merge the historical clone/savepoint/deploy-preview prefix; transport only impersonation, E2E, duplication and their required repairs. Retain shared guards and isolated tests; omit coupling to deferred features.

**Tech Stack:** Existing Python>=3.11 stdio MCP, pytest/coverage, Ruff/Mypy, Node20, optional Playwright.

**Spec:** docs/superpowers/specs/2026-10-21-delivery-validation-integration-design.md

## Global Constraints

No edits to the original checkout; no live Bubble action, remote merge or deployment. No GitHub Actions. Coverage floor45.3%. Preserve history/authorship. No new lint/type exclusions or framework migration.

### Task1: Historical clone/savepoint foundation

Files: execution/{node_edit,raw_node_edit,version_control,session_savepoint,deploy_preview}.py; server tools/schema/catalog/guide; tests/unit counterparts; tests/conftest.py.

- [ ] Run baseline raw-node/verifier/main-policy regressions; expected PASS.
- [ ] Merge19418ec without squash. Keep upstream types/null/supersession fixes and both test sets. Retain session/version guards before savepoint side effects.
- [ ] Run clone, version_control, session_savepoint, deploy_preview, node_edit and old reliability tests; fix only reproduced integration failures.
- [ ] Commit merge retaining both parents.

### Task2: Impersonation, E2E and duplication

Files: execution/{run_as,data_api,duplicate_element,editor_user_lookup}.py; e2e package; core/config.py; harness visual capture; server tools/schema/catalog/guide/completion; associated unit/UI fixtures and docs.

- [ ] Cherry-pick -x f563173,f22c21d,e3b3164,aeb8ac4,2a749cb,abdb4c5,0a9a882,e2446f3,cfdf02b,273dec1 in dependency order.
- [ ] Reconcile collisions against upstream actual schemas and current native count. Combine fixture isolation for settings/session/version/savepoint. Omit deferred core-toolset/provisioning/autoupdate/context_query/global-expression hunks.
- [ ] Preserve preview credential fields across updates and redact secrets in returned status. Compare real code paths to existing test patterns before any repair.
- [ ] Run focused impersonation, E2E, duplication, savepoint and reliability regressions. For defects, add failing regression first, repair minimally, rerun.

### Task3: Full gate, independent review and PR

Files: CHANGELOG.md; this plan/spec; .github/workflows/ci.yml read-only; existing verification scripts.

- [ ] Run coverage run -m pytest -q then coverage report: all tests pass, >=45.3%.
- [ ] Run runtime coverage and agent-routing smokes; Ruff src/tests/scripts; Mypy src; sensitive audit; package smoke Python3.11; setup smoke; npm test Node20; diff check.
- [ ] Request independent review of exact base/head. Resolve important findings with regressions and rerun affected/full gates when justified.
- [ ] Push feature branch with [skip ci], open and attach PR against pedrobefree/main. Describe provenance, deferred scope, actual local results and synthetic/live limits. Do not merge.
