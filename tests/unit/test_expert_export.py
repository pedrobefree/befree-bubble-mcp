import json
from pathlib import Path

from bubble_mcp.harness.expert import classify_editor_payload, export_expert_eval_cases


def sample_capture() -> dict:
    return {
        "id": "cap-text",
        "message": "Create a text saying Hello",
        "request": {
            "headers": {"cookie": "sid=secret", "authorization": "Bearer abcdefghijklmnop"},
            "payload": {
                "appname": "synthetic-app",
                "app_version": "test",
                "changes": [
                    {
                        "intent": {"name": "CreateElement"},
                        "path_array": ["%p3", "index", "%el", "bText"],
                        "body": {"id": "bText", "%x": "Text", "%p": {"%nm": "Title", "%3": "Hello"}},
                    }
                ],
            },
        },
    }


def test_classify_editor_payload_infers_visual_tool_hint() -> None:
    payload = sample_capture()["request"]["payload"]

    classification = classify_editor_payload(payload)

    assert classification["families"] == ["visual_element"]
    assert classification["tool_hints"] == ["create_text"]
    assert classification["change_count"] == 1


def test_export_expert_eval_cases_redacts_sensitive_capture(tmp_path: Path) -> None:
    source = tmp_path / "captures.json"
    output = tmp_path / "eval.json"
    source.write_text(json.dumps({"entries": [sample_capture()]}), encoding="utf-8")

    result = export_expert_eval_cases(source, output)
    cases = json.loads(output.read_text(encoding="utf-8"))
    rendered = json.dumps(cases)

    assert result["ok"] is True
    assert result["cases"] == 1
    assert cases[0]["expectedTool"] == "create_text"
    assert cases[0]["classification"]["families"] == ["visual_element"]
    assert "sid=secret" not in rendered
    assert "Bearer abcdefghijklmnop" not in rendered
