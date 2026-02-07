# /v2 Intel MVP API contract (local to this repo)

This contract is intentionally local until we decide to promote it to notion_assistant_contracts.

## POST /v2/context/pack
Request:
- query: string
- topics?: string[]
- token_budget?: int
- recency_days?: int
- max_items?: int

Response:
- pack:
  - items[]:
    - article_id: string
    - title: string
    - url: string
    - summary: string
    - signals[]:
      - claim: string
      - why: string
      - tradeoff?: string
      - cite:
        - article_id: string
        - section_id?: string
    - citations[]:
      - url: string
      - article_id: string
      - section_id?: string
- retrieval_confidence: "high" | "med" | "low"
- next_action: "proceed" | "refine_query" | "expand_sections"
- trace:
  - trace_id: string
  - retrieved_article_ids: string[]
  - timing_ms?: object

## GET /v2/intel/articles/{id}/outline
Response:
- article_id: string
- outline[]:
  - section_id: string
  - heading: string
  - blurb?: string

## POST /v2/intel/articles/{id}/sections
Request:
- section_ids: string[]
Response:
- article_id: string
- sections[]:
  - section_id: string
  - heading: string
  - content: string
  - rank: int

## POST /v2/intel/articles/{id}/chunks:search
Request:
- query: string
- max_chars?: int
- max_chunks?: int
Response:
- article_id: string
- chunks[]:
  - section_id: string
  - snippet: string
  - score?: number

## POST /v2/intel/ingest
Request:
- fixture_bundle: string (e.g., "default")
Response:
- ingested_article_ids: string[]
