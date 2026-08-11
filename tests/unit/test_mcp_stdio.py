import io
import json
import time
from threading import Event
from typing import Iterator

from bubble_mcp.server.stdio import serve
from bubble_mcp.sessions.browser import SessionCaptureCancelled


class CoordinatedInput:
    def __init__(self, started: Event) -> None:
        self.started = started

    def __iter__(self) -> Iterator[str]:
        yield json.dumps(
            {
                "jsonrpc": "2.0",
                "id": 10,
                "method": "tools/call",
                "params": {
                    "name": "bubble_session_login",
                    "arguments": {"profile": "smoke"},
                    "_meta": {"progressToken": "login-10"},
                },
            }
        )
        assert self.started.wait(timeout=1)
        yield json.dumps({"jsonrpc": "2.0", "id": 11, "method": "ping"})
        yield json.dumps(
            {
                "jsonrpc": "2.0",
                "method": "notifications/cancelled",
                "params": {"requestId": 10, "reason": "user cancelled"},
            }
        )


def test_stdio_login_keeps_server_responsive_and_honors_cancellation(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    started = Event()

    def fake_call_tool(name, arguments, *, cancelled=None, progress=None):  # type: ignore[no-untyped-def]
        assert name == "bubble_session_login"
        assert arguments == {"profile": "smoke"}
        assert cancelled is not None
        started.set()
        if progress is not None:
            progress("Browser opened.")
        while not cancelled():
            time.sleep(0.001)
        raise SessionCaptureCancelled("Bubble session login was cancelled by the MCP client.")

    monkeypatch.setattr("bubble_mcp.server.stdio.call_tool", fake_call_tool)
    output = io.StringIO()

    serve(CoordinatedInput(started), output)  # type: ignore[arg-type]

    messages = [json.loads(line) for line in output.getvalue().splitlines()]
    progress = next(message for message in messages if message.get("method") == "notifications/progress")
    ping_index = next(index for index, message in enumerate(messages) if message.get("id") == 11)
    login_index = next(index for index, message in enumerate(messages) if message.get("id") == 10)
    login = messages[login_index]

    assert progress["params"] == {
        "progressToken": "login-10",
        "progress": 1,
        "message": "Browser opened.",
    }
    assert ping_index < login_index
    assert login["result"]["isError"] is True
    assert login["result"]["structuredContent"]["error_class"] == "SessionCaptureCancelled"
