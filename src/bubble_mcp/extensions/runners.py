"""Execution runners for declarative extension tools."""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from bubble_mcp.compiler.payload import bubble_element_id
from bubble_mcp.sessions.store import BubbleSessionData


@dataclass(frozen=True)
class ExtensionRunnerCompileResult:
    """Compiled runtime artifact for an extension runner."""

    ok: bool
    runner: str
    write_payload: dict[str, Any] | None = None
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


ExtensionRunner = Callable[
    [dict[str, Any], dict[str, Any], BubbleSessionData | None],
    ExtensionRunnerCompileResult,
]


def _object_arg(args: dict[str, Any], key: str) -> dict[str, Any]:
    value = args.get(key)
    return dict(value) if isinstance(value, dict) else {}


def _string_arg(args: dict[str, Any], key: str, default: str = "") -> str:
    return str(args.get(key) or default).strip()


def _value_to_bubble_param(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int | float):
        return str(value)
    return json.dumps(value, ensure_ascii=False)


def _template_defaults(template: dict[str, Any]) -> dict[str, Any]:
    defaults = template.get("defaults")
    return defaults if isinstance(defaults, dict) else {}


def _defaulted_string_arg(
    template: dict[str, Any],
    args: dict[str, Any],
    key: str,
    default: str = "",
) -> str:
    template_defaults = _template_defaults(template)
    return _string_arg(args, key) or str(template_defaults.get(key) or default).strip()


def _defaulted_object_arg(
    template: dict[str, Any],
    args: dict[str, Any],
    key: str,
) -> dict[str, Any]:
    value = args.get(key)
    if isinstance(value, dict):
        return dict(value)
    template_value = _template_defaults(template).get(key)
    return dict(template_value) if isinstance(template_value, dict) else {}


def _bubble_custom_event_argument_value(value: Any) -> Any:
    if isinstance(value, str) and value.strip().lower() in {"current user", "current_user", "currentuser"}:
        return {"%x": "CurrentUser", "%p": None, "%n": None, "is_slidable": False}
    return value


def _coerce_patch_body(value: Any, value_type: str) -> Any:
    if value_type == "integer":
        return int(value)
    if value_type == "number":
        return float(value)
    if value_type == "boolean":
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in {"1", "true", "yes", "on"}
    if value_type == "string":
        return str(value)
    return value


def _expand_path_segment(segment: object, args: dict[str, Any], metadata: dict[str, Any]) -> str:
    text = str(segment)
    if text == "{{collection_id}}":
        return str(metadata.get("collection_id") or "")
    if text == "{{call_id}}":
        return str(metadata.get("call_id") or "")
    if text.startswith("{{arg:") and text.endswith("}}"):
        arg_name = text[6:-2]
        return str(args.get(arg_name) or "")
    return text


