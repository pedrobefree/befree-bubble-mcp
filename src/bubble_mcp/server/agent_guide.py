"""Compact agent guidance for using the Bubble MCP catalog."""

from __future__ import annotations

import re
from typing import Any
import unicodedata


COMPACT_CONTEXT_FIND_ARGS: dict[str, Any] = {
    "profile": "$profile",
    "query": "$target",
    "limit": 5,
    "exact": True,
    "include_metadata": False,
}


ROUTES: tuple[dict[str, Any], ...] = (
    {
        "intent": "check_server_or_catalog",
        "when": "The user asks whether the MCP is installed, healthy, covered, or ready.",
        "tools": ["bubble_readiness_check", "bubble_runtime_smoke", "bubble_health_check", "bubble_tool_coverage", "bubble_catalog_quality"],
        "notes": "Use bubble_readiness_check first for the compact health, coverage, catalog-quality, and routing sequence. Use individual smoke suites only for deeper diagnosis.",
    },
    {
        "intent": "find_profile_session_or_context",
        "when": "The user names a project/profile, asks what projects are available, or a target cannot be resolved.",
        "tools": ["bubble_project_bootstrap", "bubble_profile_status", "bubble_profile_add", "bubble_profile_list", "bubble_session_login", "bubble_session_list", "bubble_session_inspect", "bubble_context_detect", "bubble_context_find"],
        "notes": "Use bubble_project_bootstrap when profile/app setup is needed. Call bubble_profile_status first when a configured profile is known. For known page/element refs, use bubble_context_find with profile, exact=true, and include_metadata=false before broader searches.",
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
        "tools": ["create_from_html", "bubble_visual_capture", "bubble_visual_capture_actual", "bubble_visual_audit"],
        "notes": "Use create_from_html directly, then capture reference/actual snapshots and run bubble_visual_audit when visual fidelity matters.",
    },
    {
        "intent": "visual_quality_gate",
        "when": "The user asks to compare with the source, validate visual parity, review screenshots, or fix visual drift after an HTML/Figma/Bubble conversion.",
        "tools": ["bubble_visual_capture", "bubble_visual_capture_actual", "bubble_visual_compare", "bubble_visual_audit"],
        "notes": "Prefer bubble_visual_audit when the user expects a correction plan or execution. Use screenshots for LLM review and structured snapshots for executable repairs.",
    },
    {
        "intent": "manage_styles_tokens_design_system",
        "when": "The user asks to list, create, update, or sync Bubble styles, colors, fonts, or design-system tokens.",
        "tools": ["list_styles", "create_style", "add_style_condition", "list_colors", "create_color", "sync_figma_style", "sync_figma_tokens", "bubble_visual_audit"],
        "notes": "Prefer list_* before mutation when matching existing design-system assets matters. After Figma/style sync, use bubble_visual_audit when parity with a reference should be checked or repaired.",
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
        (
            "audit",
            "auditoria",
            "compare",
            "comparar",
            "corrija",
            "corrigir",
            "correcao",
            "correção",
            "difference",
            "diferenca",
            "diferença",
            "drift",
            "fidelity",
            "paridade",
            "print",
            "qualidade visual",
            "screenshot",
            "visual",
        ),
        ("visual_quality_gate",),
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
    (
        (
            "coverage",
            "cobertura",
            "health",
            "saude",
            "ready",
            "pronto",
            "catalog",
            "catalogo",
            "smoke test",
            "runtime smoke",
            "tests",
            "testing",
            "teste",
            "validate",
            "validar",
        ),
        ("check_server_or_catalog",),
    ),
    (
        (
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
        "tools": ["bubble_project_bootstrap", "bubble_profile_status", "bubble_profile_add", "bubble_profile_list", "bubble_session_login", "bubble_session_list", "bubble_session_inspect", "bubble_context_detect", "bubble_context_find"],
        "steps": [
            {
                "tool": "bubble_project_bootstrap",
                "purpose": "Use when the user provided a profile/app id or when setup readiness should be assessed in one call.",
                "args": {
                    "profile": "$profile",
                    "app_id": "$app_id",
                    "app_version": "$app_version",
                    "detect_context": False,
                },
                "required_before_execute": False,
            },
            {
                "tool": "bubble_profile_status",
                "purpose": "Check whether the requested profile has a matching session and fresh loadable context.",
                "args": {"profile": "$profile"},
                "required_before_execute": True,
            },
            {
                "tool": "bubble_profile_list",
                "purpose": "Use only when the requested profile is unclear or bubble_profile_status reports it missing.",
                "required_before_execute": False,
            },
            {
                "tool": "bubble_profile_add",
                "purpose": "Create the local profile when the user provided a profile name and Bubble app id but profile_status reports it missing.",
                "args": {"name": "$profile", "app_id": "$app_id", "app_version": "$app_version"},
                "required_before_execute": False,
            },
            {
                "tool": "bubble_session_login",
                "purpose": "Use when no stored session exists and the user can complete Bubble login in the opened browser.",
                "args": {"profile": "$profile", "app_id": "$app_id", "wait_seconds": 180},
                "required_before_execute": False,
            },
            {
                "tool": "bubble_session_inspect",
                "purpose": "Use when a stored session exists but the agent needs to confirm redacted captured headers and computed write headers.",
                "args": {"profile": "$profile"},
                "required_before_execute": False,
            },
            {
                "tool": "bubble_context_detect",
                "purpose": "Refresh the .bubble-backed project context when bubble_profile_status reports missing or stale context.",
                "args": {"profile": "$profile", "force": True},
                "required_before_execute": False,
            },
            {
                "tool": "bubble_context_find",
                "purpose": "Resolve or verify a known page, reusable, parent, or element without discovering local context paths.",
                "args": COMPACT_CONTEXT_FIND_ARGS,
                "required_before_execute": False,
            },
        ],
    },
    "html_import": {
        "when": "Convert/import/copy a URL, HTML file/snippet, or CSS selector into Bubble.",
        "tools": ["create_from_html", "bubble_context_detect", "bubble_visual_capture", "bubble_visual_capture_actual", "bubble_visual_audit"],
        "steps": [
            {
                "tool": "bubble_context_detect",
                "purpose": "Refresh context if the target page/reusable was recently changed or created.",
                "args": {"profile": "$profile", "force": True},
                "required_before_execute": False,
            },
            {
                "tool": "bubble_context_find",
                "purpose": "Verify the target context/parent by profile before importing when a page or reusable name was provided.",
                "args": COMPACT_CONTEXT_FIND_ARGS,
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
            {
                "tool": "bubble_visual_capture",
                "purpose": "Capture the source URL/HTML selector as the reference snapshot for visual parity checks.",
                "args": {"source": "$url_or_html_source", "selector": "$selector", "rendered_html": True},
                "required_before_execute": False,
            },
            {
                "tool": "bubble_visual_capture_actual",
                "purpose": "Capture the rendered Bubble result after import or when screenshots suggest visual drift.",
                "args": {"profile": "$profile", "page": "$context", "selector": "$selector_or_generated_container"},
                "required_before_execute": False,
            },
            {
                "tool": "bubble_visual_audit",
                "purpose": "Compare reference and Bubble captures, produce an actionable repair plan, and execute supported fixes only when requested.",
                "args": {
                    "profile": "$profile",
                    "context": "$context",
                    "parent": "$parent",
                    "reference": "$reference_snapshot_path",
                    "actual": "$actual_snapshot_path",
                    "execute": "$execute",
                },
                "required_before_execute": False,
            },
        ],
    },
    "visual_quality_gate": {
        "when": "Compare screenshots or structured captures, diagnose visual drift, and optionally execute supported Bubble repairs.",
        "tools": ["bubble_visual_capture", "bubble_visual_capture_actual", "bubble_visual_compare", "bubble_visual_audit"],
        "steps": [
            {
                "tool": "bubble_visual_capture",
                "purpose": "Capture the source URL/HTML/screenshot reference when no structured reference snapshot was supplied.",
                "args": {"source": "$reference_source", "selector": "$reference_selector", "rendered_html": True},
                "required_before_execute": False,
            },
            {
                "tool": "bubble_visual_capture_actual",
                "purpose": "Capture the current Bubble page or element when no structured actual snapshot was supplied.",
                "args": {"profile": "$profile", "page": "$context", "selector": "$actual_selector"},
                "required_before_execute": False,
            },
            {
                "tool": "bubble_visual_audit",
                "purpose": "Return issues, screenshots review metadata, and a repair plan; execute repairs only when execute=true is explicit.",
                "args": {
                    "profile": "$profile",
                    "context": "$context",
                    "parent": "$parent",
                    "reference": "$reference_snapshot_path",
                    "actual": "$actual_snapshot_path",
                    "reference_screenshot": "$reference_screenshot",
                    "actual_screenshot": "$actual_screenshot",
                    "execute": "$execute",
                },
                "required_before_execute": True,
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
                "tool": "bubble_context_find",
                "purpose": "Resolve the target parent or element by profile with compact exact output before choosing a mutation.",
                "args": COMPACT_CONTEXT_FIND_ARGS,
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
                "tool": "bubble_context_find",
                "purpose": "Check exact page/reusable existence by profile before create/delete decisions.",
                "args": COMPACT_CONTEXT_FIND_ARGS,
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
            {
                "tool": "bubble_context_find",
                "purpose": "After execute=true, verify exact page/reusable materialization or absence by profile.",
                "args": COMPACT_CONTEXT_FIND_ARGS,
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
                "tool": "bubble_context_find",
                "purpose": "Resolve the workflow page/element target by profile with compact exact output.",
                "args": COMPACT_CONTEXT_FIND_ARGS,
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
        "tools": ["list_styles", "list_colors", "create_style", "add_style_condition", "sync_figma_style", "sync_figma_tokens", "bubble_visual_audit"],
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
            {
                "tool": "bubble_visual_audit",
                "purpose": "Use after Figma/style sync when the intended result should be compared with a visual reference or screenshots.",
                "args": {"profile": "$profile", "context": "$context", "execute": "$execute"},
                "required_before_execute": False,
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
        "tools": ["bubble_readiness_check", "bubble_runtime_smoke", "bubble_health_check", "bubble_tool_coverage", "bubble_catalog_quality"],
        "steps": [
            {
                "tool": "bubble_readiness_check",
                "purpose": "Run health, compact coverage/catalog-quality gate, agent-routing, and optional profile checks in one call.",
                "args": {"profile": "$profile", "context": "$context", "parent": "$parent"},
                "required_before_execute": False,
            },
            {
                "tool": "bubble_runtime_smoke",
                "purpose": "Optional deeper execute=false family smoke when the profile is configured and broader runtime confidence is needed.",
                "args": {"suite": "family-preview", "profile": "$profile", "context": "$context", "parent": "$parent"},
                "required_before_execute": False,
            },
        ],
    },
}


RECIPE_KEYWORDS: tuple[tuple[tuple[str, ...], str], ...] = (
    (
        (
            "audit",
            "auditoria",
            "compare",
            "comparar",
            "corrija",
            "corrigir",
            "correcao",
            "correção",
            "difference",
            "diferenca",
            "diferença",
            "drift",
            "fidelity",
            "paridade",
            "print",
            "qualidade visual",
            "screenshot",
            "visual",
        ),
        "visual_quality_gate",
    ),
    (("html", "selector", "seletor", "url", "convert", "converter", "converta", "import", "importar"), "html_import"),
    (("workflow", "fluxo", "event", "evento", "action", "acao", "condition", "condicao", "page load", "click", "clique"), "workflow"),
    (("style", "estilo", "color", "cor", "font", "fonte", "token", "figma", "design system", "hover", "hovered"), "style_or_tokens"),
    (
        ("element", "elemento", "text", "texto", "button", "botao", "group", "grupo", "input", "image", "imagem"),
        "visual_edit",
    ),
    (("page", "pagina", "paginas", "reusable", "reutilizavel", "reutilizaveis"), "page_or_reusable"),
    (("data type", "tipo de dado", "field", "campo", "option set", "option value", "opcao", "schema"), "data_schema"),
    (("branch", "sub-branch", "version", "versao", "changelog", "history", "historico", "contributors"), "branch_or_changelog"),
    (
        (
            "coverage",
            "cobertura",
            "health",
            "saude",
            "ready",
            "pronto",
            "catalog",
            "catalogo",
            "smoke test",
            "runtime smoke",
            "tests",
            "testing",
            "teste",
            "validate",
            "validar",
        ),
        "quality_gate",
    ),
    (("context", "contexto", "profile", "perfil", "session", "sessao", "login", "cache", "resolve", "resolver", "find"), "setup_or_refresh_context"),
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
    "comparar": ("compare", "visual", "audit"),
    "compare": ("visual", "audit"),
    "condicao": ("condition",),
    "contexto": ("context", "bootstrap"),
    "converta": ("convert", "import"),
    "converter": ("convert", "import"),
    "cor": ("color",),
    "corrigir": ("repair", "fix", "visual", "audit"),
    "corrija": ("repair", "fix", "visual", "audit"),
    "criar": ("create",),
    "crie": ("create",),
    "deletar": ("delete",),
    "diferenca": ("difference", "visual", "audit"),
    "drift": ("visual", "audit", "repair"),
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
    "perfil": ("profile", "bootstrap", "setup"),
    "plano": ("plan",),
    "print": ("screenshot", "visual", "audit"),
    "qualidade": ("visual", "audit"),
    "reutilizavel": ("reusable",),
    "reutilizaveis": ("reusable",),
    "screenshot": ("visual", "audit"),
    "seletor": ("selector",),
    "sessao": ("session", "bootstrap", "setup"),
    "texto": ("text",),
    "validar": ("validate",),
    "versao": ("version",),
    "visual": ("audit", "compare", "repair"),
}


GENERIC_SEARCH_TERMS = {
    "acao",
    "add",
    "atualizar",
    "busque",
    "create",
    "criar",
    "crie",
    "delete",
    "deletar",
    "execute",
    "executar",
    "fetch",
    "list",
    "listar",
    "liste",
    "replace",
    "search",
    "update",
    "validar",
    "validate",
}


VISUAL_ELEMENT_SEARCH_TERMS = {
    "alert",
    "botao",
    "button",
    "checkbox",
    "datepicker",
    "dropdown",
    "group",
    "grupo",
    "html",
    "icon",
    "icone",
    "image",
    "imagem",
    "input",
    "link",
    "map",
    "radio",
    "repeating",
    "searchbox",
    "shape",
    "slider",
    "text",
    "texto",
    "video",
}


LOCATION_CONTEXT_SEARCH_TERMS = {
    "context",
    "em",
    "group",
    "grupo",
    "index",
    "na",
    "no",
    "page",
    "pagina",
    "paginas",
    "parent",
    "root",
}


TOOL_TARGET_SEARCH_TERMS = {
    "alert",
    "button",
    "checkbox",
    "datepicker",
    "dropdown",
    "group",
    "html",
    "icon",
    "image",
    "input",
    "link",
    "map",
    "radio",
    "repeating_group",
    "searchbox",
    "shape",
    "slider",
    "text",
    "video",
}


RUNBOOK_FALLBACK_MIN_SCORE = 15


RUNBOOK_SEARCH_QUERIES: dict[str, str] = {
    "branch_or_changelog": "branch changelog contributors version",
    "data_schema": "data type field option set option value schema",
    "html_import": "create_from_html html selector url import visual audit compare",
    "page_or_reusable": "create page reusable clone delete context",
    "quality_gate": "readiness coverage catalog smoke health",
    "setup_or_refresh_context": "bootstrap setup profile session context detect find status",
    "style_or_tokens": "style color font token figma condition hovered",
    "visual_quality_gate": "visual audit compare screenshot repair plan drift",
    "visual_edit": "create visual element text button group input image update delete",
    "workflow": "workflow event action condition click page load",
}


def _normalize_text(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_text = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", ascii_text.lower()).strip()


def _query_terms(query: str, *, prune_generic_actions: bool = True) -> list[str]:
    base_terms = [term for term in _normalize_text(query).split() if term]
    expanded: list[str] = []
    for term in base_terms:
        expanded.append(term)
        expanded.extend(SEARCH_SYNONYMS.get(term, ()))
    unique_terms = list(dict.fromkeys(expanded))
    if not prune_generic_actions:
        return unique_terms
    specific_terms = [term for term in unique_terms if term not in GENERIC_SEARCH_TERMS]
    pruned_terms = specific_terms or unique_terms
    target_terms = set(pruned_terms).intersection(VISUAL_ELEMENT_SEARCH_TERMS)
    if target_terms.difference({"group", "grupo"}):
        contextual = LOCATION_CONTEXT_SEARCH_TERMS.difference({"html"})
        pruned_terms = [term for term in pruned_terms if term not in contextual]
    return pruned_terms


def _has_keyword(normalized_text: str, keyword: str) -> bool:
    normalized_keyword = _normalize_text(keyword)
    if not normalized_keyword:
        return False
    if " " in normalized_keyword:
        return normalized_keyword in normalized_text
    return normalized_keyword in normalized_text.split()


def agent_guide(task: str = "") -> dict[str, Any]:
    """Return compact tool-routing guidance for MCP clients."""

    normalized = _normalize_text(str(task or "").strip())
    matched_intents: list[str] = []
    if normalized:
        for keywords, intents in KEYWORDS:
            if any(_has_keyword(normalized, keyword) for keyword in keywords):
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
            if any(_has_keyword(normalized, keyword) for keyword in keywords):
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
            "For known page, reusable, parent, or element refs, call bubble_context_find with profile, exact=true, and include_metadata=false before broad discovery.",
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


def _compact_tool_schema(tool: dict[str, Any]) -> dict[str, Any]:
    input_schema = tool.get("inputSchema") if isinstance(tool.get("inputSchema"), dict) else {}
    properties = input_schema.get("properties") if isinstance(input_schema, dict) else {}
    property_names = list(properties.keys()) if isinstance(properties, dict) else []
    return {
        "name": str(tool.get("name") or ""),
        "description": str(tool.get("description") or ""),
        "required": input_schema.get("required", []) if isinstance(input_schema, dict) else [],
        "properties": property_names[:40],
        "annotations": tool.get("annotations", {}),
    }


def _action_prefixes(terms: list[str]) -> set[str]:
    prefixes: set[str] = set()
    if {"create", "criar", "crie"}.intersection(terms):
        prefixes.add("create")
    if {"delete", "deletar"}.intersection(terms):
        prefixes.add("delete")
    if {"update", "atualizar"}.intersection(terms):
        prefixes.add("update")
    if {"list", "listar", "liste"}.intersection(terms):
        prefixes.add("list")
    if {"add", "acao"}.intersection(terms):
        prefixes.add("add")
    if "replace" in terms:
        prefixes.add("replace")
    return prefixes


def _tool_target_terms(terms: list[str]) -> set[str]:
    targets = set(terms).intersection(TOOL_TARGET_SEARCH_TERMS)
    if {"texto"}.intersection(terms):
        targets.add("text")
    if {"botao"}.intersection(terms):
        targets.add("button")
    if {"grupo"}.intersection(terms):
        targets.add("group")
    if {"imagem"}.intersection(terms):
        targets.add("image")
    if "repeating" in terms and "group" in terms:
        targets.add("repeating_group")
    return targets


def _runbook_tool_search(recipe: dict[str, Any], query: str, *, limit: int) -> dict[str, Any]:
    from bubble_mcp.server.schemas import list_tool_schemas

    max_results = min(max(int(limit or 6), 1), 25)
    schemas = {str(tool.get("name") or ""): tool for tool in list_tool_schemas()}
    exact_tools = [str(name) for name in recipe.get("matched", {}).get("tools", []) if str(name) in schemas]
    matches: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, name in enumerate(exact_tools):
        compact = _compact_tool_schema(schemas[name])
        matches.append({"score": 1000 - index, "source": "recipe", **compact})
        seen.add(name)
        if len(matches) >= max_results:
            break

    if len(matches) < max_results:
        lexical = search_tool_catalog(query, limit=25)
        for item in lexical["matches"]:
            name = str(item.get("name") or "")
            if name in seen:
                continue
            if int(item.get("score") or 0) < RUNBOOK_FALLBACK_MIN_SCORE:
                continue
            matches.append({"source": "search", **item})
            seen.add(name)
            if len(matches) >= max_results:
                break

    return {
        "ok": True,
        "query": query,
        "limit": max_results,
        "match_count": len(matches),
        "matches": matches,
        "usage": "Use recipe matches first; search matches are fallback candidates when the exact tool is still ambiguous.",
    }


def task_runbook(
    task: str = "",
    *,
    profile: str = "",
    context: str = "",
    parent: str = "root",
    execute: bool = False,
    search_limit: int = 6,
    include_profile_status: bool = False,
) -> dict[str, Any]:
    """Return a one-call operational runbook for a Bubble task."""

    guide = agent_guide(task)
    recipe = task_recipe(
        task,
        profile=profile,
        context=context,
        parent=parent,
        execute=execute,
    )
    search_query = RUNBOOK_SEARCH_QUERIES.get(str(recipe["recipe"]), task or str(recipe["recipe"]))
    search = _runbook_tool_search(recipe, search_query, limit=search_limit)
    profile_readiness: dict[str, Any] | None = None
    if include_profile_status and profile:
        from bubble_mcp.profile_status import profile_status

        status = profile_status(profile)
        profile_readiness = {
            "ok": bool(status.get("ok")),
            "ready": bool(status.get("ready")),
            "profile": status.get("profile"),
            "context": status.get("context"),
            "session": status.get("session"),
            "next_actions": status.get("next_actions", []),
        }

    return {
        "ok": True,
        "task": task or None,
        "inputs": recipe["inputs"],
        "profile_status": profile_readiness,
        "route_intents": [route["intent"] for route in guide["recommended_routes"]],
        "recipe": recipe["recipe"],
        "matched": recipe["matched"],
        "preflight": recipe["preflight"],
        "steps": recipe["steps"],
        "safeguards": recipe["safeguards"],
        "tool_search": search,
        "recommended_next_call": recipe["steps"][0] if recipe["steps"] else None,
        "usage": (
            "Use this runbook as the source of truth for the next MCP calls. "
            "Do not inspect CLI help, repository code, or the full tools/list response unless this runbook lacks a capability."
        ),
        "cli_equivalent": f"bubble-mcp tools runbook --task {task!r}" if task else "bubble-mcp tools runbook --task '<task>'",
    }


def search_tool_catalog(query: str, *, limit: int = 8) -> dict[str, Any]:
    """Search exposed MCP tools and return compact matching metadata."""

    from bubble_mcp.server.schemas import list_tool_schemas

    normalized_query = _normalize_text(str(query or "").strip())
    raw_terms = _query_terms(normalized_query, prune_generic_actions=False)
    terms = _query_terms(normalized_query)
    action_prefixes = _action_prefixes(raw_terms)
    target_terms = _tool_target_terms(terms)
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
        for prefix in action_prefixes:
            if normalized_name.startswith(f"{prefix} "):
                score += 6
            for target in target_terms:
                normalized_target = target.replace("_", " ")
                if normalized_name == f"{prefix} {normalized_target}":
                    score += 24
                elif normalized_name.startswith(f"{prefix} {normalized_target} "):
                    score += 16
        compact = _compact_tool_schema(tool)
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
