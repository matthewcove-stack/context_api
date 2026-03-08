# Research Observability

## Purpose
Operational dashboards and alert query references for the research ingestion and retrieval pipeline.

## API-backed dashboard endpoints
- `GET /v2/research/ops/summary?topic_key=...`
- `GET /v2/research/ops/sources?topic_key=...&limit=...`
- `GET /v2/research/ops/documents?topic_key=...`
- `GET /v2/research/ops/storage?topic_key=...`
- `GET /v2/research/ops/progress?topic_key=...&run_limit=...`
- `GET /v2/research/review/queue?topic_key=...&limit=...`

## Lightweight browser dashboard
- `GET /v2/research/ops/dashboard`
- Enter bearer token and topic key in the page controls.

## Core SQL views (reference queries)

### Ingestion lag + failure posture
```sql
SELECT
  topic_key,
  count(*) FILTER (WHERE status IN ('queued', 'running')) AS runs_open,
  count(*) FILTER (WHERE status = 'failed' AND created_at >= now() - interval '24 hours') AS runs_failed_24h
FROM research_ingestion_runs
GROUP BY topic_key
ORDER BY topic_key;
```

### Source reliability
```sql
SELECT
  s.topic_key,
  s.source_id,
  s.name,
  p.consecutive_failures,
  p.cooldown_until,
  p.last_error,
  p.last_polled_at
FROM research_sources s
JOIN research_source_policies p ON p.source_id = s.source_id
ORDER BY s.topic_key, p.consecutive_failures DESC, s.created_at ASC;
```

### Retrieval quality + operator feedback
```sql
SELECT
  q.topic_key,
  count(*) FILTER (WHERE q.created_at >= now() - interval '24 hours') AS queries_24h,
  count(*) FILTER (WHERE q.status = 'error' AND q.created_at >= now() - interval '24 hours') AS query_errors_24h,
  count(*) FILTER (WHERE f.verdict = 'useful' AND f.created_at >= now() - interval '24 hours') AS feedback_useful_24h,
  count(*) FILTER (WHERE f.verdict = 'not_useful' AND f.created_at >= now() - interval '24 hours') AS feedback_not_useful_24h
FROM research_query_logs q
LEFT JOIN research_retrieval_feedback f ON f.trace_id = q.trace_id
GROUP BY q.topic_key
ORDER BY q.topic_key;
```

## Suggested alerts
- `runs_failed_24h > 5` per topic.
- `sources_in_cooldown > 0` sustained over 30 minutes.
- `retrieval_errors_24h / retrieval_queries_24h > 0.1` when `retrieval_queries_24h >= 20`.
