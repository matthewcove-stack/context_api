from __future__ import annotations

import os
import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal, cast

from mcp.server.fastmcp import FastMCP

from app.mcp_bridge.client import BridgeClientError, ContextApiBridgeClient
from app.mcp_bridge.contracts import (
    DecisionSearchToolResponse,
    EvidenceToolResponse,
    RelatedEvidenceToolResponse,
    CompareEvidenceToolResponse,
    DomainSummaryToolResponse,
    FetchChunk,
    FetchToolRequest,
    FetchToolResponse,
    SearchCitation,
    SearchResultItem,
    SearchScoreBreakdown,
    SearchSignal,
    SearchToolRequest,
    SearchToolResponse,
    TopicDetailToolResponse,
    TopicDocument,
    TopicDocumentsToolResponse,
    TopicSearchToolResponse,
    TopicSummarizeToolResponse,
    TopicSummary,
    WeeklyDigestToolResponse,
)
from app.research.contracts import ResearchChunkSearchRequest, ResearchContextPackRequest, ResearchTopicSummarizeRequest


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
        items.append(_map_search_item(item))
    return SearchToolResponse(
        retrieval_confidence=response.retrieval_confidence,
        next_action=response.next_action,
        trace_id=response.trace.trace_id,
        retrieved_document_ids=response.trace.retrieved_document_ids,
        timing_ms=response.trace.timing_ms,
        embedding_model_id=response.trace.embedding_model_id,
        embedding_mode=response.trace.embedding_mode,
        embedding_warning=response.trace.embedding_warning,
        items=items,
    )


