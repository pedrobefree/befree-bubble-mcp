"""Local artifact generation for framework adapters."""

from __future__ import annotations

import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from bubble_mcp.core.config import get_config_dir
from bubble_mcp.core.redaction import redact_sensitive
from bubble_mcp.frameworks.adapters import get_adapter, list_adapters
from bubble_mcp.frameworks.models import FrameworkAdapter


def _utc_now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _slug(value: str, *, fallback: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", str(value or "").strip().lower()).strip("-")
    return slug or fallback


def _framework_root(output_dir: Path | None = None) -> Path:
    return output_dir.expanduser() if output_dir is not None else get_config_dir() / "frameworks"


def _base_profile_dir(framework: str, profile: str, output_dir: Path | None = None) -> Path:
    return _framework_root(output_dir) / framework / _slug(profile, fallback="profile")


def _artifact_dir(framework: str, profile: str, objective: str, output_dir: Path | None = None) -> Path:
    timestamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return _base_profile_dir(framework, profile, output_dir) / f"{timestamp}-{_slug(objective, fallback='objective')[:48]}"


def _latest_artifact_dir(framework: str, profile: str, output_dir: Path | None = None) -> Path | None:
    base = _base_profile_dir(framework, profile, output_dir)
    if not base.exists():
        return None
    candidates = [path for path in base.iterdir() if path.is_dir()]
    return sorted(candidates)[-1] if candidates else None


def _safe_artifact_dir(path: Path) -> Path:
    resolved = path.expanduser().resolve()
    if resolved.exists() and not resolved.is_dir():
        raise ValueError(f"Framework artifact path is not a directory: {resolved}")
    return resolved


def _metadata(
    adapter: FrameworkAdapter,
    *,
    profile: str,
    objective: str,
    scope: str | None,
    context_summary: dict[str, Any] | None,
) -> dict[str, Any]:
    return {
        "framework": adapter.framework_id,
        "framework_name": adapter.name,
        "profile": profile,
        "objective": objective,
        "scope": scope,
        "generated_at": _utc_now_iso(),
        "source": "bubble_mcp_framework_adapter_v1",
        "mode": "artifact_generation",
        "context_summary": redact_sensitive(context_summary or {}),
        "execution_policy": (
            "Generated artifacts are advisory planning artifacts. Bubble writes must still go through "
            "preview-first MCP tools or executable skills with approval."
        ),
    }


def _context_lines(context_summary: dict[str, Any] | None) -> list[str]:
    if not context_summary:
        return ["- No context summary was provided to this artifact generation call."]
    lines: list[str] = []
    for key in sorted(context_summary):
        value = context_summary[key]
        if isinstance(value, (str, int, float, bool)) or value is None:
            lines.append(f"- `{key}`: {value}")
        elif isinstance(value, list):
            lines.append(f"- `{key}`: {len(value)} item(s)")
        elif isinstance(value, dict):
            lines.append(f"- `{key}`: {len(value)} field(s)")
        else:
            lines.append(f"- `{key}`: {type(value).__name__}")
    return lines or ["- Context summary was empty."]


def _render_artifact(
    adapter: FrameworkAdapter,
    artifact_name: str,
    *,
    profile: str,
    objective: str,
    scope: str | None,
    context_summary: dict[str, Any] | None,
) -> str:
    title = artifact_name.removesuffix(".md").replace("-", " ").title()
    context_block = "\n".join(_context_lines(context_summary))
    scope_text = scope or "Not specified."
    if adapter.framework_id == "bmad":
        body = _render_bmad_section(artifact_name)
    elif adapter.framework_id == "superpowers":
        body = _render_superpowers_section(artifact_name)
    else:
        body = _render_sdd_section(artifact_name)
    return (
        f"# {adapter.name} - {title}\n\n"
        f"- Framework: `{adapter.framework_id}`\n"
        f"- Profile: `{profile}`\n"
        f"- Objective: {objective}\n"
        f"- Scope: {scope_text}\n"
        f"- Generated at: {_utc_now_iso()}\n\n"
        "## Bubble Context Signals\n\n"
        f"{context_block}\n\n"
        "## Adapter Guidance\n\n"
        f"{body}\n\n"
        "## Execution Boundary\n\n"
        "This artifact does not authorize Bubble writes. Implementation must use Bubble MCP tools or executable skills "
        "with preview-first validation and explicit approval for mutations.\n"
    )


def _render_bmad_section(artifact_name: str) -> str:
    sections = {
        "project-brief.md": (
            "- Capture the problem, target user, constraints, and existing Bubble surface.\n"
            "- Keep assumptions tied to discovered Bubble context."
        ),
        "prd.md": (
            "- Define goals, non-goals, user workflows, acceptance criteria, and risks.\n"
            "- Reference Bubble pages, data types, workflows, API Connector calls, and styles when known."
        ),
        "architecture.md": (
            "- Map the current Bubble implementation boundary and proposed changes.\n"
            "- Identify affected editor surfaces, data relationships, integrations, and validation gates."
        ),
        "epics.md": "- Break the objective into independently shippable Bubble change groups.",
        "stories.md": "- For each story, include context evidence, acceptance criteria, and MCP validation steps.",
        "validation-evidence.md": "- Append execution evidence, preview summaries, refreshed context checks, and known residual risks.",
    }
    return sections.get(artifact_name, "- Maintain BMAD traceability from intent to evidence.")


def _render_superpowers_section(artifact_name: str) -> str:
    sections = {
        "spec.md": "- State the desired behavior and explicit boundaries before planning implementation.",
        "implementation-plan.md": (
            "- Convert the spec into bite-sized tasks with exact MCP tools, verification steps, and rollback notes."
        ),
        "execution-gates.md": "- Define approval, preview, evidence, and verification gates before mutation.",
        "verification-checklist.md": "- Check context freshness, preview payloads, execution result, and post-change evidence.",
    }
    return sections.get(artifact_name, "- Preserve spec-to-plan-to-verification discipline.")


def _render_sdd_section(artifact_name: str) -> str:
    sections = {
        "specification.md": "- Express expected Bubble behavior as testable statements.",
        "fixtures.md": "- Derive fixtures from real Bubble context and avoid invented ids or data relationships.",
        "acceptance-tests.md": "- Define acceptance checks that can be verified from context refresh, logs, or UI inspection.",
        "traceability.md": "- Map requirements to context evidence, MCP tools, execution runs, and validation outputs.",
    }
    return sections.get(artifact_name, "- Keep specification, fixtures, and validation evidence linked.")


def list_frameworks() -> dict[str, Any]:
    return {"ok": True, "frameworks": [adapter.to_dict() for adapter in list_adapters()]}


def generate_framework_artifacts(
    *,
    framework: str,
    profile: str,
    objective: str,
    scope: str | None = None,
    context_summary: dict[str, Any] | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    adapter = get_adapter(framework)
    normalized_profile = str(profile or "").strip()
    normalized_objective = str(objective or "").strip()
    if not normalized_profile:
        raise ValueError("framework artifact generation requires profile.")
    if not normalized_objective:
        raise ValueError("framework artifact generation requires objective.")
    target_dir = _artifact_dir(adapter.framework_id, normalized_profile, normalized_objective, output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    metadata = _metadata(
        adapter,
        profile=normalized_profile,
        objective=normalized_objective,
        scope=scope,
        context_summary=context_summary,
    )
    metadata_path = target_dir / "framework.json"
    metadata_path.write_text(json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    artifact_paths: list[str] = []
    for artifact_name in adapter.artifacts:
        path = target_dir / artifact_name
        path.write_text(
            _render_artifact(
                adapter,
                artifact_name,
                profile=normalized_profile,
                objective=normalized_objective,
                scope=scope,
                context_summary=context_summary,
            ),
            encoding="utf-8",
        )
        artifact_paths.append(str(path))
    return {
        "ok": True,
        "framework": adapter.framework_id,
        "profile": normalized_profile,
        "objective": normalized_objective,
        "artifact_dir": str(target_dir),
        "artifacts": artifact_paths,
        "metadata": str(metadata_path),
        "next_mcp_calls": [
            {
                "tool": "bubble_framework_status",
                "arguments": {"framework": adapter.framework_id, "profile": normalized_profile, "output_dir": str(output_dir or "")},
            },
            {
                "tool": "bubble_framework_sync_evidence",
                "arguments": {
                    "framework": adapter.framework_id,
                    "profile": normalized_profile,
                    "artifact_dir": str(target_dir),
                    "evidence": {"summary": "Add implementation or validation evidence here."},
                },
            },
        ],
    }


def sync_framework_evidence(
    *,
    framework: str,
    profile: str,
    evidence: dict[str, Any],
    artifact_dir: Path | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    adapter = get_adapter(framework)
    normalized_profile = str(profile or "").strip()
    if not normalized_profile:
        raise ValueError("framework evidence sync requires profile.")
    if not isinstance(evidence, dict) or not evidence:
        raise ValueError("framework evidence sync requires a non-empty evidence object.")
    target_dir = _safe_artifact_dir(artifact_dir) if artifact_dir else _latest_artifact_dir(adapter.framework_id, normalized_profile, output_dir)
    if target_dir is None:
        target_dir = _base_profile_dir(adapter.framework_id, normalized_profile, output_dir) / "evidence"
    target_dir.mkdir(parents=True, exist_ok=True)
    record = {
        "framework": adapter.framework_id,
        "profile": normalized_profile,
        "recorded_at": _utc_now_iso(),
        "evidence": redact_sensitive(evidence),
    }
    evidence_jsonl = target_dir / "evidence.jsonl"
    with evidence_jsonl.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")
    evidence_md = target_dir / "evidence.md"
    with evidence_md.open("a", encoding="utf-8") as handle:
        handle.write(
            f"## Evidence - {record['recorded_at']}\n\n"
            f"- Framework: `{adapter.framework_id}`\n"
            f"- Profile: `{normalized_profile}`\n\n"
            "```json\n"
            f"{json.dumps(record['evidence'], indent=2, sort_keys=True)}\n"
            "```\n\n"
        )
    return {
        "ok": True,
        "framework": adapter.framework_id,
        "profile": normalized_profile,
        "artifact_dir": str(target_dir),
        "evidence_jsonl": str(evidence_jsonl),
        "evidence_markdown": str(evidence_md),
    }


def framework_status(
    *,
    framework: str | None = None,
    profile: str | None = None,
    output_dir: Path | None = None,
) -> dict[str, Any]:
    adapters = [get_adapter(framework)] if framework else list_adapters()
    root = _framework_root(output_dir)
    rows: list[dict[str, Any]] = []
    for adapter in adapters:
        framework_dir = root / adapter.framework_id
        profile_dirs = [framework_dir / _slug(profile, fallback="profile")] if profile else []
        if not profile_dirs and framework_dir.exists():
            profile_dirs = [path for path in framework_dir.iterdir() if path.is_dir()]
        for profile_dir in sorted(profile_dirs):
            artifact_dirs = [path for path in profile_dir.iterdir() if path.is_dir()] if profile_dir.exists() else []
            evidence_count = 0
            for artifact in artifact_dirs:
                evidence_path = artifact / "evidence.jsonl"
                if evidence_path.exists():
                    evidence_count += len([line for line in evidence_path.read_text(encoding="utf-8").splitlines() if line.strip()])
            rows.append(
                {
                    "framework": adapter.framework_id,
                    "profile": profile_dir.name,
                    "profile_dir": str(profile_dir),
                    "artifact_count": len(artifact_dirs),
                    "latest_artifact_dir": str(sorted(artifact_dirs)[-1]) if artifact_dirs else None,
                    "evidence_count": evidence_count,
                }
            )
    return {"ok": True, "root": str(root), "framework": framework, "profile": profile, "status": rows}
