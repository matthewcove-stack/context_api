# ChatGPT Custom GPT + Actions setup (Plus plan)

This repo exposes a Context API that can act as an external knowledge base for ChatGPT using a Custom GPT with Actions.

## What you'll create
- A Custom GPT (e.g. "Lambic Labs Operator")
- One Action using the OpenAPI schema in:
  - adapters/chatgpt_actions/openapi.yaml
- Bearer auth using the same CONTEXT_API_TOKEN you run the API with

## Step 1 — Run context_api publicly (HTTPS)
Use Cloudflare Tunnel (recommended):
- Follow docs/deployment/cloudflare_tunnel.md
- You will get a public HTTPS URL (e.g. https://kb.lambiclabs.com)

## Step 2 — Prepare the OpenAPI schema
Open:
- adapters/chatgpt_actions/openapi.yaml
Replace:
- https://YOUR_PUBLIC_CONTEXT_API_BASE_URL
with your real public base URL.

## Step 3 — Create the Custom GPT
In ChatGPT:
1) Create a GPT -> Configure -> Actions -> Import OpenAPI
2) Paste the OpenAPI YAML
3) Authentication: API Key / Bearer
   - Header: Authorization
   - Value: Bearer <CONTEXT_API_TOKEN>
4) Save

## Step 4 — Add Instructions
Paste:
- adapters/chatgpt_actions/gpt_instructions.md
into the GPT's Instructions.

## How to use (day to day)
Chat inside your Custom GPT as normal. For planning / architecture / repo artifact requests, it will:
- call getContextPack first
- expand sections only if needed
- then answer with grounded output

## Keep ingestion separate
For safety, the Action schema intentionally excludes write endpoints like ingest_urls.
Do ingestion via curl/scripts/CLI and keep the GPT read-only.


## Health checks
- Public connectivity (no auth): `GET /health`
- Readiness (DB reachable): `GET /ready`

Use these to verify the tunnel and service before configuring the Action.
