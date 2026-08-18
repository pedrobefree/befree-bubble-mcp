from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from bubble_mcp.aria_runtime.schema_lifecycle.references import SchemaReferenceResolver


@dataclass
class ReferenceHost:
    discovery: dict[str, Any] = field(default_factory=dict)
    cache: dict[str, Any] = field(
        default_factory=lambda: {"schema": {"profiles": {"default": {"user_types": {}, "option_sets": {}}}}}
    )
    module_dir: Path | None = None
    revision: int = 0

    def schema_reference_snapshots(self) -> tuple[dict[str, Any], dict[str, Any]]:
        return self.discovery, self.cache

    def schema_reference_revision(self) -> int:
        return self.revision

    def schema_reference_modules_dir(self) -> str | None:
        return str(self.module_dir) if self.module_dir else None

    @staticmethod
    def schema_reference_profile_key() -> str:
        return "default"

    @staticmethod
    def normalize_schema_reference(value: Any) -> str:
        return " ".join(str(value or "").strip().lower().split())

    @staticmethod
    def slugify_schema_reference(value: str) -> str:
        return "_".join(ReferenceHost.normalize_schema_reference(value).replace("-", " ").split())


def test_current_snapshot_wins_over_modules_and_cache_and_is_detached(tmp_path: Path) -> None:
    modules = tmp_path / "modules"
    (modules / "user_types").mkdir(parents=True)
    (modules / "option_sets").mkdir()
    (modules / "user_types" / "__index.json").write_text(json.dumps({"account": "Module Account", "module_only": "Module Only"}))
    (modules / "option_sets" / "__index.json").write_text(json.dumps({"os_status": "Module status"}))
    (modules / "option_sets" / "os_status.json").write_text(
        json.dumps({"values": {"module_active": {"display": "Module active"}}})
    )
    host = ReferenceHost(
        discovery={
            "user_types": {
                "account": {"%d": "Live Account", "%f3": {"email_text": {"%d": "Email"}}},
                "deleted": {"%d": "Deleted", "%del": True},
                "broken": "not a mapping",
            },
            "option_sets": {
                "os_status": {"%d": "Live status", "values": {"live_active": {"%d": "Active"}}},
                "deleted_set": {"%d": "Deleted", "%del": True},
            },
        },
        cache={
            "schema": {
                "profiles": {
                    "default": {
                        "user_types": {"account": {"%d": "Cached Account"}, "cached_only": {"%d": "Cached Only"}},
                        "option_sets": {"os_status": {"%d": "Cached status"}, "os_cached": {"%d": "Cached"}},
                    }
                }
            }
        },
        module_dir=modules,
    )
    resolver = SchemaReferenceResolver(host)

    types = resolver.user_types(include_cache=True)
    option_sets = resolver.option_sets(include_cache=True)
    values = resolver.option_values("os_status", include_cache=False)

    assert types["account"]["%d"] == "Live Account"
    assert types["module_only"]["%d"] == "Module Only"
    assert types["cached_only"]["%d"] == "Cached Only"
    assert "deleted" not in types and "broken" not in types
    assert option_sets["os_status"]["%d"] == "Live status"
    assert option_sets["os_cached"]["%d"] == "Cached"
    assert "deleted_set" not in option_sets
    assert values == {"live_active": {"%d": "Active"}}

    types["account"]["%d"] = "caller mutation"
    assert resolver.user_types(include_cache=True)["account"]["%d"] == "Live Account"


def test_current_only_resolutions_reject_cache_only_references_while_reads_can_use_cache() -> None:
    host = ReferenceHost(
        discovery={"user_types": {"live": {"%d": "Live", "%f3": {"live_text": {"%d": "Live field"}}}}},
        cache={
            "schema": {
                "profiles": {
                    "default": {
                        "user_types": {
                            "cached": {"%d": "Cached", "%f3": {"cached_text": {"%d": "Cached field"}}}
                        },
                        "option_sets": {"os_cached": {"%d": "Cached", "values": {"old": {"%d": "Old"}}}},
                    }
                }
            }
        },
    )
    resolver = SchemaReferenceResolver(host)

    assert resolver.resolve_data_type("cached", include_cache=True) == "cached"
    assert resolver.resolve_data_type("cached", include_cache=False) is None
    assert resolver.resolve_data_field("cached", "cached field", include_cache=True) == "cached_text"
    assert resolver.resolve_data_field("cached", "cached field", include_cache=False) is None
    assert resolver.resolve_option_set("os_cached", include_cache=True) == "os_cached"
    assert resolver.resolve_option_set("os_cached", include_cache=False) is None
    assert resolver.resolve_option_value("os_cached", "old", include_cache=True) == "old"
    assert resolver.resolve_option_value("os_cached", "old", include_cache=False) is None


def test_resolvers_choose_exact_key_then_normalized_label_then_unique_substring_and_fail_closed() -> None:
    resolver = SchemaReferenceResolver(
        ReferenceHost(
            discovery={
                "user_types": {
                    "customer": {"%d": "Client record", "%f3": {"customer_email": {"%d": "Email Address"}}},
                    "client_record": {"%d": "Customer", "%f3": {"client_email": {"%d": "Email"}}},
                    "prospect": {"%d": "Client profile", "%f3": {"prospect_email": {"%d": "Email"}}},
                },
                "option_sets": {
                    "os_customer": {"%d": "OS:Customer", "values": {"yes": {"%d": "Approved"}}},
                    "os_prospect": {"%d": "OS:Prospect", "values": {"no": {"%d": "Approved"}}},
                },
                "settings": {"client_safe": {"301_redirects": {"redirect_customer": {"%fr": "/customer"}}}},
            }
        )
    )

    assert resolver.resolve_data_type("customer") == "customer"
    assert resolver.resolve_data_type("client record", ref_kind="label") == "customer"
    assert resolver.resolve_data_type("client record", ref_kind="label") == "customer"
    assert resolver.resolve_data_type("client") is None
    assert resolver.resolve_data_field("customer", "email-address") == "customer_email"
    assert resolver.resolve_data_field("customer", "email") == "customer_email"
    assert resolver.resolve_option_set("customer") == "os_customer"
    assert resolver.resolve_option_value("os_customer", "yes") == "yes"
    assert resolver.resolve_option_value("os_customer", "approved", ref_kind="label") == "yes"
    assert resolver.resolve_redirect("redirect_customer") == "redirect_customer"
    assert resolver.resolve_redirect("/customer", ref_kind="label") == "redirect_customer"


