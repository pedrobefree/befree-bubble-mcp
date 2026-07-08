from bubble_mcp.context.models import BubbleContextNode, BubbleProjectContext
from bubble_mcp.transfer.collections import extract_collection_bundle, plan_collection_bundle


def _context() -> BubbleProjectContext:
    return BubbleProjectContext(
        app_id="source-app",
        source="test",
        nodes=[
            BubbleContextNode(
                id="datatype:testimonial",
                label="testimonial",
                type="data_type",
                metadata={
                    "bubble_id": "testimonial",
                    "properties": {
                        "fields": {
                            "quote_text": {"type": "text"},
                            "score_number": {"type": "number"},
                            "author_user": {"type": "user"},
                        },
                        "privacy_role": {
                            "everyone": {"%d": "Everyone else", "permissions": {"view_all": False}},
                            "public_rule": {"%d": "public_testimonial", "permissions": {"view_all": True}},
                        },
                    },
                },
            ),
            BubbleContextNode(
                id="optionset:status",
                label="Status",
                type="option_set",
                metadata={"bubble_id": "status", "properties": {"values": {"active": {"%d": "Active"}}}},
            ),
        ],
        edges=[],
    )


def test_extract_collection_bundle_preserves_exact_field_keys_and_privacy_rules() -> None:
    bundle = extract_collection_bundle(_context(), "testimonial")

    assert bundle.data_type == "testimonial"
    assert [field.key for field in bundle.fields] == ["quote_text", "score_number", "author_user"]
    assert bundle.fields[0].field_type == "text"
    assert [rule.key for rule in bundle.privacy_rules] == ["everyone", "public_rule"]
    assert bundle.option_sets[0]["key"] == "status"


def test_plan_collection_bundle_map_existing_blocks_missing_fields() -> None:
    bundle = extract_collection_bundle(_context(), "testimonial")
    target = BubbleProjectContext(
        app_id="target-app",
        source="test",
        nodes=[
            BubbleContextNode(
                id="datatype:testimonial",
                label="testimonial",
                type="data_type",
                metadata={"properties": {"fields": {"quote_text": {"type": "text"}}}},
            )
        ],
        edges=[],
    )

    plan = plan_collection_bundle(bundle, target, policy="map_existing")

    assert plan["ok"] is False
    assert "score_number" in plan["blocked_reasons"][0]
    assert plan["data_records_policy"] == "skip"


def test_plan_collection_bundle_create_missing_describes_schema_actions() -> None:
    bundle = extract_collection_bundle(_context(), "testimonial")
    target = BubbleProjectContext(app_id="target-app", source="test", nodes=[], edges=[])

    plan = plan_collection_bundle(bundle, target, policy="create_missing")

    assert plan["ok"] is True
    assert plan["actions"][0]["action"] == "create_data_type"
    assert {action["field_key"] for action in plan["actions"] if action["action"] == "create_data_field"} == {
        "quote_text",
        "score_number",
        "author_user",
    }
    assert {action["action"] for action in plan["actions"]} >= {
        "create_option_set",
        "create_option_value",
        "ensure_privacy_rule",
    }
    privacy = [action for action in plan["actions"] if action["action"] == "ensure_privacy_rule"]
    assert {action["rule_key"] for action in privacy} == {"everyone", "public_rule"}
    assert privacy[0]["payload"]["permissions"]
