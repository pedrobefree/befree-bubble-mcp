from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen


STATE_PSEUDOS = {
    "hover": ":hover",
    "focus": ":focus",
    "pressed": ":active",
    "disabled": ":disabled",
}


def _style_state_css(selector: str, style_states: dict[str, Any]) -> str:
    blocks: list[str] = []
    for state, pseudo in STATE_PSEUDOS.items():
        declarations = style_states.get(state)
        if not isinstance(declarations, dict) or not declarations:
            continue
        lines = [
            f"  {str(property_name).strip().lower()}: {str(value).strip()};"
            for property_name, value in declarations.items()
            if str(property_name).strip() and str(value).strip()
        ]
        if lines:
            blocks.append(f"{selector}{pseudo} {{\n" + "\n".join(lines) + "\n}")
    return "\n".join(blocks)


def rendered_payload_to_html(payload: dict[str, Any], *, selector: str) -> str:
    html = payload.get("html")
    if not isinstance(html, str) or not html.strip():
        raise RuntimeError("Rendered HTML extraction returned no HTML.")
    style_states = payload.get("styleStates")
    if not isinstance(style_states, dict):
        return html
    state_css = _style_state_css(selector or str(payload.get("selector") or "body"), style_states)
    if not state_css:
        return html
    return f"<style>\n{state_css}\n</style>\n{html}"


def fetch_url_html(*, url: str, timeout_ms: int = 35000) -> str:
    request = Request(url, headers={"User-Agent": "befree-bubble-mcp"})
    with urlopen(request, timeout=max(1, timeout_ms / 1000)) as response:  # noqa: S310
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def render_url_to_html(*, url: str, selector: str, timeout_ms: int = 35000) -> str:
    script_path = Path(__file__).resolve().parents[1] / "aria_runtime" / "scripts" / "extract_rendered_html.mjs"
    if not script_path.exists():
        raise FileNotFoundError(f"Rendered HTML extractor not found: {script_path}")
    node_bin = shutil.which(os.environ.get("BUBBLE_CLI_NODE_BIN", "node"))
    if not node_bin:
        raise RuntimeError("Node.js is required for rendered URL extraction.")
    with tempfile.NamedTemporaryFile(prefix="bubble-style-render-", suffix=".json", delete=False) as handle:
        output_path = Path(handle.name)
    try:
        completed = subprocess.run(
            [
                node_bin,
                str(script_path),
                "--url",
                url,
                "--selector",
                selector or "body",
                "--output",
                str(output_path),
                "--timeout",
                str(timeout_ms),
            ],
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise RuntimeError(f"Rendered HTML extraction failed: {detail[-800:]}")
        payload = json.loads(output_path.read_text(encoding="utf-8"))
        if not isinstance(payload, dict):
            raise RuntimeError("Rendered HTML extraction returned an invalid payload.")
        return rendered_payload_to_html(payload, selector=selector)
    finally:
        try:
            output_path.unlink()
        except FileNotFoundError:
            pass