def test_revision_and_explicit_invalidation_rebuild_only_after_successful_state_change() -> None:
    host = ReferenceHost(discovery={"user_types": {"old": {"%d": "Account"}}})
    resolver = SchemaReferenceResolver(host)

    assert resolver.resolve_data_type("Account") == "old"
    host.discovery["user_types"]["new"] = {"%d": "Account"}
    assert resolver.resolve_data_type("Account") == "old"

    host.revision += 1
    assert resolver.resolve_data_type("Account") is None
    host.discovery["user_types"].pop("new")
    resolver.invalidate("user_types")
    assert resolver.resolve_data_type("Account") == "old"


def test_reference_boundary_rejects_empty_malformed_and_ambiguous_inputs_without_fallback() -> None:
    resolver = SchemaReferenceResolver(
        ReferenceHost(
            discovery={
                "user_types": {
                    "user": {"%d": "User", "%f3": "malformed"},
                    "hyphen-key": {"%d": "Duplicate"},
                    "hyphen_key": {"%d": "Duplicate"},
                    "empty_fields": {"%d": "Empty fields", "%f3": {}},
                },
                "option_sets": {
                    "os_empty": {"%d": "OS:Empty"},
                    "os_values": {
                        "%d": "OS:Values",
                        "values": {
                            "one": {"%d": "One", "db_value": "one-db"},
                            "two": {"%d": "Two", "db_value": "two-db"},
                        },
                    },
                },
                "settings": "malformed",
            },
            cache="malformed",  # type: ignore[arg-type]
        )
    )

    assert resolver.resolve_data_type("") is None
    assert resolver.resolve_data_type("current user") == "user"
    assert resolver.resolve_data_type("duplicate", ref_kind="label") is None
    assert resolver.resolve_data_type("hyphen key") is None
    assert resolver.resolve_data_type("user", ref_kind="unsupported") is None
    assert resolver.resolve_data_field("missing", "field") is None
    assert resolver.resolve_data_field("user", "field") is None
    assert resolver.resolve_option_set("") is None
    assert resolver.resolve_option_value("os_empty", "one") is None
    assert resolver.resolve_option_value("missing", "one") is None
    assert resolver.resolve_option_value("os_values", "", ref_kind="label") is None
    assert resolver.resolve_option_value("os_values", "one-db", ref_kind="db_value") == "one"
    assert resolver.option_values("missing") is None
    assert resolver.redirects() == {}
    assert resolver.data_type_result("missing") is None
    assert resolver.data_type_result("user", include_cache=False).source == "current"  # type: ignore[union-attr]
    assert resolver.resolve_option_set("os:") is None
    assert resolver.resolve_option_set("os_") is None


def test_modules_and_cache_profiles_ignore_invalid_payloads_and_preserve_unique_aliases(tmp_path: Path) -> None:
    modules = tmp_path / "modules"
    (modules / "user_types").mkdir(parents=True)
    (modules / "option_sets").mkdir()
    (modules / "user_types" / "__index.json").write_text("[]")
    (modules / "option_sets" / "__index.json").write_text(json.dumps({"os_flags": "OS:Flags", "": "skip"}))
    (modules / "option_sets" / "os_flags.json").write_text(
        json.dumps({"values": {"flag": {"display": "Flag"}}})
    )
    host = ReferenceHost(
        discovery={},
        cache={
            "schema": {
                "profiles": {
                    "other": {"user_types": {"cached": {"%d": "Cached"}}, "option_sets": {}},
                }
            }
        },
        module_dir=modules,
    )
    resolver = SchemaReferenceResolver(host)

    assert resolver.user_types(include_cache=True) == {"cached": {"%d": "Cached"}}
    assert resolver.resolve_option_set("option.os_flags") == "os_flags"
    assert resolver.resolve_option_set("OS:flags") == "os_flags"
    assert resolver.resolve_option_set("os_FLAGS") == "os_flags"
    assert resolver.option_values("os_flags") == {"flag": {"display": "Flag", "%d": "Flag"}}


def test_cache_result_and_missing_profiles_do_not_cross_reference_boundaries() -> None:
    resolver = SchemaReferenceResolver(
        ReferenceHost(
            discovery="malformed",  # type: ignore[arg-type]
            cache={
                "schema": {
                    "profiles": {
                        "first": {"user_types": {"first": {"%d": "First"}}, "option_sets": {}},
                        "second": {"user_types": {"second": {"%d": "Second"}}, "option_sets": {}},
                    }
                }
            },
        )
    )
    assert resolver.user_types(include_cache=True) == {}
    assert resolver.redirects() == {}

    cached = SchemaReferenceResolver(
        ReferenceHost(
            cache={
                "schema": {
                    "profiles": {"default": {"user_types": {"cached": {"%d": "Cached"}}, "option_sets": {}}}
                }
            }
        )
    )
    assert cached.data_type_result("cached").source == "cache"  # type: ignore[union-attr]
