# Intent: Context API

## Overview

Provide a read-optimized context API backed by Postgres for fast, deterministic context packs.

## Responsibilities

- Mirror key Notion databases (start with Projects + Tasks).
- Expose compact context endpoints (project snapshots, search snippets).
- Support manual sync endpoints first; background sync later.

## Non-Goals

- Not a reasoning engine or orchestration layer.
- Not a live Notion search proxy per chat turn.
