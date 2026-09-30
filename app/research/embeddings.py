from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from typing import Iterable, List

import httpx

logger = logging.getLogger(__name__)


class EmbeddingProviderError(RuntimeError):
    """Actionable provider failure without request headers or provider prose."""

    def __init__(self, *, status: int, code: str, account_blocked: bool) -> None:
        self.status = status
        self.code = code
        self.account_blocked = account_blocked
        self.exit_status = 78 if account_blocked else 75
        self.action = (
            "Restore OpenAI account credit, limits or permissions before retrying."
            if account_blocked
            else "Wait for the provider rate limit or availability to recover before retrying."
        )
        super().__init__(f"OpenAI HTTP {status}: {code}. {self.action}")


# A long-running worker should not send the same blocked request for every
# document. Cooldowns are per credential, contain no raw response data, and
# expire so restoring credit does not require a restart.
_provider_cooldowns: dict[str, tuple[float, int, str, bool]] = {}


def _check_provider_response(response: httpx.Response, *, credential_id: str) -> None:
    if response.status_code not in {401, 403, 429, 500, 502, 503, 504}:
        response.raise_for_status()
        return
    try:
        error = response.json().get("error") or {}
        code = str(error.get("code") or error.get("type") or "provider_unavailable")
        error_type = str(error.get("type") or "")
    except (ValueError, AttributeError):
        code, error_type = "provider_unavailable", ""
    code = re.sub(r"[^a-zA-Z0-9_]", "", code)[:80]
    account_blocked = response.status_code in {401, 403} or error_type == "insufficient_quota" or code in {
        "insufficient_quota", "credit_balance_exhausted", "organization_spend_limit_exceeded",
        "project_spend_limit_exceeded", "organization_usage_limit_exceeded",
    }
    failure = EmbeddingProviderError(status=response.status_code, code=code, account_blocked=account_blocked)
    try:
        retry_after = float(response.headers.get("retry-after", "60"))
    except ValueError:
        retry_after = 60
    cooldown = 900 if account_blocked else max(60, min(retry_after, 3600))
    # Store values, not exception instances: raised exceptions retain traceback
    # frames (including request data) and accumulate frames when raised again.
    _provider_cooldowns[credential_id] = (time.monotonic() + cooldown, response.status_code, code, account_blocked)
    raise failure


def _hash_embedding(text: str, *, dims: int = 64) -> List[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    values = [digest[i % len(digest)] for i in range(max(dims, 8))]
    # Normalize bytes to [-1, 1]
    return [((value / 255.0) * 2.0) - 1.0 for value in values]


def _hash_model_dims(model: str) -> int:
    lowered = model.lower()
    if lowered.startswith("hash-"):
        suffix = lowered.split("-", 1)[1]
        try:
            return max(int(suffix), 8)
        except ValueError:
            return 64
    return 64


def hash_embeddings_allowed() -> bool:
    return os.getenv("RESEARCH_ALLOW_HASH_EMBEDDINGS", "").strip().lower() in {"1", "true", "yes", "on"}


def resolve_embedding_runtime(*, model: str, api_key: str = "") -> dict:
    normalized_model = (model or "").strip() or "text-embedding-3-small"
    key_present = bool(api_key.strip())
    is_hash = normalized_model.lower().startswith("hash")
    allow_hash = hash_embeddings_allowed()
    if is_hash:
        return {
            "model": normalized_model,
            "mode": "hash",
            "provider": "local",
            "api_key_present": key_present,
            "hash_fallback_enabled": allow_hash,
            "warning": "hash embeddings are active; retrieval quality is reduced",
        }
    if key_present:
        return {
            "model": normalized_model,
            "mode": "openai",
            "provider": "openai",
            "api_key_present": True,
            "hash_fallback_enabled": allow_hash,
            "warning": None,
        }
    return {
        "model": normalized_model,
        "mode": "misconfigured",
        "provider": "openai",
        "api_key_present": False,
        "hash_fallback_enabled": allow_hash,
        "warning": "OPENAI_API_KEY is missing for the configured embedding model",
    }


def embed_texts(
    *,
    texts: Iterable[str],
    model: str,
    api_key: str = "",
) -> List[List[float]]:
    text_list = [str(text) for text in texts]
    if not text_list:
        return []
    runtime = resolve_embedding_runtime(model=model, api_key=api_key)
    if runtime["mode"] == "hash":
        logger.warning(runtime["warning"])
        dims = _hash_model_dims(model)
        return [_hash_embedding(text, dims=dims) for text in text_list]
    if runtime["mode"] == "misconfigured":
        if hash_embeddings_allowed():
            logger.warning("%s; using explicit hash fallback", runtime["warning"])
            dims = _hash_model_dims("hash-64")
            return [_hash_embedding(text, dims=dims) for text in text_list]
        raise RuntimeError(runtime["warning"])

    base_url = "https://api.openai.com/v1/embeddings"
    credential_id = hashlib.sha256(api_key.encode()).hexdigest()
    blocked = _provider_cooldowns.get(credential_id)
    if blocked and time.monotonic() < blocked[0]:
        raise EmbeddingProviderError(status=blocked[1], code=blocked[2], account_blocked=blocked[3])
    _provider_cooldowns.pop(credential_id, None)
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    vectors = []
    batch: List[str] = []
    batch_chars = 0

    def flush(current_batch: List[str]) -> None:
        nonlocal vectors
        payload = {"model": model, "input": current_batch}
        response = httpx.post(base_url, headers=headers, json=payload, timeout=30)
        _check_provider_response(response, credential_id=credential_id)
        data = response.json()
        batch_vectors = []
        for row in data.get("data", []):
            embedding = row.get("embedding")
            if isinstance(embedding, list):
                batch_vectors.append([float(value) for value in embedding])
        if len(batch_vectors) != len(current_batch):
            raise RuntimeError("embedding response length mismatch")
        vectors.extend(batch_vectors)

    for text in text_list:
        text_chars = len(text)
        if batch and (len(batch) >= 32 or batch_chars + text_chars > 20000):
            flush(batch)
            batch = []
            batch_chars = 0
        batch.append(text)
        batch_chars += text_chars
    if batch:
        flush(batch)
    if len(vectors) != len(text_list):
        raise RuntimeError("embedding response length mismatch")
    return vectors
