"""Compact agent guidance for using the Bubble MCP catalog."""

from __future__ import annotations

from typing import Any
import unicodedata


ROUTES: tuple[dict[str, Any], ...] = (
    {
        "intent": "check_server_or_catalog",
        "when": "The user asks whether the MCP is installed, healthy, covered, or ready.",
        "tools": ["bubble_health_check", "bubble_runtime_smoke", "bubble_tool_coverage", "bubble_catalog_quality"],
        "notes": "Use bubble_runtime_smoke suite=coverage first for catalog integrity and schema quality, agent-routing for tool-selection quality, and safe-read or family-preview for runtime confidence.",
    },
    {
        "intent": "find_profile_session_or_context",
        "when": "The user names a project/profile, asks what projects are available, or a target cannot be resolved.",
        "tools": ["bubble_profile_list", "bubble_session_list", "bubble_context_detect", "bubble_context_find"],
        "notes": "Refresh context with bubble_context_detect when pages/elements may have changed in Bubble.",
    },
    {
        "intent": "create_or_update_visual_editor_elements",
        "when": "The user asks to create, update, rename, move, or delete Bubble visual elements.",
        "tools": ["create_group", "create_text", "create_button", "create_input", "update_text", "delete_group"],
        "notes": "Call the specific create_*/update_*/delete_* tool matching the requested element type; pass profile, context, parent, and execute.",
    },
    {
        "intent": "manage_pages_or_reusables",
        "when": "The user asks to create, delete, clone, or inspect Bubble pages or reusable elements.",
        "tools": ["create_page", "delete_page", "create_reusable", "delete_reusable", "bubble_context_detect"],
        "notes": "Refresh context before and after real page/reusable mutations so agents can verify materialization.",
    },
    {
        "intent": "import_html_component",
        "when": "The user asks to convert/import/copy an HTML section, URL, selector, or snippet into Bubble.",
        "tools": ["create_from_html"],
        "notes": "Use create_from_html directly. Pass profile, context, parent, url/html/html_file, selector, rendered_html, refresh_context, and execute.",
    },
    {
        "intent": "manage_styles_tokens_design_system",
        "when": "The user asks to list, create, update, or sync Bubble styles, colors, fonts, or design-system tokens.",
        "tools": ["list_styles", "create_style", "add_style_condition", "list_colors", "create_color", "sync_figma_style", "sync_figma_tokens"],
        "notes": "Prefer list_* before mutation when matching existing design-system assets matters.",
    },
    {
        "intent": "manage_workflows",
        "when": "The user asks to create events, add actions, wire buttons, change conditions, or inspect workflow refs.",
        "tools": ["create_workflow", "create_event", "add_action", "list_events", "resolve_refs", "map_workflow_ref"],
        "notes": "For page load workflows, target element_name='Page'. For element events, resolve the element first when ambiguous.",
    },
    {
        "intent": "manage_data_schema",
        "when": "The user asks to create or change Bubble data types, fields, option sets, or option values.",
        "tools": ["list_data_types", "create_data_type", "create_data_field", "create_option_set", "create_option_value", "list_option_values"],
        "notes": "Use preview mode first for schema changes unless the user explicitly asks to execute.",
    },
    {
        "intent": "branches_or_changelog",
        "when": "The user asks about branches, sub-branches, contributors, history, audit, or changelog.",
        "tools": ["bubble_branch_list", "bubble_branch_create", "bubble_branch_delete", "bubble_branch_contributors", "bubble_changelog_fetch"],
        "notes": "Branch delete requires execute=true and confirm=true. Branch create previews unless execute=true.",
    },
    {
        "intent": "execute_exact_payload_or_plan",
        "when": "A previous step produced a validated Bubble payload or structured plan.",
        "tools": ["bubble_compile_plan", "bubble_execute_plan", "bubble_editor_write"],
        "notes": "Use bubble_execute_plan for structured plans and bubble_editor_write only for exact /appeditor/write payloads.",
    },
)


