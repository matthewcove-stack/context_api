from __future__ import annotations

import json
import os
from typing import Any, Dict, List, Optional, Tuple

import httpx
from pydantic import BaseModel, Field, ValidationError

PROMPT_VERSION = "v1"
DEFAULT_MAX_SIGNALS = 8
DEFAULT_MAX_SUMMARY_CHARS = 900
DEFAULT_MAX_SIGNAL_CHARS = 280
DEFAULT_MAX_SNIPPET_CHARS = 200
DEFAULT_SECTION_PROMPT_CHARS = 2000


class CitePointer(BaseModel):
    section_id: str


class EnrichmentSignal(BaseModel):
    claim: str
    why: str
    tradeoff: Optional[str] = None
    supporting_snippet: str
    cite: CitePointer


class EnrichmentOutput(BaseModel):
    summary: str
    signals: List[EnrichmentSignal]
    topics: List[str] = Field(default_factory=list)
    freshness_half_life_days: Optional[int] = None


def _get_int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _trim(text: str, max_chars: int) -> str:
    if max_chars <= 0:
        return ""
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _build_prompt(title: Optional[str], url: str, sections: List[Dict[str, Any]]) -> str:
    max_section_chars = _get_int_env("INTEL_SECTION_PROMPT_CHARS", DEFAULT_SECTION_PROMPT_CHARS)
    section_blocks = []
    for section in sections:
        section_id = section.get("section_id")
        content = _trim(str(section.get("content") or ""), max_section_chars)
        section_blocks.append({"section_id": section_id, "content": content})
    payload = {
        "title": title or "",
        "url": url,
        "sections": section_blocks,
        "instructions": {
            "summary_max_chars": DEFAULT_MAX_SUMMARY_CHARS,
            "signals_max": DEFAULT_MAX_SIGNALS,
            "signal_field_max_chars": DEFAULT_MAX_SIGNAL_CHARS,
            "supporting_snippet_max_chars": DEFAULT_MAX_SNIPPET_CHARS,
        },
    }
    return json.dumps(payload, ensure_ascii=True)


def call_llm(prompt: str, *, model: str, api_key: str) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY is required for enrichment")
    url = os.getenv("OPENAI_API_BASE", "https://api.openai.com/v1/chat/completions")
    payload = {
        "model": model,
        "temperature": 0.2,
        "messages": [
            {
                "role": "system",
                "content": "Return strict JSON only. No markdown. Follow the provided instructions.",
            },
            {"role": "user", "content": prompt},
        ],
    }
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    response = httpx.post(url, json=payload, headers=headers, timeout=30)
    response.raise_for_status()
    data = response.json()
    content = data["choices"][0]["message"]["content"]
    return json.loads(content), {"token_usage": data.get("usage")}


def _validate_enrichment(
    output: EnrichmentOutput,
    *,
    sections: List[Dict[str, Any]],
) -> None:
    max_summary = _get_int_env("INTEL_SUMMARY_MAX_CHARS", DEFAULT_MAX_SUMMARY_CHARS)
    max_signals = _get_int_env("INTEL_SIGNALS_MAX", DEFAULT_MAX_SIGNALS)
    max_signal_chars = _get_int_env("INTEL_SIGNAL_MAX_CHARS", DEFAULT_MAX_SIGNAL_CHARS)
    max_snippet = _get_int_env("INTEL_SNIPPET_MAX_CHARS", DEFAULT_MAX_SNIPPET_CHARS)
    if len(output.summary) > max_summary:
        raise ValueError("summary too long")
    if len(output.signals) > max_signals:
        raise ValueError("too many signals")
    section_map = {section.get("section_id"): section.get("content") or "" for section in sections}
    for signal in output.signals:
        if len(signal.claim) > max_signal_chars or len(signal.why) > max_signal_chars:
            raise ValueError("signal field too long")
        if signal.tradeoff and len(signal.tradeoff) > max_signal_chars:
            raise ValueError("tradeoff too long")
        if len(signal.supporting_snippet) > max_snippet:
            raise ValueError("supporting_snippet too long")
        section_id = signal.cite.section_id
        if section_id not in section_map:
            raise ValueError(f"invalid section_id: {section_id}")
        if signal.supporting_snippet not in section_map[section_id]:
            raise ValueError("supporting_snippet not found in section content")


def enrich_article(
    *,
    title: Optional[str],
    url: str,
    sections: List[Dict[str, Any]],
    model: str,
    api_key: str,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    prompt = _build_prompt(title, url, sections)
    raw_output, usage = call_llm(prompt, model=model, api_key=api_key)
    try:
        parsed = EnrichmentOutput.model_validate(raw_output)
    except ValidationError as exc:
        raise ValueError(f"invalid enrichment schema: {exc}") from exc
    _validate_enrichment(parsed, sections=sections)
    result = parsed.model_dump()
    result["summary"] = _trim(result.get("summary", ""), DEFAULT_MAX_SUMMARY_CHARS)
    return result, {
        "model": model,
        "prompt_version": PROMPT_VERSION,
        "token_usage": usage.get("token_usage"),
    }
