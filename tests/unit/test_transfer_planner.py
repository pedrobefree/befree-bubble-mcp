from bubble_mcp.context.models import BubbleContextEdge, BubbleContextNode, BubbleProjectContext
from bubble_mcp.context.source import save_context
from bubble_mcp.core.config import BubbleMcpSettings, BubbleProfile, save_settings
from bubble_mcp.transfer.planner import create_transfer_plan
from bubble_mcp.transfer.store import load_transfer_plan


def _source_context(*, include_api_connector: bool = False) -> BubbleProjectContext:
    element_metadata = {
        "bubble_id": "bHero",
        "path": ["%p3", "bSrcPage", "%el", "bHero"],
        "properties": {"%x": "Group", "%p": {"%nm": "gp_Hero"}},
        "data_type": "User",
    }
    metadata = {}
    if include_api_connector:
        element_metadata["api_connector_call"] = "stripe.create_customer"
        metadata = {
            "settings": {
                "client_safe": {
                    "apiconnector2": {
                        "stripe": {
                            "human": "Stripe",
                            "shared_headers": {"auth": {"key": "Authorization", "value": "Bearer sk-secret"}},
                            "calls": {
                                "create_customer": {
                                    "human": "Create customer",
                                    "method": "POST",
                                    "url": "https://api.stripe.com/v1/customers",
                                }
                            },
                        }
                    }
                }
            }
        }
    return BubbleProjectContext(
        app_id="source-app",
        source="test",
        nodes=[
            BubbleContextNode(id="page:index", label="index", type="page", metadata={"bubble_id": "bSrcPage"}),
            BubbleContextNode(
                id="element:bHero",
                label="gp_Hero",
                type="element",
                metadata=element_metadata,
            ),
            BubbleContextNode(
                id="datatype:user",
                label="User",
                type="data_type",
                metadata={
                    "bubble_id": "User",
                    "properties": {
                        "fields": {
                            "name_text": {"type": "text"},
                            "email_text": {"type": "text"},
                        }
                    },
                },
            ),
        ],
        edges=[BubbleContextEdge(source="page:index", target="element:bHero", type="contains")],
        metadata=metadata,
    )


def _target_context(include_user: bool = True) -> BubbleProjectContext:
    nodes = [
        BubbleContextNode(id="page:index", label="index", type="page", metadata={"bubble_id": "bTargetPage"}),
    ]
    if include_user:
        nodes.append(BubbleContextNode(id="datatype:user", label="User", type="data_type"))
    return BubbleProjectContext(app_id="target-app", source="test", nodes=nodes, edges=[])


def _settings(tmp_path, *, target_has_user: bool = True, source_has_api_connector: bool = False) -> None:  # type: ignore[no-untyped-def]
    source_path = tmp_path / "contexts" / "source" / "source-app-context.json"
    target_path = tmp_path / "contexts" / "target" / "target-app-context.json"
    save_context(_source_context(include_api_connector=source_has_api_connector), source_path)
    save_context(_target_context(include_user=target_has_user), target_path)
    save_settings(
        BubbleMcpSettings(
            config_dir=tmp_path,
            default_profile=None,
            profiles={
                "source": BubbleProfile(name="source", app_id="source-app", appname="source-app"),
                "target": BubbleProfile(name="target", app_id="target-app", appname="target-app"),
            },
        )
    )


def test_create_transfer_plan_saves_payloads_and_dependency_decisions(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    _settings(tmp_path)

    result = create_transfer_plan(
        source_profile="source",
        target_profile="target",
        source_type="element",
        source_ref="gp_Hero",
        target_context="index",
        target_parent="root",
        target_name="gp_Hero_Copy",
        dependency_policy="map_only",
    )

    assert result["ok"] is True
    assert result["blocked_reasons"] == []
    assert result["payload_count"] == 1
    plan = load_transfer_plan(result["transfer_id"])
    assert plan["target_profile"] == "target"
    assert plan["reuse_policy"] == "prefer_existing"
    assert plan["dependency_decisions"][0]["action"] == "map_existing"
    assert plan["write_payloads"][0]["changes"][0]["body"]["%p"]["%nm"] == "gp_Hero_Copy"


def test_create_transfer_plan_blocks_when_required_dependency_missing(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    _settings(tmp_path, target_has_user=False)

    result = create_transfer_plan(
        source_profile="source",
        target_profile="target",
        source_type="element",
        source_ref="gp_Hero",
        target_context="index",
        target_parent="root",
        dependency_policy="map_only",
    )

    assert result["ok"] is False
    assert "data_type:User" in result["blocked_reasons"][0]
    assert result["payload_count"] == 0


def test_create_transfer_plan_create_missing_collection_payloads_before_element(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    _settings(tmp_path, target_has_user=False)

    result = create_transfer_plan(
        source_profile="source",
        target_profile="target",
        source_type="element",
        source_ref="gp_Hero",
        target_context="index",
        target_parent="root",
        dependency_policy="map_or_create",
        collection_policy="create_missing",
    )

    assert result["ok"] is True
    assert result["payload_count"] == 4
    plan = load_transfer_plan(result["transfer_id"])
    paths = [payload["changes"][0]["path_array"] for payload in plan["write_payloads"]]
    assert paths[0] == ["data_types", "User"]
    assert {tuple(path) for path in paths[1:3]} == {
        ("data_types", "User", "fields", "name_text"),
        ("data_types", "User", "fields", "email_text"),
    }
    assert plan["write_payloads"][3]["changes"][0]["intent"]["name"] == "CreateElement"


def test_create_transfer_plan_compiles_api_connector_structure_before_elements(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    _settings(tmp_path, source_has_api_connector=True)

    result = create_transfer_plan(
        source_profile="source",
        target_profile="target",
        source_type="element",
        source_ref="gp_Hero",
        target_context="index",
        target_parent="root",
        dependency_policy="map_or_create",
        api_connector_policy="structure_only",
    )

    assert result["ok"] is True
    plan = load_transfer_plan(result["transfer_id"])
    assert plan["write_payloads"][0]["changes"][0]["path_array"] == ["settings", "client_safe", "apiconnector2", "stripe"]
    assert plan["write_payloads"][1]["changes"][0]["intent"]["name"] == "CreateApiCall"
    assert plan["write_payloads"][-1]["changes"][0]["intent"]["name"] == "CreateElement"


def test_create_transfer_plan_creates_page_shell_when_target_context_is_omitted(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("BUBBLE_MCP_CONFIG_DIR", str(tmp_path))
    _settings(tmp_path)

    result = create_transfer_plan(
        source_profile="source",
        target_profile="target",
        source_type="page",
        source_ref="index",
        target_parent="root",
        target_name="mcp-copy",
        dependency_policy="map_only",
    )

    assert result["ok"] is True
    plan = load_transfer_plan(result["transfer_id"])
    shell_payload = plan["write_payloads"][0]
    child_payload = plan["write_payloads"][1]
    shell_ref = shell_payload["changes"][1]["path_array"][1]
    assert shell_payload["changes"][1]["body"]["%x"] == "Page"
    assert child_payload["changes"][0]["path_array"][:2] == ["%p3", shell_ref]
    assert plan["target_context"] == shell_ref
