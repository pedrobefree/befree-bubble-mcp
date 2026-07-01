from bubble_mcp.compiler.payload import compile_plan_to_write_payloads
from bubble_mcp.execution.executor import execute_plan
from bubble_mcp.sessions.store import session_from_payload


def test_compile_create_text_step_to_write_payload() -> None:
    plan = {
        "steps": [
            {
                "id": "s1",
                "tool_name": "create_text",
                "args": {"context": "index", "parent": "index", "content": "Hello", "name": "tx_hello"},
            }
        ]
    }

    compiled = compile_plan_to_write_payloads(plan, app_id="synthetic-app")
    payload = compiled["steps"][0]["args"]["write_payload"]

    assert payload["appname"] == "synthetic-app"
    assert payload["changes"][0]["intent"]["name"] == "CreateElement"
    assert payload["changes"][0]["path_array"] == ["%p3", "index"]
    assert payload["changes"][0]["body"]["%x"] == "Text"
    assert payload["changes"][0]["body"]["%p"]["%3"] == "Hello"


def test_compile_create_group_step_to_write_payload() -> None:
    plan = {
        "steps": [
            {
                "id": "s1",
                "tool_name": "create_group",
                "args": {"context": "index", "parent": "index", "name": "Card", "layout": "row"},
            }
        ]
    }

    compiled = compile_plan_to_write_payloads(plan, app_id="synthetic-app")
    payload = compiled["steps"][0]["args"]["write_payload"]

    assert payload["changes"][0]["body"]["%x"] == "Group"
    assert payload["changes"][0]["body"]["%p"]["container_layout"] == "row"


def test_execute_plan_can_compile_missing_payload_before_execution() -> None:
    class FakeClient:
        def write(self, payload, session, *, dry_run=False):  # type: ignore[no-untyped-def]
            return {"ok": True, "payload": payload, "dry_run": dry_run}

    session = session_from_payload({"appId": "synthetic-app", "headers": {"Cookie": "sid=secret"}})
    plan = {
        "steps": [
            {
                "id": "s1",
                "tool_name": "create_text",
                "args": {"context": "index", "content": "Hello"},
            }
        ]
    }

    result = execute_plan(
        plan,
        profile="dev",
        execute=True,
        compile_missing=True,
        session=session,
        client=FakeClient(),  # type: ignore[arg-type]
    )

    assert result["ok"] is True
    assert result["results"][0]["result"]["payload"]["changes"][0]["body"]["%x"] == "Text"

