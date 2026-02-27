# Research Operations Runbook

## Purpose
Operational controls for the research ingestion and retrieval pipeline.

## Runtime controls
- `RESEARCH_SOURCE_FAILURE_THRESHOLD`:
  - consecutive source failures before cooldown is applied.
  - default: `3`
- `RESEARCH_SOURCE_COOLDOWN_MINUTES`:
  - cooldown duration after threshold is crossed.
  - default: `60`
- `RESEARCH_RUN_MAX_NEW_ITEMS`:
  - max newly ingested documents per run before run exits early.
  - default: `0` (unbounded)
- `RESEARCH_SCORE_WEIGHT_LEXICAL`, `RESEARCH_SCORE_WEIGHT_EMBEDDING`,
  `RESEARCH_SCORE_WEIGHT_RECENCY`, `RESEARCH_SCORE_WEIGHT_SOURCE`:
  - retrieval scoring blend weights for tuning.
  - defaults: `0.45`, `0.35`, `0.15`, `0.05`

## Failure handling
- Source-level failures increment `research_source_policies.consecutive_failures`.
- On threshold breach, `cooldown_until` is set and schedule enqueue skips the source until cooldown expires.
- Successful source processing resets consecutive failures and clears cooldown/error.
- PDF documents (`application/pdf`) use the pypdf extraction path before chunking/embedding.

## Backpressure
- The worker enforces a per-run new-item budget via `RESEARCH_RUN_MAX_NEW_ITEMS`.
- When budget is exhausted, the run is completed with bounded run error metadata.

## Observability
- `GET /v2/research/ops/summary?topic_key=...` returns:
  - source totals and cooldown counts
  - document status totals
  - run open/failure counts and 24h failure rate
  - retrieval query/error counts
- Query-level retrieval telemetry:
  - `research_query_logs`
- Relevance telemetry:
  - `research_relevance_scores`
- Operator feedback:
  - `research_retrieval_feedback`

## Recovery drill
1. Verify DB + migrations are current.
2. Inspect `ops/summary` for elevated `sources_in_cooldown` or `run_failure_rate_24h`.
3. Lower ingest pressure by setting `RESEARCH_RUN_MAX_NEW_ITEMS` for controlled catch-up.
4. Re-enable normal budget after source health stabilizes.
