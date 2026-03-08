from __future__ import annotations

import hashlib
import re
from collections import Counter
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse


_QUOTE_RE = re.compile(r"[\"“](.{20,240}?)[\"”]")
_NUMBER_RE = re.compile(r"(?P<value>\d+(?:\.\d+)?)\s*(?P<unit>%|x|ms|s|seconds|minutes|hours|days|users|commits|documents|papers|bugs)?", re.IGNORECASE)
_SENTENCE_RE = re.compile(r"(?<=[.!?])\s+")
_TOKEN_RE = re.compile(r"[a-z][a-z0-9_-]{3,}", re.IGNORECASE)
_STOPWORDS = {
    "about",
    "after",
    "also",
    "because",
    "being",
    "between",
    "could",
    "first",
    "have",
    "into",
    "more",
    "most",
    "other",
    "over",
    "should",
    "their",
    "there",
    "these",
    "this",
    "using",
    "when",
    "with",
}
_PROBLEM_TAG_KEYWORDS = {
    "drift": ("drift", "scope creep", "wander", "off track"),
    "context_overload": ("context overload", "too much context", "large context", "overload"),
    "unclear_requirements": ("unclear requirement", "ambiguous", "underspecified", "vague"),
    "unsafe_autonomy": ("unsafe autonomy", "over autonomous", "permission", "unguarded"),
    "tool_misuse": ("tool misuse", "wrong tool", "unsafe tool", "dangerous command"),
    "review_gap": ("review gap", "no review", "missing review", "unreviewed"),
    "eval_blind_spot": ("eval blind", "missing eval", "benchmark gap", "untested"),
}
_INTERVENTION_TAG_KEYWORDS = {
    "narrow_scope": ("narrow scope", "reduce scope", "smaller task", "constrain scope"),
    "increase_checkpoints": ("checkpoint", "check point", "milestone", "pause and review"),
    "tighten_permissions": ("tighten permission", "restrict tools", "sandbox", "approval"),
    "improve_spec": ("better spec", "clear spec", "requirement", "acceptance criteria"),
    "add_acceptance_tests": ("acceptance test", "add tests", "validation", "check"),
    "reduce_context_surface": ("reduce context", "smaller context", "less context", "focused context"),
    "increase_human_review": ("human review", "manual review", "review gate", "supervision"),
}
_TRADEOFF_DIMENSION_KEYWORDS = {
    "speed_vs_control": ("speed", "fast", "control", "guardrail"),
    "autonomy_vs_safety": ("autonomy", "safety", "permissions", "approval"),
    "iteration_vs_precision": ("iterate", "iteration", "precision", "exactness"),
    "review_cost": ("review cost", "human review", "approval burden"),
    "context_size": ("context size", "large context", "small context"),
    "repo_complexity": ("repo complexity", "monorepo", "legacy repo", "complex codebase"),
    "production_risk": ("production", "risk", "incident", "regression"),
}


def infer_published_at_confidence(*, published_at: Any, extraction_meta: Dict[str, Any], fetch_meta: Dict[str, Any]) -> float:
    if published_at:
        return 1.0
    if extraction_meta.get("published_at_source"):
        return 0.8
    if fetch_meta.get("last_modified"):
        return 0.5
    return 0.0


def infer_content_type(*, canonical_url: str, source_name: str, extracted_text: str) -> str:
    url_lower = canonical_url.lower()
    source_lower = source_name.lower()
    text_lower = extracted_text.lower()
    if "/pull/" in url_lower or "/pulls/" in url_lower:
        return "pr"
    if "/issues/" in url_lower:
        return "issue"
    if "rfc" in url_lower or "request for comments" in text_lower:
        return "rfc"
    if "postmortem" in url_lower or "incident" in text_lower:
        return "postmortem"
    if "arxiv" in url_lower or "abstract" in text_lower:
        return "paper"
    if "docs" in url_lower or "documentation" in source_lower:
        return "vendor_doc"
    if "benchmark" in text_lower:
        return "benchmark"
    if "policy" in url_lower:
        return "policy"
    if "guide" in url_lower or "how to" in text_lower:
        return "guide"
    return "company_blog"


