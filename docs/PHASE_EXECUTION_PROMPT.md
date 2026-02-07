# Phase execution prompt (copy/paste into Codex)

You are implementing ONLY the requested phase from docs/phases.md.
Obey docs/codex_rules.md and the truth hierarchy: docs/current_state.md is authoritative.

## Your task
Implement: Phase 3 — URL ingestion + fetch/extract + LLM enrichment (Option B)

Do not start other phases.

## Repo constraints
- Ensure verification commands exist and pass for this phase:
  - docker compose run --rm api pytest
  - docker compose up --build (API)
  - docker compose run --rm api python -m app.intel.worker --once (worker)
- Add tests appropriate to the phase.
- Keep outputs deterministic for tests (no live internet, mock LLM).
- Update docs/current_state.md and README to reflect what is now true.

## Output required
1) List files changed/added.
2) Commands run + results.
3) Short notes on any assumptions (only if necessary).
