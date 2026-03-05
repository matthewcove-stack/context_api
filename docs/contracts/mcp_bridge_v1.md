# MCP Bridge v1 (Codex Retrieval)

Status: proposed + starter implementation available.

## Purpose

Expose Context API research retrieval as a compact MCP server optimized for Codex:
- predictable tool names (`search`, `fetch`)
- bounded, citation-first payloads
- read-only access

## Scope

### In scope (v1)
- MCP server over `stdio` (default) with optional `sse` transport.
- Tool: `search` -> `POST /v2/research/context/pack`
- Tool: `fetch` -> `POST /v2/research/documents/{document_id}/chunks:search`
- Bearer auth to Context API with `CONTEXT_API_TOKEN`.
- Stable JSON output models validated before return.

### Out of scope (v1)
- Write/ingest/admin tools.
- Server-side feedback submission from MCP.
- OAuth flow and multi-tenant identity mapping.

## Runtime config

- `CONTEXT_API_BASE_URL` (default `http://localhost:8001`)
- `CONTEXT_API_TOKEN` (required)
- `MCP_BRIDGE_TIMEOUT_S` (default `20`)
- `MCP_BRIDGE_TRANSPORT` (`stdio` or `sse`, default `stdio`)

## Tool contracts

## `search`

Input:
- `query` (string, required)
- `topic_key` (string, required)
- `source_ids` (string[], optional)
- `token_budget` (int, optional)
- `recency_days` (int, optional)
- `max_items` (int, optional, default `6`, range `1..20`)
- `min_relevance_score` (float, optional)

Output:
- `retrieval_confidence` (`high` | `med` | `low`)
- `next_action` (`proceed` | `refine_query` | `expand_sections`)
- `trace_id` (string)
- `retrieved_document_ids` (string[])
- `timing_ms` (object)
- `items[]`:
  - `document_id`, `source_id`, `title`, `canonical_url`, `published_at`
  - `summary`
  - `signals[]` (`claim`, `why`, `cite{document_id,chunk_id}`)
  - `citations[]` (`document_id`, `chunk_id`)
  - `score_breakdown` (`total`, `lexical`, `embedding`, `recency`, `source_weight`)

## `fetch`

Input:
- `document_id` (string, required)
- `query` (string, required)
- `max_chunks` (int, optional, default `6`, range `1..20`)
- `max_chars` (int, optional, default `600`, range `80..4000`)

Output:
- `document_id`
- `chunks[]`:
  - `chunk_id`
  - `snippet`
  - `score`

## Security model

- Bridge is read-only and only exposes retrieval tools.
- Requires explicit bearer token to call Context API.
- Does not forward model-provided credentials.
- Intended for trusted local runtimes (`stdio`) first.

## Performance targets

- `search` p95 < 1500ms (excluding model latency)
- `fetch` p95 < 2000ms
- Tool timeout default: 20s
- Payload bounds enforced via `max_items`, `max_chunks`, `max_chars`

## Eval plan (v1)

- Build 100+ representative queries by `topic_key`.
- Track:
  - citation presence rate
  - precision@k (manual judged)
  - low-confidence rate
  - tool failure rate
- Gate releases on regression thresholds.

## Codex wiring

Local CLI/VS Code shared config:

```powershell
$env:CONTEXT_API_BASE_URL="http://localhost:8001"
$env:CONTEXT_API_TOKEN="change-me"
codex mcp add context-api-research -- python C:\path\to\context_api\scripts\run_mcp_bridge.py --transport stdio
```

Recommended Codex config:
- enable only `search` + `fetch` for this server
- mark server required where retrieval is mandatory
- set startup and tool timeouts explicitly
