"""Threshold logic for the three typed decisions."""

from __future__ import annotations

import pytest

from server.jev import decisions as d
from server.jev import thresholds as t
from tests.conftest import noul_answers


# ----------------------------------------------------------------------
# Email screening
# ----------------------------------------------------------------------


async def _screen(jev_transport, **probabilities: float) -> d.EmailScreening:
    jev_transport(noul_answers(**probabilities))
    return await d.screen_email(
        sender="dana@example.com",
        recipient="me@example.com",
        subject="Re: contract",
        body="Can you confirm by end of day?",
    )


async def test_screening_is_undecided_without_jev() -> None:
    result = await d.screen_email(
        sender="a", recipient="b", subject="c", body="d"
    )

    assert result.verdict == d.UNDECIDED
    assert result.decided is False


async def test_high_importance_surfaces(jev_env: None, jev_transport) -> None:
    result = await _screen(
        jev_transport,
        important=0.95,
        security_code=0.01,
        automated_bulk=0.02,
        prompt_injection=0.01,
    )

    assert (result.verdict, result.reason) == (d.SURFACE, "important")


async def test_low_importance_skips(jev_env: None, jev_transport) -> None:
    result = await _screen(
        jev_transport,
        important=0.05,
        security_code=0.01,
        automated_bulk=0.9,
        prompt_injection=0.01,
    )

    assert (result.verdict, result.reason) == (d.SKIP, "not_important")


async def test_middle_band_defers_to_the_llm(jev_env: None, jev_transport) -> None:
    result = await _screen(
        jev_transport,
        important=0.5,
        security_code=0.1,
        automated_bulk=0.1,
        prompt_injection=0.01,
    )

    assert (result.verdict, result.reason) == (d.UNDECIDED, "uncertain")
    assert result.decided is False


async def test_bulk_mail_in_the_middle_band_is_dropped(jev_env: None, jev_transport) -> None:
    result = await _screen(
        jev_transport,
        important=0.4,
        security_code=0.01,
        automated_bulk=0.95,
        prompt_injection=0.01,
    )

    assert (result.verdict, result.reason) == (d.SKIP, "automated_bulk")


async def test_security_code_beats_a_low_importance_score(jev_env: None, jev_transport) -> None:
    # An OTP that reads as unimportant prose must still reach the user.
    result = await _screen(
        jev_transport,
        important=0.2,
        security_code=0.9,
        automated_bulk=0.1,
        prompt_injection=0.01,
    )

    assert (result.verdict, result.reason) == (d.SURFACE, "security_code")


async def test_prompt_injection_outranks_everything(jev_env: None, jev_transport) -> None:
    # Attacker-authored text that also looks urgent must never be forwarded to
    # the interaction agent — but it is quarantined, not silently dropped.
    result = await _screen(
        jev_transport,
        important=0.99,
        security_code=0.99,
        automated_bulk=0.0,
        prompt_injection=0.95,
    )

    assert (result.verdict, result.reason) == (d.QUARANTINE, "prompt_injection")
    assert result.decided is True


async def test_silence_is_what_a_suppression_attacker_is_buying(
    jev_env: None, jev_transport, monkeypatch: pytest.MonkeyPatch, reload_settings
) -> None:
    """Dropping a flagged email silently hands the attacker the outcome.

    Measured on this repo's own corpus: appending override text silenced an
    email 95.3% of the time [93.1, 97.2] across all 12 carriers, the one-time
    code included. Quarantine is therefore the default, and the old behaviour
    has to be asked for explicitly.
    """

    default = await _screen(
        jev_transport, important=0.5, security_code=0.0, automated_bulk=0.0,
        prompt_injection=0.95,
    )
    assert default.verdict == d.QUARANTINE

    monkeypatch.setenv("JEV_QUARANTINE_INJECTIONS", "0")
    reload_settings()
    opted_out = await _screen(
        jev_transport, important=0.5, security_code=0.0, automated_bulk=0.0,
        prompt_injection=0.95,
    )
    assert opted_out.verdict == d.SKIP


async def test_missing_importance_answer_is_undecided(jev_env: None, jev_transport) -> None:
    jev_transport(noul_answers(security_code=0.9, automated_bulk=0.1, prompt_injection=0.0))

    result = await d.screen_email(sender="a", recipient="b", subject="c", body="d")

    assert (result.verdict, result.reason) == (d.UNDECIDED, "missing_answer")


