from __future__ import annotations

import os
import time
from typing import Any, Dict
from urllib.parse import urlparse

import httpx

DEFAULT_MAX_BYTES = 2_000_000
DEFAULT_TIMEOUT_S = 20
DEFAULT_MAX_REDIRECTS = 5
DEFAULT_USER_AGENT = "context_api/1.0"

_HOST_LAST_REQUEST: Dict[str, float] = {}


def _get_int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _throttle_host(host: str) -> None:
    throttle_ms = _get_int_env("INTEL_HOST_THROTTLE_MS", 1200)
    if throttle_ms <= 0:
        return
    now = time.monotonic()
    last = _HOST_LAST_REQUEST.get(host)
    if last is not None:
        wait_s = (throttle_ms / 1000.0) - (now - last)
        if wait_s > 0:
            time.sleep(wait_s)
    _HOST_LAST_REQUEST[host] = time.monotonic()


def fetch_url(url: str) -> Dict[str, Any]:
    max_bytes = _get_int_env("INTEL_FETCH_MAX_BYTES", DEFAULT_MAX_BYTES)
    timeout_s = _get_int_env("INTEL_FETCH_TIMEOUT_S", DEFAULT_TIMEOUT_S)
    headers = {"User-Agent": os.getenv("INTEL_USER_AGENT", DEFAULT_USER_AGENT)}
    host = urlparse(url).netloc
    if host:
        _throttle_host(host)
    response_headers: Dict[str, str] = {}
    truncated = False
    html = ""
    with httpx.Client(follow_redirects=True, timeout=timeout_s, max_redirects=DEFAULT_MAX_REDIRECTS) as client:
        with client.stream("GET", url, headers=headers, follow_redirects=True) as response:
            response_headers = {key.lower(): value for key, value in response.headers.items()}
            chunks = []
            total = 0
            for chunk in response.iter_bytes():
                if not chunk:
                    continue
                if total + len(chunk) > max_bytes:
                    remaining = max_bytes - total
                    if remaining > 0:
                        chunks.append(chunk[:remaining])
                    truncated = True
                    break
                chunks.append(chunk)
                total += len(chunk)
            html = b"".join(chunks).decode("utf-8", errors="ignore")
            final_url = str(response.url)
            status_code = response.status_code
    return {
        "final_url": final_url,
        "status_code": status_code,
        "headers": response_headers,
        "html": html,
        "truncated": truncated,
    }
