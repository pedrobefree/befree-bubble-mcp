"""Preview-first scheduled deploy workflow."""

from __future__ import annotations

import hashlib
import json
import re
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable
from zoneinfo import ZoneInfo

from bubble_mcp.browser_automation.models import ScheduledDeployPreview, ScheduledDeployRecord
from bubble_mcp.browser_automation.store import (
    append_history,
    delete_preview,
    delete_scheduled_record,
    evidence_dir,
    list_all_scheduled_records,
    list_history_records,
    list_scheduled_records,
    load_preview,
    load_scheduled_record,
    save_preview,
    save_scheduled_record,
)
from bubble_mcp.context.path_api import BubblePathApiClient, PathResult
from bubble_mcp.core.config import load_settings, resolve_profile
from bubble_mcp.core.redaction import redact_sensitive
from bubble_mcp.execution.client import BubbleEditorClient
from bubble_mcp.execution.editor_api import BubbleEditorApiClient, deploy_app_test_and_hotfix
from bubble_mcp.sessions.browser import _bubble_cookie_header
from bubble_mcp.sessions.store import BubbleSessionData, load_session, save_session, session_from_payload

APP_VERSION = "test"
DEPLOY_TRIGGER_SELECTOR = '[itemid="deploy-to-live"]'
DEPLOY_DESCRIPTION_SELECTOR = (
    'textarea[aria-labelledby="deploy-description-label"], '
    'textarea[placeholder="Add a short description that describes any new changes"], '
    'textarea[placeholder*="description" i], '
    'textarea[placeholder*="short" i]'
)

_timers_lock = threading.Lock()
_timers: dict[str, threading.Timer] = {}
_POPUP_INVALID_CUSTOM_STYLE_RE = re.compile(r"^Popup .+ - None \(Custom\) is not a possible option$")


def _now() -> datetime:
    return datetime.now(UTC)


def _now_iso() -> str:
    return _now().replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _local_timezone() -> str:
    local = datetime.now().astimezone().tzinfo
    key = getattr(local, "key", None)
    if key:
        return str(key)
    name = datetime.now().astimezone().tzname()
    return str(name or "local")


def _parse_datetime(value: str, timezone_name: str) -> datetime:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("scheduled_at is required.")
    normalized = raw.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError as exc:
        raise ValueError("scheduled_at must be an ISO datetime.") from exc
    if parsed.tzinfo is None:
        try:
            parsed = parsed.replace(tzinfo=ZoneInfo(timezone_name))
        except Exception:
            parsed = parsed.astimezone().replace(tzinfo=datetime.now().astimezone().tzinfo)
    return parsed.astimezone(UTC)


def _id(prefix: str, *parts: str) -> str:
    stamp = _now().strftime("%Y%m%d_%H%M%S")
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:8]
    return f"{prefix}_{stamp}_{digest}"


def _resolve_profile(profile_name: str) -> tuple[str, str]:
    settings = load_settings()
    profile = resolve_profile(settings, profile_name)
    if profile is None:
        raise ValueError(f"Unknown profile: {profile_name}")
    return profile.name, profile.app_id


def _timer_key(profile: str, deploy_id: str) -> str:
    return f"{profile}:{deploy_id}"


def _arm_timer(record: ScheduledDeployRecord, executor: Callable[[ScheduledDeployRecord], dict[str, Any]] | None) -> None:
    if executor is None:
        return
    scheduled_at = datetime.fromisoformat(record.scheduled_at.replace("Z", "+00:00"))
    delay = max(0.0, (scheduled_at - _now()).total_seconds())
    key = _timer_key(record.profile, record.deploy_id)

    def run() -> None:
        with _timers_lock:
            _timers.pop(key, None)
        result = executor(record)
        status = "executed" if result.get("ok") else "failed"
        finished = ScheduledDeployRecord(
            **{
                **record.to_dict(),
                "status": status,
                "updated_at": _now_iso(),
                "executed_at": _now_iso(),
                "error": str(result.get("error") or "") or None,
                "evidence_dir": str(evidence_dir(record.profile, record.deploy_id)),
            }
        )
        delete_scheduled_record(record.profile, record.deploy_id)
        append_history(record.profile, finished.to_dict())

    timer = threading.Timer(delay, run)
    timer.daemon = True
    with _timers_lock:
        previous = _timers.get(key)
        if previous:
            previous.cancel()
        _timers[key] = timer
    timer.start()