def _apply_runner_patches(
    *,
    template: dict[str, Any],
    args: dict[str, Any],
    metadata: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    raw_patches = template.get("runner_patches")
    if not isinstance(raw_patches, list):
        return [], []
    changes: list[dict[str, Any]] = []
    warnings: list[str] = []
    for index, raw_patch in enumerate(raw_patches, start=1):
        if not isinstance(raw_patch, dict):
            warnings.append(f"runner_patches[{index}] ignored because it is not an object.")
            continue
        argument = str(raw_patch.get("argument") or raw_patch.get("when_argument") or "").strip()
        if not argument:
            warnings.append(f"runner_patches[{index}] ignored because it has no argument.")
            continue
        if argument not in args or args.get(argument) in (None, ""):
            continue
        raw_path = raw_patch.get("path_array")
        if not isinstance(raw_path, list) or not raw_path:
            warnings.append(f"runner_patches[{index}] ignored because it has no path_array.")
            continue
        path_array = [_expand_path_segment(segment, args, metadata) for segment in raw_path]
        if any(segment == "" for segment in path_array):
            warnings.append(
                f"runner_patches[{index}] ignored because one path placeholder could not be resolved."
            )
            continue
        body_value = args.get(argument)
        body_type = str(raw_patch.get("body_type") or "").strip()
        if body_type:
            try:
                body_value = _coerce_patch_body(body_value, body_type)
            except (TypeError, ValueError) as exc:
                warnings.append(f"runner_patches[{index}] ignored because {argument} could not be coerced: {exc}.")
                continue
        intent = raw_patch.get("intent") if isinstance(raw_patch.get("intent"), dict) else {"name": "ChangeAppSetting"}
        change: dict[str, Any] = {
            "intent": intent,
            "path_array": path_array,
            "body": body_value,
        }
        version_control_api_version = raw_patch.get("version_control_api_version")
        if isinstance(version_control_api_version, int):
            change["version_control_api_version"] = version_control_api_version
        raw_changelog_data = raw_patch.get("changelog_data")
        if isinstance(raw_changelog_data, list):
            change["changelog_data"] = raw_changelog_data
        changes.append(change)
    return changes, warnings


def _api_connector_param_changes(
    *,
    collection_id: str,
    call_id: str,
    group: str,
    values: dict[str, Any],
    private: bool,
) -> list[dict[str, Any]]:
    changes: list[dict[str, Any]] = []
    for key, value in values.items():
        key_text = str(key).strip()
        if not key_text:
            continue
        param_id = bubble_element_id()
        changes.append(
            {
                "intent": {"name": "ChangeAppSetting"},
                "path_array": [
                    "settings",
                    "secure",
                    "apiconnector2",
                    collection_id,
                    "calls",
                    call_id,
                    group,
                    param_id,
                ],
                "body": {"%k": key_text, "%v": _value_to_bubble_param(value)},
            }
        )
        changes.append(
            {
                "intent": {"name": "ChangeAppSetting"},
                "path_array": [
                    "settings",
                    "client_safe",
                    "apiconnector2",
                    collection_id,
                    "calls",
                    call_id,
                    group,
                    param_id,
                ],
                "body": {"private": private},
            }
        )
    return changes


def _compile_api_connector_resource_v1(
    template: dict[str, Any],
    args: dict[str, Any],
    session: BubbleSessionData | None,
) -> ExtensionRunnerCompileResult:
    runner = "api_connector_resource_v1"
    appname = _string_arg(args, "app_id") or (session.app_id if session else "") or "preview-app"
    app_version = _string_arg(args, "app_version") or (session.app_version if session else "") or "test"
    collection_id = _string_arg(args, "collection_id") or bubble_element_id()
    call_id = _string_arg(args, "call_id") or bubble_element_id()
    collection_name = _string_arg(args, "collection_name") or "Generated API Connector Collection"
    call_name = _string_arg(args, "name")
    method = _string_arg(args, "method", "GET").lower()
    url = _string_arg(args, "url")
    publish_as = _string_arg(args, "publish_as", "data")
    body_template = _string_arg(args, "body")
    headers = _object_arg(args, "headers")
    body_params = _object_arg(args, "body_params") or _object_arg(args, "initialization_values")
    query_params = _object_arg(args, "query_params")
    initialize = bool(args.get("initialize"))

    warnings: list[str] = []
    if query_params:
        warnings.append(
            "query_params are accepted in the schema but not yet compiled into the API Connector write payload."
        )
    if _string_arg(args, "authentication"):
        warnings.append("authentication is accepted in the schema but not yet compiled by this runner.")
    if initialize:
        warnings.append(
            "initialize=true sets should_reinitialize=true; automatic response schema/full_response initialization is not implemented yet."
        )

    initial_call = {
        "%nm": call_name or "API Call",
        "method": method,
        "publish_as": publish_as,
        "rank": int(args.get("rank") or 0),
        "url_cant_be_private": bool(args.get("url_cant_be_private", True)),
    }
    changes: list[dict[str, Any]] = []
    if not _string_arg(args, "collection_id"):
        changes.append(
            {
                "path_array": ["settings", "client_safe", "apiconnector2", collection_id],
                "body": {"calls": {call_id: initial_call}, "human": collection_name},
            }
        )
    changes.append(
        {
            "intent": {"name": "CreateApiCall"},
            "path_array": ["settings", "client_safe", "apiconnector2", collection_id, "calls", call_id],
            "body": initial_call,
        }
    )
    if call_name:
        changes.append(
            {
                "intent": {"name": "ChangeAppSetting"},
                "path_array": ["settings", "client_safe", "apiconnector2", collection_id, "calls", call_id, "%nm"],
                "body": call_name,
            }
        )
    if url:
        changes.append(
            {
                "intent": {"name": "ChangeAppSetting"},
                "path_array": ["settings", "client_safe", "apiconnector2", collection_id, "calls", call_id, "url"],
                "body": url,
            }
        )
    if method:
        changes.append(
            {
                "intent": {"name": "ChangeAppSetting"},
                "path_array": ["settings", "client_safe", "apiconnector2", collection_id, "calls", call_id, "method"],
                "body": method,
            }
        )
    if body_template:
        changes.append(
            {
                "intent": {"name": "ChangeAppSetting"},
                "path_array": ["settings", "client_safe", "apiconnector2", collection_id, "calls", call_id, "%b3"],
                "body": body_template,
            }
        )
    changes.extend(
        _api_connector_param_changes(
            collection_id=collection_id,
            call_id=call_id,
            group="body_params",
            values=body_params,
            private=True,
        )
    )
    changes.extend(
        _api_connector_param_changes(
            collection_id=collection_id,
            call_id=call_id,
            group="headers",
            values=headers,
            private=True,
        )
    )
    if url or body_template or body_params or headers or initialize:
        changes.append(
            {
                "intent": {"name": "ChangeAppSetting"},
                "path_array": [
                    "settings",
                    "client_safe",
                    "apiconnector2",
                    collection_id,
                    "calls",
                    call_id,
                    "should_reinitialize",
                ],
                "body": True,
            }
        )
    metadata = {
        "collection_id": collection_id,
        "call_id": call_id,
        "family": str(template.get("family") or ""),
    }
    patch_changes, patch_warnings = _apply_runner_patches(
        template=template,
        args=args,
        metadata=metadata,
    )
    changes.extend(patch_changes)
    warnings.extend(patch_warnings)
    return ExtensionRunnerCompileResult(
        ok=True,
        runner=runner,
        write_payload={
            "appname": appname,
            "app_version": app_version,
            "appVersion": app_version,
            "changes": changes,
        },
        warnings=warnings,
        metadata=metadata,
    )


def _compile_trigger_custom_event_v1(
    template: dict[str, Any],
    args: dict[str, Any],
    session: BubbleSessionData | None,
) -> ExtensionRunnerCompileResult:
    runner = "trigger_custom_event_v1"
    appname = _string_arg(args, "app_id") or (session.app_id if session else "") or "preview-app"
    app_version = _string_arg(args, "app_version") or (session.app_version if session else "") or "test"
    page_id = _defaulted_string_arg(template, args, "page_id")
    workflow_key = (
        _defaulted_string_arg(template, args, "workflow_key")
        or _defaulted_string_arg(template, args, "event_key")
    )
    event_id = (
        _defaulted_string_arg(template, args, "event_id")
        or _defaulted_string_arg(template, args, "event_ref")
    )
    custom_event_id = (
        _defaulted_string_arg(template, args, "custom_event_id")
        or _defaulted_string_arg(template, args, "custom_event")
    )
    action_id = _defaulted_string_arg(template, args, "action_id") or bubble_element_id()
    action_index = _defaulted_string_arg(template, args, "action_index", "1")
    existing_action_id = _defaulted_string_arg(template, args, "existing_action_id")
    existing_action_index = _defaulted_string_arg(template, args, "existing_action_index", "0")
    existing_action_type = _defaulted_string_arg(template, args, "existing_action_type", "ShowElement")
    existing_element_id = _defaulted_string_arg(template, args, "existing_element_id")
    id_counter = args.get("id_counter") or _template_defaults(template).get("id_counter")

    errors: list[str] = []
    if not page_id:
        errors.append("page_id is required unless the template provides a default.")
    if not workflow_key:
        errors.append("workflow_key is required unless the template provides a default.")
    if not event_id:
        errors.append("event_id/event_ref is required unless the template provides a default.")
    if not custom_event_id:
        errors.append("custom_event_id/custom_event is required unless the template provides a default.")
    if errors:
        return ExtensionRunnerCompileResult(ok=False, runner=runner, errors=errors)

    param_ids = _defaulted_object_arg(template, args, "param_ids")
    argument_values = _object_arg(args, "arguments") or _object_arg(args, "argument_values")
    arguments_body: dict[str, Any] = {}
    for index, (name, param_id) in enumerate(param_ids.items()):
        item: dict[str, Any] = {"param_id": str(param_id)}
        if name in argument_values:
            item["arg_value"] = _bubble_custom_event_argument_value(argument_values[name])
        arguments_body[str(index)] = item

    actions_body: dict[str, Any] = {}
    if existing_action_id:
        existing_action: dict[str, Any] = {"%x": existing_action_type, "id": existing_action_id}
        if existing_element_id:
            existing_action["%p"] = {"%ei": existing_element_id}
        actions_body[str(existing_action_index)] = existing_action
    actions_body[str(action_index)] = {
        "%x": "TriggerCustomEvent",
        "%p": {"custom_event": custom_event_id, "arguments": arguments_body},
        "id": action_id,
    }

    workflow_path = ["%p3", page_id, "%wf", workflow_key]
    action_path = [*workflow_path, "actions", str(action_index)]
    changes: list[dict[str, Any]] = []
    if existing_action_id:
        changes.append(
            {
                "body": f"%p3.{page_id}.%wf.{workflow_key}.actions.{existing_action_index}",
                "path_array": ["_index", "id_to_path", existing_action_id],
                "intent": {"name": "Update index"},
                "version_control_api_version": 4,
                "changelog_data": [],
            }
        )
    changes.extend(
        [
            {
                "body": f"%p3.{page_id}.%wf.{workflow_key}.actions.{action_index}",
                "path_array": ["_index", "id_to_path", action_id],
                "intent": {"name": "Update index"},
                "version_control_api_version": 4,
                "changelog_data": [],
            },
            {
                "body": actions_body,
                "path_array": [*workflow_path, "actions"],
                "intent": {"name": "CreateAction", "id": 16, "source_appname": ""},
                "version_control_api_version": 4,
                "changelog_data": [],
            },
            {
                "body": custom_event_id,
                "path_array": [*action_path, "%p", "custom_event"],
                "intent": {"name": "SetData", "id": 18, "source_appname": ""},
                "version_control_api_version": 4,
                "changelog_data": [],
            },
            {
                "body": arguments_body,
                "path_array": [*action_path, "%p", "arguments"],
                "intent": {"name": "SetData", "id": 19, "source_appname": ""},
                "version_control_api_version": 4,
                "changelog_data": [],
            },
            {
                "body": "[]",
                "path_array": ["_index", "issues_list", event_id],
                "intent": {"name": "Update index"},
                "version_control_api_version": 4,
                "changelog_data": [],
            },
        ]
    )
    if isinstance(id_counter, int):
        changes.append({"type": "id_counter", "value": id_counter})

    return ExtensionRunnerCompileResult(
        ok=True,
        runner=runner,
        write_payload={
            "appname": appname,
            "app_version": app_version,
            "appVersion": app_version,
            "changes": changes,
        },
        metadata={
            "page_id": page_id,
            "workflow_key": workflow_key,
            "event_id": event_id,
            "action_id": action_id,
            "custom_event_id": custom_event_id,
            "param_ids": param_ids,
        },
    )


def _template_family(template: dict[str, Any]) -> str:
    return str(template.get("family") or "").lower().strip()


def _runner_id(template: dict[str, Any]) -> str:
    runner = str(template.get("runner") or "").strip()
    if runner:
        return runner
    family = _template_family(template)
    if family in {"api_connector", "api-connector"} or "api_connector" in family:
        return "api_connector_resource_v1"
    return ""


RUNNERS: dict[str, ExtensionRunner] = {
    "api_connector_resource_v1": _compile_api_connector_resource_v1,
    "trigger_custom_event_v1": _compile_trigger_custom_event_v1,
}


def compile_extension_runner(
    template: dict[str, Any],
    args: dict[str, Any],
    *,
    session: BubbleSessionData | None = None,
) -> ExtensionRunnerCompileResult | None:
    """Compile an extension template through its declared runner."""

    runner = _runner_id(template)
    if not runner:
        return None
    compiler = RUNNERS.get(runner)
    if compiler is None:
        return ExtensionRunnerCompileResult(
            ok=False,
            runner=runner,
            errors=[f"Unknown extension runner: {runner}"],
        )
    return compiler(template, args, session)
