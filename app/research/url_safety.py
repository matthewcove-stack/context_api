from __future__ import annotations

import ipaddress
import os
from urllib.parse import urlparse


def private_source_urls_allowed() -> bool:
    return os.getenv("RESEARCH_ALLOW_PRIVATE_SOURCE_URLS", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def is_private_source_url(url: str) -> bool:
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").strip().lower().rstrip(".")
    if parsed.scheme not in {"http", "https"} or not hostname:
        return True
    if hostname == "localhost" or hostname.endswith(".localhost"):
        return True
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        return False
    return not address.is_global


def source_url_allowed(url: str) -> bool:
    return private_source_urls_allowed() or not is_private_source_url(url)
