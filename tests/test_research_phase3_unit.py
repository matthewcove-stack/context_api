from __future__ import annotations

from app.research.chunking import chunk_document
from app.research.embeddings import embed_texts


def test_chunk_document_is_deterministic() -> None:
    text = "Para one.\n\nPara two with more words.\n\nPara three."
    first = chunk_document(document_id="doc_1", text=text, max_chars=40)
    second = chunk_document(document_id="doc_1", text=text, max_chars=40)
    assert first == second
    assert len(first) >= 2
    assert first[0]["chunk_id"].startswith("chk_")


def test_hash_embeddings_are_deterministic() -> None:
    texts = ["alpha chunk", "beta chunk"]
    first = embed_texts(texts=texts, model="hash-16")
    second = embed_texts(texts=texts, model="hash-16")
    assert first == second
    assert len(first) == 2
    assert len(first[0]) == 16
