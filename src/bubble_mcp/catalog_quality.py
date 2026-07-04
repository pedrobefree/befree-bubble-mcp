"""Agent-facing catalog quality checks for the Bubble MCP server."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from bubble_mcp.runtime_coverage import catalog_coverage_report
from bubble_mcp.server.prompts import list_prompts
from bubble_mcp.server.resources import list_resource_templates, list_resources
from bubble_mcp.server.schemas import list_tool_schemas


Issue = dict[str, Any]

MIN_TOOL_DESCRIPTION_CHARS = 20
MIN_PROPERTY_DESCRIPTION_CHARS = 8
REQUIRED_ANNOTATIONS = ("readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint")


def _add_issue(
    issues: list[Issue],
    *,
    check: str,
    scope: str,
    name: str,
    message: str,
    field: str | None = None,
) -> None:
    issue: Issue = {"check": check, "scope": scope, "name": name, "message": message}
    if field:
        issue["field"] = field
    issues.append(issue)


def _has_text(value: object, *, min_chars: int = 1) -> bool:
    return isinstance(value, str) and len(value.strip()) >= min_chars


def _record_check(checks: list[dict[str, Any]], name: str, before: int, issues: list[Issue]) -> None:
    issue_count = len(issues) - before
    checks.append({"name": name, "ok": issue_count == 0, "issue_count": issue_count})


def _check_duplicate_names(
    values: Sequence[Mapping[str, Any]],
    *,
    key: str,
    scope: str,
    check: str,
    issues: list[Issue],
) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        name = str(value.get(key) or "")
        if name in seen:
            duplicates.add(name)
        seen.add(name)
    for duplicate in sorted(duplicates):
        _add_issue(
            issues,
            check=check,
            scope=scope,
            name=duplicate,
            field=key,
            message=f"Duplicate {scope} identifier.",
        )


def _check_tool_schemas(tools: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[Issue]]:
    checks: list[dict[str, Any]] = []
    issues: list[Issue] = []

    before = len(issues)
    _check_duplicate_names(tools, key="name", scope="tool", check="tool_names", issues=issues)
    for tool in tools:
        name = str(tool.get("name") or "")
        if not _has_text(name):
            _add_issue(issues, check="tool_names", scope="tool", name="<missing>", field="name", message="Tool name is required.")
    _record_check(checks, "tool_names", before, issues)

    before = len(issues)
    for tool in tools:
        name = str(tool.get("name") or "<missing>")
        if not _has_text(tool.get("description"), min_chars=MIN_TOOL_DESCRIPTION_CHARS):
            _add_issue(
                issues,
                check="tool_descriptions",
                scope="tool",
                name=name,
                field="description",
                message=f"Tool description must be at least {MIN_TOOL_DESCRIPTION_CHARS} characters.",
            )
    _record_check(checks, "tool_descriptions", before, issues)

    before = len(issues)
    for tool in tools:
        name = str(tool.get("name") or "<missing>")
        input_schema = tool.get("inputSchema")
        if not isinstance(input_schema, dict):
            _add_issue(
                issues,
                check="tool_input_schemas",
                scope="tool",
                name=name,
                field="inputSchema",
                message="Tool inputSchema must be an object.",
            )
            continue
        if input_schema.get("type") != "object":
            _add_issue(
                issues,
                check="tool_input_schemas",
                scope="tool",
                name=name,
                field="inputSchema.type",
                message="Tool inputSchema.type must be object.",
            )
        properties = input_schema.get("properties", {})
        if not isinstance(properties, dict):
            _add_issue(
                issues,
                check="tool_input_schemas",
                scope="tool",
                name=name,
                field="inputSchema.properties",
                message="Tool inputSchema.properties must be an object.",
            )
            continue
        required = input_schema.get("required", [])
        if required is not None and not isinstance(required, list):
            _add_issue(
                issues,
                check="tool_input_schemas",
                scope="tool",
                name=name,
                field="inputSchema.required",
                message="Tool inputSchema.required must be a list when present.",
            )
            required = []
        for required_field in required:
            if required_field not in properties:
                _add_issue(
                    issues,
                    check="tool_input_schemas",
                    scope="tool",
                    name=name,
                    field=f"inputSchema.required.{required_field}",
                    message="Required field is missing from properties.",
                )
    _record_check(checks, "tool_input_schemas", before, issues)

    before = len(issues)
    for tool in tools:
        name = str(tool.get("name") or "<missing>")
        input_schema = tool.get("inputSchema")
        properties = input_schema.get("properties", {}) if isinstance(input_schema, dict) else {}
        if not isinstance(properties, dict):
            continue
        for property_name, property_schema in properties.items():
            if not isinstance(property_schema, dict):
                _add_issue(
                    issues,
                    check="tool_property_descriptions",
                    scope="tool",
                    name=name,
                    field=f"inputSchema.properties.{property_name}",
                    message="Tool property schema must be an object.",
                )
                continue
            if not _has_text(property_schema.get("description"), min_chars=MIN_PROPERTY_DESCRIPTION_CHARS):
                _add_issue(
                    issues,
                    check="tool_property_descriptions",
                    scope="tool",
                    name=name,
                    field=f"inputSchema.properties.{property_name}.description",
                    message=f"Tool property description must be at least {MIN_PROPERTY_DESCRIPTION_CHARS} characters.",
                )
    _record_check(checks, "tool_property_descriptions", before, issues)

    before = len(issues)
    for tool in tools:
        name = str(tool.get("name") or "<missing>")
        annotations = tool.get("annotations")
        if not isinstance(annotations, dict):
            _add_issue(
                issues,
                check="tool_annotations",
                scope="tool",
                name=name,
                field="annotations",
                message="Tool annotations must be present.",
            )
            continue
        for annotation in REQUIRED_ANNOTATIONS:
            if not isinstance(annotations.get(annotation), bool):
                _add_issue(
                    issues,
                    check="tool_annotations",
                    scope="tool",
                    name=name,
                    field=f"annotations.{annotation}",
                    message="Tool annotation must be a boolean.",
                )
        if annotations.get("readOnlyHint") is True and annotations.get("destructiveHint") is True:
            _add_issue(
                issues,
                check="tool_annotations",
                scope="tool",
                name=name,
                field="annotations",
                message="A destructive tool cannot also be marked read-only.",
            )
    _record_check(checks, "tool_annotations", before, issues)

    return checks, issues


def _check_resources(resources: list[dict[str, Any]], templates: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[Issue]]:
    checks: list[dict[str, Any]] = []
    issues: list[Issue] = []

    before = len(issues)
    _check_duplicate_names(resources, key="uri", scope="resource", check="resources", issues=issues)
    for resource in resources:
        uri = str(resource.get("uri") or "")
        name = uri or str(resource.get("name") or "<missing>")
        if "://" not in uri:
            _add_issue(issues, check="resources", scope="resource", name=name, field="uri", message="Resource URI must include a scheme.")
        for field in ("name", "title", "description", "mimeType"):
            if not _has_text(resource.get(field)):
                _add_issue(issues, check="resources", scope="resource", name=name, field=field, message="Resource field is required.")
    _record_check(checks, "resources", before, issues)

    before = len(issues)
    _check_duplicate_names(templates, key="uriTemplate", scope="resource_template", check="resource_templates", issues=issues)
    for template in templates:
        uri_template = str(template.get("uriTemplate") or "")
        name = uri_template or str(template.get("name") or "<missing>")
        if "://" not in uri_template or "{" not in uri_template:
            _add_issue(
                issues,
                check="resource_templates",
                scope="resource_template",
                name=name,
                field="uriTemplate",
                message="Resource template must include a URI scheme and at least one placeholder.",
            )
        for field in ("name", "title", "description", "mimeType"):
            if not _has_text(template.get(field)):
                _add_issue(
                    issues,
                    check="resource_templates",
                    scope="resource_template",
                    name=name,
                    field=field,
                    message="Resource template field is required.",
                )
    _record_check(checks, "resource_templates", before, issues)

    return checks, issues


def _check_prompts(prompts: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[Issue]]:
    checks: list[dict[str, Any]] = []
    issues: list[Issue] = []

    before = len(issues)
    _check_duplicate_names(prompts, key="name", scope="prompt", check="prompts", issues=issues)
    for prompt in prompts:
        name = str(prompt.get("name") or "<missing>")
        if not _has_text(prompt.get("description"), min_chars=MIN_TOOL_DESCRIPTION_CHARS):
            _add_issue(
                issues,
                check="prompts",
                scope="prompt",
                name=name,
                field="description",
                message=f"Prompt description must be at least {MIN_TOOL_DESCRIPTION_CHARS} characters.",
            )
        arguments = prompt.get("arguments", [])
        if not isinstance(arguments, list):
            _add_issue(issues, check="prompts", scope="prompt", name=name, field="arguments", message="Prompt arguments must be a list.")
            continue
        for index, argument in enumerate(arguments):
            if not isinstance(argument, dict):
                _add_issue(
                    issues,
                    check="prompts",
                    scope="prompt",
                    name=name,
                    field=f"arguments.{index}",
                    message="Prompt argument must be an object.",
                )
                continue
            for field in ("name", "description"):
                if not _has_text(argument.get(field)):
                    _add_issue(
                        issues,
                        check="prompts",
                        scope="prompt",
                        name=name,
                        field=f"arguments.{index}.{field}",
                        message="Prompt argument field is required.",
                    )
            if not isinstance(argument.get("required"), bool):
                _add_issue(
                    issues,
                    check="prompts",
                    scope="prompt",
                    name=name,
                    field=f"arguments.{index}.required",
                    message="Prompt argument required flag must be boolean.",
                )
    _record_check(checks, "prompts", before, issues)

    return checks, issues


def _coverage_check() -> tuple[dict[str, Any], list[Issue]]:
    report = catalog_coverage_report()
    issues: list[Issue] = []
    if not report.get("ok"):
        uncovered = report.get("aria_catalog", {}).get("uncovered", [])
        _add_issue(
            issues,
            check="runtime_coverage",
            scope="catalog",
            name="aria_catalog",
            field="uncovered",
            message=f"Aria-compatible tools are uncovered: {uncovered}",
        )
    if int(report.get("uncovered_count") or 0) > 0:
        _add_issue(
            issues,
            check="runtime_coverage",
            scope="catalog",
            name="exposed_tools",
            field="uncovered",
            message=f"Exposed tools are uncovered: {report.get('uncovered', [])}",
        )
    return {
        "name": "runtime_coverage",
        "ok": not issues,
        "issue_count": len(issues),
        "aria_uncovered_count": report.get("aria_catalog", {}).get("uncovered_count"),
        "uncovered_count": report.get("uncovered_count"),
    }, issues


def catalog_quality_report() -> dict[str, Any]:
    """Return a compact machine-readable quality report for MCP clients and CI."""

    tools = list_tool_schemas()
    resources = list_resources()
    resource_templates = list_resource_templates()
    prompts = list_prompts()

    checks: list[dict[str, Any]] = []
    issues: list[Issue] = []

    tool_checks, tool_issues = _check_tool_schemas(tools)
    checks.extend(tool_checks)
    issues.extend(tool_issues)

    resource_checks, resource_issues = _check_resources(resources, resource_templates)
    checks.extend(resource_checks)
    issues.extend(resource_issues)

    prompt_checks, prompt_issues = _check_prompts(prompts)
    checks.extend(prompt_checks)
    issues.extend(prompt_issues)

    coverage_check, coverage_issues = _coverage_check()
    checks.append(coverage_check)
    issues.extend(coverage_issues)

    by_scope: dict[str, int] = {}
    for issue in issues:
        scope = str(issue.get("scope") or "unknown")
        by_scope[scope] = by_scope.get(scope, 0) + 1

    return {
        "ok": not issues,
        "summary": {
            "tool_count": len(tools),
            "resource_count": len(resources),
            "resource_template_count": len(resource_templates),
            "prompt_count": len(prompts),
            "check_count": len(checks),
            "issue_count": len(issues),
            "issues_by_scope": by_scope,
        },
        "checks": checks,
        "issues": issues,
        "policy": {
            "tool_descriptions": f">= {MIN_TOOL_DESCRIPTION_CHARS} characters",
            "property_descriptions": f">= {MIN_PROPERTY_DESCRIPTION_CHARS} characters",
            "required_annotations": list(REQUIRED_ANNOTATIONS),
            "coverage": "No uncovered exposed tools; no uncovered Aria-compatible runtime tools.",
        },
    }
