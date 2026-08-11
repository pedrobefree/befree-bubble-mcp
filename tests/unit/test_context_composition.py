from bubble_mcp.context.composition import COMPLETE, merge_project_contexts, with_provenance
from bubble_mcp.context.models import BubbleContextEdge, BubbleContextNode, BubbleProjectContext


def test_console_primary_preserves_schema_and_accepts_crawler_topology() -> None:
    console = BubbleProjectContext(
        app_id="synthetic-app",
        source="consolelog_file",
        nodes=[
            BubbleContextNode(
                id="page:index",
                label="index",
                type="page",
                metadata={
                    "bubble_id": "pgIndex",
                    "children": [],
                    "properties": {"rich_console_value": "keep"},
                },
            ),
            BubbleContextNode(
                id="datatype:user",
                label="User",
                type="data_type",
                metadata={"bubble_id": "user", "properties": {"email": "text"}},
            ),
        ],
        edges=[],
        metadata={"styles": {"Button": {"font": "Inter"}}},
    )
    crawler = BubbleProjectContext(
        app_id="synthetic-app",
        source="editor_crawler",
        nodes=[
            BubbleContextNode(
                id="page:index",
                label="index",
                type="page",
                metadata={
                    "bubble_id": "pgIndex",
                    "children": ["elTitle"],
                    "path_array": ["%p3", "pgIndex"],
                    "properties": {},
                },
            ),
            BubbleContextNode(
                id="element:elTitle",
                label="Title",
                type="element",
                metadata={"bubble_id": "elTitle", "context": "page:index"},
            ),
        ],
        edges=[BubbleContextEdge(source="page:index", target="element:elTitle", type="contains")],
        metadata={},
    )

    merged = merge_project_contexts(
        console,
        crawler,
        source="consolelog_file+editor_crawler",
        complement_is_topology=True,
    )
    merged = with_provenance(
        merged,
        primary_source="consolelog_file",
        sources=["consolelog_file", "editor_crawler"],
        completeness=COMPLETE,
        bubble_export_available=False,
    )

    page = next(node for node in merged.nodes if node.id == "page:index")
    assert page.metadata["children"] == ["elTitle"]
    assert page.metadata["properties"] == {"rich_console_value": "keep"}
    assert any(node.id == "datatype:user" for node in merged.nodes)
    assert any(node.id == "element:elTitle" for node in merged.nodes)
    assert merged.metadata["styles"] == {"Button": {"font": "Inter"}}
    assert merged.metadata["provenance"] == {
        "primary_source": "consolelog_file",
        "sources": ["consolelog_file", "editor_crawler"],
        "completeness": "complete",
        "bubble_export_available": False,
    }


def test_bubble_primary_is_not_overwritten_by_console_complement() -> None:
    bubble = BubbleProjectContext(
        app_id="synthetic-app",
        source="bubble_file",
        nodes=[
            BubbleContextNode(
                id="datatype:user",
                label="User",
                type="data_type",
                metadata={"bubble_id": "user", "properties": {"role": "bubble"}},
            )
        ],
        edges=[],
        metadata={"styles": {"Button": {"font": "Bubble Font"}}},
    )
    console = BubbleProjectContext(
        app_id="synthetic-app",
        source="consolelog_file",
        nodes=[
            BubbleContextNode(
                id="datatype:user",
                label="User from console",
                type="data_type",
                metadata={"bubble_id": "user", "properties": {"role": "console", "extra": "fill"}},
            )
        ],
        edges=[],
        metadata={"styles": {"Button": {"font": "Console Font", "size": 16}}},
    )

    merged = merge_project_contexts(bubble, console, source="bubble_file+consolelog_file")

    user = next(node for node in merged.nodes if node.id == "datatype:user")
    assert user.label == "User"
    assert user.metadata["properties"] == {"role": "bubble", "extra": "fill"}
    assert merged.metadata["styles"] == {"Button": {"font": "Bubble Font", "size": 16}}
