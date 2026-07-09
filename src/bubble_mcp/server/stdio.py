"""Minimal MCP stdio server."""

from __future__ import annotations

import json
import sys
from typing import Any, TextIO

from bubble_mcp import __version__
from bubble_mcp.core.redaction import redact_sensitive
from bubble_mcp.server.completion import complete
from bubble_mcp.server.instructions import SERVER_INSTRUCTIONS
from bubble_mcp.server.prompts import get_prompt, list_prompts
from bubble_mcp.server.resources import list_resource_templates, list_resources, read_resource
from bubble_mcp.server.schemas import list_tool_schemas
from bubble_mcp.server.tools import call_tool


JSONRPC_VERSION = "2.0"


def success_response(request_id: Any, result: Any) -> dict[str, Any]:
    return {"jsonrpc": JSONRPC_VERSION, "id": request_id, "result": result}


def error_response(request_id: Any, code: int, message: str) -> dict[str, Any]:
    return {
        "jsonrpc": JSONRPC_VERSION,
        "id": request_id,
        "error": {"code": code, "message": message},
    }


def tool_result(result: dict[str, Any]) -> dict[str, Any]:
    redacted = redact_sensitive(result)
    return {
        "content": [{"type": "text", "text": json.dumps(redacted)}],
        "structuredContent": redacted,
    }


def tool_error_result(name: str, exc: Exception) -> dict[str, Any]:
    payload = redact_sensitive(
        {
            "ok": False,
            "tool": name,
            "error": str(exc),
            "error_class": exc.__class__.__name__,
        }
    )
    return {
        "isError": True,
        "content": [{"type": "text", "text": json.dumps(payload)}],
        "structuredContent": payload,
    }


def handle_request(request: dict[str, Any]) -> dict[str, Any] | None:
    """Handle a JSON-RPC request."""

    request_id = request.get("id")
    method = request.get("method")
    raw_params = request.get("params")
    params: dict[str, Any] = raw_params if isinstance(raw_params, dict) else {}

    try:
        if method == "initialize":
            return success_response(
                request_id,
                {
                    "protocolVersion": "2024-11-05",
                    "serverInfo": {"name": "befree-bubble-mcp", "version": __version__},
                    "instructions": SERVER_INSTRUCTIONS,
                    "capabilities": {
                        "tools": {},
                        "resources": {"templates": True},
                        "prompts": {},
                        "completions": {},
                    },
                },
            )
        if method == "ping":
            return success_response(request_id, {})
        if method == "tools/list":
            return success_response(request_id, {"tools": list_tool_schemas()})
        if method == "tools/call":
            name = str(params.get("name") or "")
            raw_arguments = params.get("arguments")
            arguments: dict[str, Any] = raw_arguments if isinstance(raw_arguments, dict) else {}
            try:
                result = call_tool(name, arguments)
            except Exception as exc:
                return success_response(request_id, tool_error_result(name, exc))
            return success_response(request_id, tool_result(result))
        if method == "resources/list":
            return success_response(request_id, {"resources": list_resources()})
        if method == "resources/templates/list":
            return success_response(request_id, {"resourceTemplates": list_resource_templates()})
        if method == "resources/read":
            uri = str(params.get("uri") or "")
            return success_response(request_id, read_resource(uri))
        if method == "prompts/list":
            return success_response(request_id, {"prompts": list_prompts()})
        if method == "prompts/get":
            name = str(params.get("name") or "")
            raw_arguments = params.get("arguments")
            arguments = raw_arguments if isinstance(raw_arguments, dict) else {}
            return success_response(request_id, get_prompt(name, arguments))
        if method == "completion/complete":
            return success_response(request_id, complete(params))
        if method and str(method).startswith("notifications/"):
            return None
        return error_response(request_id, -32601, f"Method not found: {method}")
    except Exception as exc:
        return error_response(request_id, -32000, str(exc))


def serve(input_stream: TextIO = sys.stdin, output_stream: TextIO = sys.stdout) -> None:
    """Serve newline-delimited JSON-RPC over stdio."""

    for line in input_stream:
        if not line.strip():
            continue
        try:
            request = json.loads(line)
            if not isinstance(request, dict):
                response = error_response(None, -32600, "Invalid request")
            else:
                maybe_response = handle_request(request)
                if maybe_response is None:
                    continue
                response = maybe_response
        except json.JSONDecodeError as exc:
            response = error_response(None, -32700, f"Parse error: {exc.msg}")

        if response is not None:
            output_stream.write(json.dumps(response, separators=(",", ":")) + "\n")
            output_stream.flush()


def main() -> int:
    # MCP is a UTF-8 wire protocol, but Python's default stdio encoding on
    # Windows follows the console codepage (e.g. cp1252), not UTF-8. Without
    # this, any non-ASCII character in a request/response gets mis-decoded
    # (mojibake) or corrupted further on every subsequent read/write.
    for stream in (sys.stdin, sys.stdout):
        if getattr(stream, "encoding", "").lower().replace("-", "") != "utf8":
            reconfigure = getattr(stream, "reconfigure", None)
            if callable(reconfigure):
                reconfigure(encoding="utf-8")
    serve()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