def rearm_scheduled_deploys(
    executor: Callable[[ScheduledDeployRecord], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    resolved_executor = executor or execute_scheduled_deploy
    records = list_all_scheduled_records()
    for record in records:
        _arm_timer(record, resolved_executor)
    return {"ok": True, "armed": len(records), "deploy_ids": [record.deploy_id for record in records]}


def schedule_deploy(
    *,
    profile: str,
    scheduled_at: str,
    message: str,
    execute: bool = False,
    confirm: bool = False,
    preview_id: str | None = None,
    retry_count: int = 0,
    headless: bool = False,
    wait_seconds: int = 120,
    auto_fix_objective_issues: bool = False,
    executor: Callable[[ScheduledDeployRecord], dict[str, Any]] | None = None,
) -> dict[str, Any]:
    resolved_profile, app_id = _resolve_profile(profile)
    clean_message = str(message or "").strip()
    if not clean_message:
        raise ValueError("message is required.")
    timezone_name = _local_timezone()
    scheduled_dt = _parse_datetime(scheduled_at, timezone_name)
    normalized_scheduled_at = scheduled_dt.replace(microsecond=0).isoformat().replace("+00:00", "Z")
    retry = max(0, int(retry_count or 0))
    wait = max(1, int(wait_seconds or 120))

    if not execute:
        preview = ScheduledDeployPreview(
            preview_id=_id("deploy_preview", resolved_profile, app_id, normalized_scheduled_at, clean_message),
            profile=resolved_profile,
            app_id=app_id,
            app_version=APP_VERSION,
            scheduled_at=normalized_scheduled_at,
            timezone=timezone_name,
            message=clean_message,
            retry_count=retry,
            headless=bool(headless),
            wait_seconds=wait,
            auto_fix_objective_issues=bool(auto_fix_objective_issues),
            created_at=_now_iso(),
        )
        path = save_preview(preview)
        return {
            "ok": True,
            "mode": "preview",
            "preview": preview.to_dict(),
            "preview_path": str(path),
            "confirmation_required": True,
            "next_mcp_call": {
                "tool": "bubble_schedule_deploy",
                "arguments": {
                    "profile": resolved_profile,
                    "scheduled_at": normalized_scheduled_at,
                    "message": clean_message,
                    "execute": True,
                    "confirm": True,
                    "preview_id": preview.preview_id,
                    "auto_fix_objective_issues": preview.auto_fix_objective_issues,
                },
            },
        }

    if not confirm:
        return {"ok": False, "error": "scheduled_deploy_requires_confirmation", "confirmation_required": True}
    if not preview_id:
        return {"ok": False, "error": "scheduled_deploy_requires_preview_id", "confirmation_required": True}
    preview = load_preview(resolved_profile, preview_id)
    if preview.app_id != app_id or preview.message != clean_message or preview.scheduled_at != normalized_scheduled_at:
        return {"ok": False, "error": "scheduled_deploy_preview_mismatch", "confirmation_required": True}

    deploy_id = _id("deploy", resolved_profile, app_id, normalized_scheduled_at, clean_message)
    created_at = _now_iso()
    record = ScheduledDeployRecord(
        deploy_id=deploy_id,
        profile=resolved_profile,
        app_id=app_id,
        app_version=APP_VERSION,
        scheduled_at=normalized_scheduled_at,
        timezone=preview.timezone,
        message=clean_message,
        retry_count=preview.retry_count,
        headless=preview.headless,
        wait_seconds=preview.wait_seconds,
        auto_fix_objective_issues=preview.auto_fix_objective_issues,
        status="scheduled",
        created_at=created_at,
        updated_at=created_at,
        preview_id=preview.preview_id,
    )
    path = save_scheduled_record(record)
    append_history(resolved_profile, {**record.to_dict(), "event": "scheduled"})
    delete_preview(resolved_profile, preview.preview_id)
    _arm_timer(record, executor or execute_scheduled_deploy)
    return {
        "ok": True,
        "mode": "scheduled",
        "deploy": record.to_dict(),
        "deploy_path": str(path),
        "history_path": str(path.parent.parent / "history.jsonl"),
    }


def list_scheduled_deploys(*, profile: str) -> dict[str, Any]:
    resolved_profile, _app_id = _resolve_profile(profile)
    records = [record.to_dict() for record in list_scheduled_records(resolved_profile)]
    return {"ok": True, "profile": resolved_profile, "scheduled": records, "count": len(records)}


def cancel_scheduled_deploy(*, profile: str, deploy_id: str) -> dict[str, Any]:
    resolved_profile, _app_id = _resolve_profile(profile)
    record = load_scheduled_record(resolved_profile, deploy_id)
    key = _timer_key(resolved_profile, deploy_id)
    with _timers_lock:
        timer = _timers.pop(key, None)
        if timer:
            timer.cancel()
    cancelled = ScheduledDeployRecord(
        **{
            **record.to_dict(),
            "status": "cancelled",
            "updated_at": _now_iso(),
            "cancelled_at": _now_iso(),
        }
    )
    delete_scheduled_record(resolved_profile, deploy_id)
    append_history(resolved_profile, {**cancelled.to_dict(), "event": "cancelled"})
    return {"ok": True, "profile": resolved_profile, "cancelled": True, "deploy": cancelled.to_dict()}


def deploy_history(*, profile: str, limit: int = 50, include_cancelled: bool = True) -> dict[str, Any]:
    resolved_profile, _app_id = _resolve_profile(profile)
    records = list_history_records(resolved_profile, limit=limit, include_cancelled=include_cancelled)
    return {"ok": True, "profile": resolved_profile, "history": records, "count": len(records)}


def write_evidence(profile: str, deploy_id: str, payload: dict[str, Any]) -> Path:
    directory = evidence_dir(profile, deploy_id)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "result.json"
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def _json_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            return []
        return decoded if isinstance(decoded, list) else []
    return []


def _encoded_path_array(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item) for item in value if str(item)]
    if isinstance(value, str):
        return [part for part in value.split(".") if part]
    return []


def _issue_message(issue: dict[str, Any]) -> str:
    return str(issue.get("message") or issue.get("m") or "").strip()


def _issue_path_array(issue: dict[str, Any]) -> list[str]:
    node = issue.get("node")
    if not isinstance(node, dict):
        return []
    args = node.get("args")
    if not isinstance(args, list):
        return []
    for arg in args:
        if not isinstance(arg, dict) or arg.get("type") != "json":
            continue
        path_array = _encoded_path_array(arg.get("value"))
        if path_array:
            return path_array
    return []


def _issue_summary(issue: dict[str, Any]) -> dict[str, Any]:
    return {
        "issue_id": str(issue.get("issue_id") or ""),
        "message": _issue_message(issue),
        "path_array": _issue_path_array(issue),
    }


def _load_index_deploy_issues(api: BubblePathApiClient) -> list[dict[str, Any]]:
    issues_result = api.resolve_path(["_index", "issues_list"])
    issues_by_id = issues_result.data if issues_result.type == "data" and isinstance(issues_result.data, dict) else {}
    if not issues_by_id:
        return []

    page_names_result = api.resolve_path(["_index", "page_name_to_id"])
    page_names = page_names_result.data if page_names_result.type == "data" and isinstance(page_names_result.data, dict) else {}
    index_page_id = str(page_names.get("index") or "").strip()

    issues_sub_result = api.resolve_path(["_index", "issues_sub"])
    issues_sub = issues_sub_result.data if issues_sub_result.type == "data" and isinstance(issues_sub_result.data, dict) else {}
    child_issue_ids = [str(item) for item in _json_list(issues_sub.get(index_page_id)) if str(item)] if index_page_id else []
    issue_ids = ([index_page_id] if index_page_id else []) + child_issue_ids
    if not issue_ids:
        issue_ids = [str(key) for key in issues_by_id.keys()]

    issues: list[dict[str, Any]] = []
    for issue_id in issue_ids:
        for entry in _json_list(issues_by_id.get(issue_id)):
            if not isinstance(entry, dict) or not _issue_message(entry):
                continue
            issues.append({"issue_id": issue_id, **entry})
    return issues


def _classify_objective_issue_fixes(
    api: BubblePathApiClient,
    issues: list[dict[str, Any]],
) -> dict[str, Any]:
    candidates: list[dict[str, Any]] = []
    unsupported: list[dict[str, Any]] = []

    for issue in issues:
        message = _issue_message(issue)
        path_array = _issue_path_array(issue)
        if (
            _POPUP_INVALID_CUSTOM_STYLE_RE.match(message)
            and len(path_array) >= 2
            and path_array[-1] == "%s1"
            and "%el" in path_array
        ):
            candidates.append({**_issue_summary(issue), "kind": "popup_invalid_custom_style"})
        else:
            unsupported.append(_issue_summary(issue))

    if unsupported:
        return {"ok": False, "fixes": [], "unsupported_issues": unsupported}
    if not candidates:
        return {"ok": True, "fixes": [], "unsupported_issues": []}

    _last_change, current_values = api.resolve_multiple([candidate["path_array"] for candidate in candidates])
    fixes: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    for index, candidate in enumerate(candidates):
        current = current_values[index] if index < len(current_values) else PathResult(type="error", message="missing result")
        current_value = current.data if isinstance(current, PathResult) and current.type == "data" else None
        if isinstance(current_value, str) and current_value.strip():
            fixes.append(
                {
                    **candidate,
                    "previous_value": current_value,
                    "new_value": None,
                }
            )
        else:
            unresolved.append(
                {
                    **candidate,
                    "reason": "style_slot_did_not_contain_an_invalid_style_reference",
                    "current_type": current.type if isinstance(current, PathResult) else type(current).__name__,
                    "current_value": current_value,
                }
            )

    return {"ok": not unresolved, "fixes": fixes, "unsupported_issues": unresolved}


def _objective_issue_fix_payload(app_id: str, fixes: list[dict[str, Any]]) -> dict[str, Any]:
    changes: list[dict[str, Any]] = []
    for index, fix in enumerate(fixes, start=1):
        changes.append(
            {
                "intent": {"name": "SetData", "id": 910000 + index, "source_appname": ""},
                "path_array": fix["path_array"],
                "body": None,
                "version_control_api_version": 4,
                "changelog_data": [],
            }
        )
    return {"appname": app_id, "version": APP_VERSION, "changes": changes}


def auto_fix_objective_deploy_issues(
    *,
    profile: str,
    app_id: str,
    session: BubbleSessionData,
    api: BubblePathApiClient | None = None,
    editor_client: BubbleEditorClient | None = None,
) -> dict[str, Any]:
    path_api = api or BubblePathApiClient(app_id=app_id, app_version=APP_VERSION, session=session)
    issues_before = _load_index_deploy_issues(path_api)
    before_summary = [_issue_summary(issue) for issue in issues_before]
    if not issues_before:
        return {
            "ok": True,
            "fixes_applied": False,
            "issues_before": [],
            "issues_after": [],
            "fixes": [],
        }

    plan = _classify_objective_issue_fixes(path_api, issues_before)
    if not plan.get("ok"):
        return {
            "ok": False,
            "error": "scheduled_deploy_unfixable_bubble_issues",
            "issues_before": before_summary,
            "unsupported_issues": plan.get("unsupported_issues", []),
            "fixes": plan.get("fixes", []),
        }

    fixes = [fix for fix in plan.get("fixes", []) if isinstance(fix, dict)]
    if not fixes:
        return {
            "ok": True,
            "fixes_applied": False,
            "issues_before": before_summary,
            "issues_after": before_summary,
            "fixes": [],
        }

    payload = _objective_issue_fix_payload(app_id, fixes)
    write_result = (editor_client or BubbleEditorClient()).write(
        payload,
        session,
        dry_run=False,
        calculate_derived=True,
    )
    if not write_result.get("ok"):
        return {
            "ok": False,
            "error": "scheduled_deploy_objective_issue_fix_failed",
            "issues_before": before_summary,
            "fixes": fixes,
            "write_result": redact_sensitive(write_result),
        }

    issues_after = _load_index_deploy_issues(path_api)
    after_summary = [_issue_summary(issue) for issue in issues_after]
    return {
        "ok": not issues_after,
        "error": "scheduled_deploy_objective_issue_fix_unresolved" if issues_after else None,
        "fixes_applied": True,
        "issues_before": before_summary,
        "issues_after": after_summary,
        "fixes": fixes,
        "write_result": redact_sensitive(write_result),
    }


def _editor_url(app_id: str) -> str:
    return f"https://bubble.io/page?name=index&id={app_id}&version={APP_VERSION}"


def _visible_deploy_button_script() -> str:
    return """
        () => {
          const textarea = document.querySelector('__DEPLOY_DESCRIPTION_SELECTOR__');
          if (!textarea) throw new Error('Deploy description textarea not found before confirm click');
          const textareaRect = textarea.getBoundingClientRect();
          const buttons = Array.from(document.querySelectorAll('button[aria-label="Deploy"], button[arialabel="Deploy"], button'));
          const candidates = buttons
            .filter((candidate) =>
              candidate.offsetParent !== null &&
              (
                candidate.getAttribute('aria-label') === 'Deploy' ||
                candidate.getAttribute('arialabel') === 'Deploy' ||
                (candidate.innerText && candidate.innerText.trim() === 'Deploy')
              )
            )
            .map((candidate) => ({
              node: candidate,
              rect: candidate.getBoundingClientRect(),
            }));
          const buttonMatch = candidates.find((candidate) =>
            candidate.rect.top >= textareaRect.bottom - 8 &&
            candidate.rect.left >= textareaRect.left
          ) || candidates[candidates.length - 1];
          const button = buttonMatch ? buttonMatch.node : null;
          if (!button) throw new Error('Deploy confirm button not found');
          if (button.disabled || button.getAttribute('aria-disabled') === 'true') {
            throw new Error('Deploy confirm button is disabled');
          }
          button.click();
        }
    """.replace("__DEPLOY_DESCRIPTION_SELECTOR__", DEPLOY_DESCRIPTION_SELECTOR)


def _deploy_completion_script() -> str:
    return f"""
        () => {{
          const textarea = document.querySelector('{DEPLOY_DESCRIPTION_SELECTOR}');
          const visibleTextarea = Boolean(textarea && textarea.offsetParent !== null);
          const text = document.body ? document.body.innerText || '' : '';
          const successText = /deployed|deployment|live|success/i.test(text);
          return !visibleTextarea || successText;
        }}
    """


def _editor_ready_script() -> str:
    return f"""
        () => {{
          const bodyText = document.body ? document.body.innerText || '' : '';
          const loading = bodyText.includes("We're loading your app");
          const trigger = document.querySelector('{DEPLOY_TRIGGER_SELECTOR}');
          return Boolean(trigger && trigger.offsetParent !== null && !loading);
        }}
    """


def _deploy_modal_state_script() -> str:
    return f"""
        () => {{
          const text = document.body ? document.body.innerText || '' : '';
          const textarea = document.querySelector('{DEPLOY_DESCRIPTION_SELECTOR}');
          const buttons = Array.from(document.querySelectorAll('button[aria-label="Deploy"], button[arialabel="Deploy"], button'));
          const deployButtons = buttons
            .filter((button) => button.offsetParent !== null)
            .filter((button) =>
              button.getAttribute('aria-label') === 'Deploy' ||
              button.getAttribute('arialabel') === 'Deploy' ||
              (button.innerText && button.innerText.trim() === 'Deploy')
            )
            .map((button) => ({{
              text: button.innerText || '',
              disabled: Boolean(button.disabled || button.getAttribute('aria-disabled') === 'true'),
              ariaLabel: button.getAttribute('aria-label') || button.getAttribute('arialabel') || '',
            }}));
          const issuePatterns = [
            /issue/i,
            /issues/i,
            /fix/i,
            /error/i,
            /cannot deploy/i,
            /can't deploy/i,
            /resolve/i,
            /validation/i,
          ];
          const hasIssueText = issuePatterns.some((pattern) => pattern.test(text));
          return {{
            hasTextarea: Boolean(textarea && textarea.offsetParent !== null),
            deployButtons,
            hasIssueText,
            bodySnippet: text.replace(/\\s+/g, ' ').slice(0, 1200),
          }};
        }}
    """


def _deploy_blocker_error(state: dict[str, Any]) -> str:
    deploy_buttons = state.get("deployButtons") if isinstance(state.get("deployButtons"), list) else []
    disabled_deploy = any(bool(button.get("disabled")) for button in deploy_buttons if isinstance(button, dict))
    snippet = str(state.get("bodySnippet") or "").strip()
    if "temporary error deploying your app" in snippet.lower():
        return (
            "scheduled_deploy_temporary_bubble_error: Bubble reported a temporary error while deploying the app. "
            f"Visible page text: {snippet}"
        )
    if state.get("hasIssueText") or disabled_deploy:
        return (
            "scheduled_deploy_blocked_by_bubble_issues: Bubble did not expose the deploy description textarea. "
            "The deploy modal appears blocked by app issues or validation. "
            f"Visible page text: {snippet}"
        )
    return (
        "scheduled_deploy_modal_not_ready: Bubble did not expose the deploy description textarea after clicking deploy. "
        f"Visible page text: {str(state.get('bodySnippet') or '').strip()}"
    )


def _browser_session(
    *,
    context: Any,
    page: Any,
    record: ScheduledDeployRecord,
    editor_url: str,
    captured_headers: dict[str, str],
) -> BubbleSessionData | None:
    cookie_header = _bubble_cookie_header(context)
    if not cookie_header:
        return None
    user_agent = str(page.evaluate("() => navigator.userAgent") or "befree-bubble-mcp")
    return session_from_payload(
        {
            "appId": record.app_id,
            "url": editor_url,
            "headers": {
                "Cookie": cookie_header,
                "User-Agent": user_agent,
                **captured_headers,
            },
            "appVersion": APP_VERSION,
            "source": "scheduled_deploy_browser",
        }
    )


def _deploy_issue_preflight(
    record: ScheduledDeployRecord,
    session: BubbleSessionData,
    *,
    path_api: BubblePathApiClient | None = None,
    editor_client: BubbleEditorClient | None = None,
) -> dict[str, Any]:
    api = path_api or BubblePathApiClient(app_id=record.app_id, app_version=APP_VERSION, session=session)
    if record.auto_fix_objective_issues:
        return auto_fix_objective_deploy_issues(
            profile=record.profile,
            app_id=record.app_id,
            session=session,
            api=api,
            editor_client=editor_client,
        )

    issues = _load_index_deploy_issues(api)
    issue_summary = [_issue_summary(issue) for issue in issues]
    return {
        "ok": not issues,
        "fixes_applied": False,
        "issues_before": issue_summary,
        "issues_after": issue_summary,
        "fixes": [],
        **({"error": "scheduled_deploy_blocked_by_bubble_issues"} if issues else {}),
    }


def execute_scheduled_deploy_direct(
    record: ScheduledDeployRecord,
    *,
    api_client: BubbleEditorApiClient | None = None,
    editor_client: BubbleEditorClient | None = None,
    path_api: BubblePathApiClient | None = None,
) -> dict[str, Any]:
    """Execute a scheduled deploy through the authenticated editor deploy endpoint."""

    evidence = evidence_dir(record.profile, record.deploy_id)
    evidence.mkdir(parents=True, exist_ok=True)
    session = load_session(record.profile)
    objective_issue_preflight: dict[str, Any] | None = None
    if session is None:
        result = {
            "ok": False,
            "deploy_id": record.deploy_id,
            "profile": record.profile,
            "app_id": record.app_id,
            "app_version": APP_VERSION,
            "deployment_mode": "direct",
            "error": f"No Bubble session stored for profile '{record.profile}'.",
            "reason": "missing_session",
            "evidence_dir": str(evidence),
        }
        write_evidence(record.profile, record.deploy_id, redact_sensitive(result))
        return result

    try:
        objective_issue_preflight = _deploy_issue_preflight(
            record,
            session,
            path_api=path_api,
            editor_client=editor_client,
        )
        if not objective_issue_preflight.get("ok"):
            result = {
                "ok": False,
                "deploy_id": record.deploy_id,
                "profile": record.profile,
                "app_id": record.app_id,
                "app_version": APP_VERSION,
                "deployment_mode": "direct",
                "error": objective_issue_preflight.get("error") or "scheduled_deploy_blocked_by_bubble_issues",
                "reason": "bubble_issues",
                "evidence_dir": str(evidence),
                "objective_issue_preflight": redact_sensitive(objective_issue_preflight),
            }
            write_evidence(record.profile, record.deploy_id, redact_sensitive(result))
            return result

        deploy_result = deploy_app_test_and_hotfix(
            profile=record.profile,
            app_id=record.app_id,
            message=record.message,
            from_app_version=APP_VERSION,
            force_deploy=False,
            deploy_mobile=False,
            execute=True,
            client=api_client,
        )
        if not deploy_result.get("ok"):
            result = {
                "ok": False,
                "deploy_id": record.deploy_id,
                "profile": record.profile,
                "app_id": record.app_id,
                "app_version": APP_VERSION,
                "deployment_mode": "direct",
                "error": "scheduled_deploy_direct_endpoint_failed",
                "reason": deploy_result.get("reason") or "deploy_endpoint_failed",
                "status": deploy_result.get("status"),
                "evidence_dir": str(evidence),
                "objective_issue_preflight": redact_sensitive(objective_issue_preflight),
                "direct_deploy": redact_sensitive(deploy_result),
            }
            write_evidence(record.profile, record.deploy_id, redact_sensitive(result))
            return result

        result = {
            "ok": True,
            "deploy_id": record.deploy_id,
            "profile": record.profile,
            "app_id": record.app_id,
            "app_version": APP_VERSION,
            "deployment_mode": "direct",
            "deployed_at": _now_iso(),
            "evidence_dir": str(evidence),
            "session_refreshed": False,
            "objective_issue_preflight": redact_sensitive(objective_issue_preflight),
            "direct_deploy": redact_sensitive(deploy_result),
        }
        write_evidence(record.profile, record.deploy_id, redact_sensitive(result))
        return result
    except RuntimeError as exc:
        reason = "session_expired" if "session expired" in str(exc).lower() else "direct_deploy_error"
        result = {
            "ok": False,
            "deploy_id": record.deploy_id,
            "profile": record.profile,
            "app_id": record.app_id,
            "app_version": APP_VERSION,
            "deployment_mode": "direct",
            "error": str(exc),
            "reason": reason,
            "error_class": exc.__class__.__name__,
            "evidence_dir": str(evidence),
            **(
                {"objective_issue_preflight": redact_sensitive(objective_issue_preflight)}
                if objective_issue_preflight is not None
                else {}
            ),
        }
        write_evidence(record.profile, record.deploy_id, redact_sensitive(result))
        return result
    except Exception as exc:
        reason = "auth_blocked" if "blocked context api" in str(exc).lower() else "direct_deploy_error"
        result = {
            "ok": False,
            "deploy_id": record.deploy_id,
            "profile": record.profile,
            "app_id": record.app_id,
            "app_version": APP_VERSION,
            "deployment_mode": "direct",
            "error": str(exc),
            "reason": reason,
            "error_class": exc.__class__.__name__,
            "evidence_dir": str(evidence),
            **(
                {"objective_issue_preflight": redact_sensitive(objective_issue_preflight)}
                if objective_issue_preflight is not None
                else {}
            ),
        }
        write_evidence(record.profile, record.deploy_id, redact_sensitive(result))
        return result


def _should_fallback_to_browser(result: dict[str, Any]) -> bool:
    return str(result.get("reason") or "") in {"missing_session", "auth_blocked", "session_expired"}


def execute_scheduled_deploy(record: ScheduledDeployRecord) -> dict[str, Any]:
    """Execute a scheduled deploy directly, falling back to browser when needed."""

    direct_result = execute_scheduled_deploy_direct(record)
    if direct_result.get("ok") or not _should_fallback_to_browser(direct_result):
        return direct_result
    browser_result = _execute_scheduled_deploy_browser(record)
    browser_result["direct_attempt"] = redact_sensitive(direct_result)
    write_evidence(record.profile, record.deploy_id, redact_sensitive(browser_result))
    return browser_result


def _execute_scheduled_deploy_browser(record: ScheduledDeployRecord) -> dict[str, Any]:
    """Execute the stored browser-assisted deploy workflow with Playwright."""

    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:
        return {
            "ok": False,
            "deploy_id": record.deploy_id,
            "error": (
                "Playwright is required for scheduled deploy. Install with: "
                'python -m pip install "befree-bubble-mcp[browser]" && python -m playwright install chromium'
            ),
            "error_class": exc.__class__.__name__,
        }

    settings = load_settings()
    user_data_dir = settings.config_dir / "browser-profiles" / record.profile
    evidence = evidence_dir(record.profile, record.deploy_id)
    evidence.mkdir(parents=True, exist_ok=True)
    editor_url = _editor_url(record.app_id)
    captured_headers: dict[str, str] = {}
    network_events: list[dict[str, Any]] = []
    objective_issue_auto_fix: dict[str, Any] | None = None

    try:
        with sync_playwright() as playwright:
            context = playwright.chromium.launch_persistent_context(
                str(user_data_dir),
                headless=record.headless,
            )
            page = context.pages[0] if context.pages else context.new_page()

            def remember_request(request: Any) -> None:
                try:
                    url = str(request.url)
                    method = str(request.method)
                    headers = {str(key).lower(): str(value) for key, value in request.headers.items()}
                except Exception:
                    return
                if "bubble.io/" not in url:
                    return
                network_events.append({"url": url, "method": method})
                for key, value in headers.items():
                    if key.startswith("x-bubble-") or key in {
                        "accept",
                        "accept-language",
                        "origin",
                        "referer",
                        "sec-ch-ua",
                        "sec-ch-ua-mobile",
                        "sec-ch-ua-platform",
                        "user-agent",
                        "x-csrf-token",
                        "x-requested-with",
                        "x-xsrf-token",
                    }:
                        captured_headers[key] = value

            context.on("request", remember_request)
            page.goto(editor_url, wait_until="domcontentloaded", timeout=record.wait_seconds * 1000)
            page.wait_for_function(_editor_ready_script(), timeout=record.wait_seconds * 1000)
            page.screenshot(path=str(evidence / "before-deploy.png"), full_page=True)
            if record.auto_fix_objective_issues:
                active_session = _browser_session(
                    context=context,
                    page=page,
                    record=record,
                    editor_url=editor_url,
                    captured_headers=captured_headers,
                )
                if active_session is None:
                    raise RuntimeError(
                        "scheduled_deploy_objective_issue_fix_session_unavailable: "
                        "The Chromium session did not expose Bubble cookies required to inspect and fix issues."
                    )
                objective_issue_auto_fix = auto_fix_objective_deploy_issues(
                    profile=record.profile,
                    app_id=record.app_id,
                    session=active_session,
                )
                if not objective_issue_auto_fix.get("ok"):
                    raise RuntimeError(
                        f"{objective_issue_auto_fix.get('error') or 'scheduled_deploy_objective_issue_fix_failed'}: "
                        f"{json.dumps(redact_sensitive(objective_issue_auto_fix), sort_keys=True)[:2000]}"
                    )
                if objective_issue_auto_fix.get("fixes_applied"):
                    page.goto(editor_url, wait_until="domcontentloaded", timeout=record.wait_seconds * 1000)
                    page.wait_for_function(_editor_ready_script(), timeout=record.wait_seconds * 1000)
                    page.screenshot(path=str(evidence / "after-objective-issue-fix.png"), full_page=True)
            page.click(DEPLOY_TRIGGER_SELECTOR)
            page.wait_for_timeout(750)
            state = page.evaluate(_deploy_modal_state_script())
            if not isinstance(state, dict) or not state.get("hasTextarea"):
                try:
                    page.wait_for_selector(DEPLOY_DESCRIPTION_SELECTOR, timeout=8_000)
                except Exception:
                    state = page.evaluate(_deploy_modal_state_script())
                    page.screenshot(path=str(evidence / "deploy-modal-blocked.png"), full_page=True)
                    raise RuntimeError(_deploy_blocker_error(state if isinstance(state, dict) else {}))
            page.fill(DEPLOY_DESCRIPTION_SELECTOR, record.message)
            page.wait_for_timeout(500)
            page.evaluate(_visible_deploy_button_script())
            try:
                page.wait_for_function(_deploy_completion_script(), timeout=30_000)
            except Exception as exc:
                state = page.evaluate(_deploy_modal_state_script())
                page.screenshot(path=str(evidence / "deploy-confirmation-timeout.png"), full_page=True)
                raise RuntimeError(_deploy_blocker_error(state if isinstance(state, dict) else {})) from exc
            page.screenshot(path=str(evidence / "after-deploy.png"), full_page=True)
            cookie_header = _bubble_cookie_header(context)
            user_agent = str(page.evaluate("() => navigator.userAgent") or "befree-bubble-mcp")
            context.close()

        if cookie_header:
            session = session_from_payload(
                {
                    "appId": record.app_id,
                    "url": editor_url,
                    "headers": {
                        "Cookie": cookie_header,
                        "User-Agent": user_agent,
                        **captured_headers,
                    },
                    "appVersion": APP_VERSION,
                    "source": "scheduled_deploy_browser",
                }
            )
            session_path = save_session(record.profile, session)
        else:
            session_path = None

        result = {
            "ok": True,
            "deploy_id": record.deploy_id,
            "profile": record.profile,
            "app_id": record.app_id,
            "app_version": APP_VERSION,
            "deployed_at": _now_iso(),
            "evidence_dir": str(evidence),
            "screenshots": {
                "before": str(evidence / "before-deploy.png"),
                "after": str(evidence / "after-deploy.png"),
            },
            "session_refreshed": session_path is not None,
            "session_path": str(session_path) if session_path else None,
            "network_events": network_events[-25:],
            **(
                {"objective_issue_auto_fix": redact_sensitive(objective_issue_auto_fix)}
                if objective_issue_auto_fix is not None
                else {}
            ),
        }
        write_evidence(record.profile, record.deploy_id, redact_sensitive(result))
        return result
    except Exception as exc:
        result = {
            "ok": False,
            "deploy_id": record.deploy_id,
            "profile": record.profile,
            "app_id": record.app_id,
            "app_version": APP_VERSION,
            "error": str(exc),
            "error_class": exc.__class__.__name__,
            "evidence_dir": str(evidence),
            "network_events": network_events[-25:],
            **(
                {"objective_issue_auto_fix": redact_sensitive(objective_issue_auto_fix)}
                if objective_issue_auto_fix is not None
                else {}
            ),
        }
        write_evidence(record.profile, record.deploy_id, redact_sensitive(result))
        return result
