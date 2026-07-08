import pytest

from bubble_mcp.context.models import BubbleContextEdge, BubbleContextNode, BubbleProjectContext
from bubble_mcp.transfer.inventory import inventory_source_object


def _context() -> BubbleProjectContext:
    return BubbleProjectContext(
        app_id="source-app",
        source="test",
        nodes=[
            BubbleContextNode(
                id="page:index",
                label="index",
                type="page",
                metadata={"bubble_id": "bPage", "path": ["%p3", "bPage"]},
            ),
            BubbleContextNode(
                id="element:bHero",
                label="gp_Hero",
                type="element",
                metadata={
                    "bubble_id": "bHero",
                    "path": ["%p3", "bPage", "%el", "bHero"],
                    "style": "Primary Card",
                    "image_url": "https://example.com/hero.png",
                    "data_type": "User",
                    "api_connector_call": "stripe.create_customer",
                },
            ),
            BubbleContextNode(
                id="element:bButton",
                label="bt_CTA",
                type="element",
                metadata={
                    "bubble_id": "bButton",
                    "path": ["%p3", "bPage", "%el", "bHero", "%el", "bButton"],
                    "style": "Primary Button",
                    "font": "Inter",
                },
            ),
            BubbleContextNode(
                id="workflow:wf1",
                label="Button clicked",
                type="workflow",
                metadata={"bubble_id": "wf1", "context": "page:index"},
            ),
        ],
        edges=[
            BubbleContextEdge(source="page:index", target="element:bHero", type="contains"),
            BubbleContextEdge(source="element:bHero", target="element:bButton", type="contains"),
            BubbleContextEdge(source="page:index", target="workflow:wf1", type="has_workflow"),
        ],
    )


def test_inventory_element_collects_subtree_and_dependencies() -> None:
    inventory = inventory_source_object(
        context=_context(),
        profile="source",
        app_version="test",
        source_type="element",
        source_ref="gp_Hero",
        source_context="index",
    )

    assert inventory.source.app_id == "source-app"
    assert inventory.source.bubble_id == "bHero"
    assert [node["id"] for node in inventory.nodes] == ["element:bHero", "element:bButton"]
    dependencies = {(item.kind, item.key) for item in inventory.dependencies}
    assert ("style", "Primary Card") in dependencies
    assert ("style", "Primary Button") in dependencies
    assert ("asset", "https://example.com/hero.png") in dependencies
    assert ("data_type", "User") in dependencies
    assert ("font", "Inter") in dependencies
    assert ("api_connector_call", "stripe.create_customer") in dependencies


def test_inventory_page_includes_workflows() -> None:
    inventory = inventory_source_object(
        context=_context(),
        profile="source",
        app_version="test",
        source_type="page",
        source_ref="index",
    )

    assert [node["id"] for node in inventory.nodes] == [
        "page:index",
        "element:bHero",
        "workflow:wf1",
        "element:bButton",
    ]


def test_inventory_requires_matching_source_type() -> None:
    with pytest.raises(ValueError, match="No element found"):
        inventory_source_object(
            context=_context(),
            profile="source",
            app_version="test",
            source_type="element",
            source_ref="missing",
        )
