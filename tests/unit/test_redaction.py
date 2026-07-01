from bubble_mcp.core.redaction import redact_sensitive


def test_redacts_sensitive_keys_and_values() -> None:
    payload = {
        "cookie": "session=abc",
        "nested": {
            "message": "Authorization: Bearer abcdefghijklmnopqrstuvwxyz",
            "safe": "visible",
        },
    }

    redacted = redact_sensitive(payload)

    assert redacted["cookie"] == "[REDACTED]"
    assert redacted["nested"]["safe"] == "visible"
    assert "abcdefghijklmnopqrstuvwxyz" not in redacted["nested"]["message"]