async def test_screening_can_be_disabled_independently(
    jev_env: None, jev_transport, monkeypatch: pytest.MonkeyPatch, reload_settings
) -> None:
    monkeypatch.setenv("JEV_EMAIL_SCREENING", "0")
    reload_settings()
    calls = jev_transport(noul_answers(important=0.99))

    result = await d.screen_email(sender="a", recipient="b", subject="c", body="d")

    assert result.verdict == d.UNDECIDED
    assert calls == [], "a disabled decision must not spend a request"


@pytest.mark.parametrize(
    "probability,expected",
    [
        (t.EMAIL_IMPORTANT_HIGH, d.SURFACE),
        (t.EMAIL_IMPORTANT_HIGH - 0.01, d.UNDECIDED),
        (t.EMAIL_IMPORTANT_LOW, d.SKIP),
        (t.EMAIL_IMPORTANT_LOW + 0.01, d.UNDECIDED),
    ],
)
async def test_band_edges_are_inclusive(
    jev_env: None, jev_transport, probability: float, expected: str
) -> None:
    result = await _screen(
        jev_transport,
        important=probability,
        security_code=0.0,
        automated_bulk=0.0,
        prompt_injection=0.0,
    )

    assert result.verdict == expected


# ----------------------------------------------------------------------
# Tool guardrail
# ----------------------------------------------------------------------


async def _review(jev_transport, tool_name: str, **probabilities: float) -> d.ToolCallReview:
    jev_transport(noul_answers(**probabilities))
    return await d.review_tool_call(
        assignment="Reply to Dana about the contract.",
        tool_name=tool_name,
        arguments={"to": "dana@example.com", "body": "Sounds good."},
    )


async def test_guardrail_allows_without_jev() -> None:
    review = await d.review_tool_call(
        assignment="do the thing", tool_name="GMAIL_SEND_EMAIL", arguments={}
    )

    assert review.held is False


async def test_guardrail_holds_on_intent_mismatch(jev_env: None, jev_transport) -> None:
    review = await _review(
        jev_transport, "GMAIL_SEND_EMAIL", intent_mismatch=0.93, off_task=0.1, irreversible=0.99
    )

    assert (review.verdict, review.reason) == (d.HOLD, "intent_mismatch")
    assert "intent_mismatch=0.93" in review.explain()


async def test_off_task_steers_and_never_holds(jev_env: None, jev_transport) -> None:
    # pi-warden's replay over 17,160 guarded calls found off-task the weakest of
    # its four signals (AUC 0.51 against user regret) and the cause of 56 of 139
    # holds with zero user complaints. It steers here; it must never hold.
    steered = await _review(
        jev_transport, "GMAIL_SEND_EMAIL", intent_mismatch=0.2, off_task=0.95, irreversible=0.99
    )
    read = await _review(
        jev_transport, "GMAIL_LIST_DRAFTS", intent_mismatch=0.2, off_task=0.95, irreversible=0.05
    )

    assert (steered.verdict, steered.reason) == (d.STEER, "off_task_irreversible")
    assert steered.held is False
    assert steered.advisory is True
    assert read.held is False, "reads must not be blocked for wandering off task"
    assert read.verdict == d.WARN, "but the agent should still be told"


async def test_intent_mismatch_holds_only_when_irreversible(
    jev_env: None, jev_transport
) -> None:
    held = await _review(
        jev_transport, "GMAIL_SEND_EMAIL", intent_mismatch=0.93, off_task=0.1, irreversible=0.99
    )
    steered = await _review(
        jev_transport, "GMAIL_LIST_DRAFTS", intent_mismatch=0.93, off_task=0.1, irreversible=0.02
    )

    assert held.verdict == d.HOLD
    assert steered.verdict == d.STEER, "a read that misreads the assignment is corrected, not blocked"


async def test_warn_rung_fires_below_the_steer_bar(jev_env: None, jev_transport) -> None:
    # The gap this closes: before the rungs existed, off_task=0.7 produced
    # nothing at all, not even a line in the agent's context.
    review = await _review(
        jev_transport, "GMAIL_SEND_EMAIL", intent_mismatch=0.1, off_task=0.7, irreversible=0.99
    )

    assert (review.verdict, review.reason) == (d.WARN, "off_task")
    assert review.advisory is True
    assert "off_task=0.70" in review.advice()


async def test_known_irreversible_tool_does_not_need_the_model_to_agree(
    jev_env: None, jev_transport
) -> None:
    # The allow-list is the source of truth for destructive tools; a low
    # `irreversible` probability must not downgrade the rung.
    review = await _review(
        jev_transport, "GMAIL_SEND_EMAIL", intent_mismatch=0.2, off_task=0.95, irreversible=0.01
    )

    assert review.reason == "off_task_irreversible"


