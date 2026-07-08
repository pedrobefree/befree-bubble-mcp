from __future__ import annotations

import re
from collections.abc import Iterable

from bs4 import BeautifulSoup

from bubble_mcp.style_import.models import ExtractedStyleRule, StyleState


PSEUDO_TO_STATE: dict[str, StyleState] = {
    "hover": "hover",
    "focus": "focus",
    "focus-visible": "focus",
    "disabled": "disabled",
    "active": "pressed",
}
PSEUDO_PATTERN = re.compile(r":(focus-visible|hover|focus|disabled|active)\b")


def _strip_css_comments(css: str) -> str:
    return re.sub(r"/\*.*?\*/", "", css, flags=re.S)


def _parse_declarations(body: str) -> dict[str, str]:
    declarations: dict[str, str] = {}
    for raw_part in body.split(";"):
        part = raw_part.strip()
        if not part or ":" not in part:
            continue
        key, value = part.split(":", 1)
        declarations[key.strip().lower()] = value.strip()
    return declarations


def _iter_css_blocks(html: str, extra_css: Iterable[str] = ()) -> Iterable[str]:
    soup = BeautifulSoup(html, "html.parser")
    for style in soup.find_all("style"):
        text = style.get_text("\n", strip=False)
        if text.strip():
            yield text
    for css in extra_css:
        if css.strip():
            yield css


def _iter_inline_style_rules(html: str, selector: str) -> Iterable[ExtractedStyleRule]:
    soup = BeautifulSoup(html, "html.parser")
    for element in soup.select(selector):
        declarations = _parse_declarations(element.get("style", ""))
        if declarations:
            yield ExtractedStyleRule(
                selector=selector,
                source_selector=selector,
                state="base",
                declarations=declarations,
            )


def _select_element_ids(soup: BeautifulSoup, selector: str) -> set[int]:
    try:
        return {id(element) for element in soup.select(selector)}
    except Exception:
        return set()


def _state_for_selector(source_selector: str, base_selector: str, soup: BeautifulSoup) -> StyleState | None:
    selector = source_selector.strip()

    pseudo_match = PSEUDO_PATTERN.search(selector)
    if pseudo_match is None:
        if selector == base_selector:
            return "base"
        base_matches = _select_element_ids(soup, base_selector)
        if not base_matches:
            return None
        selector_matches = _select_element_ids(soup, selector)
        if base_matches.intersection(selector_matches):
            return "base"
        return None

    selector_without_pseudo = PSEUDO_PATTERN.sub("", selector, count=1).strip()
    pseudo = pseudo_match.group(1).strip().lower()
    if selector_without_pseudo == base_selector:
        return PSEUDO_TO_STATE.get(pseudo)
    base_matches = _select_element_ids(soup, base_selector)
    if not base_matches:
        return None
    selector_matches = _select_element_ids(soup, selector_without_pseudo)
    if not base_matches.intersection(selector_matches):
        return None
    return PSEUDO_TO_STATE.get(pseudo)


def extract_style_rules_from_html(
    html: str,
    selector: str,
    *,
    extra_css: Iterable[str] = (),
) -> list[ExtractedStyleRule]:
    rules: list[ExtractedStyleRule] = []
    soup = BeautifulSoup(html, "html.parser")
    for css in _iter_css_blocks(html, extra_css):
        clean_css = _strip_css_comments(css)
        for match in re.finditer(r"([^{}]+)\{([^{}]+)\}", clean_css, flags=re.S):
            selector_group = match.group(1)
            declarations = _parse_declarations(match.group(2))
            if not declarations:
                continue
            for raw_selector in selector_group.split(","):
                source_selector = raw_selector.strip()
                state = _state_for_selector(source_selector, selector, soup)
                if state is None:
                    continue
                rules.append(
                    ExtractedStyleRule(
                        selector=selector,
                        source_selector=source_selector,
                        state=state,
                        declarations=declarations,
                    )
                )
    rules.extend(_iter_inline_style_rules(html, selector))
    order = {"base": 0, "hover": 1, "focus": 2, "disabled": 3, "pressed": 4}
    return sorted(rules, key=lambda rule: order[rule.state])
