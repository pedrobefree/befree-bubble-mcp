import json
import subprocess
import sys
from pathlib import Path

import pytest

from bubble_mcp.cli_leaf_inventory import (
    CLI_LEAF_CLASSIFICATIONS,
    CliLeafClassification,
    CliLeafSpec,
    DiscoveredCliLeaf,
    cli_leaf_map_report,
    classify_cli_leaves,
    discover_cli_leaves,
    modern_cli_leaves,
    modern_cli_leaf_classifications,
)


REPOSITORY_ROOT = Path(__file__).resolve().parents[2]


def test_discover_cli_leaves_tracks_nested_paths_and_bound_handlers() -> None:
    source = '''
def build_parser():
    parser = argparse.ArgumentParser()
    roots = parser.add_subparsers(dest="command", required=True)
    init_parser = roots.add_parser("init")
    init_parser.set_defaults(func=command_init)
    profile_parser = roots.add_parser("profile")
    profile_children = profile_parser.add_subparsers(dest="profile_command", required=True)
    add_parser = profile_children.add_parser("add")
    add_parser.set_defaults(verbose=False)
    add_parser.set_defaults(func=command_profile_add)
    extension_parser = roots.add_parser("extension")
    extension_children = extension_parser.add_subparsers(dest="extension_command", required=True)
    companion_parser = extension_children.add_parser("companion")
    companion_children = companion_parser.add_subparsers(dest="companion_command", required=True)
    serve_parser = companion_children.add_parser(
        "serve",
    )
    serve_parser.set_defaults(func=command_extension_companion_serve)
'''

    assert discover_cli_leaves(source) == (
        DiscoveredCliLeaf(("extension", "companion", "serve"), "command_extension_companion_serve", 19),
        DiscoveredCliLeaf(("init",), "command_init", 6),
        DiscoveredCliLeaf(("profile", "add"), "command_profile_add", 11),
    )


def test_discover_cli_leaves_sorts_independently_of_declaration_order() -> None:
    source = '''
def build_parser():
    parser = argparse.ArgumentParser()
    roots = parser.add_subparsers(dest="command", required=True)
    z_parser = roots.add_parser("z-last")
    z_parser.set_defaults(func=command_z)
    a_parser = roots.add_parser("a-first")
    a_parser.set_defaults(func=command_a)
'''

    assert [leaf.command_path for leaf in discover_cli_leaves(source)] == [
        ("a-first",),
        ("z-last",),
    ]


