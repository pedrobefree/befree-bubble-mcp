"""Built-in framework adapter registry."""

from __future__ import annotations

from bubble_mcp.frameworks.models import FrameworkAdapter


ADAPTERS: dict[str, FrameworkAdapter] = {
    "bmad": FrameworkAdapter(
        framework_id="bmad",
        name="BMAD",
        description=(
            "Product and delivery artifacts: project brief, PRD, architecture notes, epics, stories, "
            "acceptance criteria, and validation evidence."
        ),
        modes=("project_planning", "story_breakdown", "implementation_evidence"),
        artifacts=(
            "project-brief.md",
            "prd.md",
            "architecture.md",
            "epics.md",
            "stories.md",
            "validation-evidence.md",
        ),
        evidence_targets=("stories.md", "validation-evidence.md"),
    ),
    "superpowers": FrameworkAdapter(
        framework_id="superpowers",
        name="Superpowers",
        description=(
            "Spec-to-plan execution artifacts: specs, bite-sized implementation plans, gates, and "
            "verification checklists."
        ),
        modes=("spec_to_plan", "execution_gates", "verification"),
        artifacts=(
            "spec.md",
            "implementation-plan.md",
            "execution-gates.md",
            "verification-checklist.md",
        ),
        evidence_targets=("implementation-plan.md", "verification-checklist.md"),
    ),
    "sdd": FrameworkAdapter(
        framework_id="sdd",
        name="SDD",
        description=(
            "Specification-driven development artifacts: behavioral specification, context fixtures, "
            "acceptance tests, and traceability matrix."
        ),
        modes=("behavior_spec", "fixture_generation", "acceptance_traceability"),
        artifacts=(
            "specification.md",
            "fixtures.md",
            "acceptance-tests.md",
            "traceability.md",
        ),
        evidence_targets=("acceptance-tests.md", "traceability.md"),
    ),
}


def normalize_framework_id(value: str) -> str:
    return str(value or "").strip().lower().replace("_", "-")


def get_adapter(framework: str) -> FrameworkAdapter:
    normalized = normalize_framework_id(framework)
    if normalized not in ADAPTERS:
        supported = ", ".join(sorted(ADAPTERS))
        raise ValueError(f"Unsupported framework: {framework}. Supported frameworks: {supported}.")
    return ADAPTERS[normalized]


def list_adapters() -> list[FrameworkAdapter]:
    return [ADAPTERS[key] for key in sorted(ADAPTERS)]
