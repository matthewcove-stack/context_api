from __future__ import annotations

from html import unescape
import re
from typing import Dict, List
from urllib.parse import urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree

from bs4 import BeautifulSoup


def _normalize_url(base_url: str, candidate_url: str) -> str:
    if not candidate_url:
        return ""
    joined = urljoin(base_url, candidate_url.strip())
    parsed = urlparse(joined)
    if not parsed.scheme or not parsed.netloc:
        return ""
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", parsed.query, ""))


def _dedupe_items(items: List[Dict[str, str]], *, max_items: int) -> List[Dict[str, str]]:
    seen = set()
    deduped: List[Dict[str, str]] = []
    for item in items:
        url = item.get("url", "")
        if not url or url in seen:
            continue
        seen.add(url)
        deduped.append(item)
        if len(deduped) >= max_items:
            break
    return deduped


def discover_from_feed(raw_text: str, *, base_url: str, max_items: int) -> List[Dict[str, str]]:
    try:
        root = ElementTree.fromstring(raw_text)
    except ElementTree.ParseError:
        return []

    items: List[Dict[str, str]] = []
    # RSS
    for node in root.findall(".//item"):
        link = node.findtext("link") or ""
        guid = node.findtext("guid") or ""
        normalized = _normalize_url(base_url, unescape(link.strip()))
        if normalized:
            items.append({"url": normalized, "external_id": guid.strip()})

    # Atom
    ns_entry = root.findall(".//{*}entry")
    for entry in ns_entry:
        link_url = ""
        for link_node in entry.findall("{*}link"):
            href = link_node.attrib.get("href", "").strip()
            rel = link_node.attrib.get("rel", "alternate").strip()
            if href and rel in {"alternate", ""}:
                link_url = href
                break
        if not link_url:
            link_url = entry.findtext("{*}id") or ""
        external_id = (entry.findtext("{*}id") or "").strip()
        normalized = _normalize_url(base_url, unescape(link_url.strip()))
        if normalized:
            items.append({"url": normalized, "external_id": external_id})

    return _dedupe_items(items, max_items=max_items)


def discover_from_sitemap(raw_text: str, *, base_url: str, max_items: int) -> List[Dict[str, str]]:
    try:
        root = ElementTree.fromstring(raw_text)
    except ElementTree.ParseError:
        return []
    items: List[Dict[str, str]] = []
    for node in root.findall(".//{*}url/{*}loc"):
        normalized = _normalize_url(base_url, (node.text or "").strip())
        if normalized:
            items.append({"url": normalized, "external_id": ""})
    return _dedupe_items(items, max_items=max_items)


def discover_from_html_listing(raw_text: str, *, base_url: str, max_items: int) -> List[Dict[str, str]]:
    soup = BeautifulSoup(raw_text, "html.parser")
    items: List[Dict[str, str]] = []
    for link in soup.find_all("a", href=True):
        href = str(link.get("href") or "").strip()
        normalized = _normalize_url(base_url, href)
        if not normalized:
            continue
        if normalized == base_url.rstrip("/"):
            continue
        items.append({"url": normalized, "external_id": ""})
    return _dedupe_items(items, max_items=max_items)


def discover_candidate_items(
    *,
    kind: str,
    raw_text: str,
    base_url: str,
    max_items: int,
) -> List[Dict[str, str]]:
    kind_normalized = kind.strip().lower()
    bounded_max = min(max(max_items, 1), 500)
    if kind_normalized in {"rss", "atom", "api"}:
        feed_items = discover_from_feed(raw_text, base_url=base_url, max_items=bounded_max)
        if feed_items:
            return feed_items
    if kind_normalized == "site_map":
        sitemap_items = discover_from_sitemap(raw_text, base_url=base_url, max_items=bounded_max)
        if sitemap_items:
            return sitemap_items
    return discover_from_html_listing(raw_text, base_url=base_url, max_items=bounded_max)


def is_allowed_by_robots(
    *,
    url: str,
    user_agent: str,
    timeout_seconds: int = 5,
) -> bool:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        return False
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    parser = RobotFileParser()
    parser.set_url(robots_url)
    try:
        req = Request(robots_url, headers={"User-Agent": user_agent})
        with urlopen(req, timeout=timeout_seconds) as response:
            body = response.read().decode("utf-8", errors="ignore")
        parser.parse(body.splitlines())
    except Exception:
        # Fail-open for unavailable robots files; strict deny only when explicitly disallowed.
        return True
    return parser.can_fetch(user_agent, url)


def extract_title_from_html(raw_html: str) -> str:
    match = re.search(r"<title>(.*?)</title>", raw_html, re.IGNORECASE | re.DOTALL)
    if not match:
        return ""
    return unescape(match.group(1)).strip()
