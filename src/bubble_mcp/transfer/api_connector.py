"""API Connector structure bundle extraction for transfer planning."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from typing import Any

from bubble_mcp.context.models import BubbleProjectContext
from bubble_mcp.core.redaction import redact_sensitive


@dataclass(frozen=True)
class ApiConnectorCallBundle:
    call_id: str
    name: str
    method: str | None
    url: str | None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "call_id": self.call_id,
            "name": self.name,
            "method": self.method,
            "url": self.url,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class ApiConnectorBundle:
    api_id: str
    name: str
    shared_headers: dict[str, Any]
    calls: list[ApiConnectorCallBundle]
    setup_checklist: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "api_id": self.api_id,
            "name": self.name,
            "shared_headers": dict(self.shared_headers),
            "calls": [call.to_dict() for call in self.calls],
            "setup_checklist": list(self.setup_checklist),
            "metadata": dict(self.metadata),
        }


def _obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _api_connector_payload(context: BubbleProjectContext) -> dict[str, Any]:
    settings = _obj(context.metadata.get("settings"))
    client_safe = _obj(settings.get("client_safe"))
    return _obj(client_safe.get("apiconnector2"))


def _matches(api_id: str, api_payload: dict[str, Any], ref: str) -> bool:
    normalized = str(ref or "").strip().lower()
    return normalized in {
        str(api_id).strip().lower(),
        str(api_payload.get("human") or "").strip().lower(),
        str(api_payload.get("name") or "").strip().lower(),
    }


def extract_api_connector_bundle(source_context: BubbleProjectContext, api_ref: str) -> ApiConnectorBundle:
    """Extract API Connector API/call structure from context metadata."""

    apis = _api_connector_payload(source_context)
    for api_id, raw_api in apis.items():
        api_payload = _obj(raw_api)
        if not _matches(str(api_id), api_payload, api_ref):
            continue
        calls: list[ApiConnectorCallBundle] = []
        for call_id, raw_call in _obj(api_payload.get("calls")).items():
            call = _obj(raw_call)
            calls.append(
                ApiConnectorCallBundle(
                    call_id=str(call_id),
                    name=str(call.get("human") or call.get("name") or call_id),
                    method=str(call.get("method") or "").upper() or None,
                    url=str(call.get("url") or "").strip() or None,
                    metadata={key: value for key, value in call.items() if key not in {"human", "name", "method", "url"}},
                )
            )
        return ApiConnectorBundle(
            api_id=str(api_id),
            name=str(api_payload.get("human") or api_payload.get("name") or api_id),
            shared_headers=_obj(api_payload.get("shared_headers")),
            calls=calls,
            metadata={"source": "context.metadata.settings.client_safe.apiconnector2"},
        )
    raise ValueError(f"API Connector API not found in source context: {api_ref}")


def _secret_checklist(headers: dict[str, Any], api_name: str) -> list[str]:
    checklist: list[str] = []
    for header_id, header in headers.items():
        if isinstance(header, dict) and "[REDACTED]" in {str(value) for value in header.values()}:
            checklist.append(f"Configure shared_headers.{header_id}.value for API Connector '{api_name}'.")
    return checklist


def redact_api_connector_bundle(bundle: ApiConnectorBundle) -> ApiConnectorBundle:
    """Return a copy of an API Connector bundle with sensitive values redacted."""

    redacted_headers = redact_sensitive(bundle.shared_headers)
    redacted_calls = [
        replace(call, metadata=redact_sensitive(call.metadata))
        for call in bundle.calls
    ]
    return replace(
        bundle,
        shared_headers=redacted_headers,
        calls=redacted_calls,
        setup_checklist=_secret_checklist(redacted_headers, bundle.name),
    )


def _target_has_api_call(target_context: BubbleProjectContext, bundle: ApiConnectorBundle, call: ApiConnectorCallBundle) -> bool:
    for node in target_context.nodes:
        if node.type != "api_connector_call":
            continue
        values = {
            node.id.strip().lower(),
            node.label.strip().lower(),
            str(node.metadata.get("api_id") or "").strip().lower(),
            str(node.metadata.get("call_id") or "").strip().lower(),
        }
        if bundle.api_id.lower() in values and call.call_id.lower() in values:
            return True
        if f"{bundle.api_id}.{call.call_id}".lower() in values:
            return True
    return False


def plan_api_connector_bundle(
    bundle: ApiConnectorBundle,
    target_context: BubbleProjectContext,
    *,
    policy: str,
) -> dict[str, Any]:
    """Plan API Connector structure actions for a target app."""

    if policy not in {"skip", "map_existing", "structure_only"}:
        raise ValueError("api connector policy must be one of: skip, map_existing, structure_only.")
    if policy == "skip":
        return {"ok": True, "policy": policy, "actions": [], "blocked_reasons": [], "setup_checklist": []}

    missing_calls = [
        call
        for call in bundle.calls
        if not _target_has_api_call(target_context, bundle, call)
    ]
    if policy == "map_existing" and missing_calls:
        return {
            "ok": False,
            "policy": policy,
            "actions": [],
            "blocked_reasons": [
                f"Target API Connector call not found: {bundle.name}.{call.name}"
                for call in missing_calls
            ],
            "setup_checklist": list(bundle.setup_checklist),
        }

    actions: list[dict[str, Any]] = []
    if missing_calls:
        actions.append({"action": "create_api_connector", "api_id": bundle.api_id, "name": bundle.name})
        for call in missing_calls:
            actions.append(
                {
                    "action": "create_api_connector_call",
                    "api_id": bundle.api_id,
                    "call_id": call.call_id,
                    "name": call.name,
                    "method": call.method,
                    "url": call.url,
                }
            )
    return {
        "ok": True,
        "policy": policy,
        "actions": actions,
        "blocked_reasons": [],
        "setup_checklist": list(bundle.setup_checklist),
    }
