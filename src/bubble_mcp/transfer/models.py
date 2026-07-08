"""Data models for Bubble project-to-project transfer plans."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


SourceType = Literal["page", "reusable", "element"]
DependencyKind = Literal[
    "page",
    "reusable",
    "element",
    "style",
    "color",
    "font",
    "data_type",
    "data_field",
    "privacy_rule",
    "option_set",
    "api_connector",
    "api_connector_call",
    "plugin",
    "asset",
    "workflow",
    "custom_state",
]
DependencyAction = Literal["map_existing", "create_copy", "skip", "block"]
ConflictPolicy = Literal["fail", "rename", "replace", "reuse_existing"]
AssetPolicy = Literal["reference_url", "stage_and_upload", "skip"]
CollectionPolicy = Literal["skip", "map_existing", "create_missing", "replace_schema"]
ApiConnectorPolicy = Literal["skip", "map_existing", "structure_only"]
DataRecordsPolicy = Literal["skip", "export_manifest_only", "data_api_import_preview"]
TransferStatus = Literal["planned", "previewed", "executed", "failed"]


def utc_now_iso() -> str:
    """Return a timezone-aware UTC timestamp for persisted transfer artifacts."""

    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class TransferObjectRef:
    profile: str
    app_id: str
    app_version: str
    source_type: SourceType
    ref: str
    context: str | None = None
    bubble_id: str | None = None
    path: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile,
            "app_id": self.app_id,
            "app_version": self.app_version,
            "source_type": self.source_type,
            "ref": self.ref,
            "context": self.context,
            "bubble_id": self.bubble_id,
            "path": list(self.path),
        }


@dataclass(frozen=True)
class TransferDependency:
    kind: DependencyKind
    key: str
    label: str
    source_id: str | None = None
    required: bool = True
    secret: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kind": self.kind,
            "key": self.key,
            "label": self.label,
            "source_id": self.source_id,
            "required": self.required,
            "secret": self.secret,
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class TransferInventory:
    source: TransferObjectRef
    root: dict[str, Any]
    nodes: list[dict[str, Any]]
    dependencies: list[TransferDependency]
    warnings: list[str] = field(default_factory=list)
    unsupported: list[TransferDependency] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source.to_dict(),
            "root": dict(self.root),
            "nodes": list(self.nodes),
            "dependencies": [item.to_dict() for item in self.dependencies],
            "warnings": list(self.warnings),
            "unsupported": [item.to_dict() for item in self.unsupported],
            "counts": {
                "nodes": len(self.nodes),
                "dependencies": len(self.dependencies),
                "warnings": len(self.warnings),
                "unsupported": len(self.unsupported),
            },
        }


@dataclass(frozen=True)
class TransferMappingDecision:
    dependency: TransferDependency
    action: DependencyAction
    target_id: str | None = None
    target_label: str | None = None
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "dependency": self.dependency.to_dict(),
            "action": self.action,
            "target_id": self.target_id,
            "target_label": self.target_label,
            "reason": self.reason,
        }


@dataclass(frozen=True)
class TransferPlan:
    transfer_id: str
    source: TransferObjectRef
    target_profile: str
    target_app_id: str
    target_app_version: str
    target_context: str | None
    target_parent: str | None
    target_name: str | None
    conflict_policy: ConflictPolicy
    asset_policy: AssetPolicy
    collection_policy: CollectionPolicy
    api_connector_policy: ApiConnectorPolicy
    data_records_policy: DataRecordsPolicy
    dependency_decisions: list[TransferMappingDecision]
    write_payloads: list[dict[str, Any]]
    blocked_reasons: list[str] = field(default_factory=list)
    created_at: str = field(default_factory=utc_now_iso)
    status: TransferStatus = "planned"

    def to_dict(self) -> dict[str, Any]:
        return {
            "api_connector_policy": self.api_connector_policy,
            "asset_policy": self.asset_policy,
            "blocked_reasons": list(self.blocked_reasons),
            "collection_policy": self.collection_policy,
            "conflict_policy": self.conflict_policy,
            "counts": {
                "blocked_reasons": len(self.blocked_reasons),
                "dependency_decisions": len(self.dependency_decisions),
                "write_payloads": len(self.write_payloads),
            },
            "created_at": self.created_at,
            "data_records_policy": self.data_records_policy,
            "dependency_decisions": [item.to_dict() for item in self.dependency_decisions],
            "source": self.source.to_dict(),
            "status": self.status,
            "target_app_id": self.target_app_id,
            "target_app_version": self.target_app_version,
            "target_context": self.target_context,
            "target_name": self.target_name,
            "target_parent": self.target_parent,
            "target_profile": self.target_profile,
            "transfer_id": self.transfer_id,
            "write_payloads": list(self.write_payloads),
        }