async def test_guardrail_allows_a_faithful_call(jev_env: None, jev_transport) -> None:
    review = await _review(
        jev_transport, "GMAIL_SEND_EMAIL", intent_mismatch=0.03, off_task=0.05, irreversible=0.99
    )

    assert (review.verdict, review.reason) == (d.ALLOW, "passed")


async def test_guardrail_can_be_disabled(
    jev_env: None, jev_transport, monkeypatch: pytest.MonkeyPatch, reload_settings
) -> None:
    monkeypatch.setenv("JEV_TOOL_GUARDRAIL", "0")
    reload_settings()
    calls = jev_transport(noul_answers(intent_mismatch=0.99))

    review = await d.review_tool_call(
        assignment="a", tool_name="GMAIL_SEND_EMAIL", arguments={}
    )

    assert review.held is False
    assert calls == []


# ----------------------------------------------------------------------
# Search relevance filter
# ----------------------------------------------------------------------

CANDIDATES = {
    "m1": {"from": "a@example.com", "subject": "Acme invoice", "body": "Invoice 42 attached"},
    "m2": {"from": "b@example.com", "subject": "Lunch?", "body": "Are you free Friday"},
    "m3": {"from": "c@example.com", "subject": "Acme invoice 43", "body": "Invoice 43 attached"},
}


async def test_filter_drops_only_low_scoring_results(jev_env: None, jev_transport) -> None:
    jev_transport(noul_answers(candidate_0=0.9, candidate_1=0.02, candidate_2=0.8))

    outcome = await d.filter_search_results(
        request="Acme invoices", selected_ids=["m1", "m2", "m3"], candidates=CANDIDATES
    )

    assert outcome.kept == ["m1", "m3"]
    assert outcome.dropped == ["m2"]
    assert outcome.applied is True


async def test_filter_never_empties_the_result_set(jev_env: None, jev_transport) -> None:
    jev_transport(noul_answers(candidate_0=0.01, candidate_1=0.01, candidate_2=0.01))

    outcome = await d.filter_search_results(
        request="Acme invoices", selected_ids=["m1", "m2", "m3"], candidates=CANDIDATES
    )

    assert outcome.kept == ["m1", "m2", "m3"]
    assert outcome.dropped == []


async def test_filter_skips_single_result(jev_env: None, jev_transport) -> None:
    calls = jev_transport(noul_answers(candidate_0=0.0))

    outcome = await d.filter_search_results(
        request="Acme invoices", selected_ids=["m1"], candidates=CANDIDATES
    )

    assert outcome.kept == ["m1"]
    assert calls == []


async def test_filter_keeps_ids_it_cannot_read(jev_env: None, jev_transport) -> None:
    jev_transport(noul_answers(candidate_0=0.9, candidate_1=0.01))

    outcome = await d.filter_search_results(
        request="Acme invoices",
        selected_ids=["m1", "m2", "unknown-id"],
        candidates=CANDIDATES,
    )

    assert "unknown-id" in outcome.kept


async def test_filter_question_count_matches_candidate_count(jev_env: None, jev_transport) -> None:
    calls = jev_transport(noul_answers(candidate_0=0.9, candidate_1=0.9))

    await d.filter_search_results(
        request="Acme invoices", selected_ids=["m1", "m2"], candidates=CANDIDATES
    )

    assert len(calls) == 1
    body = calls[0]
    assert len(body["questions"]) == 2
    assert len(body["state"]["candidates"]) == 2


def test_irreversible_allow_list_survives_a_tool_rename() -> None:
    """An enumeration goes stale; matching must not depend on one spelling.

    AgentDojo's Workspace suite calls the same operation `send_email`, and a
    production rename would otherwise drop the tool off the list silently.
    """

    for spelling in ("GMAIL_SEND_EMAIL", "gmail.send_email", "sendEmail", "send_email"):
        assert t.is_named_irreversible(spelling), spelling
    for other in ("GMAIL_LIST_DRAFTS", "search", "", "create_draft"):
        assert not t.is_named_irreversible(other), other


async def test_renamed_send_tool_is_still_gated(jev_env: None, jev_transport) -> None:
    review = await _review(
        jev_transport, "send_email", intent_mismatch=0.95, off_task=0.1, irreversible=0.02
    )

    assert review.verdict == d.HOLD, "a rename must not disarm the hold rung"
