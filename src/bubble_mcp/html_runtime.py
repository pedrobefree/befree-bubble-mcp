"""Run Aria's advanced HTML-to-Bubble importer inside the standalone package."""

from __future__ import annotations

import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any, cast

from bubble_mcp.context.detector import default_crawler_index_path, detect_project_context
from bubble_mcp.context.mutation_overlay import mutation_overlay_path, record_mutation_overlay
from bubble_mcp.core.config import (
    get_settings_path,
    load_json_file,
    load_settings,
    normalize_profile_name,
    resolve_profile,
)
from bubble_mcp.execution.client import BubbleEditorClient
from bubble_mcp.sessions.store import load_session


def _load_aria_runtime_modules() -> tuple[Any, Any]:
    runtime_dir = Path(__file__).resolve().parent / "aria_runtime"
    runtime_path = str(runtime_dir)
    if runtime_path not in sys.path:
        sys.path.insert(0, runtime_path)
    import bubble_cli  # type: ignore[import-not-found]
    import bubble_sdk  # type: ignore[import-not-found]

    return bubble_cli, bubble_sdk


def _raw_profile_config(profile: str) -> dict[str, Any]:
    settings_path = get_settings_path()
    try:
        payload = load_json_file(settings_path)
    except Exception:
        return {}
    raw_profiles = payload.get("profiles")
    if not isinstance(raw_profiles, dict):
        return {}
    exact = raw_profiles.get(profile)
    if isinstance(exact, dict):
        return dict(exact)
    target = normalize_profile_name(profile)
    if target:
        matches = [
            raw
            for name, raw in raw_profiles.items()
            if normalize_profile_name(str(name)) == target and isinstance(raw, dict)
        ]
        if len(matches) == 1:
            return dict(matches[0])
    return {}


def _render_config_from_profile(raw_profile: dict[str, Any]) -> dict[str, Any]:
    known_profile_fields = {
        "app_id",
        "appname",
        "editor_url",
        "app_version",
        "appVersion",
        "app_json_path",
        "consolelog_json_path",
    }
    render_config: dict[str, Any] = {}
    nested = raw_profile.get("render")
    if isinstance(nested, dict):
        render_config.update(nested)
    for key, value in raw_profile.items():
        if key in known_profile_fields:
            continue
        if key.startswith("render_") or key in {
            "rendered_html_default",
            "renderer_mode",
            "render_endpoint",
            "render_timeout_ms",
            "render_cache_enabled",
            "render_cache_dir",
            "render_cache_ttl_hours",
            "auto_install_local_renderer",
            "allow_render_fallback",
            "node_bin",
            "npm_bin",
            "enable_specialized_converters",
        }:
            render_config[key] = value
    return render_config


def _resolve_optional_profile_path(raw_profile: dict[str, Any], key: str) -> str | None:
    value = str(raw_profile.get(key) or "").strip()
    if not value:
        return None
    path = Path(value).expanduser()
    if not path.is_absolute():
        path = get_settings_path().parent / path
    return str(path) if path.exists() else None


