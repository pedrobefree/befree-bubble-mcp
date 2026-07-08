"""Preview and approved execution runner for compiled framework programs."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from bubble_mcp.server.tools import (  # type: ignore[attr-defined]
    call_tool,
    compile_framework_program,
    sync_framework_evidence,
)


def _execution_mode(program: dict[str, Any], mode: str | None) -> str:
    if mode:
        return mode
    execution = program.get("execution")
    if isinstance(execution, dict):
        raw_mode = execution.get("mode")
        if isinstance(raw_mode, str) and raw_mode.strip():
            return raw_mode.strip()
    return "preview"


def _sync_evidence_safe(
    *,
    framework: str,
    profile: str,
    evidence: dict[str, Any],
    artifact_dir: str | Path | None,
) -> dict[str, Any]:
    try:
        artifact_path = Path(artifact_dir) if artifact_dir is not None else None
        return sync_framework_evidence(
            framework=framework,
            profile=profile,
            evidence=evidence,
            artifact_dir=artifact_path,
        )
    except Exception as exc:  # Evidence sync must not mask preview or execution results.
        return {
            "ok": False,
            "warning": "framework_program_evidence_sync_failed",
            "evidence_error": str(exc),
        }


def _compile(
    *,
    framework: str,
    profile: str,
    program: dict[str, Any],
) -> dict[str, Any]:
    compiled = compile_framework_program(
        framework=framework,
        profile=profile,
        program=program,
    )
    if not isinstance(compiled, dict):
        return {
            "ok": False,
            "error": "framework_program_compile_returned_invalid_result",
            "compiled_result": compiled,
        }
    return compiled


def execute_framework_program(
    *,
    framework: str,
    profile: str,
    program: dict[str, Any],
    mode: str | None = None,
    approved: bool = False,
    artifact_dir: str | Path | None = None,
) -> dict[str, Any]:
    """Compile a framework program, then preview or execute it through MCP dispatch."""

    execution_mode = _execution_mode(program, mode)
    compiled = _compile(framework=framework, profile=profile, program=program)
    if not bool(compiled.get("ok")):
        return {
            "ok": False,
            "error": "framework_program_compile_failed",
            "mode": execution_mode,
            "executed": False,
            "compiled": compiled,
        }

    if execution_mode != "execute":
        evidence = _sync_evidence_safe(
            framework=framework,
            profile=profile,
            artifact_dir=artifact_dir,
            evidence={
                "mode": "preview",
                "executed": False,
                "compiled": compiled,
            },
        )
        return {
            "ok": True,
            "mode": "preview",
            "executed": False,
            "compiled": compiled,
            "evidence": evidence,
        }

    if bool(compiled.get("approval_required")) and not approved:
        return {
            "ok": False,
            "error": "framework_program_execution_requires_approval",
            "mode": "execute",
            "executed": False,
            "compiled": compiled,
            "approval_required": True,
        }

    step_results: list[dict[str, Any]] = []
    ok = True
    for call in compiled.get("compiled_calls", []):
        if not isinstance(call, dict):
            ok = False
            step_results.append(
                {
                    "ok": False,
                    "error": "framework_program_invalid_compiled_call",
                    "call": call,
                }
            )
            break
        tool = str(call.get("tool") or "")
        raw_arguments = call.get("arguments")
        arguments = dict(raw_arguments) if isinstance(raw_arguments, dict) else {}
        if "execute" in arguments:
            arguments["execute"] = True
        result = call_tool(tool, arguments)
        step_result = {
            "ok": result.get("ok") is not False,
            "tool": tool,
            "arguments": arguments,
            "result": result,
        }
        step_results.append(step_result)
        if result.get("ok") is False:
            ok = False
            break

    refresh_result: dict[str, Any] | None = None
    if step_results:
        refresh_result = call_tool("bubble_profile_cache_refresh", {"profile": profile, "force": True})
        if refresh_result.get("ok") is False:
            ok = False

    evidence = _sync_evidence_safe(
        framework=framework,
        profile=profile,
        artifact_dir=artifact_dir,
        evidence={
            "mode": "execute",
            "executed": True,
            "compiled": compiled,
            "step_results": step_results,
            "refresh_result": refresh_result,
        },
    )
    return {
        "ok": ok,
        "mode": "execute",
        "executed": True,
        "compiled": compiled,
        "step_results": step_results,
        "refresh_result": refresh_result,
        "evidence": evidence,
    }
