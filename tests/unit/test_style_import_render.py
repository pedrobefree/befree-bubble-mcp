import json
import subprocess
from pathlib import Path

from bubble_mcp.style_import.render import rendered_payload_to_html, render_url_to_html


def test_rendered_payload_to_html_injects_state_css() -> None:
    html = rendered_payload_to_html(
        {
            "html": '<button class="btn-primary" style="background-color: rgb(21, 94, 239);">Save</button>',
            "styleStates": {
                "base": {"background-color": "rgb(21, 94, 239)"},
                "hover": {"background-color": "rgb(0, 78, 235)"},
                "pressed": {"border-color": "rgb(0, 53, 158)"},
            },
        },
        selector=".btn-primary",
    )

    assert ".btn-primary:hover" in html
    assert "background-color: rgb(0, 78, 235);" in html
    assert ".btn-primary:active" in html
    assert "border-color: rgb(0, 53, 158);" in html
    assert '<button class="btn-primary"' in html


def test_render_url_to_html_uses_existing_render_script(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    calls = []

    def fake_run(cmd, **_kwargs):  # type: ignore[no-untyped-def]
        calls.append(cmd)
        output_path = Path(cmd[cmd.index("--output") + 1])
        output_path.write_text(
            json.dumps(
                {
                    "html": '<button class="btn-primary" style="background-color: rgb(21, 94, 239);">Save</button>',
                    "styleStates": {"hover": {"background-color": "rgb(0, 78, 235)"}},
                }
            ),
            encoding="utf-8",
        )
        return subprocess.CompletedProcess(cmd, 0, "", "")

    monkeypatch.setattr("bubble_mcp.style_import.render.shutil.which", lambda _name: "/usr/bin/node")
    monkeypatch.setattr("bubble_mcp.style_import.render.subprocess.run", fake_run)

    html = render_url_to_html(url="https://example.test/button", selector=".btn-primary", timeout_ms=12000)

    assert calls
    assert "--url" in calls[0]
    assert "https://example.test/button" in calls[0]
    assert "--selector" in calls[0]
    assert ".btn-primary" in calls[0]
    assert "--timeout" in calls[0]
    assert "12000" in calls[0]
    assert ".btn-primary:hover" in html
