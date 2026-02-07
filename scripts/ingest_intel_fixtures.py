#!/usr/bin/env python3
from __future__ import annotations

import os
import sys

from app.storage.db import create_db_engine
from app.util.intel_fixtures import ingest_intel_fixtures


def main() -> None:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("Missing DATABASE_URL")
    bundle = os.environ.get("FIXTURE_BUNDLE", "default")
    engine = create_db_engine(database_url)
    ingested_ids = ingest_intel_fixtures(engine, bundle=bundle)
    print(f"ingested={len(ingested_ids)} articles")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(str(exc))
        sys.exit(1)
