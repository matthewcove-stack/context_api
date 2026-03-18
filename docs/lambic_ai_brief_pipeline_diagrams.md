# Lambic AI Brief Pipeline Diagrams

This document gives a visual model of the production pipeline from research ingestion to website deployment.

## 1) Research Ingestion, Enrichment, and Indexing

```mermaid
flowchart TD
  A["Research Source Records (DB)"] --> B["Worker Loop (app/research/worker.py)"]
  B --> C["Claim Ingestion Run"]
  C --> D["Fetch Source Page / Feed"]
  D --> E["Discover Candidate URLs"]
  E --> F["Seed + Deduplicate Document"]
  F --> G["Fetch Document HTML/PDF"]
  G --> H["Extract Readable Text"]
  H --> I["Junk / Suppression Check"]
  I --> J["Heuristic Enrichment (summary, tags, metrics, insights)"]
  J --> K["Chunk Document Text"]
  K --> L["Create Embeddings"]
  L --> M["Store Chunks + Vectors + Enrichment in DB"]
  M --> N["Mark Run/Source Status + Counters"]
```

## 2) Daily Brief Publish Orchestration

```mermaid
flowchart TD
  A["Scheduler (GitHub Actions, self-hosted)"] --> B["scripts/publish_lambic_ai_brief.py"]
  B --> C["execute_publish (app/research/publish_pipeline.py)"]
  C --> D["Preflight Checks"]
  D --> D1["Runtime env present"]
  D --> D2["Research DB reachable"]
  D --> D3["Candidate sufficiency (daily mode)"]
  D --> D4["Website repo valid + clean (live mode)"]
  D4 --> E["Daily Digest Generation (digest_generator.py)"]
  E --> E1["Compute target date/window"]
  E --> E2["Load + score + dedupe candidates"]
  E --> E3["OpenAI draft -> normalize -> write daily JSON"]
  E3 --> F["Distribution Generation (distribution_generator.py)"]
  F --> F1["Rebuild digest-assets JSON"]
  F --> F2["Rebuild weekly JSON"]
  F2 --> G["Website Validation Steps"]
  G --> G1["npm run research:validate"]
  G --> G2["npm run research:feeds"]
  G --> G3["npm run build"]
  G3 --> H["Stage publish outputs"]
  H --> I["One commit + one push (live mode)"]
  I --> J["Write structured publish report JSON"]
```

## 3) Website Build and Deployment

```mermaid
flowchart TD
  A["Website Repo Push to main"] --> B["GitHub Workflow (.github/workflows/deploy.yml)"]
  B --> C["Build job (ubuntu): build + push GHCR image"]
  C --> D["Deploy job (self-hosted): SSH to lambic-local-1"]
  D --> E["remote_deploy.sh"]
  E --> E1["git pull --ff-only in /srv/lambic/apps/lambic-labs-site"]
  E --> E2["docker login ghcr.io (ephemeral token)"]
  E --> E3["docker pull tagged image"]
  E --> E4["WEB_IMAGE=... docker compose up -d --no-build"]
  E4 --> F["Container serves static brief content from baked image"]
```

## 4) End-to-End Data to Site Path

```mermaid
flowchart LR
  A["Raw Research Sources"] --> B["Ingestion + Enrichment + Embeddings (context_api DB)"]
  B --> C["Daily/Weekly Artifact Generation (context_api publish pipeline)"]
  C --> D["Static Content Files in lambic_labs_website"]
  D --> E["Website Build + Image Publish (GHCR)"]
  E --> F["Deploy to lambic-local-1"]
  F --> G["Public Routes (/brief, /brief/[date], /brief/weekly/[week])"]
```

## Operational Notes

- Daily brief generation and weekly/asset regeneration are now part of one canonical publish command.
- Dry-run mode performs the same generation and validation sequence in a temp workspace copy and does not push.
- The website deploy path is image-based (`docker compose up -d --no-build`) and uses the GHCR image built by CI.
- The website reads brief artifacts from `apps/web/content/research-digests` and `apps/web/content/research-weekly` at build/runtime loader boundaries.
