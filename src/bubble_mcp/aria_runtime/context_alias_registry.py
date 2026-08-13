"""Profile-scoped context, element, and workflow alias registry."""

from __future__ import annotations

import time
from collections.abc import Callable, MutableMapping
from typing import Any


CacheGetter = Callable[[], MutableMapping[str, Any]]
ProfileKeyGetter = Callable[[], str]
Normalizer = Callable[[Any], str]
PathNormalizer = Callable[[Any], list[str]]
LifecycleCallback = Callable[[], None]
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
        clock_ms: Clock | None = None,
    ) -> None:
        self._cache = cache
        self._profile_key = profile_key
        self._normalize = normalize
        self._normalize_path = normalize_path
        self._reload = reload
        self._save = save
        self._clock_ms = clock_ms or (lambda: int(time.time() * 1000))

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
        context_bucket = self.bucket("contexts")[context_kind]

        changed = False
        for token in (name, context_key, object_key):
            alias = self._normalize(token)
            if alias and context_bucket.get(alias) != payload:
                context_bucket[alias] = payload
                changed = True
        if changed:
            self._save()
        return changed

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