@pytest.mark.parametrize(
    ("source", "message"),
    [
        (
            '''
def build_parser():
    parser = argparse.ArgumentParser()
    roots = parser.add_subparsers(dest="command", required=True)
    leaf = roots.add_parser(dynamic_name)
    leaf.set_defaults(func=command_dynamic)
''',
            "literal string",
        ),
        (
            '''
def build_parser():
    parser = argparse.ArgumentParser()
    roots = parser.add_subparsers(dest="command", required=True)
    first = roots.add_parser("same")
    first.set_defaults(func=command_first)
    second = roots.add_parser("same")
    second.set_defaults(func=command_second)
''',
            "Duplicate CLI command path: same",
        ),
        (
            '''
def build_parser():
    parser = argparse.ArgumentParser()
    roots = parser.add_subparsers(dest="command", required=True)
    leaf = roots.add_parser("missing-handler")
''',
            "Terminal CLI command has no func handler: missing-handler",
        ),
        (
            '''
def build_parser():
    parser = argparse.ArgumentParser()
    roots = parser.add_subparsers(dest="command", required=True)
    leaf = roots.add_parser("dynamic-handler")
    leaf.set_defaults(func=handlers["dynamic"])
''',
            "func handler must be a named function",
        ),
    ],
)
def test_discover_cli_leaves_fails_closed_for_uninspectable_parser_contracts(
    source: str,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        discover_cli_leaves(source)


def test_modern_cli_has_complete_terminal_handler_inventory() -> None:
    leaves = modern_cli_leaves()
    paths = {leaf.command_path for leaf in leaves}

    assert len(leaves) == 105
    assert len({leaf.handler for leaf in leaves}) == 105
    assert {
        ("profile", "add"),
        ("transfer", "execute"),
        ("extension", "companion", "serve"),
        ("skill", "author", "generate"),
        ("language", "query"),
        ("tools", "quality"),
        ("smoke", "runtime"),
    } <= paths


def test_classify_cli_leaves_joins_valid_registry_to_existing_capability() -> None:
    leaves = (DiscoveredCliLeaf(("profile", "list"), "command_profile_list", 10),)
    registry = {
        ("profile", "list"): CliLeafSpec(
            "direct_mcp",
            ("bubble_profile_list",),
            "Lists profiles through the matching MCP capability.",
        )
    }

    assert classify_cli_leaves(
        leaves,
        catalog_names={"bubble_profile_list"},
        registry=registry,
    ) == (
        CliLeafClassification(
            ("profile", "list"),
            "command_profile_list",
            10,
            "direct_mcp",
            ("bubble_profile_list",),
            "Lists profiles through the matching MCP capability.",
        ),
    )


@pytest.mark.parametrize(
    ("leaves", "registry", "catalog_names", "message"),
    [
        (
            (DiscoveredCliLeaf(("profile", "list"), "command_profile_list", 10),),
            {},
            {"bubble_profile_list"},
            "Unclassified modern CLI command: profile list",
        ),
        (
            (),
            {
                ("removed",): CliLeafSpec(
                    "local_housekeeping",
                    (),
                    "Removed local command.",
                )
            },
            set(),
            "Stale modern CLI classification: removed",
        ),
        (
            (DiscoveredCliLeaf(("bad",), "command_bad", 10),),
            {("bad",): CliLeafSpec("direct_mcp", (), "Missing capability.")},
            set(),
            "direct_mcp requires exactly one capability: bad",
        ),
        (
            (DiscoveredCliLeaf(("bad",), "command_bad", 10),),
            {("bad",): CliLeafSpec("composed_mcp", (), "Missing capabilities.")},
            set(),
            "composed_mcp requires at least one capability: bad",
        ),
        (
            (DiscoveredCliLeaf(("bad",), "command_bad", 10),),
            {("bad",): CliLeafSpec("administration_only", ("bubble_profile_list",), "Must be local.")},
            {"bubble_profile_list"},
            "administration_only cannot declare MCP capabilities: bad",
        ),
        (
            (DiscoveredCliLeaf(("bad",), "command_bad", 10),),
            {("bad",): CliLeafSpec("direct_mcp", ("missing_tool",), "Unknown tool.")},
            set(),
            "Unknown MCP capability missing_tool for modern CLI command: bad",
        ),
        (
            (DiscoveredCliLeaf(("bad",), "command_bad", 10),),
            {("bad",): CliLeafSpec("unsupported", (), "Invalid class.")},
            set(),
            "Invalid modern CLI catalog class unsupported: bad",
        ),
        (
            (DiscoveredCliLeaf(("bad",), "command_bad", 10),),
            {("bad",): CliLeafSpec("local_housekeeping", (), "   ")},
            set(),
            "Modern CLI classification requires a reason: bad",
        ),
    ],
)
def test_classify_cli_leaves_fails_closed_for_invalid_registry(
    leaves: tuple[DiscoveredCliLeaf, ...],
    registry: dict[tuple[str, ...], CliLeafSpec],
    catalog_names: set[str],
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        classify_cli_leaves(leaves, catalog_names=catalog_names, registry=registry)


def test_current_modern_cli_classification_is_complete_and_reviewable() -> None:
    records = modern_cli_leaf_classifications()
    by_path = {record.command_path: record for record in records}

    assert len(records) == 105
    assert len(CLI_LEAF_CLASSIFICATIONS) == 105
    assert by_path[("profile", "list")].mcp_capabilities == ("bubble_profile_list",)
    assert by_path[("import", "html")].catalog_class == "composed_mcp"
    assert by_path[("extension", "companion", "serve")].catalog_class == "administration_only"
    assert by_path[("init",)].catalog_class == "local_housekeeping"
    assert by_path[("context", "hydrate-reusables")].catalog_class == "administration_only"
    assert by_path[("context", "inspect-bubble")].catalog_class == "administration_only"
    assert by_path[("validate-plan",)].catalog_class == "administration_only"
    assert all(record.reason.strip() for record in records)


def test_cli_leaf_map_report_is_complete_and_deterministic() -> None:
    first = cli_leaf_map_report()
    second = cli_leaf_map_report()

    assert first == second
    assert first["ok"] is True
    assert first["summary"] == {
        "leaf_count": 105,
        "classified_count": 105,
        "direct_mcp_count": 99,
        "composed_mcp_count": 1,
        "administration_only_count": 4,
        "local_housekeeping_count": 1,
        "catalog_gap_count": 0,
        "issue_count": 0,
    }
    assert first["issues"] == []
    paths = [tuple(record["command_path"]) for record in first["records"]]
    assert paths == sorted(paths)


def test_cli_leaf_map_report_names_structural_failure() -> None:
    source = '''
def build_parser():
    parser = argparse.ArgumentParser()
    roots = parser.add_subparsers(dest="command", required=True)
    leaf = roots.add_parser("new-command")
    leaf.set_defaults(func=command_new)
'''

    report = cli_leaf_map_report(source=source, registry={}, catalog_names=set())

    assert report["ok"] is False
    assert report["summary"]["leaf_count"] == 1
    assert report["summary"]["classified_count"] == 0
    assert report["summary"]["issue_count"] == 1
    assert report["issues"] == [
        {
            "scope": "modern_cli",
            "name": "cli_leaf_map",
            "message": "Unclassified modern CLI command: new-command",
        }
    ]


def test_cli_leaf_map_report_fails_when_a_catalog_gap_is_declared() -> None:
    source = '''
def build_parser():
    parser = argparse.ArgumentParser()
    roots = parser.add_subparsers(dest="command", required=True)
    leaf = roots.add_parser("unexposed")
    leaf.set_defaults(func=command_unexposed)
'''
    registry = {
        ("unexposed",): CliLeafSpec(
            "catalog_gap",
            (),
            "This project operation still has no agent-facing capability.",
        )
    }

    report = cli_leaf_map_report(source=source, registry=registry, catalog_names=set())

    assert report["ok"] is False
    assert report["summary"]["catalog_gap_count"] == 1
    assert report["issues"] == [
        {
            "scope": "modern_cli",
            "name": "unexposed",
            "message": "Modern CLI project operation has no MCP capability: unexposed",
        }
    ]


def test_cli_leaf_map_audit_script_runs_from_checkout() -> None:
    result = subprocess.run(
        [sys.executable, "scripts/audit_cli_leaf_map.py"],
        cwd=REPOSITORY_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    report = json.loads(result.stdout)
    assert report["ok"] is True
    assert report["summary"]["leaf_count"] == 105
    assert report["summary"]["catalog_gap_count"] == 0
