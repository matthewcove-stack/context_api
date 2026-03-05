from __future__ import annotations

import json
import os
from dataclasses import dataclass
from functools import lru_cache
from typing import Literal, cast

from mcp.server.fastmcp import FastMCP

from app.mcp_bridge_ops.client import ContextApiOpsBridgeClient, OpsBridgeClientError
from app.research.contracts import ResearchBootstrapRequest


@dataclass(frozen=True)
class OpsBridgeRuntimeSettings:
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
def _load_settings() -> OpsBridgeRuntimeSettings:
    enabled = os.getenv("MCP_OPS_ENABLED", "false").strip().lower()
    if enabled != "true":
        raise ValueError("MCP_OPS_ENABLED=true is required for ops bridge")
    token = os.getenv("CONTEXT_API_TOKEN", "").strip()
    if not token:
        raise ValueError("CONTEXT_API_TOKEN is required for MCP ops bridge")
    base_url = os.getenv("CONTEXT_API_BASE_URL", "http://localhost:8001").strip()
    if not base_url:
        raise ValueError("CONTEXT_API_BASE_URL cannot be empty")
    timeout_s = float(os.getenv("MCP_BRIDGE_TIMEOUT_S", "20").strip())
    if timeout_s <= 0:
        raise ValueError("MCP_BRIDGE_TIMEOUT_S must be greater than 0")
    transport = _parse_transport(os.getenv("MCP_BRIDGE_TRANSPORT", "stdio"))
    return OpsBridgeRuntimeSettings(
        context_api_base_url=base_url,
        context_api_token=token,
        timeout_s=timeout_s,
        transport=transport,
    )


mcp = FastMCP("context-api-research-ops-bridge")


@mcp.tool(
    name="sources_bootstrap",
    description="Bootstrap research sources for a topic and optionally trigger ingestion.",
)
def sources_bootstrap(
    topic_key: str,
    suggestions: list[dict],
    trigger_ingest: bool = True,
    trigger: str = "event",
    idempotency_key: str | None = None,
    dry_run: bool = False,
) -> dict:
    settings = _load_settings()
    payload = ResearchBootstrapRequest(
        topic_key=topic_key,
        suggestions=suggestions,
        trigger_ingest=trigger_ingest,
        trigger=trigger,
        idempotency_key=idempotency_key,
        dry_run=dry_run,
    )
    try:
        with ContextApiOpsBridgeClient(
            base_url=settings.context_api_base_url,
            token=settings.context_api_token,
            timeout_s=settings.timeout_s,
        ) as client:
            upstream = client.sources_bootstrap(payload)
    except OpsBridgeClientError as exc:
        raise ValueError(str(exc)) from exc
    return upstream.model_dump(mode="json")


@mcp.tool(
    name="ingest_status",
    description="Fetch ingestion run status for a previously created run.",
)
def ingest_status(run_id: str) -> dict:
    settings = _load_settings()
    try:
        with ContextApiOpsBridgeClient(
            base_url=settings.context_api_base_url,
            token=settings.context_api_token,
            timeout_s=settings.timeout_s,
        ) as client:
            upstream = client.ingest_status(run_id)
    except OpsBridgeClientError as exc:
        raise ValueError(str(exc)) from exc
    return upstream.model_dump(mode="json")


@mcp.tool(
    name="ops_summary",
    description="Fetch research operations summary metrics for a topic.",
)
def ops_summary(topic_key: str) -> dict:
    settings = _load_settings()
    try:
        with ContextApiOpsBridgeClient(
            base_url=settings.context_api_base_url,
            token=settings.context_api_token,
            timeout_s=settings.timeout_s,
        ) as client:
            upstream = client.ops_summary(topic_key)
    except OpsBridgeClientError as exc:
        raise ValueError(str(exc)) from exc
    return upstream.model_dump(mode="json")


@mcp.resource(
    "context-api://ops-bridge/status",
    name="ops_bridge_status",
    description="Ops bridge runtime status and endpoint metadata.",
    mime_type="application/json",
)
def bridge_status() -> str:
    settings = _load_settings()
    return json.dumps(
        {
            "target_base_url": settings.context_api_base_url,
            "timeout_s": settings.timeout_s,
            "tools": ["sources_bootstrap", "ingest_status", "ops_summary"],
        }
    )


def run_server(*, transport: str | None = None) -> None:
    settings = _load_settings()
    selected_transport = _parse_transport(transport) if transport else settings.transport
    mcp.run(transport=selected_transport)


if __name__ == "__main__":
    run_server()
