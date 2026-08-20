"""Deterministic inventory for terminal commands in the modern nested CLI."""

from __future__ import annotations

import ast
import argparse
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Iterable, Mapping


@dataclass(frozen=True, slots=True)
class DiscoveredCliLeaf:
    """One terminal CLI path and the function bound through ``set_defaults``."""

    command_path: tuple[str, ...]
    handler: str
    line: int


CLI_CATALOG_CLASSES = frozenset(
    {
        "direct_mcp",
        "composed_mcp",
        "administration_only",
        "local_housekeeping",
        "catalog_gap",
    }
)


@dataclass(frozen=True, slots=True)
class CliLeafSpec:
    """Semantic classification supplied for one source-derived CLI path."""

    catalog_class: str
    mcp_capabilities: tuple[str, ...]
    reason: str
    expected_handler: str | None = None


@dataclass(frozen=True, slots=True)
class CliLeafClassification:
    """Complete source and MCP relationship for one terminal CLI command."""

    command_path: tuple[str, ...]
    handler: str
    line: int
    catalog_class: str
    mcp_capabilities: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict[str, object]:
        return {
            "command_path": list(self.command_path),
            "handler": self.handler,
            "line": self.line,
            "catalog_class": self.catalog_class,
            "mcp_capabilities": list(self.mcp_capabilities),
            "reason": self.reason,
        }


def _direct(capability: str) -> CliLeafSpec:
    return CliLeafSpec(
        "direct_mcp",
        (capability,),
        f"Exposes the same operation as the existing {capability} MCP capability.",
    )


def _composed(*capabilities: str, reason: str) -> CliLeafSpec:
    return CliLeafSpec("composed_mcp", tuple(capabilities), reason)


def _administration(reason: str) -> CliLeafSpec:
    return CliLeafSpec("administration_only", (), reason)


def _local(reason: str) -> CliLeafSpec:
    return CliLeafSpec("local_housekeeping", (), reason)


