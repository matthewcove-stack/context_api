from __future__ import annotations

import re
from urllib.parse import urlparse

_JUNK_URL_PATTERNS = (
    "/login",
    "/signin",
    "/sign-in",
    "/signup",
    "/sign-up",
    "/pricing",
    "/enterprise",
    "/press-kit",
    "/presskit",
    "/sitemap",
)
_JUNK_TEXT_PATTERNS = (
    "log in",
    "sign up",
    "forgot your password",
    "with your account",
    "team & enterprise",
    "unlock sso",
    "pricing",
)
_ARCHIVE_TITLE_PATTERNS = (
    "archive for ",
    "archive:",
)
_FEED_URL_SUFFIXES = (
    ".atom",
    ".rss",
    ".xml",
)
_NAVIGATION_TERMS = (
    "models",
    "datasets",
    "spaces",
    "community",
    "docs",
    "enterprise",
    "pricing",
    "log in",
    "sign up",
)
_TOKENISH_RE = re.compile(r"[A-Za-z]{3,}")

_SITE_INDEX_RULES = {
    "huggingface.co": {"/docs"},
    "techcrunch.com": {"/"},
    "simonwillison.net": {"/", "/tags"},
    "www.latent.space": {"/archive", "/s/ainews"},
}


def looks_corrupted_text(text: str) -> bool:
    sample = (text or "")[:1200]
    if not sample:
        return False
    weird = sum(1 for ch in sample if ord(ch) < 9 or (13 < ord(ch) < 32))
    high_unicode = sum(1 for ch in sample if ord(ch) > 126 and not ch.isalpha())
    token_count = len(_TOKENISH_RE.findall(sample))
    return (weird >= 8 or high_unicode >= 40) and token_count < 25


def detect_junk_document(
    *,
    url: str,
    title: str,
    extracted_text: str,
    item_summary: str,
    fetch_status: int,
    fetch_fallback: str | None,
) -> str | None:
    lowered_url = url.lower()
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    path = (parsed.path or "/").rstrip("/") or "/"
    title_lower = title.lower()
    text_lower = extracted_text.lower()
    summary_lower = item_summary.lower()
    combined = " ".join(part for part in (title_lower, text_lower[:1200], summary_lower[:400]) if part)

    if any(path.endswith(suffix) for suffix in _FEED_URL_SUFFIXES):
        return "feed_endpoint"
    if any(pattern in lowered_url for pattern in _JUNK_URL_PATTERNS):
        return "junk_url_pattern"
    if path in _SITE_INDEX_RULES.get(host, set()):
        return "site_index_page"
    if title_lower.startswith(_ARCHIVE_TITLE_PATTERNS):
        return "archive_listing_page"
    if host == "simonwillison.net" and path.startswith("/tags/"):
        return "tag_listing_page"
    if host.endswith("huggingface.co") and any(pattern in combined for pattern in _JUNK_TEXT_PATTERNS):
        return "junk_login_or_pricing_page"
    if host.endswith("huggingface.co") and sum(term in combined for term in _NAVIGATION_TERMS) >= 5:
        return "navigation_shell_page"
    if host == "www.latent.space" and path.startswith("/s/"):
        if all(term in combined for term in ("subscribe", "sign in", "latest", "top", "discussions")):
            return "newsletter_index_page"
    if host == "techcrunch.com" and path == "/":
        if all(term in combined for term in ("top headlines", "latest news", "upcoming events")):
            return "homepage_shell_page"
    if "press-kit" in lowered_url and looks_corrupted_text(extracted_text):
        return "corrupted_press_kit_content"
    if looks_corrupted_text(extracted_text):
        return "corrupted_extraction"
    if fetch_fallback == "feed_summary":
        words = len((item_summary or "").split())
        if fetch_status >= 400 and words < 40:
            return "blocked_fetch_summary_only"
    if "page not found" in combined or title_lower.strip() == "404":
        return "not_found_page"
    return None
