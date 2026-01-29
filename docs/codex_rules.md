# Codex Rules — context_api

- Keep response payloads compact; context API is for hints, not full Notion objects.
- Avoid schema drift: any contract change must update notion_assistant_contracts.
- Maintain docker-only reproducibility; tests must run in compose.
