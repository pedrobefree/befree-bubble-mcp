from bubble_mcp.context.mutation_overlay import read_mutation_overlay
from bubble_mcp.sessions.store import save_session, session_from_payload
from bubble_mcp.transfer.executor import execute_transfer_plan, preview_transfer_plan
from bubble_mcp.transfer.models import TransferObjectRef, TransferPlan
from bubble_mcp.transfer.store import load_transfer_execution, save_transfer_plan


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
        reuse_policy="prefer_existing",
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
    assert result["verification"]["complete"] is True
    assert result["verification"]["requires_context_refresh"] is True
    assert "Refresh target context" in result["verification"]["warnings"][0]
    assert client.calls[0][1] is False
    overlay = read_mutation_overlay("target", "target-app")
    assert overlay["entries"][0]["source"] == "bubble_transfer_execute"
    evidence = load_transfer_execution("transfer_test")
    assert evidence is not None
    assert evidence["verification"]["writes_ok"] is True
    assert evidence["result_count"] == 1


def test_execute_transfer_plan_marks_partial_max_steps_execution(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    plan = _plan()
    plan = TransferPlan(
        **{
            **plan.__dict__,
            "write_payloads": [
                {"v": 1, "appname": "target-app", "app_version": "test", "changes": [{"intent": {"name": "CreateElement"}}]},
                {"v": 1, "appname": "target-app", "app_version": "test", "changes": [{"intent": {"name": "CreateElement"}}]},
            ],
        }
    )
    save_transfer_plan(plan)
    save_session(
        "target",
        session_from_payload(
            {
                "appId": "target-app",
                "headers": {"cookie": "sid=secret", "x-bubble-client-version": "client-version"},
            }
        ),
    )

    result = execute_transfer_plan("transfer_test", execute=True, confirm=True, max_steps=1, client=FakeEditorClient())

    assert result["ok"] is False
    assert result["verification"]["complete"] is False
    assert result["verification"]["expected_payload_count"] == 2
    assert result["verification"]["executed_payload_count"] == 1
    assert "partial" in result["verification"]["warnings"][0]


def test_execute_transfer_plan_blocks_blocked_or_unconfirmed_plans(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    save_transfer_plan(_plan(blocked=True))

    blocked = execute_transfer_plan("transfer_test", execute=True, confirm=True, client=FakeEditorClient())

    assert blocked["ok"] is False
    assert blocked["executed"] is False
    assert blocked["blocked_reasons"] == ["blocked"]
