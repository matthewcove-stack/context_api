# MCP Ops Bridge v1 (Codex Source Bootstrap + Run Ops)

Status: implemented as separate write-lite bridge.

## Purpose
Expose minimal operational tools for source onboarding and ingest run monitoring without changing the read-only retrieval bridge.

## Runtime config
- `MCP_OPS_ENABLED=true` (required)
- `CONTEXT_API_BASE_URL` (default `http://localhost:8001`)
- `CONTEXT_API_TOKEN` (required)
- `MCP_BRIDGE_TIMEOUT_S` (default `20`)
- `MCP_BRIDGE_TRANSPORT` (`stdio` | `sse`, default `stdio`)

## Tools
### `sources_bootstrap`
- Calls `POST /v2/research/sources/bootstrap`
- Input mirrors bootstrap request contract.
- Output mirrors bootstrap response contract.

### `ingest_status`
- Calls `GET /v2/research/ingest/runs/{run_id}`
- Returns run status + counters + errors.

### `ops_summary`
- Calls `GET /v2/research/ops/summary?topic_key=...`
- Returns operational health counters for a topic.

## Security model
- Uses bearer token in env.
- Intended for trusted local runtime first.
- Keeps retrieval bridge (`search`, `fetch`) unchanged and read-only.
