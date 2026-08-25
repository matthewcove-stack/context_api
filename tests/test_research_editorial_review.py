from __future__ import annotations

from app.research.editorial_review import review_digest_payload


def _item(index: int, *, takeaway: str) -> dict[str, object]:
    return {
        "documentId": f"doc-{index}",
        "headline": f"Toyota agent test {index} records tool failures in LangSmith",
        "sourceName": "LangChain Blog",
        "sourceTitle": f"Toyota agent test {index}",
        "whatHappened": (
            f"Toyota published test {index} with tool-call traces from its enterprise assistant programme and described how engineers inspect failed runs."
        ),
        "whyItMatters": (
            f"The trace for test {index} connects a failed answer to the tool input that caused it, which lets reviewers reproduce the defect before changing the prompt."
        ),
        "engineeringTakeaway": takeaway,
    }


def test_review_rejects_the_repeated_lambic_view_template() -> None:
    payload = {
        "title": "Enterprise agents meet controls in production",
        "intro": "Toyota described its agent programme and the tools used to inspect failures across a large organisation.",
        "summary": "The programme relies on shared traces, permissions, and tests before teams can reuse an agent workflow.",
        "issueSummary": "Agent teams need evidence from failed runs before they can standardise a workflow.",
        "topThings": [
            "Giving assistants broad access to inboxes and documents requires explicit permissions and redaction.",
            "Toyota uses LangSmith traces to inspect failures in its shared agent stack.",
        ],
        "editorial": {
            "editorialFrame": "This issue is most useful as a decision surface for teams working on agents; the signal is in implementation choices, not announcement volume.",
            "builderImplication": "Giving assistants broad access to inboxes and documents requires explicit permissions and redaction.",
            "watchSignal": "Watch whether agents signals turn into repeatable production patterns.",
        },
        "items": [
            _item(1, takeaway="Treat traces as a first-class release record for every agent change."),
            _item(2, takeaway="Build permission tests before connecting the assistant to private messages."),
            _item(3, takeaway="Implement a redaction check for documents returned from restricted channels."),
        ],
    }

    review = review_digest_payload(payload)
    codes = {finding.code for finding in review.findings}

    assert review.passed is False
    assert "decision-surface" in codes
    assert "signals-become-patterns" in codes
    assert "duplicate-copy" in codes
    assert "imperative-takeaway-template" in codes


def test_review_accepts_specific_varied_editorial_copy() -> None:
    payload = {
        "title": "Toyota exposes the maintenance cost of enterprise agents",
        "intro": (
            "Toyota's 35-person enterprise AI team uses LangGraph for workflows and LangSmith to inspect failed runs. "
            "Its account is useful because it names the engineering work behind an internal agent programme."
        ),
        "summary": (
            "Shared traces let Toyota compare failures across teams instead of debugging each assistant in isolation. "
            "That makes the maintenance cost visible: tool contracts, permissions, test cases, and failed runs all need owners."
        ),
        "issueSummary": "Toyota's account shows that shared traces, rather than model choice, determine whether its agent work can be maintained.",
        "topThings": [
            "Toyota's central team uses LangSmith traces to compare failures across separate agent projects.",
            "Access to messages and documents needs task-level permissions because a correct answer can still expose restricted material.",
        ],
        "editorial": {
            "editorialFrame": "Toyota's tooling choice matters less than the shared record it creates for failures, permissions, and fixes.",
            "builderImplication": "A reusable agent workflow needs an owner for its tool contracts, access rules, test cases, and failed-run archive.",
            "watchSignal": "Toyota or LangSmith publishing failure rates across several deployed workflows would show whether the shared approach reduces maintenance work.",
        },
        "items": [
            _item(1, takeaway="Toyota's teams should keep tool inputs with each failed trace so engineers can reproduce the fault."),
            _item(2, takeaway="Products connected to private messages need task-level access rules and tests containing deliberately restricted content."),
            _item(3, takeaway="A contract test for each tool boundary gives reviewers a stable check when the model or SDK changes."),
        ],
    }

    review = review_digest_payload(payload)

    assert review.passed is True, review.summary()


def test_review_rejects_an_opening_reused_across_recent_issues() -> None:
    payload = {
        "title": "Toyota exposes the maintenance cost of enterprise agents",
        "intro": "Toyota published a detailed account of how its central team reviews agent failures before other teams reuse a workflow.",
        "summary": "Shared traces give separate teams a common record for tool failures and permission decisions.",
        "issueSummary": "Toyota's account shows how a central team can compare failures across agent projects.",
        "topThings": ["Toyota records tool inputs with failed LangSmith traces.", "Teams compare failures before changing shared workflows."],
        "editorial": {
            "editorialFrame": "Toyota's tooling choice matters because failed runs stay available for comparison across teams.",
            "builderImplication": "A shared trace needs the tool input, permission decision, model version, and resulting output.",
            "watchSignal": "Toyota publishing failure rates across several LangSmith projects would test whether shared traces reduce repeated debugging.",
        },
        "items": [
            _item(1, takeaway="Toyota's teams should retain the tool input with each failed trace for later comparison."),
            _item(2, takeaway="Permission tests should include restricted messages that the assistant must never quote in its answer."),
            _item(3, takeaway="A stored model version makes a failed LangSmith run reproducible after a provider update."),
        ],
    }
    recent = [
        {"title": "Toyota exposes the maintenance cost of model routing"},
        {"title": "Toyota exposes the maintenance cost of tool calling"},
    ]

    review = review_digest_payload(payload, recent_payloads=recent)

    assert any(finding.code == "recent-opening-repeat" and finding.location == "title" for finding in review.findings)
