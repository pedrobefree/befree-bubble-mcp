#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List

from bs4 import BeautifulSoup

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from html_to_bubble import BubbleCommandBuilder, HTMLParser, HTMLToBubbleMapper


def _load_input_html(path: str) -> str:
    with open(path, "r", encoding="utf-8") as f:
        return f.read()


def _walk(node: Dict[str, Any]) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []

    def _rec(cur: Dict[str, Any]) -> None:
        if not cur:
            return
        out.append(cur)
        for c in cur.get("children", []) or []:
            _rec(c)

    _rec(node)
    return out


def _count_tree_nodes(node: Dict[str, Any]) -> int:
    if not node:
        return 0
    total = 1
    for child in node.get("children", []) or []:
        total += _count_tree_nodes(child)
    return total


def _count_tree_types(node: Dict[str, Any], counter: Counter) -> None:
    if not node:
        return
    counter[str(node.get("type", "unknown")).lower()] += 1
    for child in node.get("children", []) or []:
        _count_tree_types(child, counter)


def _count_mapped_types(node: Dict[str, Any], counter: Counter) -> None:
    if not node:
        return
    counter[str(node.get("bubble_type", "unknown"))] += 1
    for child in node.get("children", []) or []:
        _count_mapped_types(child, counter)


def _collect_large_fixed_heights(commands: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    issues: List[Dict[str, Any]] = []
    for cmd in commands:
        if cmd.get("action") != "create_group":
            continue
        params = cmd.get("params", {}) or {}
        height = params.get("height")
        if isinstance(height, int) and height >= 500:
            issues.append(
                {
                    "name": params.get("name", ""),
                    "height": height,
                    "parent_ref": cmd.get("parent_ref"),
                }
            )
    return issues


def _is_text_tag(tag: str) -> bool:
    return tag in {"h1", "h2", "h3", "h4", "h5", "h6", "p", "span", "li", "small", "strong", "em", "a", "button"}


def _is_media_tag(tag: str) -> bool:
    return tag in {"img", "svg", "video", "iframe", "canvas"}


def _collect_metrics(
    parsed_tree: Dict[str, Any],
    mapped_tree: Dict[str, Any],
    commands: List[Dict[str, Any]],
    parsed_type_counts: Counter,
    mapped_type_counts: Counter,
) -> Dict[str, Any]:
    parsed_nodes = _walk(parsed_tree)
    mapped_nodes = _walk(mapped_tree)
    parsed_text_nodes = 0
    parsed_media_nodes = 0
    parsed_dark_bg_nodes = 0

    for n in parsed_nodes:
        t = str(n.get("type", "")).lower()
        if _is_text_tag(t) and str(n.get("text", "")).strip():
            parsed_text_nodes += 1
        media_url = str(n.get("media_url", "")).strip()
        if _is_media_tag(t) or media_url:
            parsed_media_nodes += 1
        styles = n.get("styles", {}) or {}
        bg = str(styles.get("background-color", "")).lower()
        if bg in {"#000", "#000000", "rgb(0, 0, 0)", "rgba(0, 0, 0, 1)"}:
            parsed_dark_bg_nodes += 1

    mapped_text_nodes = sum(
        1
        for n in mapped_nodes
        if n.get("bubble_type") == "Text" and str((n.get("properties", {}) or {}).get("content", "")).strip()
    )
    mapped_media_nodes = sum(1 for n in mapped_nodes if n.get("bubble_type") == "Image")
    mapped_heading_like_nodes = sum(
        1
        for n in mapped_nodes
        if n.get("bubble_type") == "Text"
        and int((n.get("properties", {}) or {}).get("font_size", 0) or 0) >= 28
    )
    mapped_relative_groups = sum(
        1
        for n in mapped_nodes
        if n.get("bubble_type") == "Group"
        and str((n.get("properties", {}) or {}).get("layout", "")).lower() == "relative"
    )
    mapped_row_groups_with_3_children = sum(
        1
        for n in mapped_nodes
        if n.get("bubble_type") == "Group"
        and str((n.get("properties", {}) or {}).get("layout", "")).lower() == "row"
        and len(n.get("children", []) or []) >= 3
    )
    mapped_dark_bg_groups = sum(
        1
        for n in mapped_nodes
        if n.get("bubble_type") == "Group"
        and str((n.get("properties", {}) or {}).get("bg_color", "")).lower() in {"#000", "#000000"}
    )

    action_counts: Counter = Counter(str(c.get("action", "")).lower() for c in commands)
    metrics = {
        "parsed_nodes": _count_tree_nodes(parsed_tree),
        "mapped_nodes": _count_tree_nodes(mapped_tree),
        "parsed_type_counts": dict(parsed_type_counts),
        "mapped_type_counts": dict(mapped_type_counts),
        "parsed_text_nodes": parsed_text_nodes,
        "parsed_media_nodes": parsed_media_nodes,
        "parsed_dark_bg_nodes": parsed_dark_bg_nodes,
        "mapped_text_nodes": mapped_text_nodes,
        "mapped_media_nodes": mapped_media_nodes,
        "mapped_heading_like_nodes": mapped_heading_like_nodes,
        "mapped_relative_groups": mapped_relative_groups,
        "mapped_row_groups_with_3_children": mapped_row_groups_with_3_children,
        "mapped_dark_bg_groups": mapped_dark_bg_groups,
        "commands_total": len(commands),
        "action_counts": dict(action_counts),
    }
    return metrics


def _mk_check(name: str, passed: bool, details: str) -> Dict[str, Any]:
    return {"name": name, "passed": bool(passed), "details": details}


def _stage_parse(selected_nodes: int, metrics: Dict[str, Any]) -> Dict[str, Any]:
    checks = [
        _mk_check("selector_match", selected_nodes > 0, f"selected_nodes={selected_nodes}"),
        _mk_check("parsed_non_empty", metrics["parsed_nodes"] > 0, f"parsed_nodes={metrics['parsed_nodes']}"),
    ]
    return {
        "name": "parse",
        "passed": all(c["passed"] for c in checks),
        "checks": checks,
    }


def _ratio(mapped: int, parsed: int) -> float:
    if parsed <= 0:
        return 1.0
    return float(mapped) / float(parsed)


def _stage_map(metrics: Dict[str, Any]) -> Dict[str, Any]:
    text_ratio = _ratio(metrics["mapped_text_nodes"], metrics["parsed_text_nodes"])
    media_ratio = _ratio(metrics["mapped_media_nodes"], metrics["parsed_media_nodes"])
    checks = [
        _mk_check("mapped_non_empty", metrics["mapped_nodes"] > 0, f"mapped_nodes={metrics['mapped_nodes']}"),
        _mk_check("mapped_has_group", int(metrics["mapped_type_counts"].get("Group", 0)) > 0, f"group_count={metrics['mapped_type_counts'].get('Group', 0)}"),
        _mk_check("text_retention_ratio", text_ratio >= 0.35, f"text_ratio={text_ratio:.2f} ({metrics['mapped_text_nodes']}/{metrics['parsed_text_nodes']})"),
        _mk_check("media_retention_ratio", media_ratio >= 0.25, f"media_ratio={media_ratio:.2f} ({metrics['mapped_media_nodes']}/{metrics['parsed_media_nodes']})"),
    ]
    return {
        "name": "map",
        "passed": all(c["passed"] for c in checks),
        "checks": checks,
    }


def _stage_payload(commands: List[Dict[str, Any]], metrics: Dict[str, Any], large_fixed_heights: List[Dict[str, Any]]) -> Dict[str, Any]:
    action_counts = metrics["action_counts"]
    bad_actions = [a for a in action_counts.keys() if not a.startswith("create_")]
    checks = [
        _mk_check("commands_non_empty", len(commands) > 0, f"commands={len(commands)}"),
        _mk_check("group_commands_present", int(action_counts.get("create_group", 0)) > 0, f"create_group={action_counts.get('create_group', 0)}"),
        _mk_check("no_unexpected_actions", len(bad_actions) == 0, f"unexpected={bad_actions}"),
        _mk_check("fixed_height_guard", len(large_fixed_heights) <= 2, f"large_fixed_height_groups={len(large_fixed_heights)}"),
    ]
    return {
        "name": "payload",
        "passed": all(c["passed"] for c in checks),
        "checks": checks,
    }


def _stage_visual_parity(metrics: Dict[str, Any]) -> Dict[str, Any]:
    checklist = [
        _mk_check(
            "hero_heading_present",
            metrics["mapped_heading_like_nodes"] >= 1,
            f"heading_like_nodes={metrics['mapped_heading_like_nodes']}",
        ),
        _mk_check(
            "cta_button_present",
            int(metrics["action_counts"].get("create_button", 0)) >= 1,
            f"create_button={metrics['action_counts'].get('create_button', 0)}",
        ),
        _mk_check(
            "hero_media_present",
            metrics["mapped_media_nodes"] >= 1,
            f"mapped_media_nodes={metrics['mapped_media_nodes']}",
        ),
        _mk_check(
            "structured_groups_present",
            int(metrics["mapped_type_counts"].get("Group", 0)) >= 4,
            f"group_count={metrics['mapped_type_counts'].get('Group', 0)}",
        ),
        _mk_check(
            "feature_row_detected",
            metrics["mapped_row_groups_with_3_children"] >= 1,
            f"row_groups_with_3_children={metrics['mapped_row_groups_with_3_children']}",
        ),
        _mk_check(
            "theme_background_parity",
            metrics["parsed_dark_bg_nodes"] == 0 or metrics["mapped_dark_bg_groups"] >= 1,
            f"parsed_dark_bg_nodes={metrics['parsed_dark_bg_nodes']}, mapped_dark_bg_groups={metrics['mapped_dark_bg_groups']}",
        ),
    ]
    passed_count = sum(1 for c in checklist if c["passed"])
    return {
        "name": "visual_parity_checklist",
        "passed": passed_count >= 4,
        "checks": checklist,
        "passed_count": passed_count,
        "total": len(checklist),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Validate HTML -> Bubble conversion with strict staged gates.")
    ap.add_argument("--input", required=True, help="Input HTML file.")
    ap.add_argument("--selector", default="", help="Optional CSS selector to isolate conversion root.")
    ap.add_argument("--base-url", default="", help="Base URL for resolving relative media URLs.")
    ap.add_argument("--out-dir", default="tmp/html_validation", help="Output directory for debug artifacts.")
    ap.add_argument("--strict", action="store_true", help="Fail with non-zero exit when any stage fails.")
    args = ap.parse_args()

    in_path = Path(args.input).resolve()
    out_dir = Path(args.out_dir).resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    html = _load_input_html(str(in_path))
    soup = BeautifulSoup(html, "html.parser")

    selected_nodes: List[Any]
    if args.selector.strip():
        selected_nodes = soup.select(args.selector.strip())
        if not selected_nodes:
            print(f"❌ Selector matched nothing: {args.selector}")
            return 2
    else:
        root = soup.body or soup
        selected_nodes = [n for n in root.children if getattr(n, "name", None)]
        if not selected_nodes:
            selected_nodes = [root]

    selected_html = "\n".join([str(n) for n in selected_nodes])
    (out_dir / "01_selected.html").write_text(selected_html, encoding="utf-8")

    parser = HTMLParser(base_url=args.base_url.strip())
    parsed_roots = [parser.parse_element(node) for node in selected_nodes if getattr(node, "name", None)]
    parsed_roots = [n for n in parsed_roots if n]
    if not parsed_roots:
        print("❌ Parser produced no roots.")
        return 3

    if len(parsed_roots) == 1:
        parsed_tree: Dict[str, Any] = parsed_roots[0]
    else:
        parsed_tree = {
            "type": "fragment",
            "text": "",
            "attributes": {},
            "styles": {},
            "computed_styles": {},
            "children": parsed_roots,
        }

    (out_dir / "02_parsed_tree.json").write_text(
        json.dumps(parsed_tree, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    mapper = HTMLToBubbleMapper(base_url=args.base_url.strip() if args.base_url else "")
    mapped_tree = mapper.map_tree(parsed_tree)
    if not mapped_tree:
        print("❌ Mapper produced no output.")
        return 4

    (out_dir / "03_mapped_tree.json").write_text(
        json.dumps(mapped_tree, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    builder = BubbleCommandBuilder()
    commands = builder.build_commands("validation-context", "root", mapped_tree)
    (out_dir / "04_commands.json").write_text(
        json.dumps(commands, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    parsed_type_counts: Counter = Counter()
    mapped_type_counts: Counter = Counter()
    _count_tree_types(parsed_tree, parsed_type_counts)
    _count_mapped_types(mapped_tree, mapped_type_counts)
    large_fixed_heights = _collect_large_fixed_heights(commands)
    metrics = _collect_metrics(parsed_tree, mapped_tree, commands, parsed_type_counts, mapped_type_counts)

    stages = [
        _stage_parse(len(selected_nodes), metrics),
        _stage_map(metrics),
        _stage_payload(commands, metrics, large_fixed_heights),
        _stage_visual_parity(metrics),
    ]
    all_stages_passed = all(stage["passed"] for stage in stages)

    summary = {
        "input_file": str(in_path),
        "selector": args.selector.strip() or None,
        "selected_nodes": len(selected_nodes),
        "metrics": metrics,
        "stages": stages,
        "all_stages_passed": all_stages_passed,
        "large_fixed_heights": large_fixed_heights,
        "artifacts": {
            "selected_html": str(out_dir / "01_selected.html"),
            "parsed_tree": str(out_dir / "02_parsed_tree.json"),
            "mapped_tree": str(out_dir / "03_mapped_tree.json"),
            "commands": str(out_dir / "04_commands.json"),
        },
    }
    (out_dir / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")

    print("✅ Validation artifacts written:")
    print(f"- {out_dir / '01_selected.html'}")
    print(f"- {out_dir / '02_parsed_tree.json'}")
    print(f"- {out_dir / '03_mapped_tree.json'}")
    print(f"- {out_dir / '04_commands.json'}")
    print(f"- {out_dir / 'summary.json'}")
    print("\nStage results:")
    for stage in stages:
        label = "PASS" if stage["passed"] else "FAIL"
        print(f"- [{label}] {stage['name']}")
        for check in stage.get("checks", []):
            c_label = "ok" if check["passed"] else "x"
            print(f"  - ({c_label}) {check['name']}: {check['details']}")

    if summary["large_fixed_heights"]:
        print(f"\n⚠️ Large fixed-height groups: {len(summary['large_fixed_heights'])}")

    if args.strict and not all_stages_passed:
        print("\n❌ Strict validation failed.")
        return 10
    print("\n✅ Validation finished.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