KEYWORDS: tuple[tuple[tuple[str, ...], tuple[str, ...]], ...] = (
    (
        ("html", "selector", "seletor", "url", "convert", "converter", "converta", "import", "importar"),
        ("import_html_component",),
    ),
    (
        ("branch", "sub-branch", "version", "versao", "changelog", "history", "historico", "contributors", "colaboradores"),
        ("branches_or_changelog",),
    ),
    (
        ("workflow", "fluxo", "event", "evento", "action", "acao", "condition", "condicao", "page load", "click", "clique"),
        ("manage_workflows",),
    ),
    (("page", "pagina", "paginas", "reusable", "reutilizavel", "reutilizaveis"), ("manage_pages_or_reusables",)),
    (
        ("style", "estilo", "color", "cor", "font", "fonte", "token", "figma", "design system", "hover", "hovered"),
        ("manage_styles_tokens_design_system",),
    ),
    (
        ("data type", "tipo de dado", "field", "campo", "option set", "option value", "opcao", "schema"),
        ("manage_data_schema",),
    ),
    (
        ("context", "contexto", "profile", "perfil", "session", "sessao", "login", "cache", "resolve", "resolver", "find"),
        ("find_profile_session_or_context",),
    ),
    (("payload", "plan", "plano", "execute", "executar", "write", "escrever"), ("execute_exact_payload_or_plan",)),
    (("coverage", "cobertura", "health", "saude", "ready", "pronto", "catalog", "catalogo", "test", "teste", "validate", "validar"), ("check_server_or_catalog",)),
    (
        (
            "create",
            "criar",
            "crie",
            "update",
            "atualizar",
            "delete",
            "deletar",
            "element",
            "elemento",
            "text",
            "texto",
            "button",
            "botao",
            "group",
            "grupo",
            "input",
            "image",
            "imagem",
        ),
        ("create_or_update_visual_editor_elements",),
    ),
)