def infer_publisher_type(*, canonical_url: str, source_class: str) -> str:
    if source_class.startswith("internal"):
        return "internal"
    host = urlparse(canonical_url).netloc.lower()
    if "arxiv" in host:
        return "academic"
    if any(part in host for part in ("openai.com", "anthropic.com", "google.com", "deepmind.com", "huggingface.co")):
        return "vendor"
    if any(part in host for part in ("techcrunch.com", "theverge.com", "wired.com")):
        return "media"
    return "independent"


def _split_sentences(text: str) -> List[str]:
    return [part.strip() for part in _SENTENCE_RE.split(text.strip()) if part.strip()]


def _top_terms(texts: List[str], *, limit: int = 6) -> List[str]:
    counts: Counter[str] = Counter()
    for text in texts:
        for token in _TOKEN_RE.findall(text.lower()):
            if token not in _STOPWORDS:
                counts[token] += 1
    return [token for token, _ in counts.most_common(limit)]


def _chunk_heading_tags(chunk: Dict[str, Any]) -> List[str]:
    meta = chunk.get("chunk_meta") or {}
    tags = list(meta.get("tags") or [])
    headings = list(meta.get("heading_path") or [])
    normalized = []
    for value in tags + headings:
        text = str(value).strip().lower()
        if text and text not in normalized:
            normalized.append(text)
    return normalized


def _match_tags(text: str, mapping: Dict[str, tuple[str, ...]]) -> List[str]:
    lowered = text.lower()
    matches: List[str] = []
    for tag, keywords in mapping.items():
        if any(keyword in lowered for keyword in keywords):
            matches.append(tag)
    return matches


def _source_trust_tier(source_class: str) -> float:
    if source_class == "internal_authoritative":
        return 1.0
    if source_class == "external_primary":
        return 0.85
    if source_class == "internal_working":
        return 0.75
    if source_class == "external_secondary":
        return 0.65
    return 0.45


def _classify_section_type(text: str, tags: List[str]) -> str:
    lowered = " ".join(tags + [text[:120].lower()])
    if "limitation" in lowered:
        return "limitations"
    if "result" in lowered or "benchmark" in lowered:
        return "results"
    if "tradeoff" in lowered:
        return "tradeoff"
    if "recommend" in lowered or "next step" in lowered:
        return "recommendation"
    if "implement" in lowered or "architecture" in lowered:
        return "implementation"
    if "discussion" in lowered:
        return "discussion"
    return "abstract"


