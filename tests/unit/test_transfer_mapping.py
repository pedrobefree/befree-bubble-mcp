from bubble_mcp.context.models import BubbleContextNode, BubbleProjectContext
from bubble_mcp.transfer.mapping import build_dependency_decisions
from bubble_mcp.transfer.models import TransferDependency, TransferInventory, TransferObjectRef


def _inventory(dependencies: list[TransferDependency]) -> TransferInventory:
    return TransferInventory(
        source=TransferObjectRef(
            profile="source",
            app_id="source-app",
            app_version="test",
            source_type="element",
            ref="gp_Hero",
        ),
        root={"id": "element:bHero"},
        nodes=[],
        dependencies=dependencies,
    )


def _target_context() -> BubbleProjectContext:
    return BubbleProjectContext(
        app_id="target-app",
        source="test",
        nodes=[
            BubbleContextNode(id="datatype:user", label="User", type="data_type"),
            BubbleContextNode(id="style:primary-button", label="Primary Button", type="style"),
        ],
        edges=[],
    )


def test_build_dependency_decisions_maps_existing_target_nodes() -> None:
    decisions = build_dependency_decisions(
        _inventory(
            [
                TransferDependency(kind="data_type", key="User", label="User"),
                TransferDependency(kind="style", key="Primary Button", label="Primary Button"),
            ]
        ),
        _target_context(),
        dependency_policy="map_only",
    )

    assert [decision.action for decision in decisions] == ["map_existing", "map_existing"]
    assert decisions[0].target_id == "datatype:user"
    assert decisions[1].target_id == "style:primary-button"


def test_build_dependency_decisions_blocks_missing_required_dependencies_for_map_only() -> None:
    decisions = build_dependency_decisions(
        _inventory([TransferDependency(kind="data_field", key="user.email_text", label="user.email_text")]),
        _target_context(),
        dependency_policy="map_only",
    )

    assert decisions[0].action == "block"
    assert "not found" in decisions[0].reason


def test_build_dependency_decisions_creates_missing_dependencies_when_allowed() -> None:
    decisions = build_dependency_decisions(
        _inventory([TransferDependency(kind="option_set", key="Plan", label="Plan")]),
        _target_context(),
        dependency_policy="map_or_create",
    )

    assert decisions[0].action == "create_copy"
    assert "will be created" in decisions[0].reason


def test_build_dependency_decisions_skips_optional_missing_dependencies() -> None:
    decisions = build_dependency_decisions(
        _inventory([TransferDependency(kind="asset", key="https://example.com/a.png", label="Hero", required=False)]),
        _target_context(),
        dependency_policy="skip_optional",
    )

    assert decisions[0].action == "skip"
    assert "optional" in decisions[0].reason