CLI_LEAF_CLASSIFICATIONS: dict[tuple[str, ...], CliLeafSpec] = {
    ("branch", "contributors"): _direct("bubble_branch_contributors"),
    ("branch", "create"): _direct("bubble_branch_create"),
    ("branch", "delete"): _direct("bubble_branch_delete"),
    ("branch", "list"): _direct("bubble_branch_list"),
    ("branch", "merge-confirm"): _direct("bubble_branch_merge_confirm"),
    ("branch", "merge-conflicts-describe"): _direct("bubble_branch_merge_conflicts_describe"),
    ("branch", "merge-finalize"): _direct("bubble_branch_merge_finalize"),
    ("branch", "merge-resolve-conflicts"): _direct("bubble_branch_merge_resolve_conflicts"),
    ("branch", "merge-start"): _direct("bubble_branch_merge_start"),
    ("browser", "cancel-deploy"): _direct("bubble_cancel_scheduled_deploy"),
    ("browser", "deploy-history"): _direct("bubble_deploy_history"),
    ("browser", "list-deploys"): _direct("bubble_list_scheduled_deploys"),
    ("browser", "schedule-deploy"): _direct("bubble_schedule_deploy"),
    ("changelog", "fetch"): _direct("bubble_changelog_fetch"),
    ("compile-plan",): _direct("bubble_compile_plan"),
    ("context", "detect"): _direct("bubble_context_detect"),
    ("context", "find"): _direct("bubble_context_find"),
    ("context", "hydrate-reusables"): _administration(
        "Repairs a local cached export through an authenticated diagnostic path; it is not a public MCP operation."
    ),
    ("context", "import"): _direct("bubble_context_import"),
    ("context", "inspect-bubble"): _administration(
        "Inspects a local .bubble export for operator diagnostics rather than project mutation or agent execution."
    ),
    ("context", "summary"): _direct("bubble_context_summary"),
    ("eval", "capture-bubble-visual"): _direct("bubble_visual_capture_actual"),
    ("eval", "capture-visual"): _direct("bubble_visual_capture"),
    ("eval", "export-expert"): _direct("bubble_eval_export_expert"),
    ("eval", "run"): _direct("bubble_eval_run"),
    ("eval", "visual"): _direct("bubble_visual_compare"),
    ("eval", "visual-audit"): _direct("bubble_visual_audit"),
    ("execute-plan",): _direct("bubble_execute_plan"),
    ("extension", "companion", "serve"): _administration(
        "Runs the long-lived local companion process; MCP exposes bounded start, status, and stop operations instead."
    ),
    ("extension", "disable"): _direct("bubble_extension_disable"),
    ("extension", "enable"): _direct("bubble_extension_enable"),
    ("extension", "import"): _direct("bubble_extension_import"),
    ("extension", "list"): _direct("bubble_extension_list"),
    ("extension", "validate"): _direct("bubble_extension_validate"),
    ("framework", "generate"): _direct("bubble_framework_generate_artifacts"),
    ("framework", "list"): _direct("bubble_framework_list"),
    ("framework", "status"): _direct("bubble_framework_status"),
    ("import", "html"): _composed(
        "create_from_html",
        "bubble_plan",
        "bubble_compile_plan",
        reason="Chooses between runtime HTML import and local plan/compile paths according to CLI arguments.",
    ),
    ("import", "html-styles"): _direct("create_styles_from_html"),
    ("init",): _local("Creates checkout-local settings and does not operate on a Bubble project."),
    ("knowledge", "fetch"): _direct("bubble_knowledge_fetch"),
    ("knowledge", "guidance"): _direct("bubble_manual_guidance"),
    ("knowledge", "refresh-source"): _direct("bubble_knowledge_refresh_source"),
    ("knowledge", "search"): _direct("bubble_knowledge_search"),
    ("language", "cache-status"): _direct("bubble_language_cache_status"),
    ("language", "detail"): _direct("bubble_language_tool_detail"),
    ("language", "execute-program"): _direct("bubble_framework_execute_program"),
    ("language", "framework-pack"): _direct("bubble_framework_language_pack"),
    ("language", "index"): _direct("bubble_language_index"),
    ("language", "query"): _direct("bubble_language_query"),
    ("language", "text-plan"): _direct("bubble_framework_plan_from_text"),
    ("language", "workspace-sync"): _direct("bubble_framework_workspace_sync"),
    ("learning", "list"): _direct("bubble_learning_list"),
    ("learning", "record"): _direct("bubble_learning_record"),
    ("metrics", "audit"): _direct("bubble_performance_audit"),
    ("metrics", "logs"): _direct("bubble_logs_fetch"),
    ("metrics", "plan-usage"): _direct("bubble_plan_usage_get"),
    ("metrics", "storage"): _direct("bubble_storage_usage_get"),
    ("metrics", "time-series"): _direct("bubble_time_series_read"),
    ("metrics", "workflow-runs"): _direct("bubble_workflow_runs_get"),
    ("metrics", "workload-breakdown"): _direct("bubble_workload_usage_breakdown"),
    ("metrics", "workload-by-date"): _direct("bubble_workload_usage_by_date"),
    ("plan",): _direct("bubble_plan"),
    ("plugin", "install"): _direct("bubble_plugin_install"),
    ("profile", "add"): _direct("bubble_profile_add"),
    ("profile", "bootstrap"): _direct("bubble_project_bootstrap"),
    ("profile", "list"): _direct("bubble_profile_list"),
    ("profile", "refresh-cache"): _direct("bubble_profile_cache_refresh"),
    ("profile", "status"): _direct("bubble_profile_status"),
    ("readiness",): _direct("bubble_readiness_check"),
    ("session", "import"): _direct("bubble_session_import"),
    ("session", "inspect"): _direct("bubble_session_inspect"),
    ("session", "list"): _direct("bubble_session_list"),
    ("session", "login"): _direct("bubble_session_login"),
    ("skill", "author", "generate"): _direct("bubble_skill_author_generate"),
    ("skill", "author", "start"): _direct("bubble_skill_author_start"),
    ("skill", "author", "update"): _direct("bubble_skill_author_update"),
    ("skill", "describe"): _direct("bubble_skill_describe"),
    ("skill", "disable"): _direct("bubble_skill_disable"),
    ("skill", "enable"): _direct("bubble_skill_enable"),
    ("skill", "export"): _direct("bubble_skill_export"),
    ("skill", "import"): _direct("bubble_skill_import"),
    ("skill", "list"): _direct("bubble_skill_list"),
    ("skill", "run"): _direct("bubble_skill_run"),
    ("skill", "validate"): _direct("bubble_skill_validate"),
    ("smoke", "runtime"): _direct("bubble_runtime_smoke"),
    ("tool-wizard", "activate"): _direct("bubble_tool_wizard_activate"),
    ("tool-wizard", "add-capture"): _direct("bubble_tool_wizard_add_capture"),
    ("tool-wizard", "describe"): _direct("bubble_tool_wizard_describe"),
    ("tool-wizard", "finalize"): _direct("bubble_tool_wizard_finalize"),
    ("tool-wizard", "generate"): _direct("bubble_tool_wizard_generate"),
    ("tool-wizard", "start"): _direct("bubble_tool_wizard_start"),
    ("tools", "coverage"): _direct("bubble_tool_coverage"),
    ("tools", "guide"): _direct("bubble_agent_guide"),
    ("tools", "quality"): _direct("bubble_catalog_quality"),
    ("tools", "recipe"): _direct("bubble_task_recipe"),
    ("tools", "runbook"): _direct("bubble_task_runbook"),
    ("tools", "search"): _direct("bubble_tool_search"),
    ("transfer", "execute"): _direct("bubble_transfer_execute"),
    ("transfer", "inventory"): _direct("bubble_transfer_inventory"),
    ("transfer", "plan"): _direct("bubble_transfer_plan"),
    ("transfer", "preview"): _direct("bubble_transfer_preview"),
    ("transfer", "status"): _direct("bubble_transfer_status"),
    ("validate-plan",): _administration(
        "Validates a local plan file without invoking a public MCP capability or Bubble project operation."
    ),
    ("write",): _direct("bubble_editor_write"),
}


