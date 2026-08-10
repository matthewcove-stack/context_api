from __future__ import annotations

import argparse
import os
from typing import Any

from app.research.ids import compute_source_id
from app.research.url_safety import is_private_source_url
from app.storage.db import (
    create_db_engine,
    create_research_ingestion_run,
    list_research_sources,
    set_research_source_enabled,
    upsert_research_source,
)


CURATED_SOURCES: list[dict[str, Any]] = [
    {
        "kind": "site_map",
        "name": "OpenAI Sitemap",
        "base_url": "https://openai.com/sitemap.xml/research/",
        "tags": ["openai", "research", "announcements"],
        "publisher_type": "vendor",
        "source_class": "external_primary",
        "default_decision_domains": ["agent_workflows", "evals", "ai_product_engineering"],
    },
    {
        "kind": "html_listing",
        "name": "Anthropic News",
        "base_url": "https://www.anthropic.com/news",
        "tags": ["anthropic", "safety", "industry"],
        "publisher_type": "vendor",
        "source_class": "external_primary",
        "default_decision_domains": ["safety", "agent_workflows", "evals"],
    },
    {
        "kind": "html_listing",
        "name": "Anthropic Engineering",
        "base_url": "https://www.anthropic.com/engineering",
        "tags": ["anthropic", "engineering", "agents", "coding"],
        "publisher_type": "vendor",
        "source_class": "external_primary",
        "default_decision_domains": ["agent_workflows", "ai_product_engineering", "evals"],
    },
    {
        "kind": "rss",
        "name": "Google AI Blog",
        "base_url": "https://blog.google/innovation-and-ai/technology/ai/rss/",
        "tags": ["google", "research", "industry"],
        "publisher_type": "vendor",
        "source_class": "external_primary",
        "default_decision_domains": ["retrieval", "evals", "ai_product_engineering"],
    },
    {
        "kind": "html_listing",
        "name": "Google DeepMind Blog",
        "base_url": "https://deepmind.google/discover/blog/",
        "tags": ["deepmind", "research", "models"],
        "publisher_type": "vendor",
        "source_class": "external_primary",
        "default_decision_domains": ["evals", "agent_workflows", "data_modeling"],
    },
    {
        "kind": "rss",
        "name": "Hugging Face Blog",
        "base_url": "https://huggingface.co/blog/feed.xml",
        "tags": ["huggingface", "open-source", "tooling"],
        "publisher_type": "vendor",
        "source_class": "external_primary",
        "default_decision_domains": ["ai_product_engineering", "agent_workflows", "retrieval"],
    },
    {
        "kind": "rss",
        "name": "Microsoft Research Blog",
        "base_url": "https://www.microsoft.com/en-us/research/feed/",
        "tags": ["microsoft", "research", "engineering"],
        "publisher_type": "vendor",
        "source_class": "external_primary",
        "default_decision_domains": ["retrieval", "agent_workflows", "ai_product_engineering"],
    },
    {
        "kind": "rss",
        "name": "arXiv cs.AI RSS",
        "base_url": "https://export.arxiv.org/rss/cs.AI",
        "tags": ["papers", "arxiv", "cs.ai"],
        "publisher_type": "academic",
        "source_class": "external_primary",
        "default_decision_domains": ["evals", "agent_workflows", "data_modeling"],
    },
    {
        "kind": "rss",
        "name": "arXiv cs.LG RSS",
        "base_url": "https://export.arxiv.org/rss/cs.LG",
        "tags": ["papers", "arxiv", "cs.lg"],
        "publisher_type": "academic",
        "source_class": "external_primary",
        "default_decision_domains": ["evals", "retrieval", "data_modeling"],
    },
    {
        "kind": "rss",
        "name": "arXiv cs.CL RSS",
        "base_url": "https://export.arxiv.org/rss/cs.CL",
        "tags": ["papers", "arxiv", "cs.cl"],
        "publisher_type": "academic",
        "source_class": "external_primary",
        "default_decision_domains": ["retrieval", "agent_workflows", "evals"],
    },
    {
        "kind": "rss",
        "name": "TechCrunch AI",
        "base_url": "https://techcrunch.com/category/artificial-intelligence/feed/",
        "tags": ["news", "industry", "commentary"],
        "publisher_type": "media",
        "source_class": "external_secondary",
        "default_decision_domains": ["ai_product_engineering", "market"],
    },
    {
        "kind": "atom",
        "name": "Simon Willison LLMs",
        "base_url": "https://simonwillison.net/atom/everything/",
        "tags": ["llms", "tooling", "commentary"],
        "publisher_type": "independent",
        "source_class": "external_commentary",
        "default_decision_domains": ["agent_workflows", "ai_product_engineering"],
    },
    {
        "kind": "rss",
        "name": "Latent Space",
        "base_url": "https://www.latent.space/feed",
        "tags": ["agents", "commentary", "engineering"],
        "publisher_type": "independent",
        "source_class": "external_commentary",
        "default_decision_domains": ["agent_workflows", "ai_product_engineering"],
    },
    {
        "kind": "rss",
        "name": "Import AI Newsletter",
        "base_url": "https://importai.substack.com/feed",
        "tags": ["news", "policy", "commentary"],
        "publisher_type": "independent",
        "source_class": "external_commentary",
        "default_decision_domains": ["policy", "ai_product_engineering"],
    },
    {
        "kind": "html_listing",
        "name": "LangChain Blog",
        "base_url": "https://www.langchain.com/blog",
        "tags": ["langchain", "langgraph", "agents", "frameworks"],
        "publisher_type": "vendor",
        "source_class": "external_primary",
        "default_decision_domains": ["agent_workflows", "ai_product_engineering", "retrieval"],
    },
    {
        "kind": "rss",
        "name": "Model Context Protocol Blog",
        "base_url": "https://blog.modelcontextprotocol.io/index.xml",
        "tags": ["mcp", "protocol", "agents", "tooling"],
        "publisher_type": "independent",
        "source_class": "external_primary",
        "default_decision_domains": ["agent_workflows", "ai_product_engineering", "data_modeling"],
    },
]


