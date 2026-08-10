"""Import Bubble project artifacts into compact context graphs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from bubble_mcp.context.models import BubbleContextEdge, BubbleContextNode, BubbleProjectContext


def _obj(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _label(record: dict[str, Any], fallback: str) -> str:
    props = _obj(record.get("%p") or record.get("properties"))
    return str(
        record.get("display")
        or props.get("display")
        or props.get("%nm")
        or props.get("name")
        or record.get("name")
        or record.get("%nm")
        or record.get("%d")
        or record.get("label")
        or fallback
    )


def _element_type(record: dict[str, Any]) -> str:
    props = _obj(record.get("%p") or record.get("properties"))
    return str(record.get("%x") or record.get("type") or props.get("%x") or "element")


def _element_children(record: dict[str, Any]) -> list[str]:
    return [str(key) for key in _obj(record.get("%el") or record.get("elements")).keys()]


def _root_id(record: dict[str, Any]) -> str | None:
    props = _obj(record.get("%p") or record.get("properties"))
    value = record.get("rootId") or record.get("root_id") or record.get("id") or props.get("id")
    return str(value).strip() or None


def _deleted_value(record: dict[str, Any]) -> bool | None:
    props = _obj(record.get("%p") or record.get("properties"))
    for container in (record, props):
        for key in ("deleted", "%del"):
            if key not in container:
                continue
            value = container[key]
            if isinstance(value, str):
                return value.strip().lower() == "true"
            return bool(value)
    return None


def _encoded_path_to_array(path: str) -> list[str]:
    return [part for part in str(path or "").split(".") if part]


def _reusable_name_by_id(app: dict[str, Any]) -> dict[str, str]:
    raw_index = _obj(_obj(app.get("_index")).get("custom_name_to_id"))
    names: dict[str, str] = {}
    for raw in raw_index.values():
        item = _obj(raw)
        reusable_id = str(item.get("custom_id") or item.get("id") or "").strip()
        name = str(item.get("display") or item.get("name") or "").strip()
        if reusable_id and name:
            names[reusable_id] = name
    return names


def _reusable_ids_from_path_index(app: dict[str, Any]) -> set[str]:
    id_to_path = _obj(_obj(app.get("_index")).get("id_to_path"))
    reusable_ids: set[str] = set()
    reusable_roots = {"%ed", "element_definitions", "CustomDefinition", "custom_definitions"}
    for encoded_path in id_to_path.values():
        parts = _encoded_path_to_array(str(encoded_path))
        if len(parts) >= 2 and parts[0] in reusable_roots and parts[1] != "length":
            reusable_ids.add(parts[1])
    return reusable_ids


def _reusable_definitions(app: dict[str, Any]) -> dict[str, dict[str, Any]]:
    definitions: dict[str, dict[str, Any]] = {}
    for source_key in (
        "element_definitions",
        "%ed",
        "CustomDefinition",
        "custom_definitions",
        "reusables",
    ):
        for reusable_id, raw in _obj(app.get(source_key)).items():
            if reusable_id == "length" or not isinstance(raw, dict):
                continue
            current = definitions.setdefault(str(reusable_id), {})
            for key, value in raw.items():
                if key not in current or current[key] in (None, "", {}, []):
                    current[key] = value

    for reusable_id in _reusable_ids_from_path_index(app):
        definitions.setdefault(reusable_id, {"_inferred_from_index": True})
    return definitions


def _walk_elements(
    elements: dict[str, Any],
    *,
    context_node_id: str,
    base_path: list[str],
    nodes: list[BubbleContextNode],
    edges: list[BubbleContextEdge],
    parent_node_id: str,
) -> None:
    for element_id, raw in elements.items():
        if not isinstance(raw, dict):
            continue
        element_path = [*base_path, "%el", str(element_id)]
        node_id = f"element:{element_id}"
        props = _obj(raw.get("%p") or raw.get("properties"))
        nodes.append(
            BubbleContextNode(
                id=node_id,
                label=_label(raw, str(element_id)),
                type="element",
                metadata={
                    "bubble_id": str(element_id),
                    "element_type": _element_type(raw),
                    "context": context_node_id,
                    "path_array": element_path,
                    "properties": props,
                    "children": _element_children(raw),
                    "deleted": _deleted_value(raw),
                },
            )
        )
        edges.append(BubbleContextEdge(source=parent_node_id, target=node_id, type="contains"))
        child_elements = _obj(raw.get("%el") or raw.get("elements"))
        if child_elements:
            _walk_elements(
                child_elements,
                context_node_id=context_node_id,
                base_path=element_path,
                nodes=nodes,
                edges=edges,
                parent_node_id=node_id,
            )


def _context_from_crawler_payload(payload: dict[str, Any], source: str) -> BubbleProjectContext:
    if not isinstance(payload, dict):
        raise ValueError("Crawler index must be a JSON object.")

    app_id = str(payload.get("appId") or payload.get("app_id") or "unknown")
    nodes: list[BubbleContextNode] = []
    edges: list[BubbleContextEdge] = []

    id_to_path = _obj(payload.get("idToPath"))
    page_index = _obj(payload.get("pageIndex"))
    reusable_index = _obj(payload.get("reusableIndex"))

    for page in payload.get("pages") or []:
        if not isinstance(page, dict):
            continue
        page_name = str(page.get("name") or "")
        page_id = str(page.get("id") or page_index.get(page_name) or page_name or "")
        if not page_id:
            continue
        page_label = _label(page, page_id)
        node_id = f"page:{page_label}"
        nodes.append(
            BubbleContextNode(
                id=node_id,
                label=page_label,
                type="page",
                metadata={
                    "bubble_id": page_id,
                    "key": page_id,
                    "path_array": ["%p3", page_id],
                    "properties": _obj(page.get("properties")),
                    "root_id": _root_id(page),
                    "children": [str(key) for key in _obj(page.get("elements")).keys()],
                    "deleted": _deleted_value(page),
                },
            )
        )
        _walk_elements(
            _obj(page.get("elements")),
            context_node_id=node_id,
            base_path=["%p3", page_id],
            nodes=nodes,
            edges=edges,
            parent_node_id=node_id,
        )
        for workflow_id, workflow in _obj(page.get("workflows")).items():
            workflow_node_id = f"workflow:{workflow_id}"
            nodes.append(
                BubbleContextNode(
                    id=workflow_node_id,
                    label=_label(_obj(workflow), str(workflow_id)),
                    type="workflow",
                    metadata={
                        "bubble_id": str(workflow_id),
                        "context": node_id,
                        "deleted": _deleted_value(_obj(workflow)),
                    },
                )
            )
            edges.append(BubbleContextEdge(source=node_id, target=workflow_node_id, type="has_workflow"))

    for reusable in payload.get("reusables") or []:
        if not isinstance(reusable, dict):
            continue
        reusable_name = str(reusable.get("name") or "")
        reusable_id = str(
            reusable.get("id") or reusable_index.get(reusable_name) or reusable_name or ""
        )
        if not reusable_id:
            continue
        reusable_label = _label(reusable, reusable_id)
        node_id = f"reusable:{reusable_label}"
        root_key = "%ed" if str(reusable.get("sourceKey") or "").startswith("element") else "%p3"
        nodes.append(
            BubbleContextNode(
                id=node_id,
                label=reusable_label,
                type="reusable",
                metadata={
                    "bubble_id": reusable_id,
                    "key": reusable_id,
                    "path_array": [root_key, reusable_id],
                    "properties": _obj(reusable.get("properties")),
                    "root_id": _root_id(reusable),
                    "children": [str(key) for key in _obj(reusable.get("elements")).keys()],
                    "inferred_from_index": bool(reusable.get("inferredFromIndex")),
                    "deleted": _deleted_value(reusable),
                },
            )
        )
        _walk_elements(
            _obj(reusable.get("elements")),
            context_node_id=node_id,
            base_path=[root_key, reusable_id],
            nodes=nodes,
            edges=edges,
            parent_node_id=node_id,
        )

    for type_id, raw in _obj(payload.get("dataTypes")).items():
        nodes.append(
            BubbleContextNode(
                id=f"datatype:{type_id}",
                label=_label(_obj(raw), str(type_id)),
                type="data_type",
                metadata={
                    "bubble_id": str(type_id),
                    "properties": _obj(raw),
                    "deleted": _deleted_value(_obj(raw)),
                },
            )
        )

    for option_id, raw in _obj(payload.get("optionSets")).items():
        nodes.append(
            BubbleContextNode(
                id=f"optionset:{option_id}",
                label=_label(_obj(raw), str(option_id)),
                type="option_set",
                metadata={
                    "bubble_id": str(option_id),
                    "properties": _obj(raw),
                    "deleted": _deleted_value(_obj(raw)),
                },
            )
        )

    for element_id, encoded_path in id_to_path.items():
        node_id = f"element:{element_id}"
        for node in nodes:
            if node.id == node_id:
                node.metadata.setdefault("path_array", _encoded_path_to_array(str(encoded_path)))
                break

    settings = _obj(payload.get("settings"))
    client_safe = _obj(settings.get("client_safe"))
    return BubbleProjectContext(
        app_id=app_id,
        source=source,
        nodes=nodes,
        edges=edges,
        metadata={
            "settings": settings,
            "styles": _obj(payload.get("styles")),
            "default_styles": _obj(client_safe.get("default_styles")),
        },
    )


def context_from_crawler_index(path: Path) -> BubbleProjectContext:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Crawler index must be a JSON object.")
    return _context_from_crawler_payload(payload, str(path))


def context_from_bubble_export(path: Path) -> BubbleProjectContext:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Bubble export must be a JSON object.")
    raw_app = payload.get("app")
    app = raw_app if isinstance(raw_app, dict) else payload
    reusable_definitions = _reusable_definitions(app)
    reusable_names = _reusable_name_by_id(app)
    id_to_path = _obj(_obj(app.get("_index")).get("id_to_path"))
    crawler_like = {
        "appId": app.get("appname")
        or app.get("app_id")
        or app.get("id")
        or app.get("_id")
        or app.get("name")
        or payload.get("appname")
        or payload.get("app_id")
        or payload.get("_id")
        or "unknown",
        "pages": [
            {
                "id": key,
                "name": _label(_obj(value), key),
                "properties": _obj(_obj(value).get("%p") or _obj(value).get("properties")),
                "rootId": _root_id(_obj(value)),
                "elements": _obj(_obj(value).get("%el") or _obj(value).get("elements")),
                "workflows": _obj(_obj(value).get("%wf") or _obj(value).get("workflows")),
                "deleted": _deleted_value(_obj(value)),
            }
            for key, value in _obj(app.get("pages")).items()
        ],
        "reusables": [
            {
                "id": key,
                "name": _label(_obj(value), reusable_names.get(key, key)),
                "sourceKey": "element_definitions",
                "properties": _obj(_obj(value).get("%p") or _obj(value).get("properties")),
                "rootId": _root_id(_obj(value)),
                "elements": _obj(_obj(value).get("%el") or _obj(value).get("elements")),
                "workflows": _obj(_obj(value).get("%wf") or _obj(value).get("workflows")),
                "inferredFromIndex": bool(_obj(value).get("_inferred_from_index")),
                "deleted": _deleted_value(_obj(value)),
            }
            for key, value in reusable_definitions.items()
        ],
        "idToPath": id_to_path,
        "dataTypes": _obj(app.get("data_types") or app.get("dataTypes") or app.get("user_types")),
        "optionSets": _obj(app.get("option_sets") or app.get("optionSets")),
        "settings": _obj(app.get("settings")),
        "styles": _obj(app.get("styles")),
    }
    return context_from_crawler_payload(crawler_like, path)


def context_from_crawler_payload(payload: dict[str, Any], source_path: Path) -> BubbleProjectContext:
    return _context_from_crawler_payload(payload, str(source_path))


def import_context_artifact(path: Path, *, kind: str = "auto") -> BubbleProjectContext:
    resolved_kind = kind
    if resolved_kind == "auto":
        lower_name = path.name.lower()
        if lower_name.endswith("-crawler-index.json") or "crawler" in lower_name:
            resolved_kind = "crawler"
        else:
            resolved_kind = "bubble"
    if resolved_kind == "crawler":
        return context_from_crawler_index(path)
    if resolved_kind == "bubble":
        return context_from_bubble_export(path)
    raise ValueError(f"Unsupported context import kind: {kind}")
