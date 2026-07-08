from bubble_mcp.style_import.models import BubbleStyleCandidate
from bubble_mcp.style_import.planner import build_style_operations


def test_build_style_operations_uses_existing_state_tools() -> None:
    candidate = BubbleStyleCandidate(
        name="HTML Button Primary",
        element_type="Button",
        selector=".btn-primary",
        base={"bg_color": "#155eef", "font_color": "#ffffff"},
        states={
            "hover": {"bg_color": "#004eeb"},
            "focus": {"border_color": "#84caff"},
            "disabled": {"bg_color": "#d0d5dd"},
            "pressed": {"bg_color": "#00359e"},
        },
    )

    operations = build_style_operations("smoke", [candidate], False)

    assert [operation["tool"] for operation in operations] == [
        "create_style",
        "add_style_condition",
        "add_style_condition",
        "add_style_condition",
        "add_style_condition",
        "reorder_style_states",
    ]
    assert operations[0]["arguments"] == {
        "profile": "smoke",
        "name": "HTML Button Primary",
        "element_type": "Button",
        "dry_run": True,
        "execute": False,
        "allow_property_match": False,
        "bg_color": "#155eef",
        "font_color": "#ffffff",
    }
    assert operations[1]["arguments"]["condition"] == "hover"
    assert operations[1]["arguments"]["execute"] is False
    assert operations[2]["arguments"]["condition"] == "focus"
    assert operations[3]["arguments"]["condition"] == "pressed"
    assert operations[4]["arguments"]["condition"] == "disabled"
    assert operations[5]["arguments"]["order"] == "hover,focus,pressed,disabled"
    assert operations[5]["arguments"]["execute"] is False


def test_build_style_operations_sets_execute_dry_run_false() -> None:
    candidate = BubbleStyleCandidate(
        name="HTML Button Primary",
        element_type="Button",
        selector=".btn-primary",
        base={"bg_color": "#155eef"},
    )

    operations = build_style_operations(profile="smoke", candidates=[candidate], execute=True)

    assert operations == [
        {
            "tool": "create_style",
            "arguments": {
                "profile": "smoke",
                "name": "HTML Button Primary",
                "element_type": "Button",
                "dry_run": False,
                "execute": True,
                "allow_property_match": False,
                "bg_color": "#155eef",
            },
        }
    ]