def _assignment_parts(
    node: ast.Assign | ast.AnnAssign,
) -> tuple[str | None, ast.expr | None]:
    if isinstance(node, ast.AnnAssign):
        target = node.target.id if isinstance(node.target, ast.Name) else None
        return target, node.value
    if len(node.targets) != 1 or not isinstance(node.targets[0], ast.Name):
        return None, node.value
    return node.targets[0].id, node.value


def _named_target(node: ast.Assign | ast.AnnAssign) -> str | None:
    target, _ = _assignment_parts(node)
    if target is None:
        return None
    return target


def _method_call(call: ast.Call, method: str) -> ast.Name | None:
    function = call.func
    if not isinstance(function, ast.Attribute) or function.attr != method:
        return None
    return function.value if isinstance(function.value, ast.Name) else None


def _build_parser_function(tree: ast.Module) -> ast.FunctionDef | ast.AsyncFunctionDef:
    functions = [
        node
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == "build_parser"
    ]
    if len(functions) != 1:
        raise ValueError("CLI source must define exactly one build_parser function")
    return functions[0]


def _build_parser_statements(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
) -> list[ast.Assign | ast.AnnAssign | ast.Expr]:
    statements = [
        node
        for node in ast.walk(function)
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.Expr))
    ]
    return sorted(statements, key=lambda node: (node.lineno, node.col_offset))


