from __future__ import annotations

import pytest

from app.mcp_bridge.client import BridgeClientError
from app.mcp_bridge.server import (
    BridgeRuntimeSettings,
    compare_evidence,
    describe_topic,
    conflicting_evidence,
    inspect_coverage,
    list_documents,
    list_topics,
    related_evidence,
    search,
    search_evidence,
    search_topics,
    supporting_evidence,
    summarize_topic,
)
from app.research.contracts import (
    ResearchCitation,
    ResearchEvidenceCompareCluster,
    ResearchEvidenceCompareResponse,
    ResearchEvidenceItem,
    ResearchEvidenceRelatedResponse,
    ResearchEvidenceRelation,
    ResearchEvidenceSearchResponse,
    ResearchContextPack,
    ResearchContextPackItem,
    ResearchContextPackResponse,
    ResearchContextPackTrace,
    ResearchScoreBreakdown,
    ResearchSignal,
)


class _FakeClient:
    def __init__(self, **_kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        return None

    def search(self, _payload):
        citation = ResearchCitation(document_id="doc_1", chunk_id="chk_1")
        return ResearchContextPackResponse(
            pack=ResearchContextPack(
                items=[
                    ResearchContextPackItem(
                        document_id="doc_1",
                        source_id="src_1",
                        title="Architecture Patterns",
                        canonical_url="https://example.com/doc-1",
                        summary="Use evaluation loops for AI-assisted delivery.",
                        signals=[ResearchSignal(claim="Use evaluation loops.", why="Cited best practice.", cite=citation)],
                        citations=[citation],
                        score_breakdown=ResearchScoreBreakdown(total=0.9, lexical=0.7, embedding=0.8, recency=0.6, source_weight=0.5),
                    )
                ]
            ),
            retrieval_confidence="high",
            next_action="proceed",
            trace=ResearchContextPackTrace(
                trace_id="trace_1",
                retrieved_document_ids=["doc_1"],
                timing_ms={"total": 12},
                embedding_model_id="text-embedding-3-small",
                embedding_mode="openai",
            ),
        )

    def search_evidence(self, _payload):
        citation = ResearchCitation(document_id="doc_1", chunk_id="chk_1")
        item = ResearchEvidenceItem(
            insight_id="ins_1",
            document_id="doc_1",
            chunk_id="chk_1",
            evidence_type="decision_pattern",
            text="drift -> add checkpoints",
            normalized_payload={"problem_type": "drift", "candidate_intervention": "add checkpoints"},
            canonical_url="https://example.com/doc-1",
            title="Architecture Patterns",
            source_id="src_1",
            source_class="external_primary",
            publisher_type="vendor",
            topic_tags=["delivery"],
            problem_tags=["drift"],
            intervention_tags=["increase_checkpoints"],
            tradeoff_dimensions=["speed_vs_control"],
            confidence=0.8,
            evidence_strength=0.78,
            source_trust_tier=0.85,
            internal_coverage_score=0.0,
            external_coverage_score=1.0,
            evidence_quality=0.81,
            coverage_score=0.74,
            citation=citation,
        )
        return ResearchEvidenceSearchResponse(
            query="drift",
            topic_key="ai_delivery",
            items=[item],
            contradictions_present=False,
            coverage_summary={"mean_evidence_quality": 0.81},
            trace=ResearchContextPackTrace(
                trace_id="trace_e_1",
                retrieved_document_ids=["doc_1"],
                timing_ms={"total": 9},
                embedding_model_id="text-embedding-3-small",
                embedding_mode="openai",
            ),
        )

    def related_evidence(self, _payload):
        seed = self.search_evidence(_payload).items
        related = [
            ResearchEvidenceItem(
                insight_id="ins_2",
                document_id="doc_1",
                chunk_id="chk_1",
                evidence_type="tradeoff",
                text="More checkpoints slow throughput.",
                normalized_payload={"tradeoff": "speed_vs_control"},
                canonical_url="https://example.com/doc-1",
                title="Architecture Patterns",
                source_id="src_1",
                source_class="external_primary",
                publisher_type="vendor",
                tradeoff_dimensions=["speed_vs_control"],
                confidence=0.7,
                evidence_strength=0.68,
                source_trust_tier=0.85,
                internal_coverage_score=0.0,
                external_coverage_score=1.0,
                evidence_quality=0.7,
                coverage_score=0.6,
                citation=ResearchCitation(document_id="doc_1", chunk_id="chk_1"),
            )
        ]
        relation = ResearchEvidenceRelation(
            relation_id="rel_1",
            relation_type="refines",
            confidence=0.62,
            explanation="Tradeoff refines recommendation context.",
            from_insight_id="ins_1",
            to_insight_id="ins_2",
        )
        return ResearchEvidenceRelatedResponse(
            topic_key="ai_delivery",
            relation_intent=getattr(_payload, "relation_intent", None) or "related",
            seed_items=seed,
            related_items=related,
            relations=[relation],
            coverage_summary={"seed_count": 1.0, "related_count": 1.0},
        )

    def compare_evidence(self, _payload):
        cluster = ResearchEvidenceCompareCluster(
            label="drift",
            items=self.search_evidence(_payload).items,
            strongest_support=["drift -> add checkpoints"],
            strongest_contradictions=[],
            tradeoffs=["speed_vs_control"],
            coverage_score=0.74,
            confidence="high",
        )
        return ResearchEvidenceCompareResponse(
            query="drift",
            topic_key="ai_delivery",
            clusters=[cluster],
            overall_tradeoffs=["speed_vs_control"],
            contradictions_present=False,
            coverage_summary={"cluster_count": 1.0},
            trace=ResearchContextPackTrace(
                trace_id="trace_cmp_1",
                retrieved_document_ids=["doc_1"],
                timing_ms={"total": 11},
                embedding_model_id="text-embedding-3-small",
                embedding_mode="openai",
            ),
        )

    def list_topics(self, *, limit: int = 20):
        return type(
            "Resp",
            (),
            {
                "items": [
                    type(
                        "Item",
                        (),
                        {
                            "topic_key": "ai_delivery",
                            "label": "AI Delivery",
                            "description": "Research corpus for AI delivery.",
                            "source_count": 2,
                            "document_count": 4,
                            "embedded_document_count": 4,
                            "last_published_at": None,
                            "last_ingested_at": None,
                        },
                    )()
                ][:limit]
            },
        )()

    def search_topics(self, *, query: str, limit: int = 10):
        return type("Resp", (), {"query": query, "items": self.list_topics(limit=limit).items})()

    def describe_topic(self, *, topic_key: str):
        return type(
            "Resp",
            (),
            {
                "topic_key": topic_key,
                "label": "AI Delivery",
                "description": "Research corpus for AI delivery.",
                "source_count": 2,
                "document_count": 4,
                "embedded_document_count": 4,
                "last_published_at": None,
                "last_ingested_at": None,
                "top_sources": [],
                "top_themes": [],
                "suggested_queries": ["best practices for ai delivery"],
            },
        )()

    def list_topic_documents(self, *, topic_key: str, limit: int = 10, sort: str = "recent"):
        item = type(
            "Item",
            (),
            {
                "document_id": "doc_1",
                "source_id": "src_1",
                "title": f"{topic_key} {sort}",
                "canonical_url": "https://example.com/doc-1",
                "published_at": None,
                "summary": "Representative document.",
                "content_type": "company_blog",
                "publisher_type": "vendor",
                "source_class": "external_primary",
                "topic_tags": ["delivery"],
                "decision_domains": ["retrieval"],
                "metrics": [],
                "notable_quotes": [],
                "citations": [],
            },
        )()
        return type("Resp", (), {"topic_key": topic_key, "items": [item][:limit]})()

    def summarize_topic(self, *, topic_key: str, payload):
        citation = ResearchCitation(document_id="doc_1", chunk_id="chk_1")
        item = type(
            "Item",
            (),
            {
                "document_id": "doc_1",
                "source_id": "src_1",
                "title": "Representative document",
                "canonical_url": "https://example.com/doc-1",
                "published_at": None,
                "summary": "Representative summary.",
                "content_type": "company_blog",
                "publisher_type": "vendor",
                "source_class": "external_primary",
                "topic_tags": ["delivery"],
                "decision_domains": ["retrieval"],
                "metrics": [],
                "notable_quotes": [],
                "citations": [citation],
            },
        )()
        theme = type("Theme", (), {"model_dump": lambda self, mode="json": {"name": "evaluation", "score": 4.0}})()
        return type(
            "Resp",
            (),
            {
                "topic_key": topic_key,
                "focus": payload.focus,
                "synthesis": "Evaluation loops and human review recur across the topic.",
                "themes": [theme],
                "suggested_queries": ["evaluation loops"],
                "items": [item],
                "citations": [citation],
            },
        )()


def test_bridge_tools_expose_discovery_and_embedding_metadata(monkeypatch) -> None:
    monkeypatch.setattr(
        "app.mcp_bridge.server._load_settings",
        lambda: BridgeRuntimeSettings(
            context_api_base_url="http://context-api.local",
            context_api_token="token",
            timeout_s=10.0,
            transport="stdio",
        ),
    )
    monkeypatch.setattr("app.mcp_bridge.server.ContextApiBridgeClient", _FakeClient)

    search_result = search(query="ai delivery", topic_key="ai_delivery")
    assert search_result["embedding_model_id"] == "text-embedding-3-small"
    assert search_result["embedding_mode"] == "openai"

    topics = list_topics(limit=5)
    assert topics["items"][0]["topic_key"] == "ai_delivery"

    searched = search_topics(query="delivery", limit=5)
    assert searched["query"] == "delivery"

    described = describe_topic("ai_delivery")
    assert described["topic_key"] == "ai_delivery"

    documents = list_documents("ai_delivery", limit=2)
    assert documents["items"][0]["document_id"] == "doc_1"

    summary = summarize_topic("ai_delivery", focus="architecture", max_items=2)
    assert summary["synthesis"]
    assert summary["citations"]

    evidence = search_evidence(query="drift", topic_key="ai_delivery", problem_tags=["drift"])
    assert evidence["items"][0]["problem_tags"] == ["drift"]

    related = related_evidence(query="drift", topic_key="ai_delivery")
    assert related["relations"][0]["relation_type"] == "refines"

    supporting = supporting_evidence(query="drift", topic_key="ai_delivery")
    assert supporting["relation_intent"] == "supporting"

    conflicting = conflicting_evidence(query="drift", topic_key="ai_delivery")
    assert conflicting["relation_intent"] == "conflicting"

    compared = compare_evidence(query="drift", topic_key="ai_delivery")
    assert compared["overall_tradeoffs"] == ["speed_vs_control"]

    coverage = inspect_coverage(query="drift", topic_key="ai_delivery")
    assert coverage["coverage_summary"]["mean_evidence_quality"] == 0.81


def test_bridge_discovery_tools_map_client_failure(monkeypatch) -> None:
    class _FailingClient(_FakeClient):
        def describe_topic(self, *, topic_key: str):
            raise BridgeClientError(f"failed for {topic_key}")

    monkeypatch.setattr(
        "app.mcp_bridge.server._load_settings",
        lambda: BridgeRuntimeSettings(
            context_api_base_url="http://context-api.local",
            context_api_token="token",
            timeout_s=10.0,
            transport="stdio",
        ),
    )
    monkeypatch.setattr("app.mcp_bridge.server.ContextApiBridgeClient", _FailingClient)

    with pytest.raises(ValueError) as exc_info:
        describe_topic("ai_delivery")
    assert "failed for ai_delivery" in str(exc_info.value)
