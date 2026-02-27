from __future__ import annotations

import hashlib
from typing import Iterable, List

import httpx


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


def embed_texts(
    *,
    texts: Iterable[str],
    model: str,
    api_key: str = "",
) -> List[List[float]]:
    text_list = [str(text) for text in texts]
    if not text_list:
        return []
    if model.lower().startswith("hash") or not api_key:
        dims = _hash_model_dims(model)
        return [_hash_embedding(text, dims=dims) for text in text_list]

    base_url = "https://api.openai.com/v1/embeddings"
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {"model": model, "input": text_list}
    response = httpx.post(base_url, headers=headers, json=payload, timeout=30)
    response.raise_for_status()
    data = response.json()
    vectors = []
    for row in data.get("data", []):
        embedding = row.get("embedding")
        if isinstance(embedding, list):
            vectors.append([float(value) for value in embedding])
    if len(vectors) != len(text_list):
        raise RuntimeError("embedding response length mismatch")
    return vectors