def create_from_html_runtime(
    *,
    profile: str,
    context: str,
    parent: str,
    html_file: str | None = None,
    html: str | None = None,
    app_id: str | None = None,
    app_version: str = "test",
    execute: bool = False,
    selector: str | None = None,
    placement: str | None = None,
    translate_to_existing_styles: bool = False,
    style_match_threshold: float = 0.78,
    rendered_html: bool | None = None,
    strict_validate: bool = False,
    validation_out_dir: str | None = None,
    refresh_context: bool = False,
) -> dict[str, Any]:
    profile = str(profile or "").strip()
    if not profile:
        raise ValueError("create_from_html_runtime requires profile.")
    if not str(context or "").strip():
        raise ValueError("create_from_html_runtime requires context.")
    if not str(parent or "").strip():
        raise ValueError("create_from_html_runtime requires parent.")
    if not str(html_file or "").strip() and not str(html or "").strip():
        raise ValueError("create_from_html_runtime requires html_file or html.")

    settings = load_settings()
    profile_config = resolve_profile(settings, profile)
    raw_profile = _raw_profile_config(profile)
    session = load_session(profile)
    resolved_app_id = str(
        app_id
        or (session.app_id if session else "")
        or (profile_config.app_id if profile_config else "")
        or ""
    ).strip()
    if not resolved_app_id:
        raise ValueError(f"No app_id found for profile '{profile}'.")
    resolved_app_version = str(
        app_version
        or (session.app_version if session and session.app_version else "")
        or (profile_config.app_version if profile_config and profile_config.app_version else "")
        or "test"
    )

    detected = detect_project_context(
        profile=profile,
        app_id=resolved_app_id,
        app_version=resolved_app_version,
        force=refresh_context,
    )
    bubble_file = detected.context_path.with_name(f"{resolved_app_id}.bubble")
    if not bubble_file.exists():
        raise ValueError(f"Bubble export not found for Aria runtime: {bubble_file}")
    crawler_index_path = detected.crawler_index_path or default_crawler_index_path(profile, resolved_app_id)
    resolved_crawler_index_path = str(crawler_index_path) if crawler_index_path and crawler_index_path.exists() else None
    resolved_consolelog_path = _resolve_optional_profile_path(raw_profile, "consolelog_json_path")
    resolved_mutation_overlay_path = str(mutation_overlay_path(profile, resolved_app_id))
    if not Path(resolved_mutation_overlay_path).exists():
        resolved_mutation_overlay_path = _resolve_optional_profile_path(raw_profile, "mutation_overlay_path") or resolved_mutation_overlay_path
    if execute and session is None:
        raise ValueError(f"No Bubble session stored for profile '{profile}'.")

    temp_path: Path | None = None
    source_path = str(html_file or "").strip()
    if not source_path and html is not None:
        handle = tempfile.NamedTemporaryFile("w", suffix=".html", encoding="utf-8", delete=False)
        try:
            handle.write(str(html))
            source_path = handle.name
            temp_path = Path(source_path)
        finally:
            handle.close()

    bubble_cli, bubble_sdk = _load_aria_runtime_modules()
    captured_payloads: list[dict[str, Any]] = []
    captured_results: list[dict[str, Any]] = []
    captured_builder_ids: set[int] = set()
    original_send = bubble_sdk.PayloadBuilder.send_to_webhook
    original_to_json = bubble_sdk.PayloadBuilder.to_json

    def capture_payload(builder: Any) -> dict[str, Any]:
        builder_id = id(builder)
        write_payload = cast("dict[str, Any]", builder.build())
        if builder_id not in captured_builder_ids:
            captured_builder_ids.add(builder_id)
            captured_payloads.append(write_payload)
        return write_payload

    def send_to_local_bubble(builder: Any, _url: str = "") -> Any:
        write_payload = capture_payload(builder)
        if not execute:
            captured_results.append({"ok": True, "executed": False, "dry_run": True, "payload": write_payload})
            return {"ok": True, "dry_run": True}
        assert session is not None
        result = BubbleEditorClient().write(write_payload, session, dry_run=False)
        if result.get("ok"):
            record_mutation_overlay(
                profile=profile,
                app_id=resolved_app_id,
                payload=result.get("request", {}).get("payload") or write_payload,
                source="create_from_html",
                response=result.get("response"),
            )
        captured_results.append({"ok": bool(result.get("ok")), "executed": True, "result": result})
        if not result.get("ok"):
            raise RuntimeError(str(result.get("error") or result.get("reason") or "Bubble write failed"))
        return result

    def to_json_with_capture(builder: Any) -> str:
        write_payload = capture_payload(builder)
        if not execute:
            captured_results.append({"ok": True, "executed": False, "dry_run": True, "payload": write_payload})
        return cast(str, original_to_json(builder))

    stdout = StringIO()
    stderr = StringIO()
    try:
        bubble_sdk.PayloadBuilder.send_to_webhook = send_to_local_bubble
        bubble_sdk.PayloadBuilder.to_json = to_json_with_capture
        with redirect_stdout(stdout), redirect_stderr(stderr):
            cli = bubble_cli.BubbleCLI(
                app_json_path=str(bubble_file),
                consolelog_json_path=resolved_consolelog_path,
                crawler_index_path=resolved_crawler_index_path,
                mutation_overlay_path=resolved_mutation_overlay_path,
                appname=resolved_app_id,
                webhook_url="local://bubble-mcp",
                profile_name=profile,
                render_config=_render_config_from_profile(raw_profile),
            )
            success = cli.create_from_html(
                context,
                parent,
                source_path,
                selector=selector,
                dry_run=not execute,
                placement=placement,
                translate_to_existing_styles=translate_to_existing_styles,
                style_match_threshold=style_match_threshold,
                rendered_html=rendered_html,
                strict_validate=strict_validate,
                validation_out_dir=validation_out_dir,
            )
    finally:
        bubble_sdk.PayloadBuilder.send_to_webhook = original_send
        bubble_sdk.PayloadBuilder.to_json = original_to_json
        if temp_path is not None:
            try:
                temp_path.unlink()
            except Exception:
                pass

    runtime_logs = "\n".join(part for part in (stdout.getvalue().strip(), stderr.getvalue().strip()) if part)
    if not success:
        detail = runtime_logs.strip()
        if len(detail) > 2000:
            detail = detail[-2000:]
        raise RuntimeError(
            "Aria HTML import runtime failed."
            + (f"\nRuntime logs:\n{detail}" if detail else "")
        )

    return {
        "ok": all(bool(item.get("ok")) for item in captured_results),
        "engine": "aria_runtime",
        "profile": profile,
        "app_id": resolved_app_id,
        "app_version": resolved_app_version,
        "action": "create_from_html",
        "context": context,
        "parent": parent,
        "executed": execute,
        "refresh_context": refresh_context,
        "context_sources": {
            "bubble_file": str(bubble_file),
            "consolelog_json_path": resolved_consolelog_path,
            "crawler_index_path": resolved_crawler_index_path,
            "mutation_overlay_path": resolved_mutation_overlay_path
            if Path(resolved_mutation_overlay_path).exists()
            else None,
        },
        "write_count": len(captured_payloads),
        "results": [{"index": index, **item} for index, item in enumerate(captured_results, start=1)],
        "logs": runtime_logs,
    }
