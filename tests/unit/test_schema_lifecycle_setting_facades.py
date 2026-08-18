from __future__ import annotations

import ast
import inspect
from pathlib import Path
from typing import Any

from bubble_mcp.aria_runtime.bubble_cli import BubbleCLI


def test_settings_public_methods_have_exactly_one_ast_definition() -> None:
    names = {"set_app_setting", "set_project_setting", "list_project_settings", "list_301_redirects", "create_301_redirect", "delete_301_redirect"}
    source_path = inspect.getsourcefile(BubbleCLI)
    assert source_path is not None
    module = ast.parse(Path(source_path).read_text(encoding="utf-8"))
    bubble_cli = next(node for node in module.body if isinstance(node, ast.ClassDef) and node.name == "BubbleCLI")
    counts = {name: 0 for name in names}
    for node in bubble_cli.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name in counts:
            counts[node.name] += 1
    assert counts == {name: 1 for name in names}


def test_settings_facades_keep_public_signatures_and_delegate_to_composed_service() -> None:
    expected = {
        "set_app_setting": ["self", "path", "value", "value_type", "dry_run"],
        "set_project_setting": ["self", "setting_key", "value", "value_type", "dry_run"],
        "list_project_settings": ["self", "as_json"],
        "list_301_redirects": ["self", "as_json"],
        "create_301_redirect": ["self", "from_url", "to_url", "rule_key", "id_counter", "dry_run"],
        "delete_301_redirect": ["self", "rule_key", "dry_run"],
    }
    for method, parameters in expected.items():
        assert list(inspect.signature(getattr(BubbleCLI, method)).parameters) == parameters

    cli = object.__new__(BubbleCLI)

    class SentinelSettings:
        def __getattr__(self, name: str) -> Any:
            return lambda *args, **kwargs: (name, args, kwargs)

    class SentinelService:
        settings = SentinelSettings()

    cli._schema_lifecycle = SentinelService()  # type: ignore[assignment]
    assert cli.set_app_setting("favicon", "x", "string", True) == ("set_app_setting", ("favicon", "x", "string", True), {})
    assert cli.set_project_setting("favicon", "x", "string", True) == ("set_project_setting", ("favicon", "x", "string", True), {})
    assert cli.list_project_settings(True) == ("list_project_settings", (True,), {})
    assert cli.list_301_redirects(True) == ("list_301_redirects", (True,), {})
    assert cli.create_301_redirect("/from", "/to", "rule", 2, True) == ("create_301_redirect", ("/from", "/to", "rule", 2, True), {})
    assert cli.delete_301_redirect("rule", True) == ("delete_301_redirect", ("rule", True), {})


def test_api_token_methods_remain_explicit_and_do_not_delegate_to_settings_service() -> None:
    source_path = inspect.getsourcefile(BubbleCLI)
    assert source_path is not None
    source = Path(source_path).read_text(encoding="utf-8")
    module = ast.parse(source)
    bubble_cli = next(node for node in module.body if isinstance(node, ast.ClassDef) and node.name == "BubbleCLI")
    token_names = {"create_api_token", "rename_api_token", "regenerate_api_token_private_key", "delete_api_token"}
    methods = {node.name: node for node in bubble_cli.body if isinstance(node, ast.FunctionDef) and node.name in token_names}
    assert methods.keys() == token_names
    for method in methods.values():
        body = ast.get_source_segment(source, method)
        assert "_schema_lifecycle.settings" not in body
        assert "self.set_app_setting" not in body
