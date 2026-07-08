import json

import pytest

from bubble_mcp.transfer.models import TransferObjectRef, TransferPlan
from bubble_mcp.transfer.store import (
    load_transfer_plan,
    save_transfer_plan,
    transfer_plan_path,
    transfer_root,
)


def _plan(transfer_id: str = "transfer_20260708_index") -> TransferPlan:
    return TransferPlan(
        transfer_id=transfer_id,
        source=TransferObjectRef(
            profile="source",
            app_id="source-app",
            app_version="test",
            source_type="page",
            ref="index",
        ),
        target_profile="target",
        target_app_id="target-app",
        target_app_version="test",
        target_context="index",
        target_parent="root",
        target_name="index_copy",
        conflict_policy="fail",
        asset_policy="reference_url",
        collection_policy="map_existing",
        api_connector_policy="structure_only",
        data_records_policy="skip",
        reuse_policy="prefer_existing",
        dependency_decisions=[],
        write_payloads=[{"v": 1, "appname": "target-app", "changes": []}],
    )


def test_save_and_load_transfer_plan_under_config_dir(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    path = save_transfer_plan(_plan())
    loaded = load_transfer_plan("transfer_20260708_index")

    assert path == tmp_path / "transfers" / "transfer_20260708_index" / "plan.json"
    assert transfer_root() == tmp_path / "transfers"
    assert loaded["transfer_id"] == "transfer_20260708_index"
    assert loaded["target_profile"] == "target"
    assert loaded["write_payloads"][0]["appname"] == "target-app"


def test_transfer_plan_path_rejects_path_traversal(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    with pytest.raises(ValueError, match="Invalid transfer_id"):
        transfer_plan_path("../escape")


def test_load_transfer_plan_reports_missing_and_malformed_files(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    with pytest.raises(FileNotFoundError, match="Transfer plan not found"):
        load_transfer_plan("missing")

    path = transfer_plan_path("bad-json")
    path.parent.mkdir(parents=True)
    path.write_text("not-json\n", encoding="utf-8")

    with pytest.raises(ValueError, match=r"Malformed transfer plan JSON at .*plan\.json"):
        load_transfer_plan("bad-json")


def test_save_transfer_plan_writes_stable_json(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))

    path = save_transfer_plan(_plan("transfer_stable"))
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert list(payload) == sorted(payload)
    assert payload["source"]["app_id"] == "source-app"
