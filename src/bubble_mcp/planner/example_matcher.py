"""Lightweight corpus matcher for agent-facing natural-language requests."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from bubble_mcp.planner.corpus import CorpusEntry, load_corpus


TOKEN_RE = re.compile(r"[a-z0-9_#./:-]+", re.IGNORECASE)
URL_RE = re.compile(r"https?://[^\s'\"<>]+", re.IGNORECASE)
SELECTOR_RE = re.compile(
    r"(?:selector|seletor|componente)\s+([#.][a-zA-Z0-9_-]+)|([#.][a-zA-Z][a-zA-Z0-9_-]+)"
)
CONTEXT_RE = re.compile(
    r"(?:page|pagina|página|context|contexto)\s+([a-zA-Z0-9_-]+)", re.IGNORECASE
)
PARENT_RE = re.compile(
    r"(?:parent|container|grupo pai|inside|dentro de)\s+([a-zA-Z0-9_-]+)", re.IGNORECASE
)
NAME_RE = re.compile(
    r"(?:called|named|name|nome|chamad[oa])\s+['\"]?([a-zA-Z0-9 _.-]+?)['\"]?(?:\s+(?:on|na|no|em|with|com)|[.?!,]|$)",
    re.IGNORECASE,
)
LABEL_RE = re.compile(
    r"(?:label(?:ed)?|text|texto|conteudo|conteúdo)\s+['\"]?([^'\"]+?)['\"]?(?:\s+(?:on|na|no|em)|[.?!,]|$)",
    re.IGNORECASE,
)
QUOTED_RE = re.compile(r"['\"]([^'\"]+)['\"]")

STOPWORDS = {
    "a",
    "an",
    "and",
    "as",
    "com",
    "da",
    "de",
    "do",
    "e",
    "em",
    "from",
    "in",
    "into",
    "na",
    "no",
    "o",
    "os",
    "para",
    "por",
    "the",
    "to",
    "um",
    "uma",
    "with",
}


@dataclass(frozen=True)
class ExampleMatch:
    entry: CorpusEntry
    score: float
    utterance: str
    args: dict[str, Any]

    @property
    def tool_name(self) -> str:
        return self.entry.tool_name


def normalize_text(value: str) -> str:
    return " ".join(str(value).lower().replace("página", "pagina").split())


def tokenize(value: str) -> set[str]:
    normalized = normalize_text(value)
    return {
        token
        for token in TOKEN_RE.findall(normalized)
        if token not in STOPWORDS and len(token) > 1
    }


def similarity(left: str, right: str) -> float:
    left_tokens = tokenize(left)
    right_tokens = tokenize(right)
    if not left_tokens or not right_tokens:
        return 0.0
    intersection = len(left_tokens & right_tokens)
    union = len(left_tokens | right_tokens)
    return intersection / union


def _first_group(match: re.Match[str] | None) -> str:
    if match is None:
        return ""
    for value in match.groups():
        if value:
            return value.strip()
    return ""


def _quoted_or_label(message: str, *, fallback: str) -> str:
    quoted = QUOTED_RE.search(message)
    if quoted:
        return quoted.group(1).strip()
    label = LABEL_RE.search(message)
    if label:
        return label.group(1).strip().strip(".")
    return fallback


def _page_context(message: str, default: str) -> str:
    match = CONTEXT_RE.search(message)
    if not match:
        return default
    value = match.group(1).strip()
    return value or default


def _parent(message: str, default: str) -> str:
    match = PARENT_RE.search(message)
    if not match:
        return default
    value = match.group(1).strip()
    return value or default


def _name(message: str, default: str) -> str:
    quoted = QUOTED_RE.search(message)
    if quoted and re.search(r"\b(?:group|container|card|grupo|page|pagina|página)\b", message, re.IGNORECASE):
        return quoted.group(1).strip()
    match = NAME_RE.search(message)
    if not match:
        return default
    return match.group(1).strip() or default


def adapt_args(entry: CorpusEntry, message: str, *, context: str, parent: str) -> dict[str, Any]:
    args = dict(entry.default_args)
    args["context"] = _page_context(message, str(args.get("context") or context))
    args["parent"] = _parent(message, str(args.get("parent") or parent))
    tool_name = entry.tool_name
    if tool_name == "create_text":
        args["content"] = _quoted_or_label(message, fallback=str(args.get("content") or "New text"))
    elif tool_name == "create_button":
        args["label"] = _quoted_or_label(message, fallback=str(args.get("label") or "Button"))
        args.setdefault("name", f"Button {args['label']}")
    elif tool_name in {"create_group", "create_image"}:
        args["name"] = _name(message, str(args.get("name") or "Generated element"))
    elif tool_name == "create_from_html":
        url = URL_RE.search(message)
        if url:
            args["url"] = url.group(0).rstrip(".,)")
        selector = _first_group(SELECTOR_RE.search(message))
        if selector:
            args["selector"] = selector
        args.setdefault("rendered_html", True)
        args.setdefault("refresh_context", True)
    elif tool_name == "bubble_context_detect":
        profile_match = re.search(r"(?:profile|perfil|projeto)\s+([a-zA-Z0-9_-]+)", message, re.IGNORECASE)
        if profile_match:
            args["profile"] = profile_match.group(1).strip()
    elif tool_name == "bubble_context_find":
        quoted = QUOTED_RE.search(message)
        if quoted:
            args["query"] = quoted.group(1).strip()
    elif tool_name == "bubble_eval_run":
        dataset = re.search(r"([^\s'\"]+\.json)", message)
        if dataset:
            args["dataset"] = dataset.group(1).strip()
    return args


def _threshold(entry: CorpusEntry, message: str) -> float:
    if entry.tool_name == "create_from_html" and URL_RE.search(message) and SELECTOR_RE.search(message):
        return 0.18
    return 0.26


def match_example(message: str, *, context: str = "index", parent: str = "root") -> ExampleMatch | None:
    """Return the best corpus match for a request, if confidence is sufficient."""

    normalized = normalize_text(message)
    best_entry: CorpusEntry | None = None
    best_utterance = ""
    best_score = 0.0
    for entry in load_corpus():
        for utterance in entry.utterances:
            score = similarity(normalized, utterance)
            if score > best_score:
                best_score = score
                best_entry = entry
                best_utterance = utterance
    if best_entry is None or best_score < _threshold(best_entry, message):
        return None
    parsed = urlparse(str(adapt_args(best_entry, message, context=context, parent=parent).get("url") or ""))
    if best_entry.tool_name == "create_from_html" and not (parsed.scheme and parsed.netloc):
        return None
    args = adapt_args(best_entry, message, context=context, parent=parent)
    return ExampleMatch(entry=best_entry, score=round(best_score, 3), utterance=best_utterance, args=args)
