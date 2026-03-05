from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from app.research.contracts import (
    ResearchChunkSearchRequest,
    ResearchChunkSearchResponse,
    ResearchContextPackRequest,
    ResearchContextPackResponse,
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

