from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Mapping, Sequence


EDITORIAL_WORKFLOW_VERSION = "writing-repo-v1"

PROHIBITED_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("control-character", re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")),
    ("decision-surface", re.compile(r"\bdecision surface\b", re.IGNORECASE)),
    ("announcement-signal", re.compile(r"\bthe signal is in\b", re.IGNORECASE)),
    (
        "signals-become-patterns",
        re.compile(r"\bsignals? (?:keep )?turn(?:ing)? into repeatable (?:production )?patterns\b", re.IGNORECASE),
    ),
    ("issue-meta-frame", re.compile(r"\bthis issue is most useful as\b", re.IGNORECASE)),
    ("generic-issue-intro", re.compile(r"^\s*this issue (?:covers|focuses on|spans|tracks)\b", re.IGNORECASE)),
    ("operationalise", re.compile(r"\boperationali[sz](?:e|es|ed|ing|ation)\b", re.IGNORECASE)),
    ("first-class", re.compile(r"\bfirst[- ]class\b", re.IGNORECASE)),
    ("becoming-primary", re.compile(r"\bbecoming (?:a|an|the) (?:core|primary|main|default)\b", re.IGNORECASE)),
    ("increasingly-primary", re.compile(r"\bincreasingly (?:a|an|the) (?:core|primary|main|default)\b", re.IGNORECASE)),
    ("generic-practical-look", re.compile(r"\ba practical look at\b", re.IGNORECASE)),
    ("generic-reminder", re.compile(r"\b(?:is|are) a reminder that\b", re.IGNORECASE)),
    ("same-conclusion-hinge", re.compile(r"\b(?:both )?points? to the same (?:judgement|lesson|lever|shift)\b", re.IGNORECASE)),
    ("core-requirements", re.compile(r"\bcore (?:product )?requirements?\b", re.IGNORECASE)),
    ("thought-leadership-hinge", re.compile(r"\bnot just\b[^.!?]{0,120}\bbut\b", re.IGNORECASE)),
)

ABSTRACT_TERMS = {
    "adoption",
    "capability",
    "constraint",
    "differentiator",
    "governance",
    "implication",
    "infrastructure",
    "operational",
    "pressure",
    "provenance",
    "reliability",
    "signal",
    "signals",
    "system",
    "systems",
    "trust",
}

GENERIC_TOPIC_TERMS = {
    "agents",
    "agent",
    "ai",
    "builders",
    "engineering",
    "evals",
    "evaluation",
    "infrastructure",
    "models",
    "production",
    "research",
    "systems",
    "teams",
    "tooling",
}

IMPERATIVE_OPENERS = {
    "add",
    "adopt",
    "apply",
    "benchmark",
    "build",
    "design",
    "ensure",
    "expose",
    "harden",
    "implement",
    "invest",
    "keep",
    "localize",
    "make",
    "pin",
    "prefer",
    "prototype",
    "require",
    "represent",
    "separate",
    "standardize",
    "treat",
    "use",
    "version",
}

TOP_LEVEL_LOCATIONS = {
    "title",
    "intro",
    "summary",
    "issueSummary",
    "editorial.editorialFrame",
    "editorial.builderImplication",
    "editorial.watchSignal",
}


@dataclass(frozen=True)
class EditorialFinding:
    code: str
    location: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {"code": self.code, "location": self.location, "message": self.message}


@dataclass(frozen=True)
class EditorialReviewResult:
    findings: tuple[EditorialFinding, ...]
    checked_fields: int

    @property
    def passed(self) -> bool:
        return not self.findings

    def summary(self, *, limit: int = 4) -> str:
        if self.passed:
            return "editorial review passed"
        selected = self.findings[:limit]
        detail = "; ".join(f"{finding.location}: {finding.message}" for finding in selected)
        remaining = len(self.findings) - len(selected)
        if remaining:
            detail += f"; plus {remaining} more finding(s)"
        return detail


