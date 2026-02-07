# ChatGPT Actions setup (context_api)

This guide configures a Custom GPT (Actions) to use context_api as a read-only knowledge base.

## Prereqs
- A public base URL for context_api (Cloudflare Tunnel recommended)
- CONTEXT_API_TOKEN (bearer token)
- Updated OpenAPI schema with your public base URL

## Files
- OpenAPI schema: adapters/chatgpt_actions/openapi.yaml
- GPT instructions: adapters/chatgpt_actions/gpt_instructions.md

## Step 1: Set PUBLIC_BASE_URL
Set PUBLIC_BASE_URL in .env or your deployment environment.

Example:
- PUBLIC_BASE_URL=https://your-public-hostname.example

## Step 2: Create the Custom GPT
1) Open ChatGPT (Plus plan) and create a new GPT.
2) Paste adapters/chatgpt_actions/gpt_instructions.md into the Instructions field.
3) Add an Action and import adapters/chatgpt_actions/openapi.yaml.
   - Replace https://YOUR_PUBLIC_BASE_URL with your PUBLIC_BASE_URL before upload.
4) Configure Authentication:
   - Type: API key
   - Location: Header
   - Name: Authorization
   - Value: Bearer <CONTEXT_API_TOKEN>

## Step 3: Test
Use a query that should match your intel corpus:
- "What are the latest signals on GPU supply constraints?"

If results are empty, verify that:
- the API is reachable from the public URL
- the token is correct
- intel articles are ingested and enriched

## Read-only scope
The schema only exposes read-only endpoints:
- /v2/context/pack
- /v2/intel/articles/{article_id}
- /v2/intel/articles/{article_id}/outline
- /v2/intel/articles/{article_id}/sections
- /v2/intel/articles/{article_id}/chunks:search
