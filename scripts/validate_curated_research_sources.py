from __future__ import annotations

import argparse
import json
from typing import Any

from app.intel.fetch import fetch_url
from app.research.discovery import discover_candidate_items
from app.research.url_safety import is_private_source_url
from scripts.bootstrap_ai_research_sources import CURATED_SOURCES


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate the curated research source endpoints and discovery output.")
    parser.add_argument("--max-items", type=int, default=5)
    args = parser.parse_args()

    results: list[dict[str, Any]] = []
    failures = 0
    for source in CURATED_SOURCES:
        url = str(source["base_url"])
        result: dict[str, Any] = {
            "name": str(source["name"]),
            "kind": str(source["kind"]),
            "url": url,
        }
        if is_private_source_url(url):
            result.update({"status": "failed", "error": "private_source_url"})
            failures += 1
            results.append(result)
            continue
        try:
            fetched = fetch_url(url)
            status_code = int(fetched.get("status_code") or 0)
            items = discover_candidate_items(
                kind=str(source["kind"]),
                raw_text=str(fetched.get("html") or ""),
                base_url=url,
                max_items=max(args.max_items, 1),
            )
            result.update(
                {
                    "status": "ok" if 200 <= status_code < 400 and items else "failed",
                    "http_status": status_code,
                    "discovered_items": len(items),
                    "sample_url": str(items[0].get("url") or "") if items else "",
                }
            )
        except Exception as exc:
            result.update({"status": "failed", "error": str(exc)})
        if result["status"] != "ok":
            failures += 1
        results.append(result)

    print(json.dumps({"sources": results, "source_count": len(results), "failures": failures}, indent=2))
    if failures:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
