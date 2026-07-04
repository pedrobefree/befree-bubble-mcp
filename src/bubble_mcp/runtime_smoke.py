"""Operational smoke harness for MCP runtime coverage."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
import re
from typing import Any, cast
from uuid import uuid4

from bubble_mcp.core.redaction import redact_sensitive
from bubble_mcp.runtime_smoke_validation import validate_execute_write_context


ToolCaller = Callable[[str, dict[str, Any]], dict[str, Any]]
RUNTIME_SMOKE_SUITES = {
    "coverage",
    "safe-read",
    "preview-write",
    "execute-write",
    "family-preview",
    "agent-routing",
    "visual-repair",
}


VISUAL_REPAIR_REFERENCE: dict[str, Any] = {
    "root": {
        "id": "hero",
        "bbox": {"x": 0, "y": 0, "width": 1298, "height": 760},
        "style": {
            "background": "linear-gradient(110deg, #5533ff, #25b6f0)",
            "maxWidth": 1298,
        },
    },
    "nodes": [
        {
            "id": "headline",
            "type": "text",
            "text": "The best landing page for your digital product.",
            "bbox": {"x": 80, "y": 300, "width": 500, "height": 190},
            "style": {"fontFamily": "Josefin Sans", "fontSize": 60, "fontWeight": 700},
        },
        {
            "id": "watch",
            "type": "image",
            "src": "watch.png",
            "bbox": {"x": 760, "y": 270, "width": 458, "height": 458},
        },
    ],
}


VISUAL_REPAIR_ACTUAL: dict[str, Any] = {
    "root": {
        "id": "hero",
        "bbox": {"x": 0, "y": 0, "width": 1298, "height": 760},
        "style": {
            "background": "linear-gradient(110deg, #25b6f0, #5533ff)",
            "maxWidth": 2400,
        },
    },
    "nodes": [
        {
            "id": "headline",
            "type": "text",
            "text": "The best landing page for your digital product.",
            "bbox": {"x": 430, "y": 300, "width": 500, "height": 190},
            "style": {"fontFamily": "Arial", "fontSize": 44, "fontWeight": 700},
        },
        {
            "id": "watch",
            "type": "image",
            "src": "watch.png",
            "bbox": {"x": 760, "y": 270, "width": 760, "height": 760},
        },
    ],
}


@dataclass(frozen=True)
class SmokeCase:
    tool: str
    arguments: dict[str, Any]
    suite: str
    description: str
    requires_profile: bool = False


@dataclass(frozen=True)
class AgentRoutingCase:
    task: str
    expected_recipe: str
    expected_intents: tuple[str, ...]
    expected_recipe_tools: tuple[str, ...]
    search_query: str
    expected_search_tool: str
    description: str
    forbidden_intents: tuple[str, ...] = ()


AGENT_ROUTING_CASES: tuple[AgentRoutingCase, ...] = (
    AgentRoutingCase(
        task=(
            "Utilizando o befree_bubble_mcp, converta o componente com seletor #home-area "
            "da URL https://quomodosoft.com/html/jupiter/jupiter/index2.html e adicione-o "
            "na página mcp-01 do projeto smoke"
        ),
        expected_recipe="html_import",
        expected_intents=("import_html_component",),
        expected_recipe_tools=("create_from_html", "bubble_context_detect"),
        search_query="converter seletor html url",
        expected_search_tool="create_from_html",
        description="Route Portuguese HTML selector import requests to the advanced HTML importer.",
        forbidden_intents=("check_server_or_catalog",),
    ),
    AgentRoutingCase(
        task="compare o print do HTML original com o Bubble criado e corrija problemas visuais de fonte, gradiente e imagem",
        expected_recipe="visual_quality_gate",
        expected_intents=("visual_quality_gate",),
        expected_recipe_tools=("bubble_visual_capture", "bubble_visual_capture_actual", "bubble_visual_audit"),
        search_query="comparar print visual corrigir drift",
        expected_search_tool="bubble_visual_audit",
        description="Route visual parity and repair requests to the visual audit harness.",
        forbidden_intents=("check_server_or_catalog",),
    ),
    AgentRoutingCase(
        task="crie uma nova página chamada mcp-02 no app profile smoke via MCP befree_bubble_mcp",
        expected_recipe="page_or_reusable",
        expected_intents=("manage_pages_or_reusables",),
        expected_recipe_tools=("create_page", "bubble_context_detect"),
        search_query="criar página",
        expected_search_tool="create_page",
        description="Route Portuguese page creation requests without asking for internal tool names.",
        forbidden_intents=("check_server_or_catalog",),
    ),
    AgentRoutingCase(
        task="sincronize o estilo hovered de um botão vindo do Figma para o Bubble",
        expected_recipe="style_or_tokens",
        expected_intents=("manage_styles_tokens_design_system",),
        expected_recipe_tools=("sync_figma_style", "create_style"),
        search_query="estilo botão hover figma",
        expected_search_tool="sync_figma_style",
        description="Route Figma/style state sync requests to style/token tooling.",
    ),
    AgentRoutingCase(
        task="liste as branches e busque o changelog da versão test",
        expected_recipe="branch_or_changelog",
        expected_intents=("branches_or_changelog",),
        expected_recipe_tools=("bubble_branch_list", "bubble_changelog_fetch"),
        search_query="branches changelog",
        expected_search_tool="bubble_changelog_fetch",
        description="Route branch and changelog requests to editor version-control tools.",
        forbidden_intents=("check_server_or_catalog",),
    ),
    AgentRoutingCase(
        task="faça login da sessão e detecte o contexto atualizado do projeto",
        expected_recipe="setup_or_refresh_context",
        expected_intents=("find_profile_session_or_context",),
        expected_recipe_tools=("bubble_project_bootstrap", "bubble_profile_status", "bubble_context_detect"),
        search_query="sessão contexto perfil",
        expected_search_tool="bubble_project_bootstrap",
        description="Route setup/session/context requests to profile/session/context tools.",
    ),
    AgentRoutingCase(
        task="quero fazer login em outra conta Bubble para criar um novo profile e capturar a sessão",
        expected_recipe="setup_or_refresh_context",
        expected_intents=("find_profile_session_or_context",),
        expected_recipe_tools=("bubble_project_bootstrap", "bubble_session_login", "bubble_profile_status"),
        search_query="login conta bubble capturar sessão navegador",
        expected_search_tool="bubble_session_login",
        description="Route interactive Bubble login requests to the MCP session login tool.",
    ),
    AgentRoutingCase(
        task="crie um workflow de page load que mostre uma mensagem",
        expected_recipe="workflow",
        expected_intents=("manage_workflows",),
        expected_recipe_tools=("create_workflow", "add_action"),
        search_query="workflow page load ação",
        expected_search_tool="create_workflow",
        description="Route workflow requests to event/action tools.",
    ),
)


def _preview_name(prefix: str) -> str:
    return f"{prefix}_mcp_runtime_preview"


def _default_run_id() -> str:
    return f"{datetime.now(UTC).strftime('%Y%m%d%H%M%S')}_{uuid4().hex[:6]}"


def _safe_run_id(run_id: str = "") -> str:
    value = run_id.strip() or _default_run_id()
    value = re.sub(r"[^A-Za-z0-9_]+", "_", value)
    value = re.sub(r"_+", "_", value).strip("_")
    return value[:40] or _default_run_id()


def _with_app_id(args: dict[str, Any], app_id: str) -> dict[str, Any]:
    if app_id:
        return {**args, "app_id": app_id}
    return args


def _family_preview_cases(
    *,
    profile: str,
    context: str,
    parent: str,
    app_id: str,
    app_version: str,
    run_id: str,
) -> list[SmokeCase]:
    base = {
        "profile": profile,
        "context": context,
        "parent": parent,
        "app_version": app_version,
        "execute": False,
    }
    cases: list[SmokeCase] = []
    visual_cases: list[tuple[str, dict[str, Any], str]] = [
        ("create_text", {"name": f"tx_family_{run_id}", "content": "Family preview text"}, "visual:text"),
        ("create_button", {"name": f"bt_family_{run_id}", "label": "Family preview"}, "visual:button"),
        ("create_icon", {"name": f"ic_family_{run_id}", "icon_name": "feather check-circle"}, "visual:icon"),
        ("create_image", {"name": f"im_family_{run_id}", "source": "https://example.com/image.png"}, "visual:image"),
        ("create_html", {"name": f"html_family_{run_id}", "content": "<div>Family preview</div>"}, "visual:html"),
        ("create_group", {"name": f"gp_family_{run_id}", "layout": "column"}, "container:group"),
        ("create_repeating_group", {"name": f"rg_family_{run_id}", "data_type": "text"}, "container:repeating_group"),
        ("create_input", {"name": f"in_family_{run_id}", "placeholder": "Family preview"}, "input:input"),
        ("create_dropdown", {"name": f"dd_family_{run_id}", "placeholder": "Choose"}, "input:dropdown"),
        ("create_checkbox", {"name": f"cb_family_{run_id}", "label": "Family checkbox"}, "input:checkbox"),
    ]
    for tool, args, family in visual_cases:
        cases.append(
            SmokeCase(
                tool,
                _with_app_id({**base, **args}, app_id),
                "family-preview",
                f"Preview {family} creation through the MCP runtime path.",
                True,
            )
        )

    schema_base = {"profile": profile, "app_version": app_version, "execute": False, "dry_run": True}
    schema_cases: list[tuple[str, dict[str, Any], str]] = [
        ("create_data_type", {"name": f"MCP Family {run_id}", "fields": [{"name": "name", "type": "text"}]}, "schema:data_type"),
        (
            "create_data_field",
            {"data_type_key": "user", "field_name": f"family_field_{run_id}", "field_type": "text"},
            "schema:data_field",
        ),
        ("create_option_set", {"name": f"MCP Family Options {run_id}", "values": ["One", "Two"]}, "schema:option_set"),
        ("create_option_value", {"option_set_key": "os_status", "label": f"Family {run_id}"}, "schema:option_value"),
    ]
    for tool, args, family in schema_cases:
        cases.append(
            SmokeCase(
                tool,
                _with_app_id({**schema_base, **args}, app_id),
                "family-preview",
                f"Preview {family} mutation path.",
                True,
            )
        )

    style_cases: list[tuple[str, dict[str, Any], str]] = [
        ("create_color", {"name": f"family_color_{run_id}", "rgba": "rgba(18, 52, 86, 1)"}, "style:color"),
        ("create_style", {"name": f"family_style_{run_id}", "element_type": "Text"}, "style:definition"),
    ]
    for tool, args, family in style_cases:
        cases.append(
            SmokeCase(
                tool,
                _with_app_id({**schema_base, **args}, app_id),
                "family-preview",
                f"Preview {family} mutation path.",
                True,
            )
        )

    workflow_cases: list[tuple[str, dict[str, Any], str]] = [
        ("create_workflow", {"context": context, "element_name": "Page", "event_type": "PageLoaded"}, "workflow:event"),
        (
            "add_action",
            {"context": context, "element_name": "Page", "event": "PageLoaded", "action_type": "show_message", "message": "Family preview"},
            "workflow:action",
        ),
    ]
    for tool, args, family in workflow_cases:
        cases.append(
            SmokeCase(
                tool,
                _with_app_id({**schema_base, **args}, app_id),
                "family-preview",
                f"Preview {family} mutation path.",
                True,
            )
        )

    cases.extend(
        [
            SmokeCase(
                "create_from_html",
                _with_app_id(
                    {
                        **base,
                        "html": "<section id='family-preview'><h1>Family preview</h1></section>",
                        "selector": "#family-preview",
                        "rendered_html": False,
                        "refresh_context": False,
                    },
                    app_id,
                ),
                "family-preview",
                "Preview advanced HTML import path.",
                True,
            ),
            SmokeCase(
                "bubble_branch_list",
                {"profile": profile, **({"app_id": app_id} if app_id else {})},
                "family-preview",
                "Read Bubble branch list through the editor API.",
                True,
            ),
            SmokeCase(
                "bubble_changelog_fetch",
                {
                    "profile": profile,
                    "app_version": app_version,
                    "num_fetch": 5,
                    **({"app_id": app_id} if app_id else {}),
                },
                "family-preview",
                "Read Bubble changelog entries through the editor API.",
                True,
            ),
        ]
    )
    return cases


def build_runtime_smoke_cases(
    *,
    profile: str = "",
    context: str = "index",
    parent: str = "root",
    app_id: str = "",
    app_version: str = "test",
    suite: str = "coverage",
    html_url: str = "",
    selector: str = "",
    execute: bool = False,
    cleanup: bool = False,
    run_id: str = "",
) -> list[SmokeCase]:
    """Build deterministic smoke cases for the requested suite."""

    effective_run_id = _safe_run_id(run_id)
    cases: list[SmokeCase] = [
        SmokeCase("bubble_tool_coverage", {}, "coverage", "Verify catalog execution coverage is complete."),
        SmokeCase("bubble_catalog_quality", {}, "coverage", "Verify agent-facing catalog quality is complete."),
    ]

    if suite in {"coverage"}:
        return cases

    if suite in {"agent-routing"}:
        return []

    safe_read_cases = [
        SmokeCase("bubble_health_check", {}, "safe-read", "Read server capability metadata."),
        SmokeCase("bubble_profile_list", {}, "safe-read", "Read configured profiles."),
        SmokeCase("bubble_session_list", {}, "safe-read", "Read stored session metadata."),
    ]
    cases.extend(safe_read_cases)

    if profile:
        profile_args = {"profile": profile}
        if app_id:
            profile_args["app_id"] = app_id
        profile_args_with_json = {**profile_args, "json": True}
        cases.extend(
            [
                SmokeCase("bubble_profile_status", dict(profile_args), "safe-read", "Read profile session/context readiness."),
                SmokeCase("list_data_types", dict(profile_args_with_json), "safe-read", "List Bubble data types.", True),
                SmokeCase("list_styles", dict(profile_args), "safe-read", "List Bubble styles.", True),
                SmokeCase("list_colors", dict(profile_args_with_json), "safe-read", "List Bubble colors.", True),
                SmokeCase("list_fonts", dict(profile_args_with_json), "safe-read", "List Bubble fonts.", True),
                SmokeCase("list_project_settings", dict(profile_args_with_json), "safe-read", "List Bubble project settings.", True),
            ]
        )

    if suite in {"safe-read"}:
        return cases

    if suite == "family-preview":
        if profile:
            cases.extend(
                _family_preview_cases(
                    profile=profile,
                    context=context,
                    parent=parent,
                    app_id=app_id,
                    app_version=app_version,
                    run_id=effective_run_id,
                )
            )
        return cases

    if profile:
        is_execute_write = suite == "execute-write"
        mutation_suite = "execute-write" if is_execute_write else "preview-write"
        mutation_execute = bool(execute and is_execute_write)
        page_name = f"mcp_smoke_{effective_run_id}" if is_execute_write else _preview_name("page")
        target_context = page_name if is_execute_write else context
        target_parent = "root" if is_execute_write else parent
        base = {
            "profile": profile,
            "context": target_context,
            "parent": target_parent,
            "app_version": app_version,
            "execute": mutation_execute,
        }
        if app_id:
            base["app_id"] = app_id
        cases.extend(
            [
                SmokeCase(
                    "create_page",
                    {
                        "profile": profile,
                        "name": page_name,
                        "app_version": app_version,
                        "execute": mutation_execute,
                        **({"app_id": app_id} if app_id else {}),
                    },
                    mutation_suite,
                    "Execute page creation through the Aria runtime."
                    if is_execute_write
                    else "Preview page creation through the Aria runtime.",
                    True,
                ),
                SmokeCase(
                    "create_group",
                    {
                        **base,
                        "name": f"gp_mcp_smoke_{effective_run_id}" if is_execute_write else _preview_name("gp"),
                        "layout": "column",
                        "min_height": "40px",
                        "fit_height": True,
                    },
                    mutation_suite,
                    "Execute group creation through the Aria runtime."
                    if is_execute_write
                    else "Preview group creation through the Aria runtime.",
                    True,
                ),
                SmokeCase(
                    "create_text",
                    {
                        **base,
                        "name": f"tx_mcp_smoke_{effective_run_id}" if is_execute_write else _preview_name("tx"),
                        "content": f"Runtime smoke {effective_run_id}" if is_execute_write else "Runtime smoke preview",
                        "fit_height": True,
                    },
                    mutation_suite,
                    "Execute text creation with default fit-height behavior."
                    if is_execute_write
                    else "Preview text creation with default fit-height behavior.",
                    True,
                ),
                SmokeCase(
                    "create_button",
                    {
                        **base,
                        "name": f"bt_mcp_smoke_{effective_run_id}" if is_execute_write else _preview_name("bt"),
                        "label": "Runtime smoke",
                        "fit_width": True,
                        "fit_height": True,
                    },
                    mutation_suite,
                    "Execute button creation with responsive sizing defaults."
                    if is_execute_write
                    else "Preview button creation with responsive sizing defaults.",
                    True,
                ),
                SmokeCase(
                    "create_input",
                    {
                        **base,
                        "name": f"in_mcp_smoke_{effective_run_id}" if is_execute_write else _preview_name("in"),
                        "placeholder": "Runtime smoke",
                        "fixed_height": True,
                    },
                    mutation_suite,
                    "Execute input creation." if is_execute_write else "Preview input creation.",
                    True,
                ),
            ]
        )
        if html_url:
            cases.append(
                SmokeCase(
                    "create_from_html",
                    {
                        **base,
                        "url": html_url,
                        "selector": selector,
                        "rendered_html": True,
                        "refresh_context": False,
                    },
                    mutation_suite,
                    "Execute advanced HTML import through the packaged runtime."
                    if is_execute_write
                    else "Preview advanced HTML import through the packaged runtime.",
                    True,
                )
            )
        if is_execute_write and cleanup:
            cases.append(
                SmokeCase(
                    "delete_page",
                    {
                        "profile": profile,
                        "name": page_name,
                        "app_version": app_version,
                        "execute": True,
                        "confirm": True,
                        **({"app_id": app_id} if app_id else {}),
                    },
                    "execute-write",
                    "Clean up the temporary runtime smoke page.",
                    True,
                )
            )

    return cases


def _compact_result(result: dict[str, Any], *, include_details: bool) -> dict[str, Any]:
    if include_details:
        return cast("dict[str, Any]", redact_sensitive(result))
    compact: dict[str, Any] = {
        "ok": bool(result.get("ok")),
        "engine": result.get("engine"),
        "executed": result.get("executed"),
        "compiled": result.get("compiled"),
        "write_count": result.get("write_count"),
        "ready": result.get("ready"),
        "error": result.get("error"),
        "reason": result.get("reason"),
    }
    if isinstance(result.get("next_actions"), list):
        compact["next_action_count"] = len(result["next_actions"])
    return {key: value for key, value in compact.items() if value is not None}


def run_runtime_smoke(
    tool_caller: ToolCaller,
    *,
    profile: str = "",
    context: str = "index",
    parent: str = "root",
    app_id: str = "",
    app_version: str = "test",
    suite: str = "coverage",
    limit: int = 0,
    html_url: str = "",
    selector: str = "",
    include_details: bool = False,
    stop_on_failure: bool = False,
    execute: bool = False,
    cleanup: bool = False,
    run_id: str = "",
    verify_context: bool = False,
    verification_output: str = "",
) -> dict[str, Any]:
    """Run an operational smoke suite by calling MCP tool handlers."""

    if suite not in RUNTIME_SMOKE_SUITES:
        raise ValueError(
            "suite must be one of: coverage, safe-read, preview-write, execute-write, family-preview, agent-routing, visual-repair."
        )
    effective_run_id = _safe_run_id(run_id)
    if suite == "agent-routing":
        routing_results = _run_agent_routing_suite(
            tool_caller,
            profile=profile,
            context=context,
            parent=parent,
            execute=execute,
            limit=limit,
            include_details=include_details,
            stop_on_failure=stop_on_failure,
        )
        summary = {
            "cases": len(routing_results),
            "passed": sum(1 for item in routing_results if item["status"] == "passed"),
            "failed": sum(1 for item in routing_results if item["status"] == "failed"),
            "skipped": sum(1 for item in routing_results if item["status"] == "skipped"),
        }
        return {
            "ok": summary["failed"] == 0,
            "suite": suite,
            "profile": profile or None,
            "context": context,
            "parent": parent,
            "app_id": app_id or None,
            "app_version": app_version,
            "execute": bool(execute),
            "cleanup": False,
            "verify_context": False,
            "run_id": effective_run_id,
            "summary": summary,
            "results": routing_results,
        }
    if suite == "visual-repair":
        visual_results = _run_visual_repair_suite(
            tool_caller,
            profile=profile,
            context=context,
            parent=parent,
            app_id=app_id,
            app_version=app_version,
            include_details=include_details,
        )
        summary = {
            "cases": len(visual_results),
            "passed": sum(1 for item in visual_results if item["status"] == "passed"),
            "failed": sum(1 for item in visual_results if item["status"] == "failed"),
            "skipped": sum(1 for item in visual_results if item["status"] == "skipped"),
        }
        return {
            "ok": summary["failed"] == 0,
            "suite": suite,
            "profile": profile or None,
            "context": context,
            "parent": parent,
            "app_id": app_id or None,
            "app_version": app_version,
            "execute": False,
            "cleanup": False,
            "verify_context": False,
            "run_id": effective_run_id,
            "summary": summary,
            "results": visual_results,
        }
    if suite == "execute-write" and not execute:
        return {
            "ok": False,
            "suite": suite,
            "profile": profile or None,
            "context": context,
            "parent": parent,
            "app_id": app_id or None,
            "app_version": app_version,
            "execute": False,
            "cleanup": cleanup,
            "verify_context": verify_context,
            "run_id": effective_run_id,
            "error": "execute-write requires execute=true.",
            "summary": {"cases": 0, "passed": 0, "failed": 1, "skipped": 0},
            "results": [],
        }
    cases = build_runtime_smoke_cases(
        profile=profile,
        context=context,
        parent=parent,
        app_id=app_id,
        app_version=app_version,
        suite=suite,
        html_url=html_url,
        selector=selector,
        execute=execute,
        cleanup=cleanup,
        run_id=effective_run_id,
    )
    if limit > 0:
        cases = cases[:limit]
    cleanup_cases: list[SmokeCase] = []
    if suite == "execute-write" and cleanup:
        cleanup_cases = [case for case in cases if case.tool == "delete_page" and case.suite == "execute-write"]
        cases = [case for case in cases if case not in cleanup_cases]

    results: list[dict[str, Any]] = []
    for index, case in enumerate(cases, start=1):
        if case.requires_profile and not profile:
            results.append(
                {
                    "index": index,
                    "tool": case.tool,
                    "suite": case.suite,
                    "status": "skipped",
                    "ok": True,
                    "reason": "profile_required",
                    "description": case.description,
                }
            )
            continue
        try:
            result = tool_caller(case.tool, dict(case.arguments))
            case_ok = bool(result.get("ok"))
            if case.tool == "bubble_profile_status" and not result.get("ready"):
                case_ok = False
            results.append(
                {
                    "index": index,
                    "tool": case.tool,
                    "suite": case.suite,
                    "status": "passed" if case_ok else "failed",
                    "ok": case_ok,
                    "description": case.description,
                    "result": _compact_result(result, include_details=include_details),
                }
            )
        except Exception as exc:  # noqa: BLE001 - smoke reports must capture failures.
            results.append(
                {
                    "index": index,
                    "tool": case.tool,
                    "suite": case.suite,
                    "status": "failed",
                    "ok": False,
                    "description": case.description,
                    "error": str(exc),
                }
            )
        if stop_on_failure and results[-1]["status"] == "failed":
            break

    if verify_context:
        verification = _run_execute_write_verification(
            tool_caller,
            suite=suite,
            profile=profile,
            app_id=app_id,
            app_version=app_version,
            cleanup=cleanup,
            run_id=effective_run_id,
            prior_failed=any(item["status"] == "failed" for item in results),
            verification_output=verification_output,
        )
        results.append(verification)
    for cleanup_case in cleanup_cases:
        try:
            result = tool_caller(cleanup_case.tool, dict(cleanup_case.arguments))
            case_ok = bool(result.get("ok"))
            results.append(
                {
                    "index": len(results) + 1,
                    "tool": cleanup_case.tool,
                    "suite": cleanup_case.suite,
                    "status": "passed" if case_ok else "failed",
                    "ok": case_ok,
                    "description": cleanup_case.description,
                    "result": _compact_result(result, include_details=include_details),
                }
            )
        except Exception as exc:  # noqa: BLE001 - smoke cleanup must report failures.
            results.append(
                {
                    "index": len(results) + 1,
                    "tool": cleanup_case.tool,
                    "suite": cleanup_case.suite,
                    "status": "failed",
                    "ok": False,
                    "description": cleanup_case.description,
                    "error": str(exc),
                }
            )
    if suite == "execute-write" and cleanup and profile:
        cleanup_refresh = _run_post_cleanup_refresh(
            tool_caller,
            profile=profile,
            app_id=app_id,
            app_version=app_version,
        )
        results.append(cleanup_refresh)

    summary = {
        "cases": len(results),
        "passed": sum(1 for item in results if item["status"] == "passed"),
        "failed": sum(1 for item in results if item["status"] == "failed"),
        "skipped": sum(1 for item in results if item["status"] == "skipped"),
    }
    return {
        "ok": summary["failed"] == 0,
        "suite": suite,
        "profile": profile or None,
        "context": context,
        "parent": parent,
        "app_id": app_id or None,
        "app_version": app_version,
        "execute": bool(execute and suite == "execute-write"),
        "cleanup": bool(cleanup and suite == "execute-write"),
        "verify_context": verify_context,
        "run_id": effective_run_id,
        "summary": summary,
        "results": results,
    }


def _run_visual_repair_suite(
    tool_caller: ToolCaller,
    *,
    profile: str,
    context: str,
    parent: str,
    app_id: str,
    app_version: str,
    include_details: bool,
) -> list[dict[str, Any]]:
    checks: list[dict[str, Any]] = []
    try:
        result = tool_caller(
            "bubble_visual_audit",
            {
                "reference_snapshot": VISUAL_REPAIR_REFERENCE,
                "actual_snapshot": VISUAL_REPAIR_ACTUAL,
                "profile": profile or "$profile",
                "context": context,
                "parent": parent,
                "app_id": app_id or "synthetic-app",
                "app_version": app_version,
                "require_images": True,
                "execute": False,
            },
        )
        issues = result.get("issues", [])
        repair_plan = result.get("repair_plan", {}) if isinstance(result.get("repair_plan"), dict) else {}
        plan = repair_plan.get("plan", {}) if isinstance(repair_plan.get("plan"), dict) else {}
        steps = plan.get("steps", []) if isinstance(plan.get("steps"), list) else []
        repair_tools = {str(step.get("tool_name")) for step in steps if isinstance(step, dict)}
        issue_codes = {str(issue.get("code")) for issue in issues if isinstance(issue, dict)}
        checks.extend(
            [
                {
                    "name": "detects_visual_drift",
                    "ok": result.get("ok") is False and int(result.get("summary", {}).get("issue_count") or 0) >= 4,
                    "actual": result.get("summary", {}),
                },
                {
                    "name": "executable_repair_plan",
                    "ok": bool(repair_plan.get("executable")) and int(repair_plan.get("step_count") or 0) >= 4,
                    "actual": {"executable": repair_plan.get("executable"), "step_count": repair_plan.get("step_count")},
                },
                {
                    "name": "covers_expected_issue_types",
                    "ok": {
                        "gradient_direction_mismatch",
                        "root_max_width_drift",
                        "font_family_mismatch",
                        "image_width_drift",
                    }.issubset(issue_codes),
                    "actual": sorted(issue_codes),
                },
                {
                    "name": "routes_repairs_to_specific_tools",
                    "ok": {"update_group", "update_layout", "update_text_element", "update_image_element"}.issubset(repair_tools),
                    "actual": sorted(repair_tools),
                },
                {
                    "name": "does_not_execute",
                    "ok": "execution" not in result,
                },
            ]
        )
        case_ok = all(check["ok"] for check in checks)
        payload: dict[str, Any] = {
            "index": 1,
            "tool": "bubble_visual_audit",
            "suite": "visual-repair",
            "status": "passed" if case_ok else "failed",
            "ok": case_ok,
            "description": "Validate that visual audit produces an actionable repair plan without writing to Bubble.",
            "checks": checks,
        }
        if include_details:
            payload["result"] = redact_sensitive(result)
        else:
            payload["result"] = {
                "ok": result.get("ok"),
                "issue_count": result.get("summary", {}).get("issue_count"),
                "repair_step_count": repair_plan.get("step_count"),
                "repair_tools": sorted(repair_tools),
            }
        return [payload]
    except Exception as exc:  # noqa: BLE001 - smoke reports must capture failures.
        return [
            {
                "index": 1,
                "tool": "bubble_visual_audit",
                "suite": "visual-repair",
                "status": "failed",
                "ok": False,
                "description": "Validate that visual audit produces an actionable repair plan without writing to Bubble.",
                "checks": checks,
                "error": str(exc),
            }
        ]


def _run_agent_routing_suite(
    tool_caller: ToolCaller,
    *,
    profile: str,
    context: str,
    parent: str,
    execute: bool,
    limit: int,
    include_details: bool,
    stop_on_failure: bool,
) -> list[dict[str, Any]]:
    cases = list(AGENT_ROUTING_CASES)
    if limit > 0:
        cases = cases[:limit]

    results: list[dict[str, Any]] = []
    for index, case in enumerate(cases, start=1):
        checks: list[dict[str, Any]] = []
        try:
            guide = tool_caller("bubble_agent_guide", {"task": case.task})
            recipe = tool_caller(
                "bubble_task_recipe",
                {
                    "task": case.task,
                    "profile": profile or "$profile",
                    "context": context,
                    "parent": parent,
                    "execute": execute,
                },
            )
            search = tool_caller("bubble_tool_search", {"query": case.search_query, "limit": 8})
            runbook = tool_caller(
                "bubble_task_runbook",
                {
                    "task": case.task,
                    "profile": profile or "$profile",
                    "context": context,
                    "parent": parent,
                    "execute": execute,
                    "search_limit": 8,
                },
            )

            route_intents = {str(route.get("intent")) for route in guide.get("recommended_routes", [])}
            recipe_tools = set(recipe.get("matched", {}).get("tools", []))
            search_tools = [str(match.get("name")) for match in search.get("matches", [])]
            runbook_intents = set(str(intent) for intent in runbook.get("route_intents", []))
            runbook_tools = set(runbook.get("matched", {}).get("tools", []))
            runbook_matches = [
                str(match.get("name"))
                for match in runbook.get("tool_search", {}).get("matches", [])
                if match.get("source") == "recipe"
            ]
            direct_policy = guide.get("direct_tool_policy", {})
            preflight = " ".join(str(item) for item in recipe.get("preflight", []))

            checks.extend(
                [
                    {
                        "name": "direct_tool_policy",
                        "ok": bool(direct_policy.get("use_mcp_tools_directly"))
                        and bool(direct_policy.get("avoid_shell_cli_discovery")),
                    },
                    {
                        "name": "expected_recipe",
                        "ok": recipe.get("recipe") == case.expected_recipe,
                        "expected": case.expected_recipe,
                        "actual": recipe.get("recipe"),
                    },
                    {
                        "name": "runbook_expected_recipe",
                        "ok": runbook.get("recipe") == case.expected_recipe,
                        "expected": case.expected_recipe,
                        "actual": runbook.get("recipe"),
                    },
                    {
                        "name": "expected_intents",
                        "ok": set(case.expected_intents).issubset(route_intents),
                        "expected": list(case.expected_intents),
                        "actual": sorted(route_intents),
                    },
                    {
                        "name": "runbook_expected_intents",
                        "ok": set(case.expected_intents).issubset(runbook_intents),
                        "expected": list(case.expected_intents),
                        "actual": sorted(runbook_intents),
                    },
                    {
                        "name": "forbidden_intents",
                        "ok": not set(case.forbidden_intents).intersection(route_intents),
                        "forbidden": list(case.forbidden_intents),
                        "actual": sorted(route_intents),
                    },
                    {
                        "name": "runbook_forbidden_intents",
                        "ok": not set(case.forbidden_intents).intersection(runbook_intents),
                        "forbidden": list(case.forbidden_intents),
                        "actual": sorted(runbook_intents),
                    },
                    {
                        "name": "expected_recipe_tools",
                        "ok": set(case.expected_recipe_tools).issubset(recipe_tools),
                        "expected": list(case.expected_recipe_tools),
                        "actual": sorted(recipe_tools),
                    },
                    {
                        "name": "runbook_expected_recipe_tools",
                        "ok": set(case.expected_recipe_tools).issubset(runbook_tools),
                        "expected": list(case.expected_recipe_tools),
                        "actual": sorted(runbook_tools),
                    },
                    {
                        "name": "expected_search_tool",
                        "ok": case.expected_search_tool in search_tools,
                        "expected": case.expected_search_tool,
                        "actual": search_tools,
                    },
                    {
                        "name": "runbook_expected_recipe_match",
                        "ok": case.expected_search_tool in runbook_matches,
                        "expected": case.expected_search_tool,
                        "actual": runbook_matches,
                    },
                    {
                        "name": "no_internal_tool_name_requirement",
                        "ok": "Never ask the user to name internal tools" in preflight,
                    },
                ]
            )
            case_ok = all(check["ok"] for check in checks)
            result: dict[str, Any] = {
                "index": index,
                "tool": "bubble_task_runbook+bubble_agent_guide/bubble_task_recipe/bubble_tool_search",
                "suite": "agent-routing",
                "status": "passed" if case_ok else "failed",
                "ok": case_ok,
                "description": case.description,
                "task": case.task,
                "checks": checks,
            }
            if include_details:
                result["result"] = redact_sensitive({"guide": guide, "recipe": recipe, "search": search, "runbook": runbook})
            results.append(result)
        except Exception as exc:  # noqa: BLE001 - smoke reports must capture failures.
            results.append(
                {
                    "index": index,
                    "tool": "bubble_task_runbook+bubble_agent_guide/bubble_task_recipe/bubble_tool_search",
                    "suite": "agent-routing",
                    "status": "failed",
                    "ok": False,
                    "description": case.description,
                    "task": case.task,
                    "checks": checks,
                    "error": str(exc),
                }
            )
        if stop_on_failure and results[-1]["status"] == "failed":
            break
    return results


def _run_execute_write_verification(
    tool_caller: ToolCaller,
    *,
    suite: str,
    profile: str,
    app_id: str,
    app_version: str,
    cleanup: bool,
    run_id: str,
    prior_failed: bool,
    verification_output: str,
) -> dict[str, Any]:
    if suite != "execute-write":
        return {
            "index": 0,
            "tool": "bubble_context_detect",
            "suite": "post-write-verify",
            "status": "skipped",
            "ok": True,
            "reason": "execute_write_required",
            "description": "Post-write context verification applies only to execute-write.",
        }

    if prior_failed:
        return {
            "index": 0,
            "tool": "bubble_context_detect",
            "suite": "post-write-verify",
            "status": "skipped",
            "ok": True,
            "reason": "prior_failure",
            "description": "Post-write context verification skipped because a prior smoke case failed.",
        }
    try:
        args: dict[str, Any] = {
            "profile": profile,
            "app_version": app_version,
            "force": True,
        }
        if app_id:
            args["app_id"] = app_id
        if verification_output:
            args["output"] = verification_output
        detection = tool_caller("bubble_context_detect", args)
        context_path = str(detection.get("context_path") or "").strip()
        if not detection.get("ok") or not context_path:
            return {
                "index": 0,
                "tool": "bubble_context_detect",
                "suite": "post-write-verify",
                "status": "failed",
                "ok": False,
                "description": "Refresh Bubble context and verify temporary smoke objects.",
                "result": _compact_result(detection, include_details=True),
                "error": "context detection did not return a usable context_path.",
            }
        validation = validate_execute_write_context(Path(context_path), run_id=run_id)
        return {
            "index": 0,
            "tool": "bubble_context_detect",
            "suite": "post-write-verify",
            "status": "passed" if validation.get("ok") else "failed",
            "ok": bool(validation.get("ok")),
            "description": "Refresh Bubble context and verify temporary smoke objects.",
            "result": redact_sensitive(
                {
                    "detection": _compact_result(detection, include_details=False),
                    "validation": validation,
                }
            ),
        }
    except Exception as exc:  # noqa: BLE001 - smoke verification must report failures.
        return {
            "index": 0,
            "tool": "bubble_context_detect",
            "suite": "post-write-verify",
            "status": "failed",
            "ok": False,
            "description": "Refresh Bubble context and verify temporary smoke objects.",
            "error": str(exc),
        }


def _run_post_cleanup_refresh(
    tool_caller: ToolCaller,
    *,
    profile: str,
    app_id: str,
    app_version: str,
) -> dict[str, Any]:
    try:
        args: dict[str, Any] = {
            "profile": profile,
            "app_version": app_version,
            "force": True,
        }
        if app_id:
            args["app_id"] = app_id
        detection = tool_caller("bubble_context_detect", args)
        context_path = str(detection.get("context_path") or "").strip()
        return {
            "index": 0,
            "tool": "bubble_context_detect",
            "suite": "post-cleanup-refresh",
            "status": "passed" if detection.get("ok") and context_path else "failed",
            "ok": bool(detection.get("ok") and context_path),
            "description": "Refresh Bubble context after temporary smoke cleanup.",
            "result": _compact_result(detection, include_details=True),
            **({} if context_path else {"error": "context detection did not return a usable context_path."}),
        }
    except Exception as exc:  # noqa: BLE001 - cleanup refresh must report failures.
        return {
            "index": 0,
            "tool": "bubble_context_detect",
            "suite": "post-cleanup-refresh",
            "status": "failed",
            "ok": False,
            "description": "Refresh Bubble context after temporary smoke cleanup.",
            "error": str(exc),
        }
