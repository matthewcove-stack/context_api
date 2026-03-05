from __future__ import annotations

import os
import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal, cast

from mcp.server.fastmcp import FastMCP

from app.mcp_bridge.client import BridgeClientError, ContextApiBridgeClient
from app.mcp_bridge.contracts import (
    FetchChunk,
    FetchToolRequest,
    FetchToolResponse,
    SearchCitation,
    SearchResultItem,
    SearchScoreBreakdown,
    SearchSignal,
    SearchToolRequest,
    SearchToolResponse,
)
from app.research.contracts import ResearchChunkSearchRequest, ResearchContextPackRequest


@dataclass(frozen=True)
class BridgeRuntimeSettings:
    context_api_base_url: str
    context_api_token: str
    timeout_s: float
    transport: Literal["stdio", "sse"]


def _parse_transport(value: str) -> Literal["stdio", "sse"]:
    lowered = value.strip().lower()
    if lowered not in {"stdio", "sse"}:
        raise ValueError("MCP_BRIDGE_TRANSPORT must be either 'stdio' or 'sse'")
    return cast(Literal["stdio", "sse"], lowered)


@lru_cache(maxsize=1)
def _load_settings() -> BridgeRuntimeSettings:
    token = os.getenv("CONTEXT_API_TOKEN", "").strip()
    if not token:
        raise ValueError("CONTEXT_API_TOKEN is required for MCP bridge")
    base_url = os.getenv("CONTEXT_API_BASE_URL", "http://localhost:8001").strip()
    if not base_url:
        raise ValueError("CONTEXT_API_BASE_URL cannot be empty")
    timeout_s = float(os.getenv("MCP_BRIDGE_TIMEOUT_S", "20").strip())
    if timeout_s <= 0:
        raise ValueError("MCP_BRIDGE_TIMEOUT_S must be greater than 0")
    transport = _parse_transport(os.getenv("MCP_BRIDGE_TRANSPORT", "stdio"))
    return BridgeRuntimeSettings(
        context_api_base_url=base_url,
        context_api_token=token,
        timeout_s=timeout_s,
        transport=transport,
    )


def _map_search_response(response) -> SearchToolResponse:
    items = []
    for item in response.pack.items:
        items.append(
            SearchResultItem(
                document_id=item.document_id,
                source_id=item.source_id,
                title=item.title,
                canonical_url=item.canonical_url,
                published_at=item.published_at,
                summary=item.summary,
                signals=[
                    SearchSignal(
                        claim=signal.claim,
                        why=signal.why,
                        cite=SearchCitation(
                            document_id=signal.cite.document_id,
                            chunk_id=signal.cite.chunk_id,
                        ),
                    )
                    for signal in item.signals
                ],
                citations=[
                    SearchCitation(
                        document_id=citation.document_id,
                        chunk_id=citation.chunk_id,
                    )
                    for citation in item.citations
                ],
                score_breakdown=SearchScoreBreakdown(
                    total=item.score_breakdown.total,
                    lexical=item.score_breakdown.lexical,
                    embedding=item.score_breakdown.embedding,
                    recency=item.score_breakdown.recency,
                    source_weight=item.score_breakdown.source_weight,
                ),
            )
        )
    return SearchToolResponse(
        retrieval_confidence=response.retrieval_confidence,
        next_action=response.next_action,
        trace_id=response.trace.trace_id,
        retrieved_document_ids=response.trace.retrieved_document_ids,
        timing_ms=response.trace.timing_ms,
        items=items,
    )


def _map_fetch_response(response) -> FetchToolResponse:
    return FetchToolResponse(
        document_id=response.document_id,
        chunks=[
            FetchChunk(
                chunk_id=chunk.chunk_id,
                snippet=chunk.snippet,
                score=chunk.score,
            )
            for chunk in response.chunks
        ],
    )


mcp = FastMCP("context-api-research-bridge")


@mcp.tool(
    name="search",
    description=(
        "Search topic-scoped research context and return bounded citation-first results "
        "with confidence and next action guidance."
    ),
)
def search(
    query: str,
    topic_key: str,
    source_ids: list[str] | None = None,
    token_budget: int | None = None,
    recency_days: int | None = None,
    max_items: int = 6,
    min_relevance_score: float | None = None,
) -> dict:
    settings = _load_settings()
    request = SearchToolRequest(
        query=query,
        topic_key=topic_key,
        source_ids=source_ids or [],
        token_budget=token_budget,
        recency_days=recency_days,
        max_items=max_items,
        min_relevance_score=min_relevance_score,
    )
    payload = ResearchContextPackRequest(
        query=request.query,
        topic_key=request.topic_key,
        source_ids=request.source_ids,
        token_budget=request.token_budget,
        recency_days=request.recency_days,
        max_items=request.max_items,
        min_relevance_score=request.min_relevance_score,
    )
    try:
        with ContextApiBridgeClient(
            base_url=settings.context_api_base_url,
            token=settings.context_api_token,
            timeout_s=settings.timeout_s,
        ) as client:
            upstream = client.search(payload)
    except BridgeClientError as exc:
        raise ValueError(str(exc)) from exc
    return _map_search_response(upstream).model_dump(mode="json")


@mcp.tool(
    name="fetch",
    description=(
        "Fetch chunk snippets for a specific document using a follow-up query for "
        "progressive disclosure."
    ),
)
def fetch(
    document_id: str,
    query: str,
    max_chunks: int = 6,
    max_chars: int = 600,
) -> dict:
    settings = _load_settings()
    request = FetchToolRequest(
        document_id=document_id,
        query=query,
        max_chunks=max_chunks,
        max_chars=max_chars,
    )
    payload = ResearchChunkSearchRequest(
        query=request.query,
        max_chunks=request.max_chunks,
        max_chars=request.max_chars,
    )
    try:
        with ContextApiBridgeClient(
            base_url=settings.context_api_base_url,
            token=settings.context_api_token,
            timeout_s=settings.timeout_s,
        ) as client:
            upstream = client.fetch_document_chunks(document_id=request.document_id, payload=payload)
    except BridgeClientError as exc:
        raise ValueError(str(exc)) from exc
    return _map_fetch_response(upstream).model_dump(mode="json")


@mcp.resource(
    "context-api://bridge/status",
    name="bridge_status",
    description="Bridge runtime status and target endpoint metadata.",
    mime_type="application/json",
)
def bridge_status() -> str:
    settings = _load_settings()
    return json.dumps(
        {
            "target_base_url": settings.context_api_base_url,
            "timeout_s": settings.timeout_s,
            "tools": ["search", "fetch"],
        }
    )


def run_server(*, transport: str | None = None) -> None:
    settings = _load_settings()
    selected_transport = _parse_transport(transport) if transport else settings.transport
    mcp.run(transport=selected_transport)


if __name__ == "__main__":
    run_server()
