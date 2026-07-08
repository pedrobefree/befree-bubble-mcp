import json

from bubble_mcp.transfer.models import (
    TransferDependency,
    TransferInventory,
    TransferMappingDecision,
    TransferObjectRef,
    TransferPlan,
)


def test_transfer_inventory_serializes_counts_and_dependencies() -> None:
    source = TransferObjectRef(
        profile="source",
        app_id="source-app",
        app_version="test",
        source_type="reusable",
        ref="Header",
        bubble_id="bSrc1",
    )
    dependency = TransferDependency(
        kind="api_connector_call",
        key="stripe.create_customer",
        label="Stripe - Create customer",
        source_id="api1",
        secret=True,
    )

    inventory = TransferInventory(
        source=source,
        root={"id": "bSrc1", "name": "Header"},
        nodes=[{"id": "bSrc1"}, {"id": "bChild"}],
        dependencies=[dependency],
        warnings=["API Connector secret values are excluded."],
    )

    payload = inventory.to_dict()

    assert payload["source"]["profile"] == "source"
    assert payload["counts"] == {"nodes": 2, "dependencies": 1, "warnings": 1, "unsupported": 0}
    assert payload["dependencies"][0]["kind"] == "api_connector_call"
    assert payload["dependencies"][0]["secret"] is True


def test_transfer_plan_serializes_policies_and_blocked_reasons() -> None:
    source = TransferObjectRef(
        profile="source",
        app_id="source-app",
        app_version="test",
        source_type="page",
        ref="index",
    )
    dependency = TransferDependency(kind="data_field", key="user.email_text", label="User email_text")
    decision = TransferMappingDecision(
        dependency=dependency,
        action="block",
        reason="Target schema is missing field user.email_text.",
    )

    plan = TransferPlan(
        transfer_id="transfer_20260708_index",
        source=source,
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
        dependency_decisions=[decision],
        write_payloads=[],
        blocked_reasons=["Target schema is missing field user.email_text."],
    )

    payload = plan.to_dict()

    assert payload["collection_policy"] == "map_existing"
    assert payload["api_connector_policy"] == "structure_only"
    assert payload["data_records_policy"] == "skip"
    assert payload["counts"] == {"dependency_decisions": 1, "write_payloads": 0, "blocked_reasons": 1}
    assert payload["dependency_decisions"][0]["dependency"]["kind"] == "data_field"
    assert json.dumps(payload)
