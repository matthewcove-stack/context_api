from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from app.research.contracts import (
    ResearchDecisionPackResponse,
    ResearchEvidenceCompareResponse,
    ResearchEvidenceRelatedResponse,
    ResearchEvidenceSearchResponse,
    ResearchChunkSearchRequest,
    ResearchChunkSearchResponse,
    ResearchContextPackRequest,
    ResearchContextPackResponse,
    ResearchDomainSummaryResponse,
    ResearchTopicDetailResponse,
    ResearchTopicDocumentsResponse,
    ResearchTopicListResponse,
    ResearchTopicSearchResponse,
    ResearchTopicSummarizeRequest,
    ResearchTopicSummarizeResponse,
    ResearchWeeklyDigestResponse,
)


class BridgeClientError(RuntimeError):
    """Raised when calls to the Context API retrieval endpoints fail."""


def _extract_error_detail(response: httpx.Response) -> str:
    try:
        data = response.json()
    except Exception:
        return response.text or f"status={response.status_code}"
    if isinstance(data, dict):
        detail = data.get("detail")
        if detail:
            return str(detail)
    return str(data)


class ContextApiBridgeClient:
    def __init__(
        self,
        *,
        base_url: str,
        token: str,
        timeout_s: float = 20.0,
        transport: Optional[httpx.BaseTransport] = None,
    ) -> None:
        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout_s,
            transport=transport,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )

    def __enter__(self) -> "ContextApiBridgeClient":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            response = self._client.post(path, json=payload)
        except httpx.HTTPError as exc:
            raise BridgeClientError(f"Context API request failed for {path}: {exc}") from exc
        if response.status_code >= 400:
            detail = _extract_error_detail(response)
            raise BridgeClientError(f"Context API request failed for {path}: {detail}")
        try:
            data = response.json()
        except ValueError as exc:
            raise BridgeClientError(f"Context API response was not valid JSON for {path}") from exc
        if not isinstance(data, dict):
            raise BridgeClientError(f"Context API response was not an object for {path}")
        return data

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            response = self._client.get(path, params=params)
        except httpx.HTTPError as exc:
            raise BridgeClientError(f"Context API request failed for {path}: {exc}") from exc
        if response.status_code >= 400:
            detail = _extract_error_detail(response)
            raise BridgeClientError(f"Context API request failed for {path}: {detail}")
        try:
            data = response.json()
        except ValueError as exc:
            raise BridgeClientError(f"Context API response was not valid JSON for {path}") from exc
        if not isinstance(data, dict):
            raise BridgeClientError(f"Context API response was not an object for {path}")
        return data

    def search(self, payload: ResearchContextPackRequest) -> ResearchContextPackResponse:
        data = self._post("/v2/research/context/pack", payload.model_dump(exclude_none=True))
        return ResearchContextPackResponse.model_validate(data)

    def fetch_document_chunks(
        self,
        *,
        document_id: str,
        payload: ResearchChunkSearchRequest,
    ) -> ResearchChunkSearchResponse:
        data = self._post(
            f"/v2/research/documents/{document_id}/chunks:search",
            payload.model_dump(exclude_none=True),
        )
        return ResearchChunkSearchResponse.model_validate(data)

    def list_topics(self, *, limit: int = 20) -> ResearchTopicListResponse:
        data = self._get("/v2/research/topics", {"limit": limit})
        return ResearchTopicListResponse.model_validate(data)

    def search_topics(self, *, query: str, limit: int = 10) -> ResearchTopicSearchResponse:
        data = self._get("/v2/research/topics/search", {"query": query, "limit": limit})
        return ResearchTopicSearchResponse.model_validate(data)

    def describe_topic(self, *, topic_key: str) -> ResearchTopicDetailResponse:
        data = self._get(f"/v2/research/topics/{topic_key}")
        return ResearchTopicDetailResponse.model_validate(data)

    def list_topic_documents(self, *, topic_key: str, limit: int = 10, sort: str = "recent") -> ResearchTopicDocumentsResponse:
        data = self._get(f"/v2/research/topics/{topic_key}/documents", {"limit": limit, "sort": sort})
        return ResearchTopicDocumentsResponse.model_validate(data)

    def summarize_topic(self, *, topic_key: str, payload: ResearchTopicSummarizeRequest) -> ResearchTopicSummarizeResponse:
        data = self._post(f"/v2/research/topics/{topic_key}/summarize", payload.model_dump(exclude_none=True))
        return ResearchTopicSummarizeResponse.model_validate(data)

    def decision_pack(self, payload: ResearchContextPackRequest) -> ResearchDecisionPackResponse:
        data = self._post("/v2/research/decision/pack", payload.model_dump(exclude_none=True))
        return ResearchDecisionPackResponse.model_validate(data)

    def search_evidence(self, payload: ResearchContextPackRequest) -> ResearchEvidenceSearchResponse:
        data = self._post("/v2/research/evidence/search", payload.model_dump(exclude_none=True))
        return ResearchEvidenceSearchResponse.model_validate(data)

    def related_evidence(self, payload: ResearchContextPackRequest) -> ResearchEvidenceRelatedResponse:
        data = self._post("/v2/research/evidence/related", payload.model_dump(exclude_none=True))
        return ResearchEvidenceRelatedResponse.model_validate(data)

    def compare_evidence(self, payload: ResearchContextPackRequest) -> ResearchEvidenceCompareResponse:
        data = self._post("/v2/research/evidence/compare", payload.model_dump(exclude_none=True))
        return ResearchEvidenceCompareResponse.model_validate(data)

    def weekly_digest(self, *, topic_key: str, days: int = 7, limit: int = 5) -> ResearchWeeklyDigestResponse:
        data = self._get(f"/v2/research/topics/{topic_key}/weekly", {"days": days, "limit": limit})
        return ResearchWeeklyDigestResponse.model_validate(data)

    def domain_summary(self, *, topic_key: str, decision_domain: str) -> ResearchDomainSummaryResponse:
        data = self._get(f"/v2/research/topics/{topic_key}/domains/{decision_domain}/summary")
        return ResearchDomainSummaryResponse.model_validate(data)
