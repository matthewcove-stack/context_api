from __future__ import annotations

from typing import Any, Dict, Optional

import httpx

from app.research.contracts import (
    ResearchBootstrapRequest,
    ResearchBootstrapResponse,
    ResearchIngestRunStatusResponse,
    ResearchOpsSummaryResponse,
)


class OpsBridgeClientError(RuntimeError):
    """Raised when Context API ops bridge requests fail."""


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


class ContextApiOpsBridgeClient:
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

    def __enter__(self) -> "ContextApiOpsBridgeClient":
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def _post(self, path: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        try:
            response = self._client.post(path, json=payload)
        except httpx.HTTPError as exc:
            raise OpsBridgeClientError(f"Context API request failed for {path}: {exc}") from exc
        if response.status_code >= 400:
            raise OpsBridgeClientError(f"Context API request failed for {path}: {_extract_error_detail(response)}")
        try:
            data = response.json()
        except ValueError as exc:
            raise OpsBridgeClientError(f"Context API response was not valid JSON for {path}") from exc
        if not isinstance(data, dict):
            raise OpsBridgeClientError(f"Context API response was not an object for {path}")
        return data

    def _get(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        try:
            response = self._client.get(path, params=params)
        except httpx.HTTPError as exc:
            raise OpsBridgeClientError(f"Context API request failed for {path}: {exc}") from exc
        if response.status_code >= 400:
            raise OpsBridgeClientError(f"Context API request failed for {path}: {_extract_error_detail(response)}")
        try:
            data = response.json()
        except ValueError as exc:
            raise OpsBridgeClientError(f"Context API response was not valid JSON for {path}") from exc
        if not isinstance(data, dict):
            raise OpsBridgeClientError(f"Context API response was not an object for {path}")
        return data

    def sources_bootstrap(self, payload: ResearchBootstrapRequest) -> ResearchBootstrapResponse:
        data = self._post("/v2/research/sources/bootstrap", payload.model_dump(exclude_none=True))
        return ResearchBootstrapResponse.model_validate(data)

    def ingest_status(self, run_id: str) -> ResearchIngestRunStatusResponse:
        data = self._get(f"/v2/research/ingest/runs/{run_id}")
        return ResearchIngestRunStatusResponse.model_validate(data)

    def ops_summary(self, topic_key: str) -> ResearchOpsSummaryResponse:
        data = self._get("/v2/research/ops/summary", params={"topic_key": topic_key})
        return ResearchOpsSummaryResponse.model_validate(data)
