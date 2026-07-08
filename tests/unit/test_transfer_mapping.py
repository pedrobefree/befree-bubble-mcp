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
            BubbleContextNode(
                id="style:brand-button",
                label="Brand CTA",
                type="style",
                metadata={
                    "element_type": "Button",
                    "properties": {
                        "background_color": "#5b37e8",
                        "border_radius": 8,
                        "font_weight": 700,
                    },
                },
            ),
            BubbleContextNode(
                id="api:stripe.create-customer",
                label="Stripe Create Customer",
                type="api_connector_call",
                metadata={"method": "POST", "url": "https://api.stripe.com/v1/customers"},
            ),
        ],
        edges=[],
        metadata={"settings": {"client_safe": {"plugins": {"progressbar": True}}}},
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


def test_build_dependency_decisions_reuses_compatible_style_signature() -> None:
    decisions = build_dependency_decisions(
        _inventory(
            [
                TransferDependency(
                    kind="style",
                    key="Marketing Button",
                    label="Marketing Button",
                    metadata={
                        "element_type": "Button",
                        "properties": {
                            "background_color": "#5b37e8",
                            "border_radius": 8,
                            "font_weight": 700,
                        },
                    },
                )
            ]
        ),
        _target_context(),
        dependency_policy="map_or_create",
        reuse_policy="prefer_existing",
    )

    assert decisions[0].action == "map_existing"
    assert decisions[0].target_id == "style:brand-button"
    assert decisions[0].confidence == 0.95
    assert decisions[0].metadata["match_type"] == "compatible"


def test_build_dependency_decisions_exact_only_does_not_reuse_compatible_style() -> None:
    decisions = build_dependency_decisions(
        _inventory(
            [
                TransferDependency(
                    kind="style",
                    key="Marketing Button",
                    label="Marketing Button",
                    metadata={
                        "element_type": "Button",
                        "properties": {"background_color": "#5b37e8", "border_radius": 8},
                    },
                )
            ]
        ),
        _target_context(),
        dependency_policy="map_or_create",
        reuse_policy="exact_only",
    )

    assert decisions[0].action == "create_copy"


def test_build_dependency_decisions_can_force_create_new_even_when_exact_exists() -> None:
    decisions = build_dependency_decisions(
        _inventory([TransferDependency(kind="style", key="Primary Button", label="Primary Button")]),
        _target_context(),
        dependency_policy="map_or_create",
        reuse_policy="create_new",
    )

    assert decisions[0].action == "create_copy"


def test_build_dependency_decisions_reuses_compatible_api_call_without_secret_metadata() -> None:
    decisions = build_dependency_decisions(
        _inventory(
            [
                TransferDependency(
                    kind="api_connector_call",
                    key="payments.create_customer",
                    label="Create customer",
                    secret=True,
                    metadata={
                        "method": "POST",
                        "url": "https://api.stripe.com/v1/customers",
                        "authorization_header": "Bearer source-secret",
                    },
                )
            ]
        ),
        _target_context(),
        dependency_policy="map_or_create",
        reuse_policy="prefer_existing",
    )

    assert decisions[0].action == "map_existing"
    assert decisions[0].target_id == "api:stripe.create-customer"
    assert "authorization" not in decisions[0].metadata["signature_fields"]


def test_build_dependency_decisions_maps_installed_plugin_by_element_type_prefix() -> None:
    decisions = build_dependency_decisions(
        _inventory(
            [
                TransferDependency(
                    kind="plugin",
                    key="progressbar-ProgressBar",
                    label="Bubble plugin element/action type progressbar-ProgressBar",
                )
            ]
        ),
        _target_context(),
        dependency_policy="map_only",
    )

    assert decisions[0].action == "map_existing"
    assert decisions[0].target_id == "plugin:progressbar"


def test_build_dependency_decisions_blocks_missing_plugin_dependency() -> None:
    decisions = build_dependency_decisions(
        _inventory(
            [
                TransferDependency(
                    kind="plugin",
                    key="missingplugin-Widget",
                    label="Bubble plugin element/action type missingplugin-Widget",
                )
            ]
        ),
        _target_context(),
        dependency_policy="map_or_create",
    )

    assert decisions[0].action == "block"
    assert "Install the matching plugin" in decisions[0].reason