def _normalise_text(value: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _word_count(value: str) -> int:
    return len(re.findall(r"\b[\w'-]+\b", value))


def _field_values(payload: Mapping[str, Any]) -> Iterable[tuple[str, str]]:
    for name in ("title", "intro", "summary", "issueSummary"):
        value = payload.get(name)
        if isinstance(value, str) and value.strip():
            yield name, value.strip()

    top_things = payload.get("topThings")
    if isinstance(top_things, list):
        for index, value in enumerate(top_things):
            if isinstance(value, str) and value.strip():
                yield f"topThings[{index}]", value.strip()

    editorial = payload.get("editorial")
    if isinstance(editorial, Mapping):
        for name in ("editorialFrame", "builderImplication", "watchSignal"):
            value = editorial.get(name)
            if isinstance(value, str) and value.strip():
                yield f"editorial.{name}", value.strip()

    items = payload.get("items")
    if isinstance(items, list):
        for index, item in enumerate(items):
            if not isinstance(item, Mapping):
                continue
            for name in (
                "headline",
                "contextualBackground",
                "whatHappened",
                "whyItMatters",
                "engineeringTakeaway",
            ):
                value = item.get(name)
                if isinstance(value, str) and value.strip():
                    yield f"items[{index}].{name}", value.strip()


def _recent_top_level_openings(recent_payloads: Sequence[Mapping[str, Any]]) -> dict[tuple[str, str], int]:
    counts: dict[tuple[str, str], int] = {}
    for payload in recent_payloads:
        for location, value in _field_values(payload):
            if location not in TOP_LEVEL_LOCATIONS:
                continue
            words = _normalise_text(value).split()
            if len(words) < 5:
                continue
            opening = " ".join(words[:5])
            key = (location, opening)
            counts[key] = counts.get(key, 0) + 1
    return counts


def _specific_terms(payload: Mapping[str, Any]) -> set[str]:
    terms: set[str] = set()
    items = payload.get("items")
    if not isinstance(items, list):
        return terms
    for item in items:
        if not isinstance(item, Mapping):
            continue
        for field in ("headline", "sourceName", "sourceTitle", "whatHappened"):
            value = item.get(field)
            if not isinstance(value, str):
                continue
            for token in re.findall(r"\b[A-Za-z][A-Za-z0-9.+-]{3,}\b", value):
                lowered = token.lower()
                if lowered not in GENERIC_TOPIC_TERMS:
                    terms.add(lowered)
    return terms


def _add_duplicate_findings(fields: Sequence[tuple[str, str]], findings: list[EditorialFinding]) -> None:
    seen: dict[str, str] = {}
    for location, value in fields:
        if location == "title" or location.endswith(".headline"):
            continue
        normalised = _normalise_text(value)
        if len(normalised) < 45:
            continue
        previous = seen.get(normalised)
        if previous:
            findings.append(
                EditorialFinding(
                    code="duplicate-copy",
                    location=location,
                    message=f"repeats {previous} instead of doing distinct editorial work",
                )
            )
        else:
            seen[normalised] = location


def _add_length_findings(fields: Sequence[tuple[str, str]], findings: list[EditorialFinding]) -> None:
    limits = {
        "title": (5, 18),
        "intro": (15, 60),
        "issueSummary": (10, 38),
        "editorial.editorialFrame": (10, 55),
        "editorial.builderImplication": (10, 55),
        "editorial.watchSignal": (10, 55),
    }
    suffix_limits = {
        ".whatHappened": (12, 85),
        ".whyItMatters": (12, 65),
        ".engineeringTakeaway": (10, 48),
    }
    for location, value in fields:
        bounds = limits.get(location)
        if bounds is None:
            bounds = next((limit for suffix, limit in suffix_limits.items() if location.endswith(suffix)), None)
        if bounds is None:
            continue
        count = _word_count(value)
        minimum, maximum = bounds
        if count < minimum:
            findings.append(
                EditorialFinding(
                    code="copy-too-thin",
                    location=location,
                    message=f"has {count} words; needs at least {minimum} to carry a concrete point",
                )
            )
        elif count > maximum:
            findings.append(
                EditorialFinding(
                    code="copy-too-long",
                    location=location,
                    message=f"has {count} words; compress to {maximum} or fewer",
                )
            )


def _add_sentence_findings(fields: Sequence[tuple[str, str]], findings: list[EditorialFinding]) -> None:
    for location, value in fields:
        if location == "title" or location.endswith(".headline"):
            continue
        if value[-1] not in ".!?\u201d\u2019":
            findings.append(
                EditorialFinding(
                    code="unfinished-sentence",
                    location=location,
                    message="does not end as a complete sentence",
                )
            )


def _add_pattern_findings(fields: Sequence[tuple[str, str]], findings: list[EditorialFinding]) -> None:
    for location, value in fields:
        for code, pattern in PROHIBITED_PATTERNS:
            if pattern.search(value):
                findings.append(
                    EditorialFinding(
                        code=code,
                        location=location,
                        message="uses a house-style phrase that should be replaced with a fact, mechanism, or consequence",
                    )
                )

        words = set(_normalise_text(value).split())
        abstract_count = len(words & ABSTRACT_TERMS)
        if abstract_count >= 5 and not location.endswith(".whatHappened"):
            findings.append(
                EditorialFinding(
                    code="abstract-noun-stack",
                    location=location,
                    message="stacks abstract terms without enough concrete nouns",
                )
            )


def _add_template_findings(payload: Mapping[str, Any], findings: list[EditorialFinding]) -> None:
    items = payload.get("items")
    if not isinstance(items, list) or not items:
        return

    takeaways = [
        str(item.get("engineeringTakeaway") or "").strip()
        for item in items
        if isinstance(item, Mapping) and str(item.get("engineeringTakeaway") or "").strip()
    ]
    imperative_count = sum(
        1
        for value in takeaways
        if (_normalise_text(value).split() or [""])[0] in IMPERATIVE_OPENERS
    )
    if takeaways and imperative_count > max(2, len(takeaways) // 2):
        findings.append(
            EditorialFinding(
                code="imperative-takeaway-template",
                location="items[].engineeringTakeaway",
                message=f"{imperative_count} of {len(takeaways)} takeaways begin as commands; vary the sentence shape and only prescribe action where the evidence supports it",
            )
        )

    why_values = [
        str(item.get("whyItMatters") or "").strip()
        for item in items
        if isinstance(item, Mapping) and str(item.get("whyItMatters") or "").strip()
    ]
    conditional_count = sum(
        1 for value in why_values if re.match(r"^(?:As|Even|For|If|Once|When|While)\b", value, re.IGNORECASE)
    )
    if why_values and conditional_count > max(2, len(why_values) // 2):
        findings.append(
            EditorialFinding(
                code="conditional-why-template",
                location="items[].whyItMatters",
                message=f"{conditional_count} of {len(why_values)} explanations use the same conditional opening",
            )
        )


def _add_watch_specificity_finding(payload: Mapping[str, Any], findings: list[EditorialFinding]) -> None:
    editorial = payload.get("editorial")
    if not isinstance(editorial, Mapping):
        return
    watch = editorial.get("watchSignal")
    if not isinstance(watch, str) or not watch.strip():
        return
    watch_terms = set(_normalise_text(watch).split())
    if watch_terms & _specific_terms(payload):
        return
    if re.search(r"\b\d+(?:\.\d+)?(?:%|x|[kmb])?\b", watch, re.IGNORECASE):
        return
    findings.append(
        EditorialFinding(
            code="unfalsifiable-watch",
            location="editorial.watchSignal",
            message="does not name a company, product, benchmark, measurement, or other observable evidence from this issue",
        )
    )


def _add_recent_repetition_findings(
    fields: Sequence[tuple[str, str]],
    recent_payloads: Sequence[Mapping[str, Any]],
    findings: list[EditorialFinding],
) -> None:
    opening_counts = _recent_top_level_openings(recent_payloads)
    for location, value in fields:
        if location not in TOP_LEVEL_LOCATIONS:
            continue
        words = _normalise_text(value).split()
        if len(words) < 5:
            continue
        opening = " ".join(words[:5])
        repeats = opening_counts.get((location, opening), 0)
        if repeats >= 2:
            findings.append(
                EditorialFinding(
                    code="recent-opening-repeat",
                    location=location,
                    message=f"reuses the same five-word opening as {repeats} recent issues",
                )
            )


def review_digest_payload(
    payload: Mapping[str, Any],
    *,
    recent_payloads: Sequence[Mapping[str, Any]] = (),
) -> EditorialReviewResult:
    fields = list(_field_values(payload))
    findings: list[EditorialFinding] = []
    _add_duplicate_findings(fields, findings)
    _add_length_findings(fields, findings)
    _add_sentence_findings(fields, findings)
    _add_pattern_findings(fields, findings)
    _add_template_findings(payload, findings)
    _add_watch_specificity_finding(payload, findings)
    _add_recent_repetition_findings(fields, recent_payloads, findings)

    unique: list[EditorialFinding] = []
    seen: set[tuple[str, str, str]] = set()
    for finding in findings:
        key = (finding.code, finding.location, finding.message)
        if key not in seen:
            unique.append(finding)
            seen.add(key)
    return EditorialReviewResult(findings=tuple(unique), checked_fields=len(fields))


def load_recent_digest_payloads(
    digest_dir: Path,
    *,
    before_date: str,
    limit: int = 10,
) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    if not digest_dir.exists():
        return payloads
    for path in sorted(digest_dir.glob("*.json"), reverse=True):
        if path.stem >= before_date:
            continue
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(payload, dict):
            payloads.append(payload)
        if len(payloads) >= limit:
            break
    return payloads
