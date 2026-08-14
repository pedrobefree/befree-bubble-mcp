"""Profile-scoped context, element, and workflow alias registry."""

from __future__ import annotations

import copy
import time
from collections.abc import Callable, MutableMapping
from typing import Any


CacheGetter = Callable[[], MutableMapping[str, Any]]
ProfileKeyGetter = Callable[[], str]
Normalizer = Callable[[Any], str]
PathNormalizer = Callable[[Any], list[str]]
LifecycleCallback = Callable[[], None]
TransactionRunner = Callable[[Callable[[], bool]], bool]
Clock = Callable[[], int]

PROFILE_BUCKETS = (
    "option_sets",
    "user_types",
    "app_texts",
    "events",
    "workflow_refs",
    "element_refs",
    "components",
    "contexts",
)


def _new_profile_cache() -> dict[str, Any]:
    return {
        "option_sets": {},
        "user_types": {},
        "app_texts": {},
        "events": {},
        "workflow_refs": {},
        "element_refs": {},
        "components": {},
        "contexts": {"page": {}, "reusable": {}},
    }


class ContextAliasRegistry:
    """Manage profile-scoped aliases over the mutable CLI cache mapping."""

    def __init__(
        self,
        *,
        cache: CacheGetter,
        profile_key: ProfileKeyGetter,
        normalize: Normalizer,
        normalize_path: PathNormalizer,
        reload: LifecycleCallback,
        save: LifecycleCallback,
        transaction: TransactionRunner | None = None,
        clock_ms: Clock | None = None,
    ) -> None:
        self._cache = cache
        self._profile_key = profile_key
        self._normalize = normalize
        self._normalize_path = normalize_path
        self._reload = reload
        self._save = save
        self._transaction = transaction or self._default_transaction
        self._clock_ms = clock_ms or (lambda: int(time.time() * 1000))

    def _default_transaction(self, operation: Callable[[], bool]) -> bool:
        self._reload()
        changed = operation()
        if changed:
            self._save()
        return changed

    def profile_cache(self) -> dict[str, Any]:
        """Return a repaired profile cache without modifying sibling profiles."""
        root = self._cache()
        schema = root.get("schema")
        if not isinstance(schema, dict):
            schema = {}
            root["schema"] = schema
        profiles = schema.get("profiles")
        if not isinstance(profiles, dict):
            profiles = {}
            schema["profiles"] = profiles

        key = self._profile_key() or "default"
        profile = profiles.get(key)
        if not isinstance(profile, dict):
            profile = _new_profile_cache()
            profiles[key] = profile

        for bucket_name in PROFILE_BUCKETS:
            if bucket_name == "contexts":
                continue
            if not isinstance(profile.get(bucket_name), dict):
                profile[bucket_name] = {}

        contexts = profile.get("contexts")
        if not isinstance(contexts, dict):
            contexts = {}
            profile["contexts"] = contexts
        for context_type in ("page", "reusable"):
            if not isinstance(contexts.get(context_type), dict):
                contexts[context_type] = {}
        return profile

    def bucket(self, name: str) -> dict[str, Any]:
        """Return one canonical profile bucket."""
        if name not in PROFILE_BUCKETS:
            raise ValueError(f"Unknown profile cache bucket: {name}")
        return self.profile_cache()[name]

    @staticmethod
    def context_key(context_id: str, context_type: str) -> str:
        return f"{context_type}:{context_id}"

    def cache_context(
        self,
        context_type: str,
        context_name: str,
        context_id: str,
        object_id: str | None = None,
    ) -> bool:
        """Index a context by every stable caller-facing token."""
        context_kind = "reusable" if str(context_type).strip().lower() == "reusable" else "page"
        context_key = str(context_id or "").strip()
        if not context_key:
            return False
        name = str(context_name or "").strip()
        object_key = str(object_id or "").strip()
        payload = {"name": name, "context_id": context_key, "object_id": object_key}

        def operation() -> bool:
            context_bucket = self.bucket("contexts")[context_kind]
            changed = False
            for token in (name, context_key, object_key):
                alias = self._normalize(token)
                if alias and context_bucket.get(alias) != payload:
                    context_bucket[alias] = payload
                    changed = True
            return changed

        return self._transaction(operation)

    def lookup_context(self, token: str) -> tuple[str | None, str | None]:
        """Resolve ambiguous aliases with reusable-before-page precedence."""
        alias = self._normalize(token)
        if not alias:
            return None, None
        contexts = self.bucket("contexts")
        for context_type in ("reusable", "page"):
            scoped = contexts.get(context_type)
            if not isinstance(scoped, dict):
                continue
            payload = scoped.get(alias)
            if not isinstance(payload, dict):
                continue
            context_id = str(payload.get("context_id") or "").strip()
            if context_id:
                return context_id, context_type
        return None, None

    def _element_scope(self, context_id: str, context_type: str, *, create: bool) -> dict[str, Any]:
        refs = self.bucket("element_refs")
        scope_key = self.context_key(context_id, context_type)
        scoped = refs.get(scope_key)
        if isinstance(scoped, dict):
            return scoped
        if create:
            scoped = {}
            refs[scope_key] = scoped
            return scoped
        return {}

    def _upsert_element(
        self,
        *,
        context_id: str,
        context_type: str,
        alias_name: str,
        element_id: str,
        element_key: str | None,
        element_path: list[str] | None,
        element_type: str | None,
    ) -> bool:
        alias = str(alias_name or "").strip()
        element = str(element_id or "").strip()
        normalized_alias = self._normalize(alias)
        if not alias or not element or not normalized_alias:
            return False

        scoped = self._element_scope(context_id, context_type, create=True)
        existing = scoped.get(normalized_alias)
        existing_key = ""
        existing_path: list[str] = []
        if isinstance(existing, dict):
            existing_key = str(existing.get("key") or "").strip()
            existing_path = self._normalize_path(existing.get("path"))

        resolved_key = str(element_key or "").strip() or existing_key
        resolved_path = self._normalize_path(element_path) or existing_path
        payload: dict[str, Any] = {
            "name": alias,
            "id": element,
            "context_id": context_id,
            "context_type": context_type,
        }
        if resolved_key:
            payload["key"] = resolved_key
        if resolved_path:
            payload["path"] = resolved_path
        resolved_type = str(element_type or "").strip()
        if resolved_type:
            payload["type"] = resolved_type
        if existing == payload:
            return False
        scoped[normalized_alias] = payload
        return True

    def cache_element(
        self,
        context_id: str,
        context_type: str,
        alias_name: str,
        element_id: str,
        *,
        element_key: str | None = None,
        element_path: list[str] | None = None,
        element_type: str | None = None,
    ) -> bool:
        """Persist one element alias after refreshing cross-process state."""
        if not str(alias_name or "").strip() or not str(element_id or "").strip():
            return False

        def operation() -> bool:
            return self._upsert_element(
                context_id=context_id,
                context_type=context_type,
                alias_name=alias_name,
                element_id=element_id,
                element_key=element_key,
                element_path=element_path,
                element_type=element_type,
            )

        return self._transaction(operation)

    def cache_created_elements(
        self,
        context_id: str,
        context_type: str,
        aliases: list[str],
        element_id: str,
        *,
        element_key: str | None = None,
        parent_path: list[str] | None = None,
        element_type: str | None = None,
    ) -> int:
        """Persist all stable aliases for a newly created element in one write."""
        element = str(element_id or "").strip()
        key = str(element_key or "").strip()
        if not element and not key:
            return 0

        created_path = self._normalize_path(parent_path)
        if key:
            created_path.extend(["%el", key])
        candidates = list(aliases or [])
        if key:
            candidates.append(key)
        if element:
            candidates.append(element)

        changed_count = 0

        def operation() -> bool:
            nonlocal changed_count
            seen: set[str] = set()
            for raw_alias in candidates:
                alias = str(raw_alias or "").strip()
                normalized = self._normalize(alias)
                if not alias or not normalized or normalized in seen:
                    continue
                seen.add(normalized)
                changed_count += int(
                    self._upsert_element(
                        context_id=context_id,
                        context_type=context_type,
                        alias_name=alias,
                        element_id=element or key,
                        element_key=key or None,
                        element_path=created_path or None,
                        element_type=element_type,
                    )
                )
            return changed_count > 0

        return changed_count if self._transaction(operation) else 0

    def lookup_element_id(
        self,
        context_id: str,
        context_type: str,
        alias_name: str,
        *,
        reload: bool = True,
    ) -> str | None:
        """Resolve modern object and legacy string alias payloads."""
        alias = self._normalize(alias_name)
        if not alias:
            return None
        if reload:
            self._reload()
        payload = self._element_scope(context_id, context_type, create=False).get(alias)
        if isinstance(payload, dict):
            value = str(payload.get("id") or "").strip()
            return value or None
        if isinstance(payload, str):
            value = payload.strip()
            return value or None
        return None

    def lookup_element_payload(
        self,
        context_id: str,
        context_type: str,
        alias_name: str,
        *,
        reload: bool = True,
    ) -> dict[str, Any] | None:
        """Return a defensive copy of one modern element alias payload."""
        alias = self._normalize(alias_name)
        if not alias:
            return None
        if reload:
            self._reload()
        payload = self._element_scope(context_id, context_type, create=False).get(alias)
        return copy.deepcopy(payload) if isinstance(payload, dict) else None

    def remove_element_aliases(
        self,
        context_id: str,
        context_type: str,
        *,
        element_id: str | None = None,
        element_key: str | None = None,
        element_path: list[str] | None = None,
    ) -> int:
        """Remove aliases matching any supplied stable element selector."""
        target_id = str(element_id or "").strip()
        target_key = str(element_key or "").strip()
        target_path = self._normalize_path(element_path)
        removed_count = 0

        def operation() -> bool:
            nonlocal removed_count
            scoped = self._element_scope(context_id, context_type, create=False)
            removed: list[str] = []
            for alias, payload in scoped.items():
                if isinstance(payload, str):
                    if target_id and payload.strip() == target_id:
                        removed.append(alias)
                    continue
                if not isinstance(payload, dict):
                    continue
                payload_id = str(payload.get("id") or "").strip()
                payload_key = str(payload.get("key") or "").strip()
                payload_path = self._normalize_path(payload.get("path"))
                if (
                    (target_id and payload_id == target_id)
                    or (target_key and payload_key == target_key)
                    or (target_path and payload_path == target_path)
                ):
                    removed.append(alias)
            for alias in removed:
                scoped.pop(alias, None)
            removed_count = len(removed)
            return removed_count > 0

        return removed_count if self._transaction(operation) else 0

    def _workflow_scope(self, context_id: str, context_type: str, *, create: bool) -> dict[str, Any]:
        refs = self.bucket("workflow_refs")
        scope_key = self.context_key(context_id, context_type)
        scoped = refs.get(scope_key)
        if isinstance(scoped, dict):
            return scoped
        if create:
            scoped = {}
            refs[scope_key] = scoped
            return scoped
        return {}

    def cache_workflow(
        self,
        context_id: str,
        context_type: str,
        alias_name: str,
        workflow_key: str,
        workflow_id: str | None = None,
    ) -> bool:
        """Persist one workflow alias after refreshing cross-process state."""
        alias = str(alias_name or "").strip()
        key = str(workflow_key or "").strip()
        normalized = self._normalize(alias)
        if not alias or not key or not normalized:
            return False
        stable_payload: dict[str, Any] = {
            "name": alias,
            "key": key,
            "context_id": context_id,
            "context_type": context_type,
        }
        resolved_id = str(workflow_id or "").strip()
        if resolved_id:
            stable_payload["id"] = resolved_id

        def operation() -> bool:
            scoped = self._workflow_scope(context_id, context_type, create=True)
            existing = scoped.get(normalized)
            if isinstance(existing, dict):
                existing_stable = {
                    field: existing.get(field)
                    for field in ("name", "key", "context_id", "context_type", "id")
                    if field in existing
                }
                if existing_stable == stable_payload:
                    return False
            payload = dict(stable_payload)
            payload["updated_at"] = self._clock_ms()
            scoped[normalized] = payload
            return True

        return self._transaction(operation)

    def lookup_workflow(
        self,
        context_id: str,
        context_type: str,
        alias_name: str,
        *,
        reload: bool = True,
    ) -> dict[str, Any] | None:
        """Return a defensive copy of a valid workflow alias payload."""
        alias = self._normalize(alias_name)
        if not alias:
            return None
        if reload:
            self._reload()
        payload = self._workflow_scope(context_id, context_type, create=False).get(alias)
        if not isinstance(payload, dict) or not str(payload.get("key") or "").strip():
            return None
        return copy.deepcopy(payload)

    def remove_context_aliases(
        self,
        context_type: str,
        *,
        context_id: str | None = None,
        context_name: str | None = None,
        object_id: str | None = None,
    ) -> int:
        """Remove every alias token belonging to a matching context payload."""
        context_kind = "reusable" if context_type == "reusable" else "page"
        target_id = str(context_id or "").strip()
        target_object = str(object_id or "").strip()
        target_name = self._normalize(context_name)
        removed_count = 0

        def operation() -> bool:
            nonlocal removed_count
            scoped = self.bucket("contexts").get(context_kind)
            if not isinstance(scoped, dict):
                return False
            removed: list[str] = []
            for alias, payload in scoped.items():
                if not isinstance(payload, dict):
                    continue
                payload_id = str(payload.get("context_id") or "").strip()
                payload_object = str(payload.get("object_id") or "").strip()
                payload_name = self._normalize(payload.get("name"))
                if (
                    (target_id and payload_id == target_id)
                    or (target_object and payload_object == target_object)
                    or (target_name and payload_name == target_name)
                ):
                    removed.append(alias)
            for alias in removed:
                scoped.pop(alias, None)
            removed_count = len(removed)
            return removed_count > 0

        return removed_count if self._transaction(operation) else 0

    def remove_workflow_aliases(
        self,
        context_id: str,
        context_type: str,
        *,
        workflow_key: str | None = None,
        workflow_id: str | None = None,
        workflow_name: str | None = None,
    ) -> int:
        """Remove workflow aliases matching any supplied stable selector."""
        target_key = str(workflow_key or "").strip()
        target_id = str(workflow_id or "").strip()
        target_name = self._normalize(workflow_name)
        removed_count = 0

        def operation() -> bool:
            nonlocal removed_count
            scoped = self._workflow_scope(context_id, context_type, create=False)
            removed: list[str] = []
            for alias, payload in scoped.items():
                if not isinstance(payload, dict):
                    continue
                payload_key = str(payload.get("key") or "").strip()
                payload_id = str(payload.get("id") or "").strip()
                payload_name = self._normalize(payload.get("name"))
                if (
                    (target_key and payload_key == target_key)
                    or (target_id and payload_id == target_id)
                    or (target_name and payload_name == target_name)
                ):
                    removed.append(alias)
            for alias in removed:
                scoped.pop(alias, None)
            removed_count = len(removed)
            return removed_count > 0

        return removed_count if self._transaction(operation) else 0

    def remove_context_scope(self, context_id: str, context_type: str) -> bool:
        """Remove modern and historical registry entries scoped to one context."""
        scope_key = self.context_key(context_id, context_type)
        legacy_prefix = f"{scope_key}:"

        def operation() -> bool:
            changed = False
            for bucket_name in ("element_refs", "workflow_refs", "events"):
                bucket = self.bucket(bucket_name)
                keys = [
                    key
                    for key in bucket
                    if str(key) == scope_key or str(key).startswith(legacy_prefix)
                ]
                for key in keys:
                    bucket.pop(key, None)
                    changed = True
            return changed

        return self._transaction(operation)