def enrich_chunks(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    enriched: List[Dict[str, Any]] = []
    for chunk in chunks:
        content = str(chunk.get("content") or "").strip()
        if not content:
            continue
        meta = dict(chunk.get("chunk_meta") or {})
        tags = _chunk_heading_tags(chunk)
        quotes = _QUOTE_RE.findall(content)
        metrics = [match.groupdict() for match in _NUMBER_RE.finditer(content) if match.group("unit")]
        section_type = _classify_section_type(content, tags)
        meta.update(
            {
                "heading_path": list(meta.get("heading_path") or []),
                "section_type": section_type,
                "tags": tags,
                "contains_metric": bool(metrics),
                "contains_quote": bool(quotes),
                "contains_recommendation": "should " in content.lower() or "recommend" in content.lower(),
                "contains_tradeoff": "tradeoff" in content.lower() or "however" in content.lower(),
                "contains_code_or_config": "```" in content or "config" in content.lower(),
                "source_span_hash": hashlib.sha256(content[:300].encode("utf-8")).hexdigest(),
            }
        )
        next_chunk = dict(chunk)
        next_chunk["chunk_meta"] = meta
        enriched.append(next_chunk)
    return enriched


def enrich_document(
    *,
    canonical_url: str,
    source_name: str,
    source_class: str,
    default_decision_domains: List[str],
    extracted_text: str,
    chunks: List[Dict[str, Any]],
    fetch_meta: Dict[str, Any],
    extraction_meta: Dict[str, Any],
    published_at: Any,
) -> Tuple[Dict[str, Any], List[Dict[str, Any]]]:
    sentences = _split_sentences(extracted_text)
    first_sentences = " ".join(sentences[:2]).strip()
    matter_text = " ".join(sentences[2:4]).strip() or first_sentences
    content_type = infer_content_type(canonical_url=canonical_url, source_name=source_name, extracted_text=extracted_text)
    publisher_type = infer_publisher_type(canonical_url=canonical_url, source_class=source_class)
    topic_tags = _top_terms([source_name, extracted_text, " ".join(" ".join(_chunk_heading_tags(chunk)) for chunk in chunks)], limit=8)
    entity_tags = [tag for tag in topic_tags if tag[:1].isalpha()][:5]
    use_case_tags = [tag for tag in topic_tags if tag in {"security", "evals", "retrieval", "agents", "finance", "workflow", "engineering"}]
    decision_domains = list(dict.fromkeys(default_decision_domains + use_case_tags))[:6]
    metrics: List[Dict[str, Any]] = []
    quotes: List[Dict[str, Any]] = []
    claims: List[Dict[str, Any]] = []
    tradeoffs: List[Dict[str, Any]] = []
    recommendations: List[Dict[str, Any]] = []
    decision_patterns: List[Dict[str, Any]] = []
    insights: List[Dict[str, Any]] = []
    workflow_patterns: List[str] = []
    source_trust_tier = _source_trust_tier(source_class)
    freshness_score = infer_published_at_confidence(
        published_at=published_at,
        extraction_meta=extraction_meta,
        fetch_meta=fetch_meta,
    )
    for chunk in chunks:
        chunk_id = str(chunk.get("chunk_id") or "")
        content = str(chunk.get("content") or "").strip()
        meta = chunk.get("chunk_meta") or {}
        tags = list(meta.get("tags") or [])
        problem_tags = _match_tags(content, _PROBLEM_TAG_KEYWORDS)
        intervention_tags = _match_tags(content, _INTERVENTION_TAG_KEYWORDS)
        tradeoff_dimensions = _match_tags(content, _TRADEOFF_DIMENSION_KEYWORDS)
        applicability_conditions = [tag for tag in tags[:3] if tag]
        for match in _NUMBER_RE.finditer(content):
            unit = (match.group("unit") or "").strip()
            if not unit:
                continue
            metric = {
                "name": tags[0] if tags else "metric",
                "value": match.group("value") or "",
                "unit": unit,
                "qualifier": content[:120],
                "snippet": content[:240],
                "chunk_id": chunk_id,
            }
            metrics.append(metric)
            insights.append({
                "chunk_id": chunk_id,
                "insight_type": "metric",
                "text": metric["snippet"],
                "normalized_payload": metric,
                "confidence": 0.7,
                "evidence_strength": 0.8,
                "topic_tags": topic_tags,
                "entity_tags": entity_tags,
                "problem_tags": problem_tags,
                "intervention_tags": intervention_tags,
                "tradeoff_dimensions": tradeoff_dimensions,
                "decision_domains": decision_domains,
                "source_class": source_class,
                "publisher_type": publisher_type,
                "freshness_score": freshness_score,
                "applicability_conditions": applicability_conditions,
                "source_trust_tier": source_trust_tier,
                "coverage_score": 0.5,
                "internal_coverage_score": 1.0 if source_class.startswith("internal") else 0.0,
                "external_coverage_score": 0.0 if source_class.startswith("internal") else 1.0,
                "evidence_quality": 0.82,
            })
            if len(metrics) >= 5:
                break
        for quote_text in _QUOTE_RE.findall(content):
            quote = {"speaker": "", "text": quote_text.strip(), "snippet": content[:240], "chunk_id": chunk_id}
            quotes.append(quote)
            insights.append({
                "chunk_id": chunk_id,
                "insight_type": "quote",
                "text": quote["text"],
                "normalized_payload": quote,
                "confidence": 0.65,
                "evidence_strength": 0.7,
                "topic_tags": topic_tags,
                "entity_tags": entity_tags,
                "problem_tags": problem_tags,
                "intervention_tags": intervention_tags,
                "tradeoff_dimensions": tradeoff_dimensions,
                "decision_domains": decision_domains,
                "source_class": source_class,
                "publisher_type": publisher_type,
                "freshness_score": freshness_score,
                "applicability_conditions": applicability_conditions,
                "source_trust_tier": source_trust_tier,
                "coverage_score": 0.4,
                "internal_coverage_score": 1.0 if source_class.startswith("internal") else 0.0,
                "external_coverage_score": 0.0 if source_class.startswith("internal") else 1.0,
                "evidence_quality": 0.72,
            })
            if len(quotes) >= 5:
                break
        for sentence in _split_sentences(content)[:3]:
            lowered = sentence.lower()
            if any(word in lowered for word in ("should", "recommend", "best practice", "use ", "prefer ")):
                rec = {"action": sentence[:180], "rationale": content[:220], "applicability": ", ".join(tags[:2]), "chunk_id": chunk_id}
                recommendations.append(rec)
                insights.append({
                    "chunk_id": chunk_id,
                    "insight_type": "recommendation",
                    "text": rec["action"],
                    "normalized_payload": rec,
                    "confidence": 0.7,
                    "evidence_strength": 0.76,
                    "topic_tags": topic_tags,
                    "entity_tags": entity_tags,
                    "problem_tags": problem_tags,
                    "intervention_tags": list(dict.fromkeys(intervention_tags + _match_tags(sentence, _INTERVENTION_TAG_KEYWORDS))),
                    "tradeoff_dimensions": tradeoff_dimensions,
                    "decision_domains": decision_domains,
                    "source_class": source_class,
                    "publisher_type": publisher_type,
                    "freshness_score": freshness_score,
                    "applicability_conditions": applicability_conditions,
                    "source_trust_tier": source_trust_tier,
                    "coverage_score": 0.65,
                    "internal_coverage_score": 1.0 if source_class.startswith("internal") else 0.0,
                    "external_coverage_score": 0.0 if source_class.startswith("internal") else 1.0,
                    "evidence_quality": 0.8,
                })
            if "however" in lowered or "tradeoff" in lowered or "but" in lowered:
                trade = {"benefit": sentence[:120], "cost": content[:180], "condition": ", ".join(tags[:2]), "chunk_id": chunk_id}
                tradeoffs.append(trade)
                insights.append({
                    "chunk_id": chunk_id,
                    "insight_type": "tradeoff",
                    "text": trade["benefit"],
                    "normalized_payload": trade,
                    "confidence": 0.6,
                    "evidence_strength": 0.68,
                    "topic_tags": topic_tags,
                    "entity_tags": entity_tags,
                    "problem_tags": problem_tags,
                    "intervention_tags": intervention_tags,
                    "tradeoff_dimensions": list(dict.fromkeys(tradeoff_dimensions + _match_tags(sentence, _TRADEOFF_DIMENSION_KEYWORDS))),
                    "decision_domains": decision_domains,
                    "source_class": source_class,
                    "publisher_type": publisher_type,
                    "freshness_score": freshness_score,
                    "applicability_conditions": applicability_conditions,
                    "source_trust_tier": source_trust_tier,
                    "coverage_score": 0.6,
                    "internal_coverage_score": 1.0 if source_class.startswith("internal") else 0.0,
                    "external_coverage_score": 0.0 if source_class.startswith("internal") else 1.0,
                    "evidence_quality": 0.74,
                })
            if any(word in lowered for word in ("workflow", "loop", "review", "deploy", "evaluate", "validation")):
                workflow_patterns.append(sentence[:180])
                insights.append({
                    "chunk_id": chunk_id,
                    "insight_type": "workflow_pattern",
                    "text": sentence[:180],
                    "normalized_payload": {"pattern": sentence[:180]},
                    "confidence": 0.6,
                    "evidence_strength": 0.63,
                    "topic_tags": topic_tags,
                    "entity_tags": entity_tags,
                    "problem_tags": problem_tags,
                    "intervention_tags": intervention_tags,
                    "tradeoff_dimensions": tradeoff_dimensions,
                    "decision_domains": decision_domains,
                    "source_class": source_class,
                    "publisher_type": publisher_type,
                    "freshness_score": freshness_score,
                    "applicability_conditions": applicability_conditions,
                    "source_trust_tier": source_trust_tier,
                    "coverage_score": 0.52,
                    "internal_coverage_score": 1.0 if source_class.startswith("internal") else 0.0,
                    "external_coverage_score": 0.0 if source_class.startswith("internal") else 1.0,
                    "evidence_quality": 0.66,
                })
            claim = {"claim": sentence[:180], "support_level": "medium", "chunk_id": chunk_id}
            claims.append(claim)
            insights.append({
                "chunk_id": chunk_id,
                "insight_type": "claim",
                "text": claim["claim"],
                "normalized_payload": claim,
                "confidence": 0.55,
                "evidence_strength": 0.58,
                "topic_tags": topic_tags,
                "entity_tags": entity_tags,
                "problem_tags": problem_tags,
                "intervention_tags": intervention_tags,
                "tradeoff_dimensions": tradeoff_dimensions,
                "decision_domains": decision_domains,
                "source_class": source_class,
                "publisher_type": publisher_type,
                "freshness_score": freshness_score,
                "applicability_conditions": applicability_conditions,
                "source_trust_tier": source_trust_tier,
                "coverage_score": 0.42,
                "internal_coverage_score": 1.0 if source_class.startswith("internal") else 0.0,
                "external_coverage_score": 0.0 if source_class.startswith("internal") else 1.0,
                "evidence_quality": 0.58,
            })
            if len(claims) >= 8:
                break
        if (problem_tags or intervention_tags) and (recommendations or tradeoffs):
            decision_pattern = {
                "problem_type": problem_tags[0] if problem_tags else "general",
                "context_conditions": applicability_conditions,
                "candidate_intervention": (recommendations[-1]["action"] if recommendations else sentence[:180]),
                "expected_benefit": tradeoffs[-1]["benefit"] if tradeoffs else content[:140],
                "cost_or_tradeoff": tradeoffs[-1]["cost"] if tradeoffs else "",
                "failure_mode": "insufficient evidence" if not tradeoffs else tradeoffs[-1]["condition"],
                "applicability": ", ".join(applicability_conditions),
                "confidence": 0.7 if len(problem_tags) + len(intervention_tags) >= 2 else 0.55,
                "supporting_evidence_ids": [],
                "chunk_id": chunk_id,
            }
            decision_patterns.append(decision_pattern)
            insights.append({
                "chunk_id": chunk_id,
                "insight_type": "decision_pattern",
                "text": f"{decision_pattern['problem_type']} -> {decision_pattern['candidate_intervention']}",
                "normalized_payload": decision_pattern,
                "confidence": float(decision_pattern["confidence"]),
                "evidence_strength": 0.72,
                "topic_tags": topic_tags,
                "entity_tags": entity_tags,
                "problem_tags": problem_tags,
                "intervention_tags": intervention_tags,
                "tradeoff_dimensions": tradeoff_dimensions,
                "decision_domains": decision_domains,
                "source_class": source_class,
                "publisher_type": publisher_type,
                "freshness_score": freshness_score,
                "applicability_conditions": applicability_conditions,
                "source_trust_tier": source_trust_tier,
                "coverage_score": 0.7,
                "internal_coverage_score": 1.0 if source_class.startswith("internal") else 0.0,
                "external_coverage_score": 0.0 if source_class.startswith("internal") else 1.0,
                "evidence_quality": 0.78,
            })
    quality_signals = {
        "has_metrics": bool(metrics),
        "has_quotes": bool(quotes),
        "has_recommendations": bool(recommendations),
        "has_tradeoffs": bool(tradeoffs),
        "has_decision_patterns": bool(decision_patterns),
        "chunk_count": len(chunks),
        "degraded": bool(fetch_meta.get("fallback")),
    }
    evidence_density_score = min(1.0, float(len(metrics) + len(quotes) + len(recommendations) + len(tradeoffs)) / 10.0)
    novelty_score = min(1.0, float(len(topic_tags)) / 8.0)
    document_signal_score = min(1.0, 0.5 * evidence_density_score + 0.3 * novelty_score + (0.2 if not fetch_meta.get("fallback") else 0.0))
    enrichment = {
        "content_type": content_type,
        "publisher_type": publisher_type,
        "source_class": source_class,
        "summary_short": first_sentences[:320],
        "why_it_matters": matter_text[:320],
        "topic_tags": topic_tags,
        "entity_tags": entity_tags,
        "use_case_tags": use_case_tags,
        "decision_domains": decision_domains,
        "quality_signals": quality_signals,
        "metrics": metrics[:5],
        "notable_quotes": quotes[:5],
        "key_claims": claims[:8],
        "tradeoffs": tradeoffs[:5],
        "recommendations": recommendations[:5],
        "novelty_score": novelty_score,
        "evidence_density_score": evidence_density_score,
        "document_signal_score": document_signal_score,
        "embedding_ready": bool(chunks),
        "published_at_confidence": infer_published_at_confidence(
            published_at=published_at,
            extraction_meta=extraction_meta,
            fetch_meta=fetch_meta,
        ),
        "enrichment_meta": {
            "status": "completed",
            "workflow_patterns": workflow_patterns[:5],
            "decision_patterns": decision_patterns[:5],
        },
    }
    return enrichment, insights


def derive_evidence_relations(insight_rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    relations: List[Dict[str, Any]] = []
    by_chunk: Dict[str, List[Dict[str, Any]]] = {}
    for insight in insight_rows:
        chunk_id = str(insight.get("chunk_id") or "")
        if chunk_id:
            by_chunk.setdefault(chunk_id, []).append(insight)
    for chunk_items in by_chunk.values():
        recommendations = [item for item in chunk_items if item.get("insight_type") in {"recommendation", "decision_pattern"}]
        tradeoffs = [item for item in chunk_items if item.get("insight_type") == "tradeoff"]
        claims = [item for item in chunk_items if item.get("insight_type") == "claim"]
        metrics = [item for item in chunk_items if item.get("insight_type") == "metric"]
        for recommendation in recommendations:
            for tradeoff in tradeoffs[:2]:
                relations.append(
                    {
                        "from_insight_id": recommendation.get("insight_id"),
                        "to_insight_id": tradeoff.get("insight_id"),
                        "relation_type": "refines",
                        "confidence": 0.62,
                        "explanation": "Tradeoff in same chunk refines recommendation context.",
                    }
                )
            for claim in claims[:2]:
                relations.append(
                    {
                        "from_insight_id": claim.get("insight_id"),
                        "to_insight_id": recommendation.get("insight_id"),
                        "relation_type": "supports",
                        "confidence": 0.58,
                        "explanation": "Claim in same chunk supports recommendation.",
                    }
                )
        for metric in metrics:
            for claim in claims[:2]:
                relations.append(
                    {
                        "from_insight_id": metric.get("insight_id"),
                        "to_insight_id": claim.get("insight_id"),
                        "relation_type": "supports",
                        "confidence": 0.55,
                        "explanation": "Metric in same chunk likely supports claim.",
                    }
                )
    return [relation for relation in relations if relation.get("from_insight_id") and relation.get("to_insight_id")]