REPLACED_SOURCES: list[dict[str, str]] = [
    {"kind": "site_map", "base_url": "https://openai.com/sitemap.xml"},
    {"kind": "html_listing", "base_url": "https://blog.google/technology/ai/"},
    {"kind": "html_listing", "base_url": "https://huggingface.co/blog"},
    {"kind": "html_listing", "base_url": "https://www.microsoft.com/en-us/research/blog/"},
    {"kind": "html_listing", "base_url": "https://techcrunch.com/category/artificial-intelligence/"},
    {"kind": "html_listing", "base_url": "https://simonwillison.net/tags/llms/"},
    {"kind": "html_listing", "base_url": "https://www.latent.space/"},
    {"kind": "html_listing", "base_url": "https://importai.substack.com/archive"},
    {"kind": "html_listing", "base_url": "https://blog.langchain.dev/"},
    {"kind": "html_listing", "base_url": "https://blog.modelcontextprotocol.io/"},
    # These pages remain useful to people, but their current HTML/robots
    # contracts do not yield documents through the strict automated collector.
    {"kind": "html_listing", "base_url": "https://ai.meta.com/blog/"},
    {"kind": "html_listing", "base_url": "https://developers.openai.com/resources"},
    {"kind": "html_listing", "base_url": "https://www.llamaindex.ai/blog"},
]


def main() -> None:
    parser = argparse.ArgumentParser(description="Bootstrap the ai_research source set directly into the context_api database.")
    parser.add_argument("--topic-key", default="ai_research")
    parser.add_argument("--enqueue-run", action="store_true")
    parser.add_argument("--run-idempotency-key", default="bootstrap-ai-research-sources")
    parser.add_argument("--max-items-per-run", type=int, default=25)
    parser.add_argument("--rate-limit-per-hour", type=int, default=60)
    parser.add_argument("--poll-interval-minutes", type=int, default=240)
    parser.add_argument(
        "--disable-private-sources",
        action="store_true",
        help="Disable enabled loopback or private-address sources for this topic",
    )
    args = parser.parse_args()

    database_url = os.getenv("DATABASE_URL", "").strip()
    if not database_url:
        raise RuntimeError("DATABASE_URL is not set")

    topic_key = args.topic_key.strip().lower()
    engine = create_db_engine(database_url)
    source_ids: list[str] = []
    for source in CURATED_SOURCES:
        source_id = compute_source_id(topic_key=topic_key, kind=str(source["kind"]), base_url=str(source["base_url"]))
        source_ids.append(source_id)
        result = upsert_research_source(
            engine,
            source_id=source_id,
            topic_key=topic_key,
            kind=str(source["kind"]),
            name=str(source["name"]),
            base_url_original=str(source["base_url"]),
            base_url_canonical=str(source["base_url"]),
            enabled=True,
            tags=list(source["tags"]),
            publisher_type=str(source["publisher_type"]),
            source_class=str(source["source_class"]),
            default_decision_domains=list(source["default_decision_domains"]),
            poll_interval_minutes=max(args.poll_interval_minutes, 15),
            rate_limit_per_hour=max(args.rate_limit_per_hour, 1),
            robots_mode="strict",
            max_items_per_run=max(args.max_items_per_run, 1),
            source_weight=1.0 if str(source["source_class"]) == "external_primary" else 0.8 if str(source["source_class"]) == "external_secondary" else 0.6,
        )
        print({"name": source["name"], "source_id": source_id, "status": result["status"]})

    for source in REPLACED_SOURCES:
        legacy_id = compute_source_id(
            topic_key=topic_key,
            kind=source["kind"],
            base_url=source["base_url"],
        )
        if legacy_id not in source_ids and set_research_source_enabled(engine, source_id=legacy_id, enabled=False):
            print({"source_id": legacy_id, "status": "disabled-replaced"})

    if args.disable_private_sources:
        for source in list_research_sources(engine, topic_key=topic_key, enabled_only=True):
            base_url = str(source.get("base_url_canonical") or source.get("base_url_original") or "")
            if is_private_source_url(base_url):
                set_research_source_enabled(engine, source_id=str(source["source_id"]), enabled=False)
                print({"source_id": str(source["source_id"]), "status": "disabled-private"})

    if args.enqueue_run:
        run = create_research_ingestion_run(
            engine,
            topic_key=topic_key,
            trigger="manual",
            requested_source_ids=source_ids,
            selected_source_ids=source_ids,
            idempotency_key=args.run_idempotency_key,
        )
        print({"topic_key": topic_key, "run_id": str(run["run_id"]), "status": run["status"], "sources_selected": len(source_ids)})


if __name__ == "__main__":
    main()