def discover_cli_leaves(source: str) -> tuple[DiscoveredCliLeaf, ...]:
    """Return terminal command paths derived from a ``build_parser`` source."""

    tree = ast.parse(source)
    function = _build_parser_function(tree)
    module_helpers = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name != "build_parser"
    }
    for node in ast.walk(function):
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in module_helpers
        ):
            raise ValueError(f"Unsupported CLI parser helper: {node.func.id} at line {node.lineno}")

    relevant_methods = {"add_parser", "add_subparsers", "set_defaults"}
    relevant_calls = [
        node
        for node in ast.walk(function)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in relevant_methods
    ]
    consumed_calls: set[int] = set()
    parser_paths: dict[str, tuple[str, ...]] = {}
    container_paths: dict[str, tuple[tuple[str, ...], bool]] = {}
    declared_paths: dict[tuple[str, ...], int] = {}
    parents: set[tuple[str, ...]] = set()
    required_parents: set[tuple[str, ...]] = set()
    handlers: dict[tuple[str, ...], tuple[str, int]] = {}

    for statement in _build_parser_statements(function):
        call: ast.Call | None = None
        if isinstance(statement, (ast.Assign, ast.AnnAssign)):
            target, value = _assignment_parts(statement)
            if isinstance(value, ast.Name) and target is not None:
                if value.id in parser_paths:
                    parser_paths[target] = parser_paths[value.id]
                elif value.id in container_paths:
                    container_paths[target] = container_paths[value.id]
                continue
            if not isinstance(value, ast.Call):
                continue
            call = value
            target = _named_target(statement)
            if target is None:
                continue
            call_function = call.func
            if (
                isinstance(call_function, ast.Attribute)
                and call_function.attr == "ArgumentParser"
            ):
                parser_paths[target] = ()
                continue
            parent_parser = _method_call(call, "add_subparsers")
            if parent_parser is not None and parent_parser.id in parser_paths:
                consumed_calls.add(id(call))
                parent_path = parser_paths[parent_parser.id]
                required_keywords = [
                    keyword for keyword in call.keywords if keyword.arg == "required"
                ]
                required_node = required_keywords[-1].value if required_keywords else None
                if required_node is None:
                    required = False
                elif isinstance(required_node, ast.Constant) and isinstance(
                    required_node.value, bool
                ):
                    required = required_node.value
                else:
                    raise ValueError(
                        f"CLI add_subparsers required must be a literal boolean at line {statement.lineno}"
                    )
                container_paths[target] = (parent_path, required)
                parents.add(parent_path)
                if required:
                    required_parents.add(parent_path)
                continue
            container = _method_call(call, "add_parser")
            if container is not None and container.id in container_paths:
                consumed_calls.add(id(call))
                if any(keyword.arg == "aliases" for keyword in call.keywords):
                    raise ValueError(
                        f"CLI add_parser aliases are unsupported at line {statement.lineno}"
                    )
                if not call.args or not isinstance(call.args[0], ast.Constant) or not isinstance(call.args[0].value, str):
                    raise ValueError(f"CLI add_parser name must be a literal string at line {statement.lineno}")
                parent_path, _ = container_paths[container.id]
                command_path = (*parent_path, call.args[0].value)
                if command_path in declared_paths:
                    raise ValueError(f"Duplicate CLI command path: {' '.join(command_path)}")
                declared_paths[command_path] = statement.lineno
                parser_paths[target] = command_path
                continue

        if isinstance(statement, ast.Expr) and isinstance(statement.value, ast.Call):
            call = statement.value
        if call is None:
            continue
        parser = _method_call(call, "set_defaults")
        if parser is None or parser.id not in parser_paths:
            continue
        consumed_calls.add(id(call))
        func_keywords = [keyword for keyword in call.keywords if keyword.arg == "func"]
        if not func_keywords:
            continue
        handler_node = func_keywords[-1].value
        if not isinstance(handler_node, ast.Name):
            raise ValueError(f"CLI func handler must be a named function at line {statement.lineno}")
        handlers[parser_paths[parser.id]] = (handler_node.id, statement.lineno)

    unconsumed = sorted(
        (call for call in relevant_calls if id(call) not in consumed_calls),
        key=lambda call: (call.lineno, call.col_offset),
    )
    if unconsumed:
        call = unconsumed[0]
        method = call.func.attr if isinstance(call.func, ast.Attribute) else "parser"
        if isinstance(call.func, ast.Attribute) and isinstance(call.func.value, ast.Call):
            raise ValueError(f"Unsupported nested CLI parser call at line {call.lineno}")
        raise ValueError(f"Unresolved CLI parser call {method} at line {call.lineno}")

    leaves: list[DiscoveredCliLeaf] = []
    for command_path in sorted(declared_paths):
        if command_path in required_parents:
            continue
        binding = handlers.get(command_path)
        if binding is None:
            for length in range(len(command_path) - 1, 0, -1):
                binding = handlers.get(command_path[:length])
                if binding is not None:
                    break
        if binding is None:
            if command_path in parents:
                continue
            raise ValueError(f"Terminal CLI command has no func handler: {' '.join(command_path)}")
        leaves.append(DiscoveredCliLeaf(command_path, binding[0], binding[1]))
    return tuple(leaves)


