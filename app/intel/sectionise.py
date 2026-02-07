from __future__ import annotations

import re
from typing import Any, Dict, List


def _split_paragraphs(text: str) -> List[str]:
    chunks = re.split(r"\n{2,}", text)
    return [chunk.strip() for chunk in chunks if chunk.strip()]


def sectionise(text: str) -> Dict[str, List[Dict[str, Any]]]:
    paragraphs = _split_paragraphs(text)
    if not paragraphs:
        return {"sections": [], "outline": []}

    sections: List[Dict[str, Any]] = []
    outline: List[Dict[str, Any]] = []
    buffer: List[str] = []
    max_chars = 2000
    rank = 1

    def flush() -> None:
        nonlocal rank, buffer
        if not buffer:
            return
        content = "\n\n".join(buffer)
        section_id = f"s{rank:02d}"
        heading = f"Section {rank}"
        blurb = content[:160].strip()
        sections.append(
            {"section_id": section_id, "heading": heading, "content": content, "rank": rank}
        )
        outline.append({"section_id": section_id, "heading": heading, "blurb": blurb})
        rank += 1
        buffer = []

    for para in paragraphs:
        if buffer and sum(len(p) for p in buffer) + len(para) > max_chars:
            flush()
        buffer.append(para)
    flush()

    return {"sections": sections, "outline": outline}