RECIPES: dict[str, dict[str, Any]] = {
    "setup_or_refresh_context": {
        "when": "A profile, session, page, element, or context target must be confirmed before mutation.",
        "tools": ["bubble_profile_list", "bubble_session_list", "bubble_context_detect", "bubble_context_find"],
        "steps": [
            {
                "tool": "bubble_profile_list",
                "purpose": "Confirm the requested profile exists and maps to the expected Bubble app.",
                "required_before_execute": True,
            },
            {
                "tool": "bubble_session_list",
                "purpose": "Confirm a captured editor session exists for the profile before any real write.",
                "required_before_execute": True,
            },
            {
                "tool": "bubble_context_detect",
                "purpose": "Refresh the .bubble-backed project context when targets may be stale.",
                "args": {"profile": "$profile", "force": True},
                "required_before_execute": True,
            },
            {
                "tool": "bubble_context_find",
                "purpose": "Resolve page, reusable, parent, or element names only when the target is ambiguous.",
                "required_before_execute": False,
            },
        ],
    },
    "html_import": {
        "when": "Convert/import/copy a URL, HTML file/snippet, or CSS selector into Bubble.",
        "tools": ["create_from_html", "bubble_context_detect"],
        "steps": [
            {
                "tool": "bubble_context_detect",
                "purpose": "Refresh context if the target page/reusable was recently changed or created.",
                "args": {"profile": "$profile", "force": True},
                "required_before_execute": False,
            },
            {
                "tool": "create_from_html",
                "purpose": "Run the advanced HTML importer in preview mode first.",
                "args": {
                    "profile": "$profile",
                    "context": "$context",
                    "parent": "$parent",
                    "url": "$url",
                    "selector": "$selector",
                    "rendered_html": True,
                    "refresh_context": True,
                    "execute": False,
                },
                "required_before_execute": True,
            },
            {
                "tool": "create_from_html",
                "purpose": "Repeat with execute=true only after the preview is valid and the user asked to apply it.",
                "args": {"execute": "$execute"},
                "required_before_execute": False,
            },
        ],
    },
    "visual_edit": {
        "when": "Create, update, rename, move, style, or delete Bubble visual elements.",
        "tools": ["bubble_context_detect", "bubble_tool_search", "create_text", "create_group", "update_text", "delete_group"],
        "steps": [
            {
                "tool": "bubble_tool_search",
                "purpose": "Find the specific create_*, update_*, or delete_* tool for the requested element type.",
                "args": {"query": "$task", "limit": 6},
                "required_before_execute": True,
            },
            {
                "tool": "bubble_context_detect",
                "purpose": "Refresh context when the target parent or element may not be in the local overlay.",
                "args": {"profile": "$profile", "force": True},
                "required_before_execute": False,
            },
            {
                "tool": "<specific visual tool>",
                "purpose": "Call the exact visual tool with profile, context, parent/element_name, and execute.",
                "args": {"profile": "$profile", "context": "$context", "parent": "$parent", "execute": "$execute"},
                "required_before_execute": True,
            },
        ],
    },
    "page_or_reusable": {
        "when": "Create, delete, clone, or inspect Bubble pages and reusable elements.",
        "tools": ["create_page", "delete_page", "create_reusable", "delete_reusable", "bubble_context_detect"],
        "steps": [
            {
                "tool": "bubble_context_detect",
                "purpose": "Refresh context first so page/reusable name collisions are visible.",
                "args": {"profile": "$profile", "force": True},
                "required_before_execute": False,
            },
            {
                "tool": "<specific page/reusable tool>",
                "purpose": "Call create_page, create_reusable, delete_page, or delete_reusable with explicit names and execute.",
                "args": {"profile": "$profile", "name": "$name", "execute": "$execute"},
                "required_before_execute": True,
            },
            {
                "tool": "bubble_context_detect",
                "purpose": "After execute=true, refresh context to verify the page or reusable exists or was removed.",
                "args": {"profile": "$profile", "force": True},
                "required_before_execute": False,
            },
        ],
    },
    "workflow": {
        "when": "Create events, add actions, wire button/page workflows, or update workflow conditions.",
        "tools": ["create_workflow", "create_event", "add_action", "resolve_refs", "map_workflow_ref"],
        "steps": [
            {
                "tool": "bubble_context_detect",
                "purpose": "Refresh context before resolving page or element workflow targets.",
                "args": {"profile": "$profile", "force": True},
                "required_before_execute": False,
            },
            {
                "tool": "create_workflow",
                "purpose": "Create or locate the workflow event. Use element_name='Page' for page-load workflows.",
                "args": {"profile": "$profile", "context": "$context", "element_name": "$element_or_Page", "execute": "$execute"},
                "required_before_execute": True,
            },
            {
                "tool": "add_action",
                "purpose": "Add the requested workflow action after the event reference is known or inferred.",
                "args": {"profile": "$profile", "context": "$context", "action_type": "$action_type", "execute": "$execute"},
                "required_before_execute": True,
            },
        ],
    },
    "data_schema": {
        "when": "Create or update data types, fields, option sets, or option values.",
        "tools": ["list_data_types", "create_data_type", "create_data_field", "create_option_set", "create_option_value"],
        "steps": [
            {
                "tool": "list_data_types",
                "purpose": "Inspect existing schema before creating duplicates.",
                "args": {"profile": "$profile"},
                "required_before_execute": True,
            },
            {
                "tool": "<specific schema tool>",
                "purpose": "Preview the schema mutation first; execute only after the requested names/types are explicit.",
                "args": {"profile": "$profile", "context": "$context", "execute": "$execute"},
                "required_before_execute": True,
            },
        ],
    },
    "style_or_tokens": {
        "when": "List, create, sync, or apply styles, colors, fonts, or design-system tokens.",
        "tools": ["list_styles", "list_colors", "create_style", "add_style_condition", "sync_figma_style", "sync_figma_tokens"],
        "steps": [
            {
                "tool": "list_styles",
                "purpose": "Inspect existing styles before creating or applying new ones.",
                "args": {"profile": "$profile"},
                "required_before_execute": False,
            },
            {
                "tool": "bubble_tool_search",
                "purpose": "Choose the exact style/color/token tool based on requested outcome.",
                "args": {"query": "$task", "limit": 6},
                "required_before_execute": True,
            },
            {
                "tool": "<specific style/token tool>",
                "purpose": "Preview or execute the selected style/token operation.",
                "args": {"profile": "$profile", "context": "$context", "execute": "$execute"},
                "required_before_execute": True,
            },
        ],
    },
    "branch_or_changelog": {
        "when": "List/create/delete branches or fetch changelog/audit entries.",
        "tools": ["bubble_branch_list", "bubble_branch_create", "bubble_branch_delete", "bubble_branch_contributors", "bubble_changelog_fetch"],
        "steps": [
            {
                "tool": "bubble_branch_list",
                "purpose": "Inspect available branches before creating sub-branches or fetching branch-specific history.",
                "args": {"profile": "$profile"},
                "required_before_execute": False,
            },
            {
                "tool": "<specific branch/changelog tool>",
                "purpose": "Run the requested branch or changelog operation. Delete requires confirm=true.",
                "args": {"profile": "$profile", "execute": "$execute"},
                "required_before_execute": True,
            },
        ],
    },
    "quality_gate": {
        "when": "Verify install health, catalog coverage, runtime behavior, or safe profile integration.",
        "tools": ["bubble_health_check", "bubble_runtime_smoke", "bubble_tool_coverage", "bubble_catalog_quality"],
        "steps": [
            {
                "tool": "bubble_health_check",
                "purpose": "Check server capabilities.",
                "required_before_execute": False,
            },
            {
                "tool": "bubble_runtime_smoke",
                "purpose": "Run the compact coverage gate: execution coverage plus agent-facing catalog quality.",
                "args": {"suite": "coverage"},
                "required_before_execute": False,
            },
            {
                "tool": "bubble_runtime_smoke",
                "purpose": "Run agent-routing, safe-read, preview-write, family-preview, or execute-write depending on risk.",
                "args": {"suite": "agent-routing", "profile": "$profile", "context": "$context", "parent": "$parent"},
                "required_before_execute": False,
            },
        ],
    },
}


