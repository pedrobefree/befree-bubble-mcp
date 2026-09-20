"""The suite manifest: what a suite declares, and what it deliberately does not.

A manifest carries environment only - which app, which branch, which impersonated user, and
whether a run records video or paints the demo cursor. It never carries steps. Steps are
Python, in a case module, because the cases this replaces assert on computed font weight, on
the relative order of three strings inside one card and on a conditional date picker; a
serialized step list covering those would be a programming language wearing a config file.

JSON rather than YAML: the config directory is already JSON end to end (``settings.json``, the
``.bubble`` exports, the run-as storage states) and the project ships no YAML parser. Adding a
dependency to make one file prettier is not a trade this repository makes.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bubble_mcp.e2e.paths import SUITE_SUFFIX, case_key, suite_path, suites_dir

DEFAULT_VIEWPORT = (1440, 900)


class E2ESuiteError(ValueError):
    """A manifest that cannot be trusted to run, with a message that says how to fix it."""


@dataclass(frozen=True)
class E2ECaseSpec:
    """One case: an id an agent can name, a description a human reads, and a module to run."""

    case_id: str
    description: str
    module: str
    tags: tuple[str, ...] = ()
    params: dict[str, Any] = field(default_factory=dict)

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "id": self.case_id,
            "description": self.description,
            "module": self.module,
        }
        if self.tags:
            payload["tags"] = list(self.tags)
        if self.params:
            payload["params"] = dict(self.params)
        return payload


@dataclass(frozen=True)
class E2ESuite:
    """A named set of cases pointed at one app version, run as one impersonated user."""

    name: str
    profile: str
    cases: tuple[E2ECaseSpec, ...]
    app_id: str = ""
    branch: str = ""
    user_id: str = ""
    base_url: str = ""
    cases_root: str = ""
    viewport: tuple[int, int] = DEFAULT_VIEWPORT
    headless: bool = True
    video: bool = False
    cursor: bool = False
    slow_mo: int = 0
    timeout_ms: int = 30_000
    path: Path | None = None

    def case(self, case_id: str) -> E2ECaseSpec:
        wanted = case_key(case_id)
        for spec in self.cases:
            if case_key(spec.case_id) == wanted:
                return spec
        known = ", ".join(spec.case_id for spec in self.cases) or "none"
        raise E2ESuiteError(f"Suite {self.name!r} has no case {case_id!r}. Cases declared: {known}.")

    def select(
        self, case_ids: Iterable[str] = (), tags: Iterable[str] = ()
    ) -> tuple[E2ECaseSpec, ...]:
        """Narrow the suite by explicit ids, by tag, or neither (the whole suite)."""

        wanted_ids = [str(value) for value in case_ids if str(value).strip()]
        wanted_tags = {str(value).strip().lower() for value in tags if str(value).strip()}
        if wanted_ids:
            return tuple(self.case(case_id) for case_id in wanted_ids)
        if wanted_tags:
            selected = tuple(
                spec for spec in self.cases if wanted_tags & {tag.lower() for tag in spec.tags}
            )
            if not selected:
                raise E2ESuiteError(
                    f"No case in suite {self.name!r} carries any of the tags: "
                    f"{', '.join(sorted(wanted_tags))}."
                )
            return selected
        return self.cases

    def to_payload(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": self.name,
            "profile": self.profile,
            "cases": [spec.to_payload() for spec in self.cases],
        }
        for key, value in (
            ("app_id", self.app_id),
            ("branch", self.branch),
            ("base_url", self.base_url),
            ("cases_root", self.cases_root),
        ):
            if value:
                payload[key] = value
        if self.user_id:
            payload["run_as"] = {"user_id": self.user_id}
        payload["viewport"] = {"width": self.viewport[0], "height": self.viewport[1]}
        payload["defaults"] = {
            "headless": self.headless,
            "video": self.video,
            "cursor": self.cursor,
            "slow_mo": self.slow_mo,
            "timeout_ms": self.timeout_ms,
        }
        return payload


def _as_int(value: Any, fallback: int, *, label: str) -> int:
    if value is None or value == "":
        return fallback
    try:
        return int(value)
    except (TypeError, ValueError) as error:
        raise E2ESuiteError(f"{label} must be a whole number, got {value!r}.") from error


def _as_bool(value: Any, fallback: bool) -> bool:
    if value is None or value == "":
        return fallback
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in {"true", "1", "yes", "on"}:
        return True
    if text in {"false", "0", "no", "off"}:
        return False
    return fallback


def _parse_case(entry: Any, *, index: int, suite_name: str) -> E2ECaseSpec:
    if not isinstance(entry, dict):
        raise E2ESuiteError(
            f"Case #{index} of suite {suite_name!r} must be an object with id, description "
            "and module."
        )
    case_id = str(entry.get("id") or entry.get("case_id") or "").strip()
    if not case_id:
        raise E2ESuiteError(f"Case #{index} of suite {suite_name!r} is missing 'id'.")
    module = str(entry.get("module") or "").strip()
    if not module:
        raise E2ESuiteError(
            f"Case {case_id!r} is missing 'module': the path of its Python file, relative to "
            "the profile's cases directory."
        )
    raw_tags = entry.get("tags")
    raw_tags = () if raw_tags is None else raw_tags
    if isinstance(raw_tags, str):
        raw_tags = [raw_tags]
    if not isinstance(raw_tags, list | tuple):
        raise E2ESuiteError(f"Case {case_id!r}: 'tags' must be a list of strings.")
    params = entry.get("params")
    params = {} if params is None else params
    if not isinstance(params, dict):
        raise E2ESuiteError(f"Case {case_id!r}: 'params' must be an object.")
    return E2ECaseSpec(
        case_id=case_id,
        description=str(entry.get("description") or "").strip(),
        module=module,
        tags=tuple(str(tag).strip() for tag in raw_tags if str(tag).strip()),
        params=dict(params),
    )


def parse_suite(payload: Any, *, path: Path | None = None, profile: str = "") -> E2ESuite:
    """Turn manifest JSON into a suite, or explain precisely what is wrong with it."""

    where = f" in {path}" if path else ""
    if not isinstance(payload, dict):
        raise E2ESuiteError(f"A suite manifest{where} must be a JSON object.")

    fallback_name = path.name[: -len(SUITE_SUFFIX)] if path else ""
    name = str(payload.get("name") or fallback_name).strip()
    if not name:
        raise E2ESuiteError(f"The suite manifest{where} is missing 'name'.")
    suite_profile = str(payload.get("profile") or profile or "").strip()
    if not suite_profile:
        raise E2ESuiteError(f"Suite {name!r}{where} is missing 'profile'.")

    raw_cases = payload.get("cases")
    if not isinstance(raw_cases, list) or not raw_cases:
        raise E2ESuiteError(f"Suite {name!r}{where} must declare a non-empty 'cases' list.")
    cases = tuple(
        _parse_case(entry, index=index, suite_name=name)
        for index, entry in enumerate(raw_cases, start=1)
    )
    seen: set[str] = set()
    for spec in cases:
        key = case_key(spec.case_id)
        if key in seen:
            raise E2ESuiteError(f"Suite {name!r}{where} declares case id {spec.case_id!r} twice.")
        seen.add(key)

    run_as = payload.get("run_as") or {}
    if not isinstance(run_as, dict):
        raise E2ESuiteError(f"Suite {name!r}{where}: 'run_as' must be an object with 'user_id'.")

    viewport = payload.get("viewport") or {}
    if not isinstance(viewport, dict):
        raise E2ESuiteError(f"Suite {name!r}{where}: 'viewport' must be an object.")
    defaults = payload.get("defaults") or {}
    if not isinstance(defaults, dict):
        raise E2ESuiteError(f"Suite {name!r}{where}: 'defaults' must be an object.")

    return E2ESuite(
        name=name,
        profile=suite_profile,
        cases=cases,
        app_id=str(payload.get("app_id") or "").strip(),
        branch=str(payload.get("branch") or payload.get("app_version") or "").strip(),
        user_id=str(run_as.get("user_id") or "").strip(),
        base_url=str(payload.get("base_url") or "").strip().rstrip("/"),
        cases_root=str(payload.get("cases_root") or "").strip(),
        viewport=(
            _as_int(viewport.get("width"), DEFAULT_VIEWPORT[0], label="viewport.width"),
            _as_int(viewport.get("height"), DEFAULT_VIEWPORT[1], label="viewport.height"),
        ),
        headless=_as_bool(defaults.get("headless"), True),
        video=_as_bool(defaults.get("video"), False),
        cursor=_as_bool(defaults.get("cursor"), False),
        slow_mo=_as_int(defaults.get("slow_mo"), 0, label="defaults.slow_mo"),
        timeout_ms=_as_int(defaults.get("timeout_ms"), 30_000, label="defaults.timeout_ms"),
        path=path,
    )


def load_suite(profile: str, name: str, config_dir: Path | None = None) -> E2ESuite:
    path = suite_path(profile, name, config_dir)
    if not path.exists():
        known = sorted(item.name for item in list_suites(profile, config_dir))
        raise E2ESuiteError(
            f"No suite {name!r} for profile {profile!r} at {path}. "
            f"Suites available: {', '.join(known) or 'none'}. "
            "Create one with bubble_e2e_scaffold."
        )
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise E2ESuiteError(f"Suite manifest {path} could not be read: {error}") from error
    return parse_suite(payload, path=path, profile=profile)


def list_suites(profile: str, config_dir: Path | None = None) -> list[E2ESuite]:
    """Every readable suite for a profile. An unreadable one is skipped, not fatal."""

    directory = suites_dir(profile, config_dir)
    if not directory.is_dir():
        return []
    suites: list[E2ESuite] = []
    for path in sorted(directory.glob(f"*{SUITE_SUFFIX}")):
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
            suites.append(parse_suite(payload, path=path, profile=profile))
        except (OSError, ValueError):
            continue
    return suites
