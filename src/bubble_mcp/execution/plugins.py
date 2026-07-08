"""Bubble plugin installation helpers."""

from __future__ import annotations

from typing import Any

from bubble_mcp.compiler.payload import bubble_session_id, change_app_setting_change
from bubble_mcp.execution.client import BubbleEditorClient, DEFAULT_DERIVED_FUNCTIONS
from bubble_mcp.sessions.store import BubbleSessionData


PLUGIN_DERIVED_FUNCTIONS: list[dict[str, Any]] = [
    {"function_name": "UserCalls", "args": [], "verbose": False},
    {"function_name": "ElementTypeToPath", "args": [], "verbose": False},
]


def normalize_plugin_key(value: str) -> str:
    """Return the Bubble plugin registry key from an element/action type."""

    key = str(value or "").strip()
    if not key:
        raise ValueError("plugin_key is required.")
    if "-" in key:
        key = key.split("-", 1)[0].strip()
    if not key:
        raise ValueError("plugin_key is required.")
    return key


def build_install_plugin_payload(
    *,
    app_id: str,
    app_version: str = "test",
    plugin_key: str,
    plugin_value: Any = True,
    installed_version: Any = 1,
    installed_version_key: str | None = None,
    include_installed_version: bool = True,
    id_counter: int | None = None,
) -> dict[str, Any]:
    """Build the Bubble /appeditor/write payload for installing a plugin."""

    normalized_key = normalize_plugin_key(plugin_key)
    target_app = str(app_id or "").strip()
    if not target_app:
        raise ValueError("app_id is required.")
    target_version = str(app_version or "test").strip() or "test"
    session_id = bubble_session_id()
    changes: list[dict[str, Any]] = [
        change_app_setting_change(
            ["settings", "client_safe", "plugins", normalized_key],
            plugin_value,
            session_id,
        )
    ]
    if include_installed_version:
        version_key = str(installed_version_key or f"{normalized_key}_installed_version").strip()
        if not version_key:
            raise ValueError("installed_version_key cannot be empty when include_installed_version=true.")
        changes.append(
            change_app_setting_change(
                ["settings", "client_safe", version_key],
                installed_version,
                session_id,
            )
        )
    if id_counter is not None:
        changes.append({"type": "id_counter", "value": int(id_counter)})
    return {
        "v": 1,
        "appname": target_app,
        "app_version": target_version,
        "appVersion": target_version,
        "changes": changes,
    }


def install_plugin(
    *,
    profile: str,
    session: BubbleSessionData,
    plugin_key: str,
    app_id: str | None = None,
    app_version: str | None = None,
    plugin_value: Any = True,
    installed_version: Any = 1,
    installed_version_key: str | None = None,
    include_installed_version: bool | None = None,
    id_counter: int | None = None,
    execute: bool = False,
    post_check_conflicts: bool = True,
    calculate_derived: bool = True,
    notify_ai_context_change: bool = True,
    client: BubbleEditorClient | None = None,
) -> dict[str, Any]:
    """Preview or execute a Bubble plugin installation."""

    editor_client = client or BubbleEditorClient()
    target_app = str(app_id or session.app_id or "").strip()
    target_version = str(app_version or session.app_version or "test").strip() or "test"
    normalized_key = normalize_plugin_key(plugin_key)
    resolved_include_installed_version = plugin_value is True if include_installed_version is None else include_installed_version
    payload = build_install_plugin_payload(
        app_id=target_app,
        app_version=target_version,
        plugin_key=normalized_key,
        plugin_value=plugin_value,
        installed_version=installed_version,
        installed_version_key=installed_version_key,
        include_installed_version=resolved_include_installed_version,
        id_counter=id_counter,
    )
    dry_run = not execute
    result: dict[str, Any] = {
        "ok": True,
        "profile": profile,
        "plugin_key": normalized_key,
        "plugin_value": plugin_value,
        "include_installed_version": resolved_include_installed_version,
        "executed": execute,
        "write_payload": payload,
        "steps": {},
    }
    write_result = editor_client.write(payload, session, dry_run=dry_run)
    result["steps"]["write"] = write_result
    result["ok"] = bool(write_result.get("ok"))

    if not result["ok"]:
        return result

    if post_check_conflicts:
        result["steps"]["get_plugin_conflicts"] = editor_client.get_plugin_conflicts(
            {"appname": target_app},
            session,
            dry_run=dry_run,
        )
        result["ok"] = result["ok"] and bool(result["steps"]["get_plugin_conflicts"].get("ok"))

    if calculate_derived:
        result["steps"]["calculate_derived"] = editor_client.calculate_derived(
            {"appname": target_app, "app_version": target_version, "derived": DEFAULT_DERIVED_FUNCTIONS},
            session,
            dry_run=dry_run,
            derived=PLUGIN_DERIVED_FUNCTIONS,
        )
        result["ok"] = result["ok"] and bool(result["steps"]["calculate_derived"].get("ok"))

    if notify_ai_context_change:
        result["steps"]["notify_ai_app_context_change"] = editor_client.notify_ai_app_context_change(
            {
                "appname": target_app,
                "appVersion": target_version,
                "changedViewIds": [],
                "globalContextChanged": True,
                "useTestEnv": target_version == "test",
            },
            session,
            dry_run=dry_run,
        )
        result["ok"] = result["ok"] and bool(result["steps"]["notify_ai_app_context_change"].get("ok"))

    result["next_action"] = (
        "Refresh Bubble context and rerun the blocked transfer plan."
        if execute and result["ok"]
        else "Review the previewed plugin install payload before executing."
    )
    return result
