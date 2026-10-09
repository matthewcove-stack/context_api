# Lambic AI Brief: economical credit recovery — 9 October 2026

## Decision

Restore credit for the OpenAI account actually used by the host runtime first.
Retain `text-embedding-3-small` and the current editorial model for a bounded
recovery validation. A cheaper editorial model does not bypass exhausted account
credit, because embedding repair runs first against OpenAI. No billing change,
runtime model switch, deployment, workflow dispatch or publication was performed
for this assessment.

A later `gpt-4.1-mini` trial is a reasonable cost optimisation. It is compatible
with the existing chat request shape in principle, but has not been validated
against Lambic's source-grounding and editorial requirements. Do not switch
production merely on a price comparison.

## Evidence and scope

Inspected current default-branch source: BrainOS
`c44babf3320415809f44d1a0ad9510c6f7a4be28`, context_api
`17d217d8c767edf025ad396ee2c90c77406b993f`.
No open context_api pull request was returned at inspection.

- [8 October publication run](https://github.com/matthewcove-stack/brain_os/actions/runs/37787980364):
  repair selected 250 documents; processed zero; reported one failed and 249
  remaining; HTTP 429 `credit_balance_exhausted`; exit 78. The failed item also
  remains unresolved, so 249 is not the total outstanding backlog.
- [8 October ingestion run](https://github.com/matthewcove-stack/brain_os/actions/runs/37741897950):
  ingestion step succeeded; the separate freshness step failed.
- Public freshness in the publication log: latest issue 18 September; age 20 days;
  threshold seven days. This is dated evidence, not a new live-feed observation.
- [BrainOS PR #4](https://github.com/matthewcove-stack/brain_os/pull/4) and
  [context_api PR #9](https://github.com/matthewcove-stack/context_api/pull/9)
  already record recovery and protect quality; both are merged.

Production secrets, host environment overrides, billing records and token usage
were not accessible here. Model names below describe source defaults, not a
verified effective host configuration. The failed request identifies OpenAI but
does not establish the production editorial model or actual monthly bill.

## What actually spends tokens

| Component | Repository evidence | Consequence |
|---|---|---|
| Research enrichment | `app/research/enrichment.py` uses local heuristics; the research worker invokes it | Do not budget a chat completion per ingested research document |
| Embeddings | `app/research/embeddings.py`; default `text-embedding-3-small`; fixed OpenAI embeddings URL | Already a low-cost embedding model; no alternate provider endpoint integration |
| Repair | `scripts/reembed_research_documents.py` requires OpenAI mode; SQL selects missing/mismatched embeddings, newest first | 250 is a batch limit, not 250 completions or the full corpus size |
| Draft and editor | `app/research/digest_generator.py`; default `DAILY_DIGEST_MODEL=gpt-5.2` | One drafting call and up to three editor/rewrite calls; both use the same model |
| Distribution/weekly | `app/research/distribution_generator.py` derives artifacts from reviewed issues | No additional synthesis-model fee on this path |

Repair chunks text at a default 1,200 characters with overlap. Batches are at
most 32 chunks or approximately 20,000 characters, but per-document repair can
make multiple HTTP calls. Ingestion also embeds fresh documents, so count those
tokens once in an operating budget.

The separate legacy Intel pipeline's `OPENAI_MODEL=gpt-4.1-mini` setting is
not the Brief's editorial setting. The chat client permits an
`OPENAI_API_BASE` override, but embeddings do not. That override alone cannot
provide an end-to-end provider fallback.

## Alternatives

| Route | Status and decision |
|---|---|
| Restore OpenAI credit; retain current models | Smallest operational change; restores the blocked embedding dependency and avoids an unvalidated quality change |
| GPT-4.1 mini for drafting and review | Same Chat Completions/JSON request shape; needs credited OpenAI embeddings, model access and a nonpublishing quality trial |
| GPT-5 mini | Lower list prices, but not a drop-in replacement: current client sends `temperature=0.2`, unsupported for this older reasoning model; official model page also labels it deprecated |
| Other OpenAI-compatible chat provider | Chat URL configurability is not a tested adapter; JSON, authentication, response, parameter and error semantics need validation; OpenAI embeddings still block |
| Hash/local embeddings | Hash implementation exists for explicit test/degraded use, with reduced-retrieval warning; repair CLI refuses non-OpenAI mode. Not a defensible production recovery |
| Local semantic embeddings or Batch API | No integrated implementation found on this path; migration requires model-space/retrieval evaluation or asynchronous orchestration. Not justified to solve today's tiny embedding cost |

Do not mix vector spaces under the same model identity. No quality evidence
supports substituting hash vectors or lowering publication thresholds.

## Cost scenarios, not measured usage

Standard USD list prices checked 9 October; exclude tax, hosting and other account
workloads. No cache discount or Batch discount assumed.

| Model | Input per million tokens | Output per million tokens |
|---|---:|---:|
| text-embedding-3-small | $0.02 | — |
| GPT-5.2 | $1.75 | $14.00 |
| GPT-4.1 mini | $0.40 | $1.60 |
| GPT-5 mini (comparison only) | $0.25 | $2.00 |

Sources: [embedding model](https://developers.openai.com/api/docs/models/text-embedding-3-small),
[GPT-5.2](https://developers.openai.com/api/docs/models/gpt-5.2),
[GPT-4.1 mini](https://developers.openai.com/api/docs/models/gpt-4.1-mini),
[GPT-5 mini](https://developers.openai.com/api/docs/models/gpt-5-mini).
[Parameter guidance](https://developers.openai.com/api/docs/guides/latest-model?model=gpt-5.2)
distinguishes GPT-5.2's default no-reasoning mode from older GPT-5 models.

Assume 10,000 input and 2,000 output tokens **per call**, two to four calls per
issue. This is an illustrative budget, not a token measurement or hard cap.

| Editorial route | Per issue | 30 issue attempts/month | 60 issue attempts/month |
|---|---:|---:|---:|
| GPT-5.2 | $0.091–$0.182 | $2.73–$5.46 | $5.46–$10.92 |
| GPT-4.1 mini | $0.0144–$0.0288 | $0.43–$0.86 | $0.86–$1.73 |

The schedule has two publish attempts/day plus host fallbacks. Existing-date
checks can avoid generation after a successful issue, but withheld drafts can
consume calls again. Tokens spent on rejected drafts still count. Prompts include
source excerpts, draft JSON and recent issue material; longer inputs, outputs or
other workloads can make actual costs exceed these scenarios. There is currently
no explicit completion-token cap in the editorial request.

Embedding examples at 2,000–10,000 billable tokens/document, including overlap:

- A 250-document repair batch: $0.01–$0.05.
- The historically recorded 709-document gap: $0.028–$0.142; this is not today's
  verified backlog.
- 100 new documents/day for 30 days: $0.12–$0.60.

Formula: embedding tokens × $0.02 / 1,000,000; chat cost is
(input tokens × input rate + output tokens × output rate) / 1,000,000.
Existing `get_research_ai_usage_by_model` estimates embedding tokens from stored
chunk bytes / 4. It is not billing usage and does not measure editorial tokens.

## Narrow change in this PR

Repair now writes a terminal `embedding-repair-*.json` summary to the existing
`BRIEF_PUBLISH_REPORT_DIR` when configured. BrainOS already uploads
`artifacts/*.json`. Previously the 8 October failure occurred before the
publisher created any artifact.

The report adds phase and exit status to the existing safe summary. It contains
no credentials, source bodies or raw exception prose. Writes use a temporary file
and rename; reporting failure falls back to stdout without masking the provider
status. Repair still stops at the first provider restriction. No cooldown,
selection, model, threshold or scheduling behaviour changes.

Verification: 24 scoped tests passed, including existing provider classification,
per-credential cooldown/expiry and no-backfill scheduler checks, plus new report
checks for blocked, successful and failed repair and optional/unwritable output.
These ran without a database or live provider. Docker is unavailable in this
workspace; the canonical disposable-Postgres `make test` and end-to-end
production validation were not run.

Further improvements to consider only after measured recovery: record provider
usage for draft/review calls; evaluate the cheaper model on the same source sets;
make any output-token cap large enough for complete valid JSON; consider
deduplicating repeated weak-issue attempts without hiding freshness failure.
Do not remove independent review to save a few cents.

## Safe recovery validation

1. Owner checks the account/project used by the **effective host credential**,
   available balance, expiry and applicable limits. A rotated key for the same
   exhausted account is not a credit fix. Choose a bounded top-up and any
   auto-recharge deliberately; this assessment does not authorise either.
2. Coordinate a temporary hold of automatic publication with the operator before
   adding credit if the first recovered draft must be reviewed before delivery.
   Crediting the account can otherwise unblock existing schedules immediately.
   Keep collection and stale-feed visibility. Do not change freshness thresholds.
3. After account approval, make one tiny stateless embedding request with the
   effective runtime credential/model. Verify a valid vector and safe status;
   do not log the key or raw provider body. Test model access with one tiny JSON
   chat request as well. Neither request publishes or alters the corpus.
4. Perform a bounded `reembed_research_documents --topic-key ai_research --limit 1`
   through the existing host runtime, then a capped repair batch if successful.
   This writes embedding state: it is not a stateless credit probe.
5. In a temporary website checkout, run the canonical daily publish dry-run with
   `force=false` and unchanged gates. The host wrapper normally repairs the
   production corpus even with `--dry-run`; after deliberate repair, set
   `BRIEF_MAINTAIN_RESEARCH_CORPUS=false` for this validation only. Confirm the
   effective setting after host env loading. Dry-run still spends model tokens.
6. Review source grounding, document IDs, at least four strong items and three
   sources, independent editor output and deterministic style checks; validate
   artifacts, feeds and build. Generate one issue covering the unpublished
   period, not a calendar backfill.
7. Obtain delivery authorisation before live publish/resuming a held schedule.
   Validate the resulting public issue URL and rerun the independent seven-day
   freshness check. A green embedding probe or dry-run is not publication recovery.
