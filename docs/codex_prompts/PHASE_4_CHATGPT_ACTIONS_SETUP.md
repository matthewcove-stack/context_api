# Phase 4 — ChatGPT Custom GPT (Actions) integration

Implement ONLY Phase 4 from docs/phases.md.
Obey docs/codex_rules.md. Truth hierarchy: docs/current_state.md is authoritative.

## Goal
Provide everything needed to use context_api as a knowledge base from ChatGPT (Plus plan) via a Custom GPT with Actions:
- OpenAPI schema file (read-only endpoints)
- GPT instructions file
- Cloudflare Tunnel deployment guide + docker compose override
- docs updates, env example updates

## Required changes
1) Add adapter assets
- adapters/chatgpt_actions/openapi.yaml
- adapters/chatgpt_actions/gpt_instructions.md

2) Add docs
- docs/chatgpt_actions_setup.md
- docs/deployment/cloudflare_tunnel.md

3) Add docker compose override for tunnel
- docker-compose.cloudflare-tunnel.yml
  - cloudflared service using CLOUDFLARE_TUNNEL_TOKEN
  - routes to api:8001

4) Update docs for drift prevention
- docs/current_state.md: add Actions integration section
- docs/phases.md: add Phase 4
- docs/codex_rules.md: add Actions/read-only schema guidance
- README.md: link to setup doc
- AGENTS.md: mention Phase 4 and where the adapter assets live
- .env.example: add CLOUDFLARE_TUNNEL_TOKEN and PUBLIC_BASE_URL (used when generating OpenAPI)

## Verification
- Ensure no /v1 endpoints are changed.
- Ensure docs are consistent.
- No tests required for Phase 4, but keep changes minimal and reviewable.

## Output required
1) List files added/changed.
2) Commands run (if any).
