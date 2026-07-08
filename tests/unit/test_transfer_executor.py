from bubble_mcp.context.mutation_overlay import read_mutation_overlay
from bubble_mcp.sessions.store import save_session, session_from_payload
from bubble_mcp.transfer.executor import execute_transfer_plan, preview_transfer_plan
from bubble_mcp.transfer.models import TransferObjectRef, TransferPlan
from bubble_mcp.transfer.store import save_transfer_plan


class FakeEditorClient:
    def __init__(self) -> None:
        self.calls: list[tuple[dict, bool]] = []

    def write(self, payload, session, *, dry_run=False, calculate_derived=False):  # type: ignore[no-untyped-def]
        self.calls.append((payload, dry_run))
        return {
            "ok": True,
            "dry_run": dry_run,
            "request": {"payload": payload},
            "response": {"last_change": "1"},
        }


def _plan(blocked: bool = False) -> TransferPlan:
    return TransferPlan(
        transfer_id="transfer_test",
        source=TransferObjectRef(
            profile="source",
            app_id="source-app",
            app_version="test",
            source_type="element",
            ref="gp_Hero",
        ),
        target_profile="target",
        target_app_id="target-app",
        target_app_version="test",
        target_context="index",
        target_parent="root",
        target_name="gp_Hero_Copy",
        conflict_policy="fail",
        asset_policy="reference_url",
        collection_policy="map_existing",
        api_connector_policy="structure_only",
        data_records_policy="skip",
        dependency_decisions=[],
        write_payloads=[{"v": 1, "appname": "target-app", "app_version": "test", "changes": [{"intent": {"name": "CreateElement"}}]}],
        blocked_reasons=["blocked"] if blocked else [],
    )


def test_preview_transfer_plan_dry_runs_payloads(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    save_transfer_plan(_plan())
    save_session(
        "target",
        session_from_payload(
            {
                "appId": "target-app",
                "headers": {"cookie": "sid=secret", "x-bubble-client-version": "client-version"},
            }
        ),
    )
    client = FakeEditorClient()

    preview = preview_transfer_plan("transfer_test", client=client)

    assert preview["ok"] is True
    assert preview["payload_count"] == 1
    assert client.calls[0][1] is True


def test_execute_transfer_plan_requires_confirm_and_records_overlay(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    save_transfer_plan(_plan())
    save_session(
        "target",
        session_from_payload(
            {
                "appId": "target-app",
                "headers": {"cookie": "sid=secret", "x-bubble-client-version": "client-version"},
            }
        ),
    )
    client = FakeEditorClient()

    result = execute_transfer_plan("transfer_test", execute=True, confirm=True, client=client)

    assert result["ok"] is True
    assert result["executed"] is True
    assert client.calls[0][1] is False
    overlay = read_mutation_overlay("target", "target-app")
    assert overlay["entries"][0]["source"] == "bubble_transfer_execute"


def test_execute_transfer_plan_blocks_blocked_or_unconfirmed_plans(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    save_transfer_plan(_plan(blocked=True))

    blocked = execute_transfer_plan("transfer_test", execute=True, confirm=True, client=FakeEditorClient())

    assert blocked["ok"] is False
    assert blocked["executed"] is False
    assert blocked["blocked_reasons"] == ["blocked"]