RECIPE_KEYWORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (("html", "selector", "seletor", "url", "convert", "converter", "converta", "import", "importar"), "html_import"),
    (("workflow", "fluxo", "event", "evento", "action", "acao", "condition", "condicao", "page load", "click", "clique"), "workflow"),
    (("page", "pagina", "paginas", "reusable", "reutilizavel", "reutilizaveis"), "page_or_reusable"),
    (("data type", "tipo de dado", "field", "campo", "option set", "option value", "opcao", "schema"), "data_schema"),
    (("style", "estilo", "color", "cor", "font", "fonte", "token", "figma", "design system", "hover", "hovered"), "style_or_tokens"),
    (("branch", "sub-branch", "version", "versao", "changelog", "history", "historico", "contributors"), "branch_or_changelog"),
    (("coverage", "cobertura", "health", "saude", "ready", "pronto", "catalog", "catalogo", "test", "teste", "validate", "validar"), "quality_gate"),
    (("context", "contexto", "profile", "perfil", "session", "sessao", "login", "cache", "resolve", "resolver", "find"), "setup_or_refresh_context"),
    (
        ("create", "criar", "crie", "update", "atualizar", "delete", "deletar", "element", "elemento", "text", "texto", "button", "botao", "group", "grupo", "input", "image", "imagem"),
        "visual_edit",
    ),
)


SEARCH_SYNONYMS: dict[str, tuple[str, ...]] = {
    "acao": ("action",),
    "atualizar": ("update",),
    "botao": ("button",),
    "busque": ("fetch", "search"),
    "campo": ("field",),
    "catalogo": ("catalog",),
    "changelog": ("history",),
    "clique": ("click",),
    "condicao": ("condition",),
    "contexto": ("context",),
    "converta": ("convert", "import"),
    "converter": ("convert", "import"),
    "cor": ("color",),
    "criar": ("create",),
    "crie": ("create",),
    "deletar": ("delete",),
    "elemento": ("element",),
    "estilo": ("style",),
    "evento": ("event",),
    "executar": ("execute",),
    "figma": ("style", "token"),
    "fluxo": ("workflow",),
    "fonte": ("font",),
    "grupo": ("group",),
    "historico": ("history", "changelog"),
    "hover": ("condition", "style"),
    "hovered": ("condition", "style"),
    "imagem": ("image",),
    "importar": ("import",),
    "liste": ("list",),
    "listar": ("list",),
    "opcao": ("option",),
    "pagina": ("page",),
    "paginas": ("page",),
    "perfil": ("profile",),
    "plano": ("plan",),
    "reutilizavel": ("reusable",),
    "reutilizaveis": ("reusable",),
    "seletor": ("selector",),
    "sessao": ("session",),
    "texto": ("text",),
    "validar": ("validate",),
    "versao": ("version",),
}


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return ascii_text.lower().replace("_", " ").replace("-", " ")


def _query_terms(query: str) -> list[str]:
    base_terms = [term for term in _normalize_text(query).split() if term]
    expanded: list[str] = []
    for term in base_terms:
        expanded.append(term)
        expanded.extend(SEARCH_SYNONYMS.get(term, ()))
    return list(dict.fromkeys(expanded))


def agent_guide(task: str = "") -> dict[str, Any]:
    """Return compact tool-routing guidance for MCP clients."""

    normalized = _normalize_text(str(task or "").strip())
    matched_intents: list[str] = []
    if normalized:
        for keywords, intents in KEYWORDS:
            if any(keyword in normalized for keyword in keywords):
                matched_intents.extend(intents)

    unique_intents = list(dict.fromkeys(matched_intents))
    if not unique_intents:
        unique_intents = [
            "find_profile_session_or_context",
            "create_or_update_visual_editor_elements",
            "import_html_component",
            "execute_exact_payload_or_plan",
        ]

    route_map = {route["intent"]: route for route in ROUTES}
    recommended = [route_map[intent] for intent in unique_intents if intent in route_map]

    return {
        "ok": True,
        "task": task or None,
        "direct_tool_policy": {
            "use_mcp_tools_directly": True,
            "avoid_shell_cli_discovery": True,
            "preview_default": "Leave execute=false unless the user explicitly asked to apply the change in Bubble.",
            "profile_first": "Prefer profile-based calls so the server can use stored session, context, and mutation overlay.",
            "refresh_context_when_stale": "Run bubble_context_detect with force=true when the Bubble editor changed outside this MCP session.",
        },
        "setup_requirements": [
            "Each Bubble project needs a profile.",
            "Mutating calls need a stored editor session for that profile.",
            "Reliable target resolution needs a current context from bubble_context_detect.",
        ],
        "recommended_routes": recommended,
        "all_routes": list(ROUTES),
    }


