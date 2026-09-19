"""The decision log: what makes thresholds re-tunable offline."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from server.jev import decisions as d
from server.jev import thresholds as t
from server.jev.decision_log import DecisionLog
from tests.conftest import noul_answers


async def test_screening_decisions_are_recorded(
    jev_env: None, jev_transport, isolated_decision_log: DecisionLog
) -> None:
    jev_transport(
        noul_answers(important=0.91, security_code=0.0, automated_bulk=0.0, prompt_injection=0.0)
    )

    screening = await d.screen_email(
        sender="dana@example.com", recipient="me@example.com", subject="Contract", body="..."
    )
    d.record_screening(screening, message_id="msg-1", sender="dana@example.com", subject="Contract")

    entries = isolated_decision_log.entries()
    assert len(entries) == 1
    assert entries[0]["kind"] == "email_screening"
    assert entries[0]["verdict"] == d.SURFACE
    assert entries[0]["probabilities"]["important"] == 0.91
    assert entries[0]["model"] == "jev-1.13.0", "the model version must travel with the number"


async def test_log_stores_no_email_body(
    jev_env: None, jev_transport, isolated_decision_log: DecisionLog
) -> None:
    jev_transport(
        noul_answers(important=0.9, security_code=0.0, automated_bulk=0.0, prompt_injection=0.0)
    )
    secret = "PLEASE-DO-NOT-STORE-THIS-BODY"

    screening = await d.screen_email(
        sender="a@example.com", recipient="b@example.com", subject="s", body=secret
    )
    d.record_screening(screening, message_id="m", sender="a@example.com", subject="s")

    blob = json.dumps(isolated_decision_log.entries())
    assert secret not in blob, "the log re-thresholds decisions; it is not a copy of the mailbox"

    # An allow-list, so that adding any new field to a record is a deliberate
    # act someone has to come here and change.
    allowed = {
        "ts",
        "kind",
        "verdict",
        "reason",
        "model",
        "probabilities",
        "message_id",
        "sender",
        "subject",
        "tool",
    }
    for entry in isolated_decision_log.entries():
        assert set(entry) <= allowed, f"unexpected field in the decision log: {set(entry) - allowed}"


async def test_guardrail_decisions_are_recorded(
    jev_env: None, jev_transport, isolated_decision_log: DecisionLog
) -> None:
    jev_transport(
        noul_answers(intent_mismatch=0.92, off_task=0.1, irreversible=0.99, mutates=0.98)
    )

    await d.review_tool_call(
        assignment="Reply to Dana.", tool_name="GMAIL_SEND_EMAIL", arguments={"to": "d@e.com"}
    )

    entries = isolated_decision_log.entries()
    assert entries[0]["kind"] == "tool_guardrail"
    assert entries[0]["tool"] == "GMAIL_SEND_EMAIL"
    assert entries[0]["verdict"] == d.HOLD
    # Collected for calibration even though nothing gates on it yet.
    assert "mutates" in entries[0]["probabilities"]


async def test_counters_are_the_three_integers_that_matter(
    jev_env: None, jev_transport, isolated_decision_log: DecisionLog
) -> None:
    for mismatch in (0.95, 0.95, 0.01):
        jev_transport(
            noul_answers(intent_mismatch=mismatch, off_task=0.0, irreversible=0.99, mutates=0.9)
        )
        await d.review_tool_call(
            assignment="Reply to Dana.", tool_name="GMAIL_SEND_EMAIL", arguments={"to": "d@e.com"}
        )

    counters = isolated_decision_log.counters("tool_guardrail")
    assert counters == {d.HOLD: 2, d.ALLOW: 1}


def test_log_is_bounded_and_survives_a_reload(tmp_path: Path) -> None:
    path = tmp_path / "decisions.jsonl"
    log = DecisionLog(path, max_entries=5)

    for index in range(20):
        log.record(
            kind="email_screening",
            verdict="skip",
            reason="not_important",
            probabilities={"important": index / 100},
        )

    assert len(log.entries()) == 5
    reloaded = DecisionLog(path, max_entries=5)
    assert len(reloaded.entries()) == 5
    assert reloaded.entries()[-1]["probabilities"]["important"] == 0.19


def test_log_can_be_disabled(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, reload_settings
) -> None:
    monkeypatch.setenv("JEV_DECISION_LOG", "0")
    reload_settings()
    log = DecisionLog(tmp_path / "decisions.jsonl")

    log.record(kind="email_screening", verdict="skip", reason="x", probabilities={"important": 0.1})

    assert log.entries() == []
    assert not (tmp_path / "decisions.jsonl").exists()


def test_stored_probabilities_can_be_re_thresholded_without_new_calls(
    tmp_path: Path,
) -> None:
    """The whole point: a sweep over the log costs nothing."""

    log = DecisionLog(tmp_path / "decisions.jsonl")
    for probability in (0.05, 0.35, 0.55, 0.8, 0.95):
        log.record(
            kind="email_screening",
            verdict="skip" if probability <= t.EMAIL_IMPORTANT_LOW else "uncertain",
            reason="x",
            probabilities={"important": probability},
        )

    stored = [e["probabilities"]["important"] for e in log.entries()]
    surfaced_at_default = [p for p in stored if p >= t.EMAIL_IMPORTANT_HIGH]
    surfaced_at_half = [p for p in stored if p >= 0.5]

    assert len(surfaced_at_default) == 2
    assert len(surfaced_at_half) == 3
