"""The state builders and the question definitions themselves."""

from __future__ import annotations

import json

import pytest

from server.jev import questions as q
from server.jev import state as s


def test_email_state_omits_timestamps() -> None:
    # jev-1.13 reads dates as text, not as ordered quantities, so no date or
    # time may be handed to it. Age reasoning stays in Python.
    built = s.email_state(
        sender="a@example.com",
        recipient="b@example.com",
        subject="Re: lunch",
        body="body",
    )

    # Checked against the field names, not the body text: a real email may
    # well say "let me know a time".
    for forbidden in ("timestamp", "received", "date", "time", "age"):
        assert forbidden not in built, forbidden
    assert set(built) == {
        "from",
        "to",
        "subject",
        "labels",
        "has_attachments",
        "attachment_filenames",
        "body",
    }


def test_email_state_clips_body_to_budget(monkeypatch: pytest.MonkeyPatch, reload_settings) -> None:
    monkeypatch.setenv("JEV_STATE_CHAR_BUDGET", "50")
    reload_settings()

    built = s.email_state(
        sender="a@example.com", recipient="b@example.com", subject="s", body="x" * 5000
    )

    assert len(built["body"]) == 50, "clip must respect the budget, marker included"
    assert built["body"].endswith("[truncated]")


def test_search_state_splits_budget_across_candidates(
    monkeypatch: pytest.MonkeyPatch, reload_settings
) -> None:
    monkeypatch.setenv("JEV_STATE_CHAR_BUDGET", "1024")
    reload_settings()

    built = s.search_state(
        request="invoices from Acme",
        candidates=[{"from": "a", "subject": "s", "body": "y" * 4000} for _ in range(8)],
    )

    assert [c["index"] for c in built["candidates"]] == list(range(8))
    assert sum(len(c["body"]) for c in built["candidates"]) <= 1024


def test_search_state_caps_the_candidate_count(
    monkeypatch: pytest.MonkeyPatch, reload_settings
) -> None:
    # The candidate count comes from an LLM's selection, so the state size
    # must not grow with it.
    monkeypatch.setenv("JEV_SEARCH_MAX_CANDIDATES", "5")
    monkeypatch.setenv("JEV_STATE_CHAR_BUDGET", "1024")
    reload_settings()

    built = s.search_state(
        request="invoices",
        candidates=[{"from": "a", "subject": "s", "body": "y" * 9000} for _ in range(400)],
    )

    assert len(built["candidates"]) == 5
    assert len(json.dumps(built)) < 4000


def test_tool_call_state_keeps_non_string_arguments() -> None:
    built = s.tool_call_state(
        assignment="reply to Dana",
        tool_name="GMAIL_SEND_EMAIL",
        arguments={"to": "dana@example.com", "cc": ["x@example.com"], "draft": True},
    )

    assert built["tool"]["arguments"]["cc"] == ["x@example.com"]
    assert built["tool"]["arguments"]["draft"] is True


def test_clip_handles_degenerate_limits() -> None:
    assert s.clip("abc", 0) == ""
    assert s.clip(None, 10) == ""
    assert s.clip("abc", 10) == "abc"
    assert len(s.clip("x" * 100, 5)) == 5
    assert len(s.clip("x" * 100, 40)) == 40


@pytest.mark.parametrize("questions", [q.EMAIL_QUESTIONS, q.TOOL_QUESTIONS])
def test_question_definitions_are_atomic_nouls(questions) -> None:
    for key, question in questions.items():
        assert question["type"] == "noul", key
        assert isinstance(question["instructions"], str) and question["instructions"], key
        # Atomic: one judgement per question. A conjunction is the smell the
        # docs warn about, so keep the instruction short and single-clause.
        assert " and " not in question["instructions"].lower().replace(" and the ", " "), key
        assert set(question["criteria"]) == {"true", "false"}, key


def test_search_relevance_keys_are_positional() -> None:
    built = q.search_relevance_questions(3)

    assert list(built) == ["candidate_0", "candidate_1", "candidate_2"]
    assert q.relevance_key(2) == "candidate_2"
    assert "index 2" in built["candidate_2"]["instructions"]
