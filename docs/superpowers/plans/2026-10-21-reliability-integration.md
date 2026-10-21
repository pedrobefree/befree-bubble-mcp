# Reliability Integration Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans inline; request one independent whole-branch review at the end.

**Goal:** Integrate the fork reliability block into upstream main and open a reviewed PR.

**Architecture:** Keep upstream reference/overlay contracts. Merge the historical foundational node/read-back block, then cherry-pick selected session, version and profile corrections with original authorship and origin trailers.

**Tech Stack:** Python >=3.11, pytest/coverage, Ruff, Mypy, Node tests, existing Python stdio MCP server.

**Spec:** docs/superpowers/specs/2026-10-21-reliability-integration-design.md

## Global Constraints

No modifications to the original checkout; no remote merge or live Bubble changes. Do not trigger GitHub Actions. Coverage floor45.3%. Preserve history and explicit deletions/sibling writes. No new framework or dependency migration.

### Task 1: Historical foundation and contract reconciliation

Files: execution/{raw_node_edit,node_keys,live_node_read,node_edit,write_verify}.py; compiler/payload.py; context/importers.py; runtime_discovery.py; aria_runtime/bubble_cli.py; server tools/schema; corresponding unit tests.

- [x] Run existing workflow/reference baseline against upstream; expected PASS.
- [x] Merge 5e70624 without squashing. Resolve source conflicts by retaining upstream proven object IDs and fork dry-run guards; combine independent test functions/imports rather than dropping either side.
- [x] Run workflow_listing, reference_payload_contracts, compiler, CLI, write_verify, node_edit and live_node_read; expected PASS. Any new adaptation follows a reproduced failure and smallest repair.
- [x] Commit merge retaining both parents and original authors.

### Task 2: Target version, session and profile corrections

Files: execution/{client,editor_page,version_policy}.py; core/versions.py; sessions/{browser,health}.py; server/{tools,schema_families,agent_catalog,instructions}.py; aria_dispatch.py; catalog_quality.py; context/detector.py and tests.

- [x] Transport selected original commits with git cherry-pick -x in dependency order: cf95377, 0e5f560, c758ae6 (package-loader dependency), 0c46a0f, e6f4dec, 8960c9c, 9a7cb4f, 6dc3651, 40fff27, 8831a33, 6ced754, 05cd031. Omit only hunks that wire deferred capabilities absent from this branch, documenting each omission.
- [x] Run each corresponding test module before resolving behavioral conflicts; inspect the actual exception and contract.
- [x] Keep catalog snapshots at the actual isolated native inventory, not fork full count. Keep all isolated-config and no-network fixtures relevant to this block.
- [x] Run focused session/version/profile/schema/overlay regressions; expected PASS.

### Task 3: Whole-branch gates and PR

Files: CHANGELOG.md; plan/spec; .github/workflows/ci.yml read-only; existing verification scripts.

- [x] Run coverage run -m pytest -q then coverage report; expected all tests pass and >=45.3%.
- [x] Run runtime smoke suites coverage and agent-routing; Ruff src tests scripts; Mypy src; sensitive audit; package_smoke Python3.11; setup_smoke; npm test; diff check.
- [x] Request independent review with exact base/head; fix important findings with regression tests and rerun affected/full gates when necessary.
- [ ] Commit, push feature branch with [skip ci], create PR against pedrobefree/main, attach it and report local results/limits. Do not merge.

## Validation record

- Source reviewed:8c3c4d26fb58dbf46993abbcb73700e482dc7183. The only later source adjustment trims a blank line at EOF; diff ignoring blank lines is empty.
- Full workflow suite:2422 passed in563.30s; coverage48.8% >=45.3%. macOS/Python3.11.9.
- Ruff, Mypy160 source files, sensitive audit, complete diff check:PASS. No new lint/type exclusions.
- Runtime coverage2/2; routing9/9; package smoke and setup smoke:PASS. Setup correctly reports a fresh unauthenticated profile as not ready.
- Node20.20.2:11/11 passed; Node24.18.0 also11/11.
- Independent review found two P2s in imported write verification. Regression run before repair:3failed/1passed; all4 pass after repair. Full verifier/policy/session group67passed. Reviewer confirmed both closed and no newP1/P2.
- All fixtures are synthetic; no Bubble live edit or deployment, nativeLinux/Windows acceptance or GitHub Actions run.
- Original main0fc8e5e and10 untracked files remain byte-for-byte intact.
