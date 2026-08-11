# Bubble Context Source Priority And Readiness Design

Date: 2026-08-11
Status: Approved design
Scope: Issue #10 in the Befree Bubble MCP standalone package

## Problem

`bubble-mcp context detect` can successfully materialize the deterministic compact context at
`contexts/{profile}/{appId}-context.json` without configuring `profile.app_json_path`. In that state,
`bubble-mcp profile status` ignores the compact context, reports it as unconfigured and missing, and
keeps `ready` false.

The source fallback also does not satisfy the required behavior for Bubble Free-plan apps and
templates. The detector currently treats a `console.log(app)` artifact and the editor crawler as
mutually exclusive fallbacks. A console payload returns immediately, so it is not enriched with the
editor crawler. Automatic console extraction is also currently a stub.

For apps where a `.bubble` export is unavailable, neither console data nor crawler data is sufficient
alone. Console data supplies the richer app schema; the crawler supplies current editor trees and
path indexes. The compact context must compose both sources before it is considered complete.

## Goals

- Always prefer a valid `.bubble` export as the authoritative primary source.
- Never require or run the crawler when a valid `.bubble` export is available.
- Permit `console.log(app)` to complement a `.bubble` export without overriding authoritative data.
- When no `.bubble` export exists, combine `console.log(app)` with editor crawler data.
- Persist useful partial artifacts for diagnosis without misreporting a partial context as ready.
- Make profile status discover the deterministic compact context without repurposing `app_json_path`.
- Expose safe source provenance and completeness in detection and profile status results.
- Preserve existing CLI and MCP tool inputs.

## Non-Goals

- Do not infer the Bubble billing plan from account or app metadata.
- Do not add a new profile configuration field solely for the deterministic compact context path.
- Do not repurpose `app_json_path`; it remains the configured `.bubble` source artifact.
- Do not make `console.log(app)` mandatory when a valid `.bubble` export exists.
- Do not run the crawler to enrich an already valid `.bubble` export.
- Do not expose raw console payloads, cookies, headers, or sensitive settings in status responses.

## Considered Approaches

### 1. Status-only fallback

Teach `profile_status` to find `default_context_path` and otherwise leave detection unchanged.

This fixes the literal false-negative from issue #10, but it can mark crawler-only or console-only
contexts as ready even though they are incomplete for Free-plan apps and templates. This approach is
rejected.

### 2. Persist the compact path in `app_json_path`

Save every generated compact context path back to the profile.

This resolves discovery but conflates an authoritative `.bubble` source with a derived compact
artifact. It can break flows that specifically require the raw export and adds unnecessary config
writes. This approach is rejected.

### 3. Source-aware composition with deterministic path discovery

Keep source artifacts distinct, compose console and crawler data when no `.bubble` exists, record
provenance, and let status resolve the deterministic compact path. This is the selected approach.

## Source Contract

| `.bubble` | `console.log(app)` | crawler | Detection result | Complete |
| --- | --- | --- | --- | --- |
| valid | absent | not run | `.bubble` context | yes |
| valid | valid | not run | `.bubble` plus console complement | yes |
| absent | valid | valid | console plus crawler composite | yes |
| absent | valid | unavailable | persisted partial console context | no |
| absent | unavailable | valid | persisted partial crawler context | no |
| absent | unavailable | unavailable | detection error | no |

An export rejection such as HTTP 401 is an unavailable-source attempt, not a terminal detector error.
The detector continues through the no-export composition path.

## Architecture

### Source collection

`bubble_mcp.context.detector` remains the orchestrator and collects sources in this order:

1. Explicit or configured local `.bubble` candidate.
2. Authenticated `.bubble` download.
3. Optional console candidate or browser capture.
4. Editor crawler and, when the path API is sparse, editor network-index capture.

The detector must not return immediately after finding console data. It retains the console payload,
collects crawler data, and composes both when the `.bubble` path is unavailable.

Browser-backed fallback collection should reuse the authenticated persistent browser profile. When a
browser visit is required, it should serialize the editor's global `app` object to JSON with an
explicit timeout and size limit, while collecting network indexes during the same editor load. A
serialization or size failure is recorded as a safe source failure and does not expose the payload in
logs.

### Source composition

A focused context composition module owns normalization and merge policy instead of importing the
large Aria runtime into the detector. The existing crawler enrichment behavior in `PathDiscovery`
should be extracted or adapted into this module so runtime and detector behavior cannot drift.

Merge rules:

- `.bubble` is authoritative on every conflict.
- Console may fill fields absent from `.bubble`, but cannot overwrite non-empty `.bubble` data.
- Without `.bubble`, console is the base for data types, option sets, styles, settings, plugins, and
  full definitions.
