"""Run Aria's advanced HTML-to-Bubble importer inside the standalone package."""

from __future__ import annotations

import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from typing import Any

from bubble_mcp.context.detector import detect_project_context
from bubble_mcp.core.config import load_settings, resolve_profile
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
        force=execute,
    )
    bubble_file = detected.context_path.with_name(f"{resolved_app_id}.bubble")
    if not bubble_file.exists():
        raise ValueError(f"Bubble export not found for Aria runtime: {bubble_file}")
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
    original_send = bubble_sdk.PayloadBuilder.send_to_webhook

    def send_to_local_bubble(builder: Any, _url: str = "") -> Any:
        write_payload = builder.build()
        captured_payloads.append(write_payload)
        if not execute:
            captured_results.append({"ok": True, "executed": False, "dry_run": True, "payload": write_payload})
            return {"ok": True, "dry_run": True}
        assert session is not None
        result = BubbleEditorClient().write(write_payload, session, dry_run=False)
        captured_results.append({"ok": bool(result.get("ok")), "executed": True, "result": result})
        if not result.get("ok"):
            raise RuntimeError(str(result.get("error") or result.get("reason") or "Bubble write failed"))
        return result

    stdout = StringIO()
    stderr = StringIO()
    try:
        bubble_sdk.PayloadBuilder.send_to_webhook = send_to_local_bubble
        with redirect_stdout(stdout), redirect_stderr(stderr):
            cli = bubble_cli.BubbleCLI(
                app_json_path=str(bubble_file),
                appname=resolved_app_id,
                webhook_url="local://bubble-mcp",
                profile_name=profile,
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
        if temp_path is not None:
            try:
                temp_path.unlink()
            except Exception:
                pass

    if not success:
        raise RuntimeError("Aria HTML import runtime failed.")

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
        "write_count": len(captured_payloads),
        "results": [{"index": index, **item} for index, item in enumerate(captured_results, start=1)],
        "logs": "\n".join(part for part in (stdout.getvalue().strip(), stderr.getvalue().strip()) if part),
    }
