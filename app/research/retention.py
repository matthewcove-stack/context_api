from __future__ import annotations

import argparse
import os

from app.storage.db import create_db_engine, redact_research_raw_payloads


def main() -> None:
    parser = argparse.ArgumentParser(description="Research raw-payload redaction utility")
    parser.add_argument("--topic-key", required=True)
    parser.add_argument("--older-than-days", type=int, default=30)
    args = parser.parse_args()

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set")
    engine = create_db_engine(database_url)
    redacted = redact_research_raw_payloads(
        engine,
        topic_key=args.topic_key.strip().lower(),
        older_than_days=max(args.older_than_days, 0),
    )
    print(f"redacted_documents={redacted}")


if __name__ == "__main__":
    main()
