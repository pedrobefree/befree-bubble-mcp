"""Typed host callbacks for style lifecycle services."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Protocol


class StyleReferenceHost(Protocol):
    """Immutable snapshots and normalization callbacks used by style reads."""

    def style_reference_snapshots(self) -> tuple[dict[str, Any], dict[str, Any]]: ...

    def style_reference_revision(self) -> int: ...

    def list_style_references(self) -> list[dict[str, Any]]: ...

    def list_style_reference_elements(self) -> list[dict[str, Any]]: ...

    def normalize_style_reference(self, value: Any) -> str: ...

    def compact_style_reference(self, value: Any) -> str: ...

    def plain_style_reference_text(self, value: Any) -> str: ...


class StyleAssignmentHost(StyleReferenceHost, Protocol):
    """Read-only snapshots required by assignment and override policy."""


@dataclass(frozen=True)
class TokenMutationResult:
    """Internal token mutation outcome with the generated ID and complete plan."""

    ok: bool
    payload: Any | None = None
    token_id: str | None = None
    error: str | None = None


def dispatch_token_mutation(
    host: StyleTokenHost,
    payload: Any,
    *,
    dry_run: bool,
    token_id: str | None = None,
    after: Callable[[], None] | None = None,
) -> TokenMutationResult:
    """Dispatch once and report post-write cache failures without losing remote success."""
    if dry_run:
        return TokenMutationResult(ok=True, payload=payload, token_id=token_id)
    try:
        host.dispatch_style_token_payload(payload)
    except Exception as exc:
        return TokenMutationResult(ok=False, payload=payload, token_id=token_id, error=str(exc))
    if after is not None:
        try:
            after()
        except Exception as exc:
            return TokenMutationResult(
                ok=True,
                payload=payload,
                token_id=token_id,
                error=f"Post-write token cache update failed: {exc}",
            )
    return TokenMutationResult(ok=True, payload=payload, token_id=token_id)


class StyleTokenHost(Protocol):
    """Narrow BubbleCLI boundary used by color and font lifecycle writes."""

    appname: str

    def style_reference_snapshots(self) -> tuple[dict[str, Any], dict[str, Any]]: ...

    def new_style_token_payload(self) -> Any: ...

    def dispatch_style_token_payload(self, payload: Any) -> None: ...

    def put_style_token_cache(self, kind: str, token_id: str, data: dict[str, Any]) -> None: ...

    def remove_style_token_cache(self, kind: str, token_id: str) -> None: ...

    def clear_style_token_cache(self, kind: str) -> None: ...


class StyleLifecycleHost(StyleAssignmentHost, StyleTokenHost, Protocol):
    """Complete composition-root host without widening individual services."""
