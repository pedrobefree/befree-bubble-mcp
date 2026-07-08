from bubble_mcp.context.models import BubbleProjectContext
from bubble_mcp.transfer.api_connector import (
    extract_api_connector_bundle,
    plan_api_connector_bundle,
    redact_api_connector_bundle,
)


def _context() -> BubbleProjectContext:
    return BubbleProjectContext(
        app_id="source-app",
        source="test",
        nodes=[],
        edges=[],
        metadata={
            "settings": {
                "client_safe": {
                    "apiconnector2": {
                        "stripe": {
                            "human": "Stripe",
                            "shared_headers": {"auth": {"key": "Authorization", "value": "Bearer sk-secret-value"}},
                            "calls": {
                                "create_customer": {
                                    "human": "Create customer",
                                    "method": "POST",
                                    "url": "https://api.stripe.com/v1/customers",
                                    "body": {"email": "<email>"},
                                    "headers": {"Idempotency-Key": "safe-dynamic-key"},
                                }
                            },
                        }
                    }
                }
            }
        },
    )


def test_extract_api_connector_bundle_preserves_call_structure() -> None:
    bundle = extract_api_connector_bundle(_context(), "Stripe")

    assert bundle.api_id == "stripe"
    assert bundle.name == "Stripe"
    assert bundle.calls[0].call_id == "create_customer"
    assert bundle.calls[0].method == "POST"
    assert bundle.calls[0].url == "https://api.stripe.com/v1/customers"


def test_redact_api_connector_bundle_removes_secret_values_and_creates_checklist() -> None:
    bundle = redact_api_connector_bundle(extract_api_connector_bundle(_context(), "stripe"))

    assert bundle.shared_headers["auth"]["value"] == "[REDACTED]"
    assert bundle.setup_checklist == ["Configure shared_headers.auth.value for API Connector 'Stripe'."]


def test_plan_api_connector_bundle_structure_only_creates_missing_structure() -> None:
    bundle = redact_api_connector_bundle(extract_api_connector_bundle(_context(), "stripe"))
    target = BubbleProjectContext(app_id="target-app", source="test", nodes=[], edges=[])

    plan = plan_api_connector_bundle(bundle, target, policy="structure_only")

    assert plan["ok"] is True
    assert plan["actions"][0]["action"] == "create_api_connector"
    assert plan["actions"][1]["action"] == "create_api_connector_call"
    assert plan["setup_checklist"] == ["Configure shared_headers.auth.value for API Connector 'Stripe'."]


def test_plan_api_connector_bundle_map_existing_blocks_missing_call() -> None:
    bundle = redact_api_connector_bundle(extract_api_connector_bundle(_context(), "stripe"))
    target = BubbleProjectContext(app_id="target-app", source="test", nodes=[], edges=[])

    plan = plan_api_connector_bundle(bundle, target, policy="map_existing")

    assert plan["ok"] is False
    assert "Stripe" in plan["blocked_reasons"][0]