def task_recipe(
    task: str = "",
    *,
    recipe: str = "",
    profile: str = "",
    context: str = "",
    parent: str = "root",
    execute: bool = False,
) -> dict[str, Any]:
    """Return a compact operational recipe for a Bubble task."""

    normalized = _normalize_text(str(task or "").strip())
    requested_recipe = str(recipe or "").strip()
    recipe_id = requested_recipe if requested_recipe in RECIPES else ""
    if not recipe_id:
        for keywords, candidate in RECIPE_KEYWORDS:
            if any(keyword in normalized for keyword in keywords):
                recipe_id = candidate
                break
    if not recipe_id:
        recipe_id = "visual_edit"

    selected = RECIPES[recipe_id]
    guide = agent_guide(task)
    return {
        "ok": True,
        "task": task or None,
        "recipe": recipe_id,
        "matched": {
            "when": selected["when"],
            "tools": selected["tools"],
        },
        "inputs": {
            "profile": profile or "$profile",
            "context": context or "$context",
            "parent": parent or "root",
            "execute": bool(execute),
        },
        "preflight": [
            "Use profile-based calls whenever possible.",
            "Run a preview first unless the user explicitly asked to execute.",
            "Refresh context when targets may have changed outside this MCP session.",
            "Never ask the user to name internal tools; infer from the task and use search/recipe when uncertain.",
        ],
        "steps": selected["steps"],
        "recommended_routes": guide["recommended_routes"],
        "safeguards": {
            "default_execute": False,
            "destructive_operations_need_confirm": True,
            "mutations_need_session": True,
            "real_write_verification": "After execute=true, refresh context or use changelog/smoke verification when materialization matters.",
        },
        "cli_equivalent": f"bubble-mcp tools recipe --task {task!r}" if task else "bubble-mcp tools recipe --task '<task>'",
    }


def search_tool_catalog(query: str, *, limit: int = 8) -> dict[str, Any]:
    """Search exposed MCP tools and return compact matching metadata."""

    from bubble_mcp.server.schemas import list_tool_schemas

    normalized_query = _normalize_text(str(query or "").strip())
    terms = _query_terms(normalized_query)
    max_results = min(max(int(limit or 8), 1), 25)
    tools = list_tool_schemas()
    scored: list[tuple[int, dict[str, Any]]] = []

    for tool in tools:
        name = str(tool.get("name") or "")
        description = str(tool.get("description") or "")
        input_schema = tool.get("inputSchema") if isinstance(tool.get("inputSchema"), dict) else {}
        properties = input_schema.get("properties") if isinstance(input_schema, dict) else {}
        property_names = list(properties.keys()) if isinstance(properties, dict) else []
        haystack = _normalize_text(" ".join([name, description, *property_names]))
        if not terms:
            score = 1
        else:
            score = 0
            normalized_name = _normalize_text(name)
            normalized_description = _normalize_text(description)
            normalized_properties = [_normalize_text(property_name) for property_name in property_names]
            for term in terms:
                if term == normalized_name:
                    score += 20
                if term in normalized_name:
                    score += 10
                if term in normalized_description:
                    score += 4
                if term in normalized_properties:
                    score += 3
                if term in haystack:
                    score += 1
        if score <= 0:
            continue
        compact = {
            "name": name,
            "description": description,
            "required": input_schema.get("required", []) if isinstance(input_schema, dict) else [],
            "properties": property_names[:40],
            "annotations": tool.get("annotations", {}),
        }
        scored.append((score, compact))

    scored.sort(key=lambda item: (-item[0], item[1]["name"]))
    matches = [{"score": score, **tool} for score, tool in scored[:max_results]]
    return {
        "ok": True,
        "query": query,
        "limit": max_results,
        "match_count": len(matches),
        "matches": matches,
        "usage": "Use this read-only search when a client needs a compact subset of the MCP catalog before choosing a tool.",
    }
