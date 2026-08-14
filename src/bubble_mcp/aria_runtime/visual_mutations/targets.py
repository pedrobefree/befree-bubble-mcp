"""Shared target discovery and canonical-path selection for visual writes."""

from __future__ import annotations

from typing import Any

try:
    from ..bubble_sdk import logger
except ImportError:  # pragma: no cover - direct BubbleCLI execution compatibility
    from bubble_sdk import logger

from .protocols import VisualElementTarget, VisualMutationHost


class VisualMutationTargets:
    """Resolve existing visual elements without owning discovery persistence."""

    def __init__(self, host: VisualMutationHost) -> None:
        self._host = host

    def resolve_existing(
        self,
        context_name: str,
        element_name: str,
        *,
        prefer_last: bool = False,
    ) -> VisualElementTarget | None:
        logger.info(f"Searching for context: {context_name}")
        context_id, context_type = self._host._find_context(context_name)
        if not context_id or not context_type:
            logger.error(f"'{context_name}' not found")
            return None

        logger.info(f"Searching for element: '{element_name}'")
        result = self._host.discovery.find_element_by_name(
            context_id,
            element_name,
            context_type=context_type,
            prefer_last=prefer_last,
        )
        if not result:
            result = self._find_by_button_label(context_id, context_type, element_name)
        if not result:
            result = self._host._find_element_by_ref(
                context_id,
                context_type,
                element_name,
                ref_kind="auto",
                match_index=1,
            )
            if result:
                logger.info(f"Resolved '{element_name}' by reference lookup.")
        if not result:
            result = self._host._resolve_cached_element_alias(
                context_id,
                context_type,
                element_name,
            )
            if result:
                logger.info(f"Resolved '{element_name}' via local alias cache.")
        if not isinstance(result, dict):
            logger.error(f"Element '{element_name}' not found")
            return None

        target = self.from_result(context_id, context_type, result)
        if target is None:
            logger.error(f"Could not resolve element id for '{element_name}'.")
        return target

    def from_result(
        self,
        context_id: str,
        context_type: str,
        result: dict[str, Any],
    ) -> VisualElementTarget | None:
        """Hydrate a discovery result and bind it to its canonical write path."""
        result = self._hydrate_result(context_id, context_type, result)
        element = result.get("element") if isinstance(result.get("element"), dict) else {}
        element_id = str(result.get("id") or element.get("id") or result.get("key") or "").strip()
        path = self.canonical_path(context_id, context_type, result, element_id)
        if not element_id:
            element_id = self._last_element_token(path)
        if not element_id:
            return None
        element_type = str(element.get("%x") or element.get("type") or "").strip().lower()
        return VisualElementTarget(
            context_id=context_id,
            context_type=context_type,
            result=result,
            element_id=element_id,
            element_type=element_type,
            path=path,
        )

    def resolve_existing_tuple(
        self,
        context_name: str,
        element_name: str,
        *,
        prefer_last: bool = False,
    ) -> tuple[str, str, dict[str, Any]] | None:
        target = self.resolve_existing(context_name, element_name, prefer_last=prefer_last)
        if target is None:
            return None
        return target.context_id, target.context_type, target.result

    def canonical_path(
        self,
        context_id: str,
        context_type: str,
        result: dict[str, Any],
        target_id: str = "",
    ) -> list[str]:
        data = self._host.discovery.data if isinstance(self._host.discovery.data, dict) else {}
        index = data.get("_index", {}) if isinstance(data.get("_index"), dict) else {}
        id_to_path = index.get("id_to_path", {}) if isinstance(index.get("id_to_path"), dict) else {}
        expected_prefix = self._host._workflow_prefix(context_type)

        element = result.get("element") if isinstance(result.get("element"), dict) else {}
        candidates: list[str] = []
        for raw_candidate in (
            target_id,
            result.get("key"),
            result.get("id"),
            element.get("id"),
        ):
            candidate = str(raw_candidate or "").strip()
            if candidate and candidate not in candidates:
                candidates.append(candidate)
        relative_path = result.get("path")
        if isinstance(relative_path, list) and relative_path:
            tail = str(relative_path[-1] or "").strip()
            if tail and tail not in candidates:
                candidates.append(tail)

        for candidate in candidates:
            normalized = self._host._normalize_capture_path(id_to_path.get(candidate))
            if (
                len(normalized) >= 4
                and normalized[0] == expected_prefix
                and normalized[1] == context_id
                and "%el" in normalized
            ):
                return normalized

        fallback = self._host.discovery.build_path_array(
            context_id,
            relative_path if isinstance(relative_path, list) else [],
            context_type=context_type,
        )
        fallback = self._host._canonicalize_context_prefix_on_path(
            fallback,
            context_id,
            context_type,
        )
        return self._host._normalize_payload_path(fallback)

    def _find_by_button_label(
        self,
        context_id: str,
        context_type: str,
        element_name: str,
    ) -> dict[str, Any] | None:
        candidates: list[str] = []
        raw_name = str(element_name or "").strip()
        if raw_name:
            candidates.append(raw_name)
        if raw_name.lower().startswith("button "):
            stripped = raw_name[7:].strip()
            if stripped and stripped not in candidates:
                candidates.insert(0, stripped)
        for candidate in candidates:
            result = self._host._find_button_by_label(context_id, context_type, candidate)
            if result:
                logger.info(f"Resolved '{element_name}' by button label.")
                return result
        return None

    def _hydrate_result(
        self,
        context_id: str,
        context_type: str,
        result: dict[str, Any],
    ) -> dict[str, Any]:
        hydrated = result.get("element")
        needs_hydration = not isinstance(hydrated, dict) or not hydrated or not self._has_props(hydrated)
        candidate_path = result.get("path")
        if needs_hydration and isinstance(candidate_path, list) and candidate_path:
            resolved_path = self._host.discovery.build_path_array(
                context_id,
                candidate_path,
                context_type=context_type,
            )
            node = self._host._get_value_at_path(resolved_path)
            if isinstance(node, dict):
                result = dict(result)
                result["element"] = node
                result["id"] = result.get("id") or node.get("id")

        hydrated = result.get("element")
        if isinstance(hydrated, dict) and self._has_props(hydrated):
            return result

        target_id = str(result.get("id") or result.get("key") or "").strip()
        target_path = result.get("path")
        try:
            candidates = self._host.discovery.list_elements(
                context_id,
                context_type=context_type,
            ) or []
        except Exception:
            candidates = []
        for candidate in candidates:
            if not isinstance(candidate, dict):
                continue
            candidate_element = candidate.get("element")
            if not isinstance(candidate_element, dict):
                continue
            candidate_id = str(candidate.get("id") or candidate_element.get("id") or "").strip()
            candidate_path = candidate.get("path")
            if target_id and candidate_id == target_id or (
                isinstance(target_path, list)
                and isinstance(candidate_path, list)
                and candidate_path == target_path
            ):
                merged = dict(result)
                merged["element"] = candidate_element
                merged["id"] = result.get("id") or candidate_id
                return merged
        return result

    @staticmethod
    def _has_props(element: dict[str, Any]) -> bool:
        return isinstance(element.get("%p"), dict) or isinstance(element.get("properties"), dict)

    @staticmethod
    def _last_element_token(path: list[str]) -> str:
        token = ""
        for index, part in enumerate(path[:-1]):
            if part == "%el":
                token = str(path[index + 1] or "").strip()
        return token
