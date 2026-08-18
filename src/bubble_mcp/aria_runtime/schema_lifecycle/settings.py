"""Project-setting and 301-redirect lifecycle operations."""

from __future__ import annotations

import copy
import json
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from ..bubble_sdk import PayloadBuilder
else:
    try:
        from ..bubble_sdk import PayloadBuilder
    except ImportError:  # pragma: no cover - direct BubbleCLI execution compatibility
        from bubble_sdk import PayloadBuilder

from .protocols import SchemaLifecycleHost
from .references import SchemaReferenceResolver


# This registry is deliberately kept with its lifecycle owner.  It is the public
# inventory of every supported project-setting alias, not a cache of live values.
PROJECT_SETTING_ALIASES: dict[str, dict[str, Any]] = {
    "app-rights": {"path": ["settings", "client_safe", "app_rights"], "value_type": "string"},
    "preview-password-protection": {"path": ["settings", "client_safe", "pw_protection"], "value_type": "bool"},
    "preview-username": {"path": ["settings", "secure", "username"], "value_type": "string", "sensitive": True},
    "preview-password": {"path": ["settings", "secure", "%pw"], "value_type": "string", "sensitive": True},
    "preview-password-dev-only": {"path": ["settings", "client_safe", "pw_protection_dev_only"], "value_type": "bool"},
    "password-policy-enabled": {"path": ["settings", "client_safe", "have_pw_policy"], "value_type": "bool"},
    "password-min-length": {"path": ["settings", "client_safe", "pw_length"], "value_type": "int"},
    "password-require-number": {"path": ["settings", "client_safe", "pw_require_number"], "value_type": "bool"},
    "password-require-capital": {"path": ["settings", "client_safe", "pw_require_capital_letter"], "value_type": "bool"},
    "password-require-special-char": {"path": ["settings", "client_safe", "pw_require_special_char"], "value_type": "bool"},
    "temp-password-redirect-page": {"path": ["settings", "client_safe", "temp_pw_page_redirect"], "value_type": "string"},
    "iframe-policy": {"path": ["settings", "client_safe", "allow_iframe"], "value_type": "string"},
    "cookie-opt-in": {"path": ["settings", "client_safe", "cookie_opt_in"], "value_type": "bool"},
    "disable-file-upload-api": {"path": ["settings", "client_safe", "is_deprecated_fileupload_disabled"], "value_type": "bool"},
    "favicon": {"path": ["favicon"], "value_type": "string"},
    "status-bar-color": {"path": ["settings", "client_safe", "status_bar_color"], "value_type": "string"},
    "spinner-color": {"path": ["settings", "client_safe", "spinner_color"], "value_type": "string"},
    "ios-hide-safari-ui": {"path": ["settings", "client_safe", "ios_meta_tag_hide_safari_ui"], "value_type": "bool"},
    "ios-prevent-zoom": {"path": ["settings", "client_safe", "ios_meta_tag_prevent_zoom"], "value_type": "bool"},
    "google-geocode-key": {
        "path": ["settings", "secure", "general_keys", "google_geocode_key"],
        "value_type": "string",
        "sensitive": True,
    },
    "google-map-key": {"path": ["settings", "client_safe", "general_keys", "google_map_key"], "value_type": "string"},
    "advanced-timezone-controls": {"path": ["settings", "client_safe", "advanced_features", "timezone_controls"], "value_type": "bool"},
    "advanced-timezone-date-time-inputs": {"path": ["settings", "client_safe", "advanced_features", "timezone_controls_date_time_inputs"], "value_type": "bool"},
    "advanced-timezone-page": {"path": ["settings", "client_safe", "advanced_features", "timezone_controls_page"], "value_type": "bool"},
    "advanced-timezone-backend-workflows": {"path": ["settings", "client_safe", "advanced_features", "timezone_controls_backend_workflows"], "value_type": "bool"},
    "advanced-expose-id-option": {"path": ["settings", "client_safe", "advanced_features", "expose_id_option"], "value_type": "bool"},
    "advanced-show-parens": {"path": ["settings", "client_safe", "advanced_features", "parens"], "value_type": "bool"},
    "api-backend-workflows-enabled": {"path": ["settings", "client_safe", "exposes_wf_api"], "value_type": "bool"},
    "api-data-enabled": {"path": ["settings", "client_safe", "exposes_get_api"], "value_type": "bool"},
    "api-data-use-display-fields": {"path": ["settings", "client_safe", "use_captions_for_get"], "value_type": "bool"},
    "api-hide-swagger-docs": {"path": ["settings", "client_safe", "hide_swagger_api"], "value_type": "bool"},
    "workflow-max-depth-dev": {"path": ["settings", "client_safe", "max_recursive_workflow_depth_test"], "value_type": "auto"},
    "workflow-max-depth-live": {"path": ["settings", "client_safe", "max_recursive_workflow_depth_live"], "value_type": "auto"},
    "meta-title": {"path": ["settings", "client_safe", "facebook_meta_tag_title"], "value_type": "string"},
    "meta-site-name": {"path": ["settings", "client_safe", "facebook_meta_tag_site_name"], "value_type": "string"},
    "meta-description": {"path": ["settings", "client_safe", "facebook_meta_tag_description"], "value_type": "string"},
    "meta-thumbnail": {"path": ["settings", "client_safe", "facebook_meta_tag_image"], "value_type": "string"},
    "seo-expose-text-tags": {"path": ["settings", "client_safe", "expose_text_tags"], "value_type": "bool"},
    "seo-enable-canonical-url": {"path": ["settings", "client_safe", "enable_canonical_url"], "value_type": "bool"},
    "seo-customize-robots-txt-enabled": {"path": ["settings", "client_safe", "customize_robots_txt"], "value_type": "bool"},
    "seo-custom-robots-txt": {"path": ["settings", "client_safe", "custom_robot_txt"], "value_type": "string"},
    "seo-generate-sitemap": {"path": ["settings", "client_safe", "generate_sitemap"], "value_type": "bool"},
    "seo-sitemap-pages": {"path": ["settings", "client_safe", "sitemap_pages"], "value_type": "string"},
    "seo-header-meta-tags": {"path": ["settings", "client_safe", "custom_header_meta_tag_content"], "value_type": "string"},
    "seo-body-scripts": {"path": ["settings", "client_safe", "custom_header_meta_tag_body_content"], "value_type": "string"},
    "seo-allow-wildcard-redirects": {"path": ["settings", "client_safe", "allow_wildcards"], "value_type": "bool"},
    "app-primary-language": {"path": ["settings", "client_safe", "app_language"], "value_type": "string"},
    "user-language-field": {"path": ["settings", "client_safe", "language_field"], "value_type": "string"},
}


