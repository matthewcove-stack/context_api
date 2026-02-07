# Cloudflare Tunnel setup (Plus-friendly) — context_api

Goal: expose your local or VPS-hosted context_api over HTTPS so ChatGPT Actions can call it.

This guide uses the official cloudflared container in Docker Compose.

## Prerequisites
- A Cloudflare account
- A domain on Cloudflare DNS (e.g. kb.lambiclabs.com)
- The context_api stack running via docker compose

## 1) Create a tunnel and token (Cloudflare Dashboard)
1. In Cloudflare Dashboard: Zero Trust -> Networks -> Tunnels -> Create tunnel.
2. Choose "Cloudflared" connector.
3. Give it a name (e.g. context-api).
4. Copy the token that Cloudflare provides (a long string).

## 2) Configure DNS / Public hostname
In the tunnel setup UI, add a public hostname:
- Hostname: kb.lambiclabs.com (or whatever you choose)
- Service: http://api:8001  (this is the docker-compose service name + port)

Cloudflare will create the required DNS record automatically.

## 3) Add env var locally
Add this to your .env file (do not commit it):
- CLOUDFLARE_TUNNEL_TOKEN=...your token...

## 4) Start with the tunnel compose override
From the repo root:

    docker compose -f docker-compose.yml -f docker-compose.cloudflare-tunnel.yml up --build

This runs:
- postgres
- migrate
- api
- cloudflared (the tunnel)

## 5) Verify
- Confirm your public hostname returns something:
  - https://kb.lambiclabs.com/docs  (FastAPI docs, if enabled)
  - Or call a known endpoint with bearer token.

Example:

    curl -sS -H "Authorization: Bearer YOUR_CONTEXT_API_TOKEN" \
      -H "Content-Type: application/json" \
      https://kb.lambiclabs.com/v2/context/pack \
      -d '{"query":"test"}'

## Notes
- Actions requires HTTPS and public reachability.
- Keep your CONTEXT_API_TOKEN long and random. Treat it like a password.
