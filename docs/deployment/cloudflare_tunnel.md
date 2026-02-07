# Cloudflare Tunnel deployment

This guide exposes context_api using Cloudflare Tunnel for ChatGPT Actions.

## Prereqs
- A Cloudflare account and a Tunnel token
- docker compose

## Steps
1) Create a Cloudflare Tunnel and copy the token.
2) Set CLOUDFLARE_TUNNEL_TOKEN in your environment (.env or CI secrets).
3) Start the stack with the tunnel override:

```
docker compose -f docker-compose.yml -f docker-compose.cloudflare-tunnel.yml up --build
```

4) Configure your DNS or tunnel hostname in Cloudflare so it routes to the tunnel.
5) Use that hostname as PUBLIC_BASE_URL for the ChatGPT Actions schema.

## Notes
- The tunnel routes to api:8001 inside docker compose.
- Keep CONTEXT_API_TOKEN private; use it only in the ChatGPT Action auth configuration.