- Crawler data enriches pages, reusables, elements, workflows, internal ids, and path indexes.
- Crawler values fill missing console values and may supply newer editor topology.
- Empty crawler values never erase non-empty console values.
- Collections are deduplicated by stable Bubble id, not display name.

### Persisted artifacts

The detector always writes the canonical profile context to `default_context_path(profile, app_id)`.
If the caller explicitly provides `output`, it also writes an identical secondary copy there. The
canonical path remains the source used by profile readiness, so a diagnostic output override cannot
make a successfully refreshed profile appear unconfigured.

When available, it also persists:

- the raw `.bubble` export at the existing default export path;
- the captured console payload in the profile context directory;
- the crawler index at the existing default crawler-index path.

Captured console artifacts are local sensitive data. They must use restrictive file permissions where
the platform supports them and must never be embedded in user-facing MCP responses.

### Provenance and completeness

The compact context metadata records a safe structure such as:

```json
{
  "provenance": {
    "primary_source": "consolelog_app",
    "sources": ["consolelog_app", "editor_crawler"],
    "completeness": "complete",
    "bubble_export_available": false
  }
}
```

Allowed completeness values are `complete` and `partial`. Attempts retain source-specific failure
reasons, but status summaries expose only safe diagnostics and never raw payloads or credentials.

### Profile readiness

`profile_status` resolves context independently from `app_json_path`:

- A configured non-`.bubble` compact JSON path remains supported for backward compatibility.
- A configured `.bubble` source resolves to the deterministic compact context as it does today.
- With no configured source, status resolves `default_context_path(profile.name, profile.app_id)`.

`ready` requires the existing session, app-id, write-readiness, and freshness conditions plus a
complete context. A valid `.bubble` context is complete. A no-export context is complete only when it
contains both console and crawler provenance.

Legacy compact contexts without provenance remain compatible when backed by a configured `.bubble`
source. No-export legacy contexts are reported as partial until refreshed through the corrected
detector.

## Error Handling

- A failed `.bubble` download records the exact safe reason and continues to console and crawler.
- If only console succeeds, detection returns the partial artifact with `console_missing=false` and
  an actionable `crawler_missing` or `crawler_failed` diagnostic.
- If only crawler succeeds, detection returns the partial artifact with `console_missing` guidance.
- If neither source succeeds, detection raises a consolidated error containing safe per-source
  reasons.
- Optional console collection failure never downgrades an otherwise valid `.bubble` context.
- Crawler execution is skipped whenever a valid `.bubble` source was selected.

## MCP And CLI Responses

Existing tools and commands keep their current inputs. Detection, cache refresh, bootstrap, and profile
status responses add safe provenance and completeness fields.

Affected surfaces:

- `bubble_context_detect`
- `bubble_profile_status`
- `bubble_profile_cache_refresh`
- `bubble_project_bootstrap`
- `bubble_context_find`
- corresponding `bubble-mcp context` and `bubble-mcp profile` commands

Partial detection remains useful and may return `ok: true`, but it must return `ready: false` and a
specific next action. A complete context returns `ready: true` when all other readiness conditions pass.

## Testing

### Unit coverage

- Profile without `app_json_path` discovers a valid default compact context.
- `.bubble` wins conflicts with console complement data.
- Valid `.bubble` skips crawler execution.
- Export HTTP 401 continues to console and crawler.
- Console plus crawler produces a complete composite.
- Console-only and crawler-only outputs are partial.
- Crawler topology enriches console schema without erasing rich console fields.
- Merge collections deduplicate by Bubble id.
- Captured console payloads are not exposed in status responses.
- Missing, invalid, stale, and wrong-app contexts remain not ready.

### Integration coverage

- `context detect` followed by `profile status` is ready for a valid `.bubble` flow.
- The same sequence is ready for a no-export console-plus-crawler flow.
- `bubble_profile_cache_refresh` returns the same completeness and readiness as profile status.
- `bubble_project_bootstrap` and `bubble_context_find` consume the deterministic compact context.
- Explicit `--consolelog-file` participates in composition instead of short-circuiting crawler capture.

### Validation commands

```bash
PYTHONPATH=src ./.venv/bin/python -m pytest \
  tests/unit/test_profile_status.py \
  tests/unit/test_context_detector.py \
  tests/unit/test_cli_commands.py \
  tests/unit/test_mcp_server.py -q
./.venv/bin/python -m ruff check src/bubble_mcp/context src/bubble_mcp/profile_status.py \
  tests/unit/test_context_detector.py tests/unit/test_profile_status.py
git diff --check
```

## Delivery

The implementation will stay on `fix/issue-10-context-source-priority`, include focused regression
tests, and be suitable for a draft pull request after validation. Creating or publishing the pull
request remains a separate explicit delivery action.
