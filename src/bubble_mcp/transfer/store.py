"""Local persistence for Bubble transfer plans and evidence."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from bubble_mcp.core.config import get_config_dir
from bubble_mcp.transfer.models import TransferPlan


_TRANSFER_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")


def transfer_root() -> Path:
    """Return the root directory for local transfer artifacts."""

    return get_config_dir() / "transfers"


def _validate_transfer_id(transfer_id: str) -> str:
    normalized = str(transfer_id or "").strip()
    if not _TRANSFER_ID_RE.fullmatch(normalized):
        raise ValueError(f"Invalid transfer_id: {transfer_id!r}")
    return normalized


def transfer_dir(transfer_id: str) -> Path:
    """Return the local artifact directory for a transfer id."""

    return transfer_root() / _validate_transfer_id(transfer_id)


def transfer_plan_path(transfer_id: str) -> Path:
    """Return the local plan path for a transfer id."""

    return transfer_dir(transfer_id) / "plan.json"


def transfer_execution_path(transfer_id: str) -> Path:
    """Return the local execution evidence path for a transfer id."""

    return transfer_dir(transfer_id) / "execution.json"


def save_transfer_plan(plan: TransferPlan) -> Path:
    """Persist a transfer plan as stable JSON and return its path."""

    path = transfer_plan_path(plan.transfer_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(plan.to_dict(), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def save_transfer_execution(transfer_id: str, evidence: dict[str, Any]) -> Path:
    """Persist transfer execution evidence as stable JSON and return its path."""

    path = transfer_execution_path(transfer_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(evidence, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    return path


def load_transfer_execution(transfer_id: str) -> dict[str, Any] | None:
    """Load transfer execution evidence when it exists."""

    path = transfer_execution_path(transfer_id)
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed transfer execution JSON at {path}: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Expected transfer execution JSON object at {path}")
    return payload


def load_transfer_plan(transfer_id: str) -> dict[str, Any]:
    """Load a transfer plan JSON object from local storage."""

    path = transfer_plan_path(transfer_id)
    if not path.exists():
        raise FileNotFoundError(f"Transfer plan not found: {path}")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Malformed transfer plan JSON at {path}: {exc.msg}") from exc
    if not isinstance(payload, dict):
        raise ValueError(f"Expected transfer plan JSON object at {path}")
    return payload