class SettingsLifecycleService:
    """Build, dispatch, and project settings without treating them as schema cache."""

    def __init__(self, host: SchemaLifecycleHost, references: SchemaReferenceResolver) -> None:
        self._host = host
        self._references = references

    def set_app_setting(self, path: Any, value: Any, value_type: str = "string", dry_run: bool = False) -> bool:
        return self._set_app_setting(path, value, value_type, dry_run, sensitive=None)

    def _set_app_setting(
        self, path: Any, value: Any, value_type: str, dry_run: bool, *, sensitive: bool | None
    ) -> bool:
        try:
            path_array = self._path(path)
            coerced_value = self._host.coerce_schema_setting_value(value, value_type=value_type)
        except ValueError as exc:
            self._host.log_schema_lifecycle_error(str(exc))
            return False
        payload = self._payload()
        self._change(payload, path_array, coerced_value)
        is_sensitive = self._is_sensitive_path(path_array) if sensitive is None else sensitive
        return self._commit(
            payload,
            dry_run,
            f"App setting '{'.'.join(path_array)}' updated.",
            [(path_array, coerced_value)],
            sensitive=is_sensitive,
        )

    def set_project_setting(self, setting_key: str, value: Any, value_type: str | None = None, dry_run: bool = False) -> bool:
        normalized_key = str(setting_key or "").strip().lower().replace("_", "-")
        spec = PROJECT_SETTING_ALIASES.get(normalized_key)
        if not spec:
            self._host.log_schema_lifecycle_error(
                f"Unknown project setting '{setting_key}'. Use 'list-project-settings' to inspect available aliases."
            )
            return False
        return self._set_app_setting(
            spec["path"],
            value,
            (value_type or spec["value_type"]).strip().lower(),
            dry_run,
            sensitive=spec.get("sensitive") is True,
        )

    def list_project_settings(self, as_json: bool = False) -> bool:
        rows = [
            {"alias": alias, "path": ".".join(spec["path"]), "value_type": spec["value_type"]}
            for alias, spec in sorted(PROJECT_SETTING_ALIASES.items())
        ]
        if as_json:
            print(json.dumps(rows, indent=2, ensure_ascii=False))
            return True
        print(f"📋 Project setting aliases ({len(rows)}):")
        for row in rows:
            print(f"- {row['alias']} ({row['value_type']}): {row['path']}")
        return True

    def list_301_redirects(self, as_json: bool = False) -> bool:
        rows = [
            {"key": key, "from": rule.get("%fr"), "to": rule.get("to")}
            for key, rule in sorted(self._references.redirects().items())
            if isinstance(rule, dict)
        ]
        if as_json:
            print(json.dumps(rows, indent=2, ensure_ascii=False))
            return True
        print(f"📋 301 redirects ({len(rows)}):")
        for row in rows:
            print(f"- {row['key']}: {row.get('from')} -> {row.get('to')}")
        return True

    def create_301_redirect(
        self, from_url: str, to_url: str, rule_key: str | None = None, id_counter: int | None = None, dry_run: bool = False
    ) -> bool:
        redirects = self._current_redirects_for_write()
        if redirects is None:
            return False
        source = str(from_url or "").strip()
        destination = str(to_url or "").strip()
        if not source or not destination:
            self._host.log_schema_lifecycle_error("301 redirect requires non-empty from_url and to_url.")
            return False
        resolved_key = str(rule_key or self._host.next_schema_redirect_key()).strip()
        if not resolved_key:
            self._host.log_schema_lifecycle_error("301 redirect rule key cannot be empty.")
            return False
        if resolved_key in redirects:
            self._host.log_schema_lifecycle_error(f"301 redirect '{resolved_key}' already exists in current discovery data.")
            return False
        if any(str(rule.get("%fr") or "").strip() == source for rule in redirects.values()):
            self._host.log_schema_lifecycle_error(f"301 redirect source '{source}' already exists in current discovery data.")
            return False
        try:
            parsed_counter = int(id_counter) if id_counter is not None else None
        except (TypeError, ValueError):
            self._host.log_schema_lifecycle_error("Invalid id_counter.")
            return False
        path = ["settings", "client_safe", "301_redirects", resolved_key]
        rule = {"%fr": source, "to": destination}
        payload = self._payload()
        self._change(payload, path, rule)
        if parsed_counter is not None:
            payload.add_change_raw({"type": "id_counter", "value": parsed_counter})
        ok = self._commit(payload, dry_run, f"301 redirect created ({resolved_key}).", [(path, rule)])
        if ok:
            self._host.log_schema_lifecycle_info(f"Redirect key: {resolved_key}")
        return ok

    def delete_301_redirect(self, rule_key: str, dry_run: bool = False) -> bool:
        redirects = self._current_redirects_for_write()
        if redirects is None:
            return False
        resolved_key = self._references.resolve_redirect(str(rule_key or ""), ref_kind="key")
        if not resolved_key or resolved_key not in redirects:
            self._host.log_schema_lifecycle_error(f"Could not resolve current 301 redirect '{rule_key}'.")
            return False
        path = ["settings", "client_safe", "301_redirects", resolved_key]
        payload = self._payload()
        self._change(payload, path, None)
        return self._commit(payload, dry_run, f"App setting '{'.'.join(path)}' updated.", [(path, None)])

    def _current_redirects_for_write(self) -> dict[str, dict[str, Any]] | None:
        discovery, _cache = self._host.schema_reference_snapshots()
        settings = discovery.get("settings") if isinstance(discovery, dict) else None
        if settings is None:
            return {}
        if not isinstance(settings, dict):
            self._host.log_schema_lifecycle_error("Could not resolve current 301 redirects: malformed settings metadata.")
            return None
        client_safe = settings.get("client_safe")
        if client_safe is None:
            return {}
        if not isinstance(client_safe, dict):
            self._host.log_schema_lifecycle_error("Could not resolve current 301 redirects: malformed client_safe metadata.")
            return None
        raw = client_safe.get("301_redirects")
        if raw is None:
            return {}
        if not isinstance(raw, dict):
            self._host.log_schema_lifecycle_error("Could not resolve current 301 redirects: malformed redirect metadata.")
            return None
        redirects: dict[str, dict[str, Any]] = {}
        for key, rule in raw.items():
            if not str(key).strip() or not isinstance(rule, dict):
                self._host.log_schema_lifecycle_error("Could not resolve current 301 redirects: malformed redirect metadata.")
                return None
            if rule.get("%del") is True:
                continue
            source = rule.get("%fr")
            target = rule.get("to")
            if not isinstance(source, str) or not source.strip() or not isinstance(target, str) or not target.strip():
                self._host.log_schema_lifecycle_error("Could not resolve current 301 redirects: malformed redirect metadata.")
                return None
            redirects[str(key)] = copy.deepcopy(rule)
        return redirects

    def _path(self, path: Any) -> list[str]:
        parsed = self._host.parse_schema_setting_path(path)
        if not parsed or any(not str(part).strip() for part in parsed):
            raise ValueError("Path cannot be empty.")
        return [str(part) for part in parsed]

    def _payload(self) -> PayloadBuilder:
        return cast(PayloadBuilder, self._host.new_schema_lifecycle_payload())

    def _change(self, payload: PayloadBuilder, path: list[str], body: Any) -> None:
        self._host.add_schema_lifecycle_change(payload, "ChangeAppSetting", path, body, intent_id=self._host.next_schema_setting_intent_id(), source_appname="")

    def _commit(
        self,
        payload: PayloadBuilder,
        dry_run: bool,
        message: str,
        updates: list[tuple[list[str], Any]],
        *,
        sensitive: bool = False,
    ) -> bool:
        if dry_run:
            self._host.preview_schema_lifecycle_payload(self._redacted_preview(payload, updates))
            return True
        try:
            if sensitive:
                self._host.dispatch_schema_lifecycle_payload(payload, sensitive=True)
            else:
                self._host.dispatch_schema_lifecycle_payload(payload)
        except Exception as exc:
            if sensitive:
                self._host.log_schema_lifecycle_error("Failed to send: Sensitive project setting write failed.")
            else:
                self._host.log_schema_lifecycle_error(f"Failed to send: {exc}")
            return False
        warning = self._host.project_schema_settings(updates)
        if warning:
            if sensitive:
                self._host.log_schema_lifecycle_error("Post-write sensitive setting cache update failed.")
            else:
                self._host.log_schema_lifecycle_error(warning)
        self._host.log_schema_lifecycle_success(message)
        return True

    def _redacted_preview(self, payload: PayloadBuilder, updates: list[tuple[list[str], Any]]) -> PayloadBuilder:
        if not any(self._is_sensitive_path(path) for path, _body in updates):
            return payload
        preview = copy.deepcopy(payload)
        for change in getattr(preview, "changes", []):
            if isinstance(change, dict) and self._is_sensitive_path(change.get("path_array", [])):
                change["body"] = "[REDACTED]"
        return cast(PayloadBuilder, preview)

    @staticmethod
    def _is_sensitive_path(path: Any) -> bool:
        if not isinstance(path, list):
            return False
        normalized = [str(part) for part in path]
        return any(spec.get("sensitive") is True and spec.get("path") == normalized for spec in PROJECT_SETTING_ALIASES.values())