def _map_search_item(item) -> SearchResultItem:
    return SearchResultItem(
        document_id=item.document_id,
        source_id=item.source_id,
        title=item.title,
        canonical_url=item.canonical_url,
        published_at=item.published_at,
        summary=item.summary,
        content_type=item.content_type,
        publisher_type=item.publisher_type,
        source_class=item.source_class,
        topic_tags=list(item.topic_tags),
        decision_domains=list(item.decision_domains),
        metrics=[metric.model_dump(mode="json") for metric in item.metrics],
        notable_quotes=[quote.model_dump(mode="json") for quote in item.notable_quotes],
        tradeoffs=[tradeoff.model_dump(mode="json") for tradeoff in item.tradeoffs],
        recommendations=[recommendation.model_dump(mode="json") for recommendation in item.recommendations],
        document_signal_score=item.document_signal_score,
        evidence_quality=item.evidence_quality,
        corroboration_count=item.corroboration_count,
        contradiction_count=item.contradiction_count,
        freshness_score=item.freshness_score,
        coverage_score=item.coverage_score,
        problem_tags=list(item.problem_tags),
        intervention_tags=list(item.intervention_tags),
        tradeoff_dimensions=list(item.tradeoff_dimensions),
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


def _map_fetch_response(response) -> FetchToolResponse:
    return FetchToolResponse(
        document_id=response.document_id,
        chunks=[
            FetchChunk(
                chunk_id=chunk.chunk_id,
                snippet=chunk.snippet,
                score=chunk.score,
                heading_path=list(chunk.heading_path),
            )
            for chunk in response.chunks
        ],
    )


def _map_topic_summary(item) -> TopicSummary:
    return TopicSummary(
        topic_key=item.topic_key,
        label=item.label,
        description=item.description,
        source_count=item.source_count,
        document_count=item.document_count,
        embedded_document_count=item.embedded_document_count,
        last_published_at=item.last_published_at,
        last_ingested_at=item.last_ingested_at,
    )


def _map_topic_document(item) -> TopicDocument:
    return TopicDocument(
        document_id=item.document_id,
        source_id=item.source_id,
        title=item.title,
        canonical_url=item.canonical_url,
        published_at=item.published_at,
        summary=item.summary,
        content_type=item.content_type,
        publisher_type=item.publisher_type,
        source_class=item.source_class,
        topic_tags=list(item.topic_tags),
        decision_domains=list(item.decision_domains),
        metrics=[metric.model_dump(mode="json") for metric in item.metrics],
        notable_quotes=[quote.model_dump(mode="json") for quote in item.notable_quotes],
        citations=[
            SearchCitation(document_id=c.document_id, chunk_id=c.chunk_id)
            for c in item.citations
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
    intent_mode: str | None = None,
    decision_domain: str | None = None,
    content_types: list[str] | None = None,
    source_classes: list[str] | None = None,
    publisher_types: list[str] | None = None,
    must_have: list[str] | None = None,
    exclude_content_types: list[str] | None = None,
    sort_mode: str | None = None,
    evidence_types: list[str] | None = None,
    problem_tags: list[str] | None = None,
    intervention_tags: list[str] | None = None,
    tradeoff_dimensions: list[str] | None = None,
    corpus_preference: str | None = None,
    relation_intent: str | None = None,
    source_trust_min: float | None = None,
    coverage_bias: str | None = None,
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
        intent_mode=intent_mode,
        decision_domain=decision_domain,
        content_types=content_types or [],
        source_classes=source_classes or [],
        publisher_types=publisher_types or [],
        must_have=must_have or [],
        exclude_content_types=exclude_content_types or [],
        sort_mode=sort_mode,
        evidence_types=evidence_types or [],
        problem_tags=problem_tags or [],
        intervention_tags=intervention_tags or [],
        tradeoff_dimensions=tradeoff_dimensions or [],
        corpus_preference=corpus_preference,
        relation_intent=relation_intent,
        source_trust_min=source_trust_min,
        coverage_bias=coverage_bias,
    )
    payload = ResearchContextPackRequest(
        query=request.query,
        topic_key=request.topic_key,
        source_ids=request.source_ids,
        token_budget=request.token_budget,
        recency_days=request.recency_days,
        max_items=request.max_items,
        min_relevance_score=request.min_relevance_score,
        intent_mode=request.intent_mode or "general",
        decision_domain=request.decision_domain,
        content_types=request.content_types,
        source_classes=request.source_classes,
        publisher_types=request.publisher_types,
        must_have=request.must_have,
        exclude_content_types=request.exclude_content_types,
        sort_mode=request.sort_mode or "relevance",
        evidence_types=request.evidence_types,
        problem_tags=request.problem_tags,
        intervention_tags=request.intervention_tags,
        tradeoff_dimensions=request.tradeoff_dimensions,
        corpus_preference=request.corpus_preference or "mixed",
        relation_intent=request.relation_intent,
        source_trust_min=request.source_trust_min,
        coverage_bias=request.coverage_bias or "balanced",
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


@mcp.tool(
    name="list_topics",
    description="List available research topics with document counts and freshness metadata.",
)
def list_topics(limit: int = 20) -> dict:
    settings = _load_settings()
    try:
        with ContextApiBridgeClient(
            base_url=settings.context_api_base_url,
            token=settings.context_api_token,
            timeout_s=settings.timeout_s,
        ) as client:
            upstream = client.list_topics(limit=limit)
    except BridgeClientError as exc:
        raise ValueError(str(exc)) from exc
    return {"items": [_map_topic_summary(item).model_dump(mode="json") for item in upstream.items]}


@mcp.tool(
    name="search_topics",
    description="Find likely research topics from a natural-language query.",
)
def search_topics(query: str, limit: int = 10) -> dict:
    settings = _load_settings()
    try:
        with ContextApiBridgeClient(
            base_url=settings.context_api_base_url,
            token=settings.context_api_token,
            timeout_s=settings.timeout_s,
        ) as client:
            upstream = client.search_topics(query=query, limit=limit)
    except BridgeClientError as exc:
        raise ValueError(str(exc)) from exc
    return TopicSearchToolResponse(
        query=upstream.query,
        items=[_map_topic_summary(item) for item in upstream.items],
    ).model_dump(mode="json")


@mcp.tool(
    name="describe_topic",
    description="Inspect a topic's coverage, top sources, themes, and suggested starter queries.",
)
def describe_topic(topic_key: str) -> dict:
    settings = _load_settings()
    try:
        with ContextApiBridgeClient(
            base_url=settings.context_api_base_url,
            token=settings.context_api_token,
            timeout_s=settings.timeout_s,
        ) as client:
            upstream = client.describe_topic(topic_key=topic_key)
    except BridgeClientError as exc:
        raise ValueError(str(exc)) from exc
    return TopicDetailToolResponse(
        topic_key=upstream.topic_key,
        label=upstream.label,
        description=upstream.description,
        source_count=upstream.source_count,
        document_count=upstream.document_count,
        embedded_document_count=upstream.embedded_document_count,
        last_published_at=upstream.last_published_at,
        last_ingested_at=upstream.last_ingested_at,
        top_sources=[item.model_dump(mode="json") for item in upstream.top_sources],
        top_themes=[item.model_dump(mode="json") for item in upstream.top_themes],
        suggested_queries=list(upstream.suggested_queries),
    ).model_dump(mode="json")


@mcp.tool(
    name="list_documents",
    description="List recent documents for a topic to inspect the corpus before deeper retrieval.",
)
def list_documents(topic_key: str, limit: int = 10, sort: str = "recent") -> dict:
    settings = _load_settings()
    try:
        with ContextApiBridgeClient(
            base_url=settings.context_api_base_url,
            token=settings.context_api_token,
            timeout_s=settings.timeout_s,
        ) as client:
            upstream = client.list_topic_documents(topic_key=topic_key, limit=limit, sort=sort)
    except BridgeClientError as exc:
        raise ValueError(str(exc)) from exc
    return TopicDocumentsToolResponse(
        topic_key=upstream.topic_key,
        items=[_map_topic_document(item) for item in upstream.items],
    ).model_dump(mode="json")


@mcp.tool(
    name="summarize_topic",
    description="Synthesize a topic into themes, suggested follow-up queries, and cited representative documents.",
)
def summarize_topic(topic_key: str, focus: str | None = None, recency_days: int | None = None, max_items: int = 5) -> dict:
    settings = _load_settings()
    payload = ResearchTopicSummarizeRequest(
        focus=focus,
        recency_days=recency_days,
        max_items=max_items,
    )
    try:
        with ContextApiBridgeClient(
            base_url=settings.context_api_base_url,
            token=settings.context_api_token,
            timeout_s=settings.timeout_s,
        ) as client:
            upstream = client.summarize_topic(topic_key=topic_key, payload=payload)
    except BridgeClientError as exc:
        raise ValueError(str(exc)) from exc
    return TopicSummarizeToolResponse(
        topic_key=upstream.topic_key,
        focus=upstream.focus,
        synthesis=upstream.synthesis,
        themes=[item.model_dump(mode="json") for item in upstream.themes],
        suggested_queries=list(upstream.suggested_queries),
        items=[_map_topic_document(item) for item in upstream.items],
        citations=[
            SearchCitation(document_id=c.document_id, chunk_id=c.chunk_id)
            for c in upstream.citations
        ],
    ).model_dump(mode="json")


@mcp.tool(
    name="decision_search",
    description="Return a decision-oriented pack with recommended approach, tradeoffs, and cited supporting evidence.",
)
def decision_search(
    query: str,
    topic_key: str,
    decision_domain: str = "",
    recency_days: int | None = None,
    max_items: int = 6,
) -> dict:
    settings = _load_settings()
    payload = ResearchContextPackRequest(
        query=query,
        topic_key=topic_key,
        decision_domain=decision_domain or None,
        recency_days=recency_days,
        max_items=max_items,
        intent_mode="decision_support",
        sort_mode="signal",
        must_have=["recommendations"],
    )
    try:
        with ContextApiBridgeClient(
            base_url=settings.context_api_base_url,
            token=settings.context_api_token,
            timeout_s=settings.timeout_s,
        ) as client:
            upstream = client.decision_pack(payload)
    except BridgeClientError as exc:
        raise ValueError(str(exc)) from exc
    return DecisionSearchToolResponse(
        query=upstream.query,
        topic_key=upstream.topic_key,
        decision_domain=upstream.decision_domain,
        recommended_approach=upstream.recommended_approach,
        alternatives=[item.model_dump(mode="json") for item in upstream.alternatives],
        tradeoffs=[item.model_dump(mode="json") for item in upstream.tradeoffs],
        risks=[item.model_dump(mode="json") for item in upstream.risks],
        workflow_recommendations=[item.model_dump(mode="json") for item in upstream.workflow_recommendations],
        implementation_notes=list(upstream.implementation_notes),
        supporting_evidence=[_map_search_item(item) for item in upstream.supporting_evidence],
        open_questions=list(upstream.open_questions),
        confidence=upstream.confidence,
        trace_id=upstream.trace.trace_id,
        timing_ms=upstream.trace.timing_ms,
    ).model_dump(mode="json")


@mcp.tool(
    name="weekly_digest",
    description="Return weekly digest clusters with top quotes, metrics, and citations for editorial synthesis.",
)
def weekly_digest(topic_key: str, days: int = 7, limit: int = 5) -> dict:
    settings = _load_settings()
    try:
        with ContextApiBridgeClient(
            base_url=settings.context_api_base_url,
            token=settings.context_api_token,
            timeout_s=settings.timeout_s,
        ) as client:
            upstream = client.weekly_digest(topic_key=topic_key, days=days, limit=limit)
    except BridgeClientError as exc:
        raise ValueError(str(exc)) from exc
    return WeeklyDigestToolResponse(
        topic_key=upstream.topic_key,
        days=upstream.days,
        items=[item.model_dump(mode="json") for item in upstream.items],
    ).model_dump(mode="json")


@mcp.tool(
    name="domain_summary",
    description="Summarize evidence-backed recommendations and tradeoffs for a decision domain.",
)
def domain_summary(topic_key: str, decision_domain: str) -> dict:
    settings = _load_settings()
    try:
        with ContextApiBridgeClient(
            base_url=settings.context_api_base_url,
            token=settings.context_api_token,
            timeout_s=settings.timeout_s,
        ) as client:
            upstream = client.domain_summary(topic_key=topic_key, decision_domain=decision_domain)
    except BridgeClientError as exc:
        raise ValueError(str(exc)) from exc
    return DomainSummaryToolResponse(
        topic_key=upstream.topic_key,
        decision_domain=upstream.decision_domain,
        summary=upstream.summary,
        recommendations=[item.model_dump(mode="json") for item in upstream.recommendations],
        tradeoffs=[item.model_dump(mode="json") for item in upstream.tradeoffs],
        workflow_patterns=list(upstream.workflow_patterns),
        citations=[SearchCitation(document_id=c.document_id, chunk_id=c.chunk_id) for c in upstream.citations],
    ).model_dump(mode="json")


@mcp.tool(
    name="search_evidence",
    description="Search normalized evidence items with citations, trust, and coverage metadata.",
)
def search_evidence(
    query: str,
    topic_key: str,
    evidence_types: list[str] | None = None,
    problem_tags: list[str] | None = None,
    intervention_tags: list[str] | None = None,
    tradeoff_dimensions: list[str] | None = None,
    corpus_preference: str = "mixed",
    source_trust_min: float | None = None,
    recency_days: int | None = None,
    max_items: int = 6,
) -> dict:
    settings = _load_settings()
    payload = ResearchContextPackRequest(
        query=query,
        topic_key=topic_key,
        evidence_types=evidence_types or [],
        problem_tags=problem_tags or [],
        intervention_tags=intervention_tags or [],
        tradeoff_dimensions=tradeoff_dimensions or [],
        corpus_preference=cast(Literal["internal", "external", "mixed"], corpus_preference if corpus_preference in {"internal", "external", "mixed"} else "mixed"),
        source_trust_min=source_trust_min,
        recency_days=recency_days,
        max_items=max_items,
    )
    try:
        with ContextApiBridgeClient(
            base_url=settings.context_api_base_url,
            token=settings.context_api_token,
            timeout_s=settings.timeout_s,
        ) as client:
            upstream = client.search_evidence(payload)
    except BridgeClientError as exc:
        raise ValueError(str(exc)) from exc
    return EvidenceToolResponse(
        query=upstream.query,
        topic_key=upstream.topic_key,
        contradictions_present=upstream.contradictions_present,
        coverage_summary=upstream.coverage_summary,
        trace_id=upstream.trace.trace_id,
        timing_ms=upstream.trace.timing_ms,
        items=[item.model_dump(mode="json") for item in upstream.items],
    ).model_dump(mode="json")


@mcp.tool(
    name="related_evidence",
    description="Fetch supporting, conflicting, or generally related evidence for a query.",
)
def related_evidence(
    query: str,
    topic_key: str,
    relation_intent: str = "related",
    evidence_types: list[str] | None = None,
    problem_tags: list[str] | None = None,
    intervention_tags: list[str] | None = None,
    max_items: int = 6,
) -> dict:
    settings = _load_settings()
    payload = ResearchContextPackRequest(
        query=query,
        topic_key=topic_key,
        relation_intent=cast(Literal["supporting", "conflicting", "related"], relation_intent if relation_intent in {"supporting", "conflicting", "related"} else "related"),
        evidence_types=evidence_types or [],
        problem_tags=problem_tags or [],
        intervention_tags=intervention_tags or [],
        max_items=max_items,
    )
    try:
        with ContextApiBridgeClient(
            base_url=settings.context_api_base_url,
            token=settings.context_api_token,
            timeout_s=settings.timeout_s,
        ) as client:
            upstream = client.related_evidence(payload)
    except BridgeClientError as exc:
        raise ValueError(str(exc)) from exc
    return RelatedEvidenceToolResponse(
        topic_key=upstream.topic_key,
        relation_intent=upstream.relation_intent,
        seed_items=[item.model_dump(mode="json") for item in upstream.seed_items],
        related_items=[item.model_dump(mode="json") for item in upstream.related_items],
        relations=[item.model_dump(mode="json") for item in upstream.relations],
        coverage_summary=upstream.coverage_summary,
    ).model_dump(mode="json")


@mcp.tool(
    name="supporting_evidence",
    description="Convenience wrapper that returns evidence supporting the seed results for a query.",
)
def supporting_evidence(
    query: str,
    topic_key: str,
    evidence_types: list[str] | None = None,
    problem_tags: list[str] | None = None,
    intervention_tags: list[str] | None = None,
    max_items: int = 6,
) -> dict:
    return related_evidence(
        query=query,
        topic_key=topic_key,
        relation_intent="supporting",
        evidence_types=evidence_types,
        problem_tags=problem_tags,
        intervention_tags=intervention_tags,
        max_items=max_items,
    )


@mcp.tool(
    name="conflicting_evidence",
    description="Convenience wrapper that returns evidence contradicting or superseding the seed results for a query.",
)
def conflicting_evidence(
    query: str,
    topic_key: str,
    evidence_types: list[str] | None = None,
    problem_tags: list[str] | None = None,
    intervention_tags: list[str] | None = None,
    max_items: int = 6,
) -> dict:
    return related_evidence(
        query=query,
        topic_key=topic_key,
        relation_intent="conflicting",
        evidence_types=evidence_types,
        problem_tags=problem_tags,
        intervention_tags=intervention_tags,
        max_items=max_items,
    )


@mcp.tool(
    name="compare_evidence",
    description="Compare competing evidence clusters, tradeoffs, and contradiction signals for a query.",
)
def compare_evidence(
    query: str,
    topic_key: str,
    problem_tags: list[str] | None = None,
    intervention_tags: list[str] | None = None,
    tradeoff_dimensions: list[str] | None = None,
    max_items: int = 6,
) -> dict:
    settings = _load_settings()
    payload = ResearchContextPackRequest(
        query=query,
        topic_key=topic_key,
        problem_tags=problem_tags or [],
        intervention_tags=intervention_tags or [],
        tradeoff_dimensions=tradeoff_dimensions or [],
        max_items=max_items,
    )
    try:
        with ContextApiBridgeClient(
            base_url=settings.context_api_base_url,
            token=settings.context_api_token,
            timeout_s=settings.timeout_s,
        ) as client:
            upstream = client.compare_evidence(payload)
    except BridgeClientError as exc:
        raise ValueError(str(exc)) from exc
    return CompareEvidenceToolResponse(
        query=upstream.query,
        topic_key=upstream.topic_key,
        clusters=[item.model_dump(mode="json") for item in upstream.clusters],
        overall_tradeoffs=upstream.overall_tradeoffs,
        contradictions_present=upstream.contradictions_present,
        coverage_summary=upstream.coverage_summary,
        trace_id=upstream.trace.trace_id,
        timing_ms=upstream.trace.timing_ms,
    ).model_dump(mode="json")


@mcp.tool(
    name="inspect_coverage",
    description="Inspect evidence quality and corpus coverage signals for a query without a task-specific wrapper.",
)
def inspect_coverage(
    query: str,
    topic_key: str,
    evidence_types: list[str] | None = None,
    problem_tags: list[str] | None = None,
    intervention_tags: list[str] | None = None,
    max_items: int = 6,
) -> dict:
    return search_evidence(
        query=query,
        topic_key=topic_key,
        evidence_types=evidence_types,
        problem_tags=problem_tags,
        intervention_tags=intervention_tags,
        max_items=max_items,
    )


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
            "tools": ["search", "fetch", "search_evidence", "related_evidence", "supporting_evidence", "conflicting_evidence", "compare_evidence", "inspect_coverage", "list_topics", "search_topics", "describe_topic", "list_documents", "summarize_topic", "decision_search", "weekly_digest", "domain_summary"],
        }
    )


def run_server(*, transport: str | None = None) -> None:
    settings = _load_settings()
    selected_transport = _parse_transport(transport) if transport else settings.transport
    mcp.run(transport=selected_transport)


if __name__ == "__main__":
    run_server()
