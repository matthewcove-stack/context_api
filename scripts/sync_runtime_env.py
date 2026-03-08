from __future__ import annotations

import argparse
from pathlib import Path


SYNC_MAP = {
    "CONTEXT_API_BEARER_TOKEN": "CONTEXT_API_TOKEN",
    "CONTEXT_POSTGRES_DATA_DIR": "CONTEXT_POSTGRES_DATA_DIR",
    "OPENAI_API_KEY": "OPENAI_API_KEY",
    "RESEARCH_EMBEDDING_MODEL": "RESEARCH_EMBEDDING_MODEL",
    "RESEARCH_ALLOW_HASH_EMBEDDINGS": "RESEARCH_ALLOW_HASH_EMBEDDINGS",
}

DEFAULTS = {
    "DATABASE_URL": "postgresql+psycopg://context:context@postgres:5432/context",
    "CONTEXT_API_RESEARCH_TOPIC_KEY": "ai_research",
    "CONTEXT_API_EXPECT_PERSISTENT_CORPUS": "true",
    "CONTEXT_API_EXPECTED_MIN_DOCUMENTS": "100",
    "RESEARCH_WORKER_ENABLED": "true",
    "RESEARCH_RUN_MAX_NEW_ITEMS": "0",
}


def parse_env(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    if not path.exists():
        return values
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        values[key.strip()] = value.strip()
    return values


def render_env(values: dict[str, str]) -> str:
    ordered_keys = [
        "DATABASE_URL",
        "CONTEXT_API_TOKEN",
        "CONTEXT_API_RESEARCH_TOPIC_KEY",
        "CONTEXT_POSTGRES_DATA_DIR",
        "CONTEXT_API_EXPECT_PERSISTENT_CORPUS",
        "CONTEXT_API_EXPECTED_MIN_DOCUMENTS",
        "OPENAI_API_KEY",
        "RESEARCH_EMBEDDING_MODEL",
        "RESEARCH_ALLOW_HASH_EMBEDDINGS",
        "RESEARCH_WORKER_ENABLED",
        "RESEARCH_RUN_MAX_NEW_ITEMS",
    ]
    keys = ordered_keys + sorted(key for key in values.keys() if key not in ordered_keys)
    return "\n".join(f"{key}={values[key]}" for key in keys if key in values and values[key] != "") + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Sync context_api runtime env from brain_os/.env")
    parser.add_argument("--source", default="../brain_os/.env")
    parser.add_argument("--target", default=".env")
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parent
    source_path = (repo_root / args.source).resolve()
    target_path = (repo_root / args.target).resolve()

    source_values = parse_env(source_path)
    target_values = parse_env(target_path)

    for source_key, target_key in SYNC_MAP.items():
        value = source_values.get(source_key, "").strip()
        if value:
            target_values[target_key] = value

    for key, value in DEFAULTS.items():
        target_values.setdefault(key, value)

    target_path.write_text(render_env(target_values), encoding="utf-8")
    print(f"Synced runtime env to {target_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
