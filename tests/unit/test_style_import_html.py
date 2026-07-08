from pathlib import Path

from bubble_mcp.style_import.html import extract_style_rules_from_html


def test_extract_style_rules_groups_base_and_pseudo_states() -> None:
    html = Path("tests/fixtures/html/style-states.html").read_text(encoding="utf-8")

    rules = extract_style_rules_from_html(html, ".btn-primary")

    assert [rule.state for rule in rules] == ["base", "hover", "focus", "disabled", "pressed"]
    base = rules[0]
    assert base.selector == ".btn-primary"
    assert base.declarations["background-color"] == "#155eef"
    assert base.declarations["border-radius"] == "8px"
    pressed = rules[-1]
    assert pressed.state == "pressed"
    assert pressed.source_selector == ".btn-primary:active"


def test_extract_style_rules_includes_extra_css_and_inline_style_attributes() -> None:
    html = '<button class="btn-primary" style="color: #111111; font-size: 14px">Save</button>'

    rules = extract_style_rules_from_html(
        html,
        selector=".btn-primary",
        extra_css=[".btn-primary:focus-visible { border-color: #84caff; }"],
    )

    assert [rule.state for rule in rules] == ["base", "focus"]
    assert rules[0].declarations["color"] == "#111111"
    assert rules[0].declarations["font-size"] == "14px"
    assert rules[1].source_selector == ".btn-primary:focus-visible"


def test_extract_style_rules_matches_compound_selectors_for_selected_element() -> None:
    html = """
    <style>
      button.btn-primary { color: #ffffff; }
      .card .btn-primary:hover { color: #eeeeee; }
      button.btn-primary:focus { border-color: #84caff; }
    </style>
    <section class="card"><button class="btn-primary">Save</button></section>
    """

    rules = extract_style_rules_from_html(html, ".btn-primary")

    assert [rule.state for rule in rules] == ["base", "hover", "focus"]
    assert rules[0].source_selector == "button.btn-primary"
    assert rules[1].source_selector == ".card .btn-primary:hover"
    assert rules[2].source_selector == "button.btn-primary:focus"


def test_extract_style_rules_resolves_simple_css_variables() -> None:
    html = """
    <style>
      :root { --primary: rgb(21, 94, 239); }
      .btn-primary { background-color: var(--primary); }
      .btn-primary:hover {
        --hover-bg: #004eeb;
        background-color: var(--hover-bg, #000000);
      }
    </style>
    <button class="btn-primary">Save</button>
    """

    rules = extract_style_rules_from_html(html, ".btn-primary")

    assert rules[0].declarations["background-color"] == "rgb(21, 94, 239)"
    assert rules[1].declarations["background-color"] == "#004eeb"
