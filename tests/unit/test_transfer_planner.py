from bubble_mcp.context.models import BubbleContextEdge, BubbleContextNode, BubbleProjectContext
from bubble_mcp.context.source import save_context
from bubble_mcp.core.config import BubbleMcpSettings, BubbleProfile, save_settings
from bubble_mcp.transfer.planner import create_transfer_plan
from bubble_mcp.transfer.store import load_transfer_plan


def _source_context() -> BubbleProjectContext:
    return BubbleProjectContext(
        app_id="source-app",
        source="test",
        nodes=[
            BubbleContextNode(id="page:index", label="index", type="page", metadata={"bubble_id": "bSrcPage"}),
            BubbleContextNode(
                id="element:bHero",
                label="gp_Hero",
                type="element",
                metadata={
                    "bubble_id": "bHero",
                    "path": ["%p3", "bSrcPage", "%el", "bHero"],
                    "properties": {"%x": "Group", "%p": {"%nm": "gp_Hero"}},
                    "data_type": "User",
                },
            ),
        ],
        edges=[BubbleContextEdge(source="page:index", target="element:bHero", type="contains")],
    )


def _target_context(include_user: bool = True) -> BubbleProjectContext:
    nodes = [
        BubbleContextNode(id="page:index", label="index", type="page", metadata={"bubble_id": "bTargetPage"}),
    ]
    if include_user:
        nodes.append(BubbleContextNode(id="datatype:user", label="User", type="data_type"))
    return BubbleProjectContext(app_id="target-app", source="test", nodes=nodes, edges=[])


def _settings(tmp_path, *, target_has_user: bool = True) -> None:  # type: ignore[no-untyped-def]
    source_path = tmp_path / "contexts" / "source" / "source-app-context.json"
    target_path = tmp_path / "contexts" / "target" / "target-app-context.json"
    save_context(_source_context(), source_path)
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
