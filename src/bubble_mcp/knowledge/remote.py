"""Selective remote knowledge fetch adapters."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from html import unescape
from typing import Any
from urllib.parse import quote, urlparse
from xml.etree import ElementTree

import requests
from bs4 import BeautifulSoup

from bubble_mcp.knowledge.models import KnowledgeRecord
from bubble_mcp.knowledge.sanitize import sanitize_remote_docs_query


DEFAULT_TIMEOUT_SECONDS = 12
MANUAL_SITEMAP_URL = "https://manual.bubble.io/sitemap-pages.xml"
USER_AGENT = "befree-bubble-mcp/knowledge-advisor"


@dataclass(frozen=True)
class KnowledgeSource:
    """One allowlisted remote knowledge source."""

    id: str
    type: str
    base_url: str
    trust_level: str
    max_results: int
    enabled_by_default: bool = True


DEFAULT_SOURCES: tuple[KnowledgeSource, ...] = (
    KnowledgeSource(
        id="bubble_manual",
        type="official_docs",
        base_url="https://manual.bubble.io",
        trust_level="official",
        max_results=3,
    ),
    KnowledgeSource(
        id="bubble_forum",
        type="discourse",
        base_url="https://forum.bubble.io",
        trust_level="community",
        max_results=5,
    ),
)


def _now_iso() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _tokens(value: str) -> list[str]:
    return [token for token in re.findall(r"[a-z0-9_]+", value.lower()) if len(token) > 2]


def _text_from_html(value: str) -> str:
    soup = BeautifulSoup(value or "", "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    text = " ".join(soup.get_text(" ").split())
    return unescape(text)


def _summary(value: str, *, limit: int = 420) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "..."


def _record_id(prefix: str, url: str) -> str:
    path = urlparse(url).path.strip("/")
    slug = re.sub(r"[^a-z0-9]+", "-", path.lower()).strip("-") or "root"
    digest = hashlib.sha256(url.encode("utf-8")).hexdigest()[:12]
    return f"{prefix}:{slug}:{digest}"


def _content_hash(content: str) -> str:
    return "sha256:" + hashlib.sha256(content.encode("utf-8")).hexdigest()


def _get_json(url: str, *, params: dict[str, str] | None = None) -> dict[str, Any]:
    response = requests.get(
        url,
        params=params,
        timeout=DEFAULT_TIMEOUT_SECONDS,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    )
    response.raise_for_status()
    payload = response.json()
    return payload if isinstance(payload, dict) else {}


def _get_text(url: str) -> str:
    response = requests.get(
        url,
        timeout=DEFAULT_TIMEOUT_SECONDS,
        headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xml"},
    )
    response.raise_for_status()
    return response.text


def _manual_urls() -> list[str]:
    xml = _get_text(MANUAL_SITEMAP_URL)
    root = ElementTree.fromstring(xml)
    urls: list[str] = []
    for loc in root.findall(".//{http://www.sitemaps.org/schemas/sitemap/0.9}loc"):
        if loc.text and loc.text.startswith("https://manual.bubble.io"):
            urls.append(loc.text.strip())
    return urls


def _score_url(query_tokens: list[str], url: str) -> int:
    normalized_url = url.lower().replace("-", " ").replace("/", " ")
    return sum(1 for token in query_tokens if token in normalized_url)


def fetch_bubble_manual_records(query: str, *, max_results: int = 3) -> list[KnowledgeRecord]:
    """Fetch a few likely Bubble manual pages selected from the sitemap."""

    sanitized = sanitize_remote_docs_query(query)
    query_tokens = _tokens(sanitized)
    if not query_tokens:
        return []
    scored = [(_score_url(query_tokens, url), url) for url in _manual_urls()]
    candidates = [url for score, url in sorted(scored, key=lambda item: (-item[0], item[1])) if score > 0]
    records: list[KnowledgeRecord] = []
    for url in candidates[: max(1, min(max_results, 3))]:
        html = _get_text(url)
        text = _text_from_html(html)
        if not text:
            continue
        title = urlparse(url).path.strip("/").split("/")[-1].replace("-", " ").title() or "Bubble Manual"
        records.append(
            KnowledgeRecord.from_dict(
                {
                    "id": _record_id("bubble-manual:remote", url),
                    "source": "bubble_manual",
                    "source_url": url,
                    "title": title,
                    "section_path": [part.replace("-", " ") for part in urlparse(url).path.strip("/").split("/") if part],
                    "content": _summary(text, limit=2500),
                    "summary": _summary(text),
                    "tags": query_tokens,
                    "retrieved_at": _now_iso(),
                    "content_hash": _content_hash(text),
                    "ttl_seconds": 604800,
                    "license_note": "Bubble manual page fetched selectively for local developer assistance.",
                    "confidence": "official_cached",
                }
            )
        )
    return records


def _topic_url(base_url: str, topic: dict[str, Any], topic_id: int) -> str:
    slug = str(topic.get("slug") or topic.get("topic_slug") or "").strip()
    if slug:
        return f"{base_url.rstrip('/')}/t/{quote(slug)}/{topic_id}"
    return f"{base_url.rstrip('/')}/t/{topic_id}"


def fetch_discourse_records(
    query: str,
    *,
    base_url: str = "https://forum.bubble.io",
    source_id: str = "bubble_forum",
    max_results: int = 5,
) -> list[KnowledgeRecord]:
    """Fetch a few likely Discourse topics for a sanitized query."""

    sanitized = sanitize_remote_docs_query(query)
    if not sanitized:
        return []
    search = _get_json(f"{base_url.rstrip('/')}/search.json", params={"q": sanitized})
    raw_posts = search.get("posts")
    raw_topics = search.get("topics")
    posts: list[Any] = raw_posts if isinstance(raw_posts, list) else []
    topics: list[Any] = raw_topics if isinstance(raw_topics, list) else []
    topic_by_id = {
        int(str(topic.get("id"))): topic
        for topic in topics
        if isinstance(topic, dict) and str(topic.get("id") or "").isdigit()
    }
    topic_ids: list[int] = []
    for post in posts:
        if not isinstance(post, dict):
            continue
        raw_id = post.get("topic_id") or post.get("topicId")
        if str(raw_id or "").isdigit():
            topic_id = int(str(raw_id))
            if topic_id not in topic_ids:
                topic_ids.append(topic_id)
    for topic_id in topic_by_id:
        if topic_id not in topic_ids:
            topic_ids.append(topic_id)

    records: list[KnowledgeRecord] = []
    for topic_id in topic_ids[: max(1, min(max_results, 5))]:
        topic_payload = _get_json(f"{base_url.rstrip('/')}/t/{topic_id}.json")
        topic = topic_by_id.get(topic_id, topic_payload)
        post_stream = topic_payload.get("post_stream")
        raw_topic_posts = post_stream.get("posts") if isinstance(post_stream, dict) else []
        posts_payload: list[Any] = raw_topic_posts if isinstance(raw_topic_posts, list) else []
        post_text = " ".join(
            _text_from_html(str(post.get("cooked") or post.get("blurb") or ""))
            for post in posts_payload[:4]
            if isinstance(post, dict)
        )
        if not post_text:
            post_text = " ".join(str(post.get("blurb") or "") for post in posts if isinstance(post, dict))
        if not post_text:
            continue
        title = str(topic_payload.get("title") or topic.get("title") or f"Bubble Forum topic {topic_id}").strip()
        url = _topic_url(base_url, topic_payload if isinstance(topic_payload, dict) else topic, topic_id)
        tags = _tokens(sanitized)
        records.append(
            KnowledgeRecord.from_dict(
                {
                    "id": _record_id("bubble-forum:topic", url),
                    "source": source_id,
                    "source_url": url,
                    "title": title,
                    "section_path": ["Bubble Forum"],
                    "content": _summary(post_text, limit=2500),
                    "summary": _summary(post_text),
                    "tags": tags,
                    "retrieved_at": _now_iso(),
                    "content_hash": _content_hash(post_text),
                    "ttl_seconds": 604800,
                    "license_note": "Bubble Forum community topic fetched selectively for local developer assistance.",
                    "confidence": "community_observed",
                }
            )
        )
    return records


def fetch_remote_records(queries: list[str], *, max_records: int = 8) -> list[KnowledgeRecord]:
    """Fetch source-attributed remote records for sanitized queries."""

    records: list[KnowledgeRecord] = []
    seen: set[str] = set()
    for query in queries[:3]:
        for source in DEFAULT_SOURCES:
            fetched: list[KnowledgeRecord] = []
            if source.type == "official_docs":
                fetched = fetch_bubble_manual_records(query, max_results=source.max_results)
            elif source.type == "discourse":
                fetched = fetch_discourse_records(
                    query,
                    base_url=source.base_url,
                    source_id=source.id,
                    max_results=source.max_results,
                )
            for record in fetched:
                if record.id in seen:
                    continue
                records.append(record)
                seen.add(record.id)
                if len(records) >= max_records:
                    return records[:max_records]
            if len(records) >= max_records:
                return records[:max_records]
    return records[:max_records]