def modern_cli_source() -> Path:
    """Return the authoritative source file for the modern CLI parser."""

    return Path(__file__).resolve().parent / "cli" / "main.py"


@lru_cache(maxsize=1)
def modern_cli_leaves() -> tuple[DiscoveredCliLeaf, ...]:
    """Discover terminal commands from the installed package source."""

    return discover_cli_leaves(modern_cli_source().read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def runtime_cli_leaves() -> tuple[DiscoveredCliLeaf, ...]:
    """Inspect the instantiated parser to cross-check reachable command paths."""

    from bubble_mcp.cli import main as cli_main

    leaves: list[DiscoveredCliLeaf] = []

    def visit(
        parser: argparse.ArgumentParser,
        path: tuple[str, ...],
        inherited_handler: object | None = None,
    ) -> None:
        defaults = getattr(parser, "_defaults", {})
        handler = defaults.get("func", inherited_handler) if isinstance(defaults, dict) else inherited_handler
        subparser_actions = [
            action
            for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        ]
        requires_child = any(bool(action.required) for action in subparser_actions)
        if path and handler is not None and not requires_child:
            handler_name = getattr(handler, "__name__", "")
            if not handler_name or getattr(cli_main, handler_name, None) is not handler:
                raise ValueError(
                    f"Modern CLI handler is not a named cli.main function: {' '.join(path)}"
                )
            code = getattr(handler, "__code__", None)
            leaves.append(
                DiscoveredCliLeaf(path, handler_name, int(getattr(code, "co_firstlineno", 0)))
            )

        for action in subparser_actions:
            for command_name, child in action.choices.items():
                visit(child, (*path, command_name), handler)
        if path and not subparser_actions and handler is None:
            raise ValueError(f"Runtime terminal CLI command has no func handler: {' '.join(path)}")

    visit(cli_main.build_parser(), ())
    return tuple(sorted(leaves, key=lambda leaf: leaf.command_path))


def classify_cli_leaves(
    leaves: Iterable[DiscoveredCliLeaf],
    *,
    catalog_names: Iterable[str],
    registry: Mapping[tuple[str, ...], CliLeafSpec] | None = None,
) -> tuple[CliLeafClassification, ...]:
    """Join source-derived leaves to explicit semantic and MCP relationships."""

    resolved_registry = CLI_LEAF_CLASSIFICATIONS if registry is None else registry
    ordered_leaves = tuple(sorted(leaves, key=lambda leaf: leaf.command_path))
    leaf_paths = {leaf.command_path for leaf in ordered_leaves}
    registry_paths = set(resolved_registry)
    missing = sorted(leaf_paths - registry_paths)
    if missing:
        raise ValueError(f"Unclassified modern CLI command: {' '.join(missing[0])}")
    stale = sorted(registry_paths - leaf_paths)
    if stale:
        raise ValueError(f"Stale modern CLI classification: {' '.join(stale[0])}")

    known_capabilities = {str(name) for name in catalog_names}
    records: list[CliLeafClassification] = []
    for leaf in ordered_leaves:
        spec = resolved_registry[leaf.command_path]
        path_text = " ".join(leaf.command_path)
        expected_handler = spec.expected_handler or f"command_{'_'.join(leaf.command_path).replace('-', '_')}"
        if leaf.handler != expected_handler:
            raise ValueError(
                f"Modern CLI handler mismatch for {path_text}: "
                f"expected {expected_handler}, got {leaf.handler}"
            )
        if spec.catalog_class not in CLI_CATALOG_CLASSES:
            raise ValueError(f"Invalid modern CLI catalog class {spec.catalog_class}: {path_text}")
        if not spec.reason.strip():
            raise ValueError(f"Modern CLI classification requires a reason: {path_text}")
        if spec.catalog_class == "direct_mcp" and len(spec.mcp_capabilities) != 1:
            raise ValueError(f"direct_mcp requires exactly one capability: {path_text}")
        if spec.catalog_class == "composed_mcp" and not spec.mcp_capabilities:
            raise ValueError(f"composed_mcp requires at least one capability: {path_text}")
        if spec.catalog_class not in {"direct_mcp", "composed_mcp"} and spec.mcp_capabilities:
            raise ValueError(f"{spec.catalog_class} cannot declare MCP capabilities: {path_text}")
        for capability in spec.mcp_capabilities:
            if capability not in known_capabilities:
                raise ValueError(f"Unknown MCP capability {capability} for modern CLI command: {path_text}")
        records.append(
            CliLeafClassification(
                leaf.command_path,
                leaf.handler,
                leaf.line,
                spec.catalog_class,
                spec.mcp_capabilities,
                spec.reason,
            )
        )
    return tuple(records)


@lru_cache(maxsize=1)
def modern_cli_leaf_classifications() -> tuple[CliLeafClassification, ...]:
    """Return the complete modern CLI map against the public MCP catalog."""

    from bubble_mcp.server.schemas import list_tool_schemas

    return classify_cli_leaves(
        modern_cli_leaves(),
        catalog_names=(str(tool.get("name") or "") for tool in list_tool_schemas()),
    )


def cli_leaf_map_report(
    *,
    source: str | None = None,
    registry: Mapping[tuple[str, ...], CliLeafSpec] | None = None,
    catalog_names: Iterable[str] | None = None,
) -> dict[str, object]:
    """Return the deterministic modern-CLI classification audit."""

    leaves: tuple[DiscoveredCliLeaf, ...] = ()
    records: tuple[CliLeafClassification, ...] = ()
    issues: list[dict[str, str]] = []
    try:
        leaves = modern_cli_leaves() if source is None else discover_cli_leaves(source)
        if source is None:
            runtime_leaves = runtime_cli_leaves()
            ast_bindings = {(leaf.command_path, leaf.handler) for leaf in leaves}
            runtime_bindings = {(leaf.command_path, leaf.handler) for leaf in runtime_leaves}
            runtime_only = sorted(runtime_bindings - ast_bindings)
            ast_only = sorted(ast_bindings - runtime_bindings)
            if runtime_only or ast_only:
                direction, binding = (
                    ("runtime-only", runtime_only[0])
                    if runtime_only
                    else ("AST-only", ast_only[0])
                )
                raise ValueError(
                    f"Modern CLI AST/runtime inventory mismatch: {direction} "
                    f"{' '.join(binding[0])}"
                )
        if catalog_names is None:
            from bubble_mcp.server.schemas import list_tool_schemas

            catalog_names = (str(tool.get("name") or "") for tool in list_tool_schemas())
        records = classify_cli_leaves(
            leaves,
            catalog_names=catalog_names,
            registry=registry,
        )
        for record in records:
            if record.catalog_class == "catalog_gap":
                path_text = " ".join(record.command_path)
                issues.append(
                    {
                        "scope": "modern_cli",
                        "name": path_text,
                        "message": f"Modern CLI project operation has no MCP capability: {path_text}",
                    }
                )
    except (SyntaxError, ValueError) as exc:
        issues.append(
            {
                "scope": "modern_cli",
                "name": "cli_leaf_map",
                "message": str(exc),
            }
        )

    class_counts = {
        catalog_class: sum(record.catalog_class == catalog_class for record in records)
        for catalog_class in sorted(CLI_CATALOG_CLASSES)
    }
    return {
        "ok": not issues,
        "summary": {
            "leaf_count": len(leaves),
            "classified_count": len(records),
            "direct_mcp_count": class_counts["direct_mcp"],
            "composed_mcp_count": class_counts["composed_mcp"],
            "administration_only_count": class_counts["administration_only"],
            "local_housekeeping_count": class_counts["local_housekeeping"],
            "catalog_gap_count": class_counts["catalog_gap"],
            "issue_count": len(issues),
        },
        "records": [record.to_dict() for record in records],
        "issues": issues,
    }
