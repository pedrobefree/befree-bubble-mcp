from __future__ import annotations

import copy
import json
import time
from pathlib import Path

import pytest

from bubble_mcp.aria_runtime.bubble_cli import BubbleCLI, PayloadBuilder
from bubble_mcp.aria_runtime.schema_lifecycle.options import OptionLifecycleService
from bubble_mcp.aria_dispatch import _method_kwargs
from bubble_mcp.server.schemas import list_tool_schemas


@pytest.fixture
def cli(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> BubbleCLI:
    app_path = tmp_path / "app.json"
    app_path.write_text(
        json.dumps(
            {
                "option_sets": {
                    "os_status": {
                        "%d": "OS:status",
                        "attributes": {"color": {"%d": "Color", "%v": "text", "plugin": {"keep": True}}},
                        "values": {
                            "open": {"%d": "Open", "db_value": "open", "sort_factor": 1, "plugin": {"keep": True}},
                            "closed": {"%d": "Closed", "db_value": "closed", "sort_factor": 2},
                            "plugin_owned": {"%d": "Plugin", "db_value": "plugin", "sort_factor": 3, "opaque": [1, 2]},
                        },
                        "plugin_owned": {"keep": True},
                    },
                    "os_duplicate": {"%d": "OS:Duplicate", "values": {"one": {"%d": "Same"}, "two": {"%d": "Same"}}},
                }
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("BUBBLE_CLI_CACHE_PATH", str(tmp_path / "cache.json"))
    return BubbleCLI(app_json_path=str(app_path), appname="schema-options")


def _payload(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    preview = capsys.readouterr().out.split("Payload preview:\n", 1)[1]
    return json.JSONDecoder().raw_decode(preview)[0]


@pytest.mark.parametrize(
    ("operation", "paths", "bodies"),
    [
        (lambda instance: instance.create_option_set("Status", dry_run=True), [["option_sets", "os_status"]], [{"%d": "OS:status", "creation_source": "editor"}]),
        (lambda instance: instance.rename_option_set("OS:status", "Status 2", dry_run=True), [["option_sets", "os_status", "%d"]], ["OS:status_2"]),
        (lambda instance: instance.delete_option_set("OS:status", dry_run=True), [["option_sets", "os_status", "%del"]], [True]),
        (lambda instance: instance.create_option_attribute("OS:status", "Size", "number", dry_run=True), [["option_sets", "os_status", "attributes", "size"]], [{"%d": "Size", "%v": "number", "creation_source": "editor"}]),
        (lambda instance: instance.create_option_value("OS:status", "Pending", value_key="pending", db_value="pending", sort_factor=4, dry_run=True), [["option_sets", "os_status", "values", "pending", "%d"], ["option_sets", "os_status", "values", "pending", "db_value"], ["option_sets", "os_status", "values", "pending", "sort_factor"]], ["Pending", "pending", 4]),
        (lambda instance: instance.delete_option_value("OS:status", "open", ref_kind="label", dry_run=True), [["option_sets", "os_status", "values", "open", "%del"]], [True]),
        (lambda instance: instance.rename_option_value("OS:status", "open", "Opened", ref_kind="db_value", dry_run=True), [["option_sets", "os_status", "values", "open", "%d"]], ["Opened"]),
        (lambda instance: instance.set_option_value_attribute("OS:status", "open", "color", '{"tone":"blue"}', parse_json=True, dry_run=True), [["option_sets", "os_status", "values", "open", "color"]], [{"tone": "blue"}]),
        (lambda instance: instance.reorder_option_values("OS:status", ["open:3", "closed:2", "plugin_owned:1"], dry_run=True), [["option_sets", "os_status", "values", "open", "sort_factor"], ["option_sets", "os_status", "values", "closed", "sort_factor"], ["option_sets", "os_status", "values", "plugin_owned", "sort_factor"]], [3, 2, 1]),
    ],
)
def test_option_lifecycle_preserves_golden_payload_paths_and_order(
    cli: BubbleCLI, capsys: pytest.CaptureFixture[str], operation: object, paths: list[list[str]], bodies: list[object]
) -> None:
    assert operation(cli) is True  # type: ignore[operator]
    payload = _payload(capsys)
    changes = payload["changes"]  # type: ignore[index]
    assert [change["path_array"] for change in changes] == paths  # type: ignore[index]
    assert [change["body"] for change in changes] == bodies  # type: ignore[index]


def test_option_writes_use_current_only_alias_resolution_and_fail_closed_before_payload(cli: BubbleCLI, monkeypatch: pytest.MonkeyPatch) -> None:
    cli._schema_option_sets_cache()["os_cached"] = {"%d": "OS:Cached", "values": {"old": {"%d": "Old"}}}
    cli._invalidate_schema_reference_index("option_sets")
    monkeypatch.setattr("bubble_mcp.aria_runtime.schema_lifecycle.options.PayloadBuilder", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("payload built")))
    assert cli.rename_option_set("OS:Cached", "Nope", dry_run=True) is False
    assert cli.delete_option_value("os_duplicate", "Same", ref_kind="label", dry_run=True) is False


def test_option_success_projects_only_the_set_and_permits_sequential_writes_without_refresh(cli: BubbleCLI, monkeypatch: pytest.MonkeyPatch) -> None:
    before_other = copy.deepcopy(cli.discovery.data["option_sets"]["os_duplicate"])
    revision = cli.schema_reference_revision()
    saves = 0
    monkeypatch.setattr(PayloadBuilder, "send_to_webhook", lambda _payload, _url: None)
    original_save = cli._save_cli_cache

    def count_save() -> None:
        nonlocal saves
        saves += 1
        original_save()

    monkeypatch.setattr(cli, "_save_cli_cache", count_save)
    assert cli.create_option_value("os_status", "Pending", value_key="pending", db_value="pending")
    assert cli.rename_option_value("os_status", "pending", "Queued")
    assert cli.discovery.data["option_sets"]["os_status"]["values"]["pending"]["%d"] == "Queued"
    assert cli.discovery.data["option_sets"]["os_status"]["plugin_owned"] == {"keep": True}
    assert cli.discovery.data["option_sets"]["os_status"]["values"]["open"]["plugin"] == {"keep": True}
    assert cli.discovery.data["option_sets"]["os_duplicate"] == before_other
    assert cli.schema_reference_revision() == revision + 2
    assert saves == 2


def test_option_dry_run_and_dispatch_failure_have_zero_projected_state_or_cache_writes(
    cli: BubbleCLI, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    before = copy.deepcopy(cli.discovery.data)
    revision = cli.schema_reference_revision()
    saves = 0

    def count_save() -> None:
        nonlocal saves
        saves += 1

    monkeypatch.setattr(cli, "_save_cli_cache", count_save)
    assert cli.rename_option_value("os_status", "open", "Opened", dry_run=True)
    first = capsys.readouterr().out
    assert cli.rename_option_value("os_status", "open", "Opened", dry_run=True)
    assert capsys.readouterr().out == first
    monkeypatch.setattr(PayloadBuilder, "send_to_webhook", lambda _payload, _url: (_ for _ in ()).throw(RuntimeError("offline")))
    assert cli.rename_option_value("os_status", "open", "Opened") is False
    assert cli.discovery.data == before
    assert cli.schema_reference_revision() == revision
    assert saves == 0


@pytest.mark.parametrize(
    "assignments",
    [
        ["open:1", "open:2", "plugin_owned:3"],
        ["open:1", "closed:2"],
        ["open:1", "closed:1", "plugin_owned:3"],
        ["open:4", "closed:2", "plugin_owned:1"],
        ["unknown:1", "closed:2", "plugin_owned:3"],
    ],
)
def test_reorder_rejects_non_permutations_before_builder_or_projection(
    cli: BubbleCLI, monkeypatch: pytest.MonkeyPatch, assignments: list[str]
) -> None:
    before = copy.deepcopy(cli.discovery.data)
    monkeypatch.setattr("bubble_mcp.aria_runtime.schema_lifecycle.options.PayloadBuilder", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("payload built")))
    assert cli.reorder_option_values("os_status", assignments, dry_run=True) is False
    assert cli.discovery.data == before


def test_reorder_500_values_is_deterministic_and_persists_once(cli: BubbleCLI, monkeypatch: pytest.MonkeyPatch) -> None:
    values = {f"v{index:03d}": {"%d": f"Value {index}", "sort_factor": index + 1} for index in range(500)}
    cli.discovery.data["option_sets"]["os_status"]["values"] = values
    cli._invalidate_schema_reference_index("option_sets")
    calls = 0
    monkeypatch.setattr(PayloadBuilder, "send_to_webhook", lambda _payload, _url: None)
    original_save = cli._save_cli_cache

    def count_save() -> None:
        nonlocal calls
        calls += 1
        original_save()

    monkeypatch.setattr(cli, "_save_cli_cache", count_save)
    assignments = [f"v{index:03d}:{500 - index}" for index in range(500)]
    started = time.perf_counter()
    assert cli.reorder_option_values("os_status", assignments)
    elapsed = time.perf_counter() - started
    assert elapsed < 5
    assert calls == 1
    assert cli.discovery.data["option_sets"]["os_status"]["values"]["v000"]["sort_factor"] == 500


def test_option_mcp_schemas_and_runtime_arguments_preserve_each_conditional_signature() -> None:
    tools = {tool["name"]: tool for tool in list_tool_schemas()}
    expected_required = {
        "create_option_set": ["profile", "name"],
        "rename_option_set": ["profile", "option_set_ref", "new_name"],
        "delete_option_set": ["profile", "option_set_ref"],
        "create_option_attribute": ["profile", "option_set_ref", "name", "type"],
        "create_option_value": ["profile", "option_set_ref", "name"],
        "delete_option_value": ["profile", "option_set_ref", "option_value_ref"],
        "rename_option_value": ["profile", "option_set_ref", "option_value_ref", "new_name"],
        "set_option_value_attribute": ["profile", "option_set_ref", "option_value_ref", "name", "value"],
        "reorder_option_values": ["profile", "option_set_ref", "order"],
        "list_option_values": ["profile", "option_set_ref"],
    }
    for name, required in expected_required.items():
        schema = tools[name]["inputSchema"]
        assert schema["required"] == required
        assert schema["properties"]["dry_run"]["default"] is True

    method = getattr(BubbleCLI, "set_option_value_attribute")
    assert _method_kwargs(
        method,
        {"option_set_ref": "os_status", "option_value_ref": "open", "name": "color", "value": "blue", "execute": False},
        execute=False,
    ) == {"option_set_key": "os_status", "value_ref": "open", "attribute_key": "color", "value": "blue", "dry_run": True}
    method = getattr(BubbleCLI, "reorder_option_values")
    assert _method_kwargs(method, {"option_set_ref": "os_status", "order": ["open:1"], "execute": False}, execute=False) == {
        "option_set_key": "os_status", "assignments": ["open:1"], "dry_run": True
    }


@pytest.mark.parametrize(
    "operation",
    [
        lambda instance: instance.delete_option_set("missing", dry_run=True),
        lambda instance: instance.create_option_attribute("missing", "Size", "number", dry_run=True),
        lambda instance: instance.create_option_value("missing", "Queued", dry_run=True),
        lambda instance: instance.delete_option_value("missing", "open", dry_run=True),
        lambda instance: instance.rename_option_value("missing", "open", "Opened", dry_run=True),
        lambda instance: instance.set_option_value_attribute("missing", "open", "color", "blue", dry_run=True),
        lambda instance: instance.reorder_option_values("missing", ["open:1"], dry_run=True),
    ],
)
def test_option_write_operations_reject_missing_current_set_before_payload(
    cli: BubbleCLI, monkeypatch: pytest.MonkeyPatch, operation: object
) -> None:
    monkeypatch.setattr("bubble_mcp.aria_runtime.schema_lifecycle.options.PayloadBuilder", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("payload built")))
    assert operation(cli) is False  # type: ignore[operator]


def test_option_value_create_preserves_existing_data_and_covers_safe_patch_variants(
    cli: BubbleCLI, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.create_option_value("os_status", "Reopened", value_key="open", id_counter=9, dry_run=True)
    existing_payload = _payload(capsys)
    assert existing_payload["changes"][0]["body"]["plugin"] == {"keep": True}  # type: ignore[index]
    assert {key: existing_payload["changes"][-1][key] for key in ("type", "value")} == {"type": "id_counter", "value": 9}  # type: ignore[index]
    assert cli.create_option_value("os_status", "Future", value_key="future", dry_run=True)
    safe_payload = _payload(capsys)
    assert [change["path_array"][-1] for change in safe_payload["changes"]] == ["%d"]  # type: ignore[index]


@pytest.mark.parametrize("assignments", [[], ["open"], ["open:not-a-number", "closed:2", "plugin_owned:3"]])
def test_reorder_rejects_empty_and_malformed_assignments_before_builder(
    cli: BubbleCLI, monkeypatch: pytest.MonkeyPatch, assignments: list[str]
) -> None:
    monkeypatch.setattr("bubble_mcp.aria_runtime.schema_lifecycle.options.PayloadBuilder", lambda **_kwargs: (_ for _ in ()).throw(AssertionError("payload built")))
    assert cli.reorder_option_values("os_status", assignments, dry_run=True) is False


def test_reorder_accepts_equals_delimiter_and_list_reads_remain_cache_assisted(
    cli: BubbleCLI, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.reorder_option_values("os_status", ["open=1", "closed=2", "plugin_owned=3"], dry_run=True)
    capsys.readouterr()
    assert cli.list_option_values("os_status", as_json=True)
    assert json.loads(capsys.readouterr().out)[0]["key"] == "open"
    cli.discovery._data = {"option_sets": {}}  # type: ignore[assignment]
    cli._schema_option_sets_cache()["os_cached"] = {"%d": "OS:Cached", "values": {}}
    cli._invalidate_schema_reference_index("option_sets")
    assert cli.list_option_values("os_cached")
    assert cli.list_option_values("missing") is False
    cli.discovery._data = {"option_sets": {"os_status": {"%d": "OS:status", "values": {"open": {"%d": "Open", "sort_factor": "1"}}}}}  # type: ignore[assignment]
    cli._invalidate_schema_reference_index("option_sets")
    assert cli.list_option_values("os_status")


def test_empty_option_value_list_keeps_legacy_info_log_level(
    cli: BubbleCLI, monkeypatch: pytest.MonkeyPatch
) -> None:
    infos: list[str] = []
    successes: list[str] = []
    cli.discovery.data["option_sets"]["os_status"]["values"] = {}
    cli._invalidate_schema_reference_index("option_sets")
    monkeypatch.setattr("bubble_mcp.aria_runtime.bubble_cli.logger.info", infos.append)
    monkeypatch.setattr("bubble_mcp.aria_runtime.bubble_cli.logger.success", successes.append)

    assert cli.list_option_values("os_status") is True
    assert infos == ["No values found for option set 'os_status'."]
    assert successes == []


def test_option_helpers_cover_malformed_current_data_and_sort_fallbacks(cli: BubbleCLI) -> None:
    assert OptionLifecycleService._sort_weight("2") == 2
    assert OptionLifecycleService._sort_weight(object()) == 10**9
    cli.discovery._data = {}  # type: ignore[assignment]
    cli._invalidate_schema_reference_index("option_sets")
    assert cli.create_option_attribute("os_status", "Size", "number", dry_run=True) is False


def test_option_dispatch_warning_logs_after_successful_atomic_projection(cli: BubbleCLI, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(PayloadBuilder, "send_to_webhook", lambda _payload, _url: None)
    monkeypatch.setattr(cli, "project_schema_option_set", lambda _key, _entry: "cache warning")
    assert cli.rename_option_set("os_status", "Status")


def test_option_value_default_dry_run_preview_is_byte_stable_and_collision_safe(
    cli: BubbleCLI, capsys: pytest.CaptureFixture[str]
) -> None:
    cli.discovery.data["option_sets"]["os_status"]["values"]["bpreview"] = {"%d": "Reserved"}
    cli._invalidate_schema_reference_index("option_sets")
    assert cli.create_option_value("os_status", "Pending", dry_run=True)
    first = capsys.readouterr().out
    assert cli.create_option_value("os_status", "Pending", dry_run=True)
    second = capsys.readouterr().out
    assert second == first
    assert '"bpreview_2"' in first


@pytest.mark.parametrize("dry_run", [True, False])
def test_option_value_logs_legacy_option_key_at_info_level_after_every_success(
    cli: BubbleCLI, monkeypatch: pytest.MonkeyPatch, dry_run: bool
) -> None:
    infos: list[str] = []
    monkeypatch.setattr("bubble_mcp.aria_runtime.bubble_cli.logger.info", infos.append)
    if not dry_run:
        monkeypatch.setattr(PayloadBuilder, "send_to_webhook", lambda _payload, _url: None)
    assert cli.create_option_value("os_status", "Pending", value_key="pending", dry_run=dry_run)
    assert infos == ["Option key: pending"]


def test_option_attribute_and_reorder_keep_literal_legacy_resolution_errors(
    cli: BubbleCLI, capsys: pytest.CaptureFixture[str]
) -> None:
    assert cli.set_option_value_attribute("os_status", "missing", "color", "blue", ref_kind="label", dry_run=True) is False
    assert capsys.readouterr().out == "❌ Could not resolve option value 'missing' in 'os_status' by label.\n"
    assert cli.reorder_option_values("os_status", ["missing:1", "open:2", "closed:3"], ref_kind="label", dry_run=True) is False
    assert capsys.readouterr().out == "❌ Could not resolve option value 'missing' in 'os_status' by label.\n"
