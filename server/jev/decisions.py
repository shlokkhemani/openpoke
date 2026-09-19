"""The typed decisions OpenPoke makes with Jev.

Each function here turns one batched Jev call into a small frozen result that
call sites can branch on. Every one of them has an "I don't know" state, and
reaching it must leave the caller behaving exactly as it did before this layer
existed.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence

from ..config import get_settings
from ..logging_config import logger
from . import questions as q
from . import state as s
from . import thresholds as t
from .client import ask, is_enabled, noul
from .decision_log import get_decision_log

# ----------------------------------------------------------------------
# Email screening
# ----------------------------------------------------------------------

SURFACE = "surface"
SKIP = "skip"
QUARANTINE = "quarantine"
UNDECIDED = "undecided"


@dataclass(frozen=True)
class EmailScreening:
    """Outcome of screening one incoming email."""

    verdict: str
    reason: str
    probabilities: Dict[str, float] = field(default_factory=dict)

    @property
    def decided(self) -> bool:
        """Return ``True`` when the caller may skip the LLM decision entirely."""

        return self.verdict in (SURFACE, SKIP, QUARANTINE)


UNDECIDED_EMAIL = EmailScreening(verdict=UNDECIDED, reason="jev_unavailable")


# Screen one email with a single batched Jev call
async def screen_email(
    *,
    sender: str,
    recipient: str,
    subject: str,
    body: str,
    labels: Sequence[str] = (),
    has_attachments: bool = False,
    attachment_filenames: Sequence[str] = (),
) -> EmailScreening:
    """Decide whether an email should be surfaced, dropped, or sent to an LLM."""

    settings = get_settings()
    if not settings.jev_email_screening_enabled or not is_enabled():
        return UNDECIDED_EMAIL


    response = await ask(
        state=s.email_state(
            sender=sender,
            recipient=recipient,
            subject=subject,
            body=body,
            labels=labels,
            has_attachments=has_attachments,
            attachment_filenames=attachment_filenames,
        ),
        questions=q.EMAIL_QUESTIONS,
        purpose="email_screening",
    )
    if response is None:
        return UNDECIDED_EMAIL

    probabilities: Dict[str, float] = {}
    for key in q.EMAIL_QUESTIONS:
        value = noul(response, key)
        if value is not None:
            probabilities[key] = value

    # The security gate is checked first and on its own: it must not depend on
    # an unrelated answer having arrived.
    injection = probabilities.get("prompt_injection")
    if injection is not None and injection >= t.EMAIL_PROMPT_INJECTION:
        # The body never reaches the interaction agent. But dropping the message
        # silently is itself an attack: appending "ignore all previous
        # instructions" to an email silenced it 95.3% of the time [93.1, 97.2]
        # across all 12 carriers in our own measurement, the OTP included, which
        # made this question the most reliable attack in the experiment rather
        # than a defence. So the default is to quarantine and tell the user that
        # something was withheld, not to make it disappear.
        # See evals/contamination/FINDINGS.md.
        logger.warning(
            "Quarantining email that reads as a prompt-injection attempt",
            extra={"prompt_injection": injection},
        )
        verdict = QUARANTINE if settings.jev_quarantine_injections else SKIP
        return EmailScreening(
            verdict=verdict, reason="prompt_injection", probabilities=probabilities
        )

    important = probabilities.get("important")
    if important is None:
        # The question the rest of the decision turns on came back unusable.
        return EmailScreening(verdict=UNDECIDED, reason="missing_answer", probabilities=probabilities)

    security = probabilities.get("security_code")
    if security is not None and security >= t.EMAIL_SECURITY_CODE:
        return EmailScreening(verdict=SURFACE, reason="security_code", probabilities=probabilities)

    if important >= t.EMAIL_IMPORTANT_HIGH:
        return EmailScreening(verdict=SURFACE, reason="important", probabilities=probabilities)

    if important <= t.EMAIL_IMPORTANT_LOW:
        return EmailScreening(verdict=SKIP, reason="not_important", probabilities=probabilities)

    bulk = probabilities.get("automated_bulk")
    if bulk is not None and bulk >= t.EMAIL_AUTOMATED_BULK:
        return EmailScreening(verdict=SKIP, reason="automated_bulk", probabilities=probabilities)

    # Between the bands: noul probabilities near 0.5 are the uncertain region,
    # so this is exactly where the expensive model earns its cost.
    return EmailScreening(verdict=UNDECIDED, reason="uncertain", probabilities=probabilities)


# Write one screening decision to the log
def record_screening(
    screening: EmailScreening,
    *,
    message_id: Optional[str] = None,
    sender: Optional[str] = None,
    subject: Optional[str] = None,
) -> None:
    """Persist a screening decision so thresholds can be swept offline later."""

    if not screening.probabilities:
        # Nothing was measured, so there is nothing to re-threshold.
        return
    get_decision_log().record(
        kind="email_screening",
        verdict=screening.verdict,
        reason=screening.reason,
        probabilities=screening.probabilities,
        message_id=message_id,
        sender=sender,
        subject=subject,
    )


# ----------------------------------------------------------------------
# Execution-agent tool guardrail
# ----------------------------------------------------------------------

ALLOW = "allow"
WARN = "warn"
STEER = "steer"
HOLD = "hold"


@dataclass(frozen=True)
class ToolCallReview:
    """Advisory verdict on a pending tool call.

    Three rungs above ``allow``. Only ``hold`` stops the call; ``steer`` and
    ``warn`` let it run and put the judgement into the agent's next tool result,
    because the agent is the right consumer of a correction and the user is not
    an approval button.
    """

    verdict: str
    reason: str
    probabilities: Dict[str, float] = field(default_factory=dict)

    @property
    def held(self) -> bool:
        """Return ``True`` when the call should be returned to the agent unrun."""

        return self.verdict == HOLD

    @property
    def advisory(self) -> bool:
        """Return ``True`` when the call runs but the agent should be told why."""

        return self.verdict in (WARN, STEER)

    def _detail(self) -> str:
        return ", ".join(f"{key}={value:.2f}" for key, value in sorted(self.probabilities.items()))

    def explain(self) -> str:
        """Return the message handed back to the agent when a call is held."""

        return (
            f"Blocked by the typed-decision guardrail ({self.reason}). "
            "Re-read your assignment and either correct the arguments or "
            f"explain what you intend to do. [{self._detail()}]"
        )

    def advice(self) -> str:
        """Return the note appended to a tool result when the call still runs."""

        if self.verdict == STEER:
            lead = "The typed-decision guardrail flagged this call"
            tail = "It ran anyway. Check it against your assignment before relying on the result."
        else:
            lead = "The typed-decision guardrail noted this call"
            tail = "No action needed unless it looks wrong to you."
        return f"{lead} ({self.reason}). {tail} [{self._detail()}]"


ALLOWED_TOOL_CALL = ToolCallReview(verdict=ALLOW, reason="jev_unavailable")


# Review a pending tool call with a single batched Jev call
async def review_tool_call(
    *,
    assignment: str,
    tool_name: str,
    arguments: Mapping[str, Any],
) -> ToolCallReview:
    """Judge whether a tool call matches the assignment before it runs.

    The verdict is advisory and fails open. Only an irreversible call is ever
    held, and a held call is reported back to the agent as a tool error so it
    can correct itself; it is never surfaced to the user as a refusal.
    """

    settings = get_settings()
    if not settings.jev_tool_guardrail_enabled or not is_enabled():
        return ALLOWED_TOOL_CALL
    if not assignment or not tool_name:
        return ALLOWED_TOOL_CALL
    if not isinstance(arguments, Mapping):
        # Tool arguments come from `json.loads` on model output and are not
        # guaranteed to be an object. Let the tool itself reject the shape, as
        # it did before this guardrail existed.
        return ALLOWED_TOOL_CALL

    response = await ask(
        state=s.tool_call_state(assignment=assignment, tool_name=tool_name, arguments=arguments),
        questions=q.TOOL_QUESTIONS,
        purpose="tool_guardrail",
        deadline=settings.jev_guardrail_deadline_seconds,
    )
    if response is None:
        return ALLOWED_TOOL_CALL

    probabilities: Dict[str, float] = {}
    for key in q.TOOL_QUESTIONS:
        value = noul(response, key)
        if value is not None:
            probabilities[key] = value

    irreversible_answer = probabilities.get("irreversible")
    irreversible = t.is_named_irreversible(tool_name) or (
        irreversible_answer is not None and irreversible_answer >= t.TOOL_IRREVERSIBLE_HOLD
    )

    mismatch = probabilities.get("intent_mismatch")
    off_task = probabilities.get("off_task")

    review: ToolCallReview
    if mismatch is not None and mismatch >= t.TOOL_INTENT_MISMATCH_HOLD and irreversible:
        # The only rung that stops a call, and only for something unrecoverable.
        review = ToolCallReview(verdict=HOLD, reason="intent_mismatch", probabilities=probabilities)
    elif mismatch is not None and mismatch >= t.TOOL_INTENT_MISMATCH_HOLD:
        review = ToolCallReview(verdict=STEER, reason="intent_mismatch", probabilities=probabilities)
    elif irreversible and off_task is not None and off_task >= t.TOOL_OFF_TASK_STEER:
        review = ToolCallReview(
            verdict=STEER, reason="off_task_irreversible", probabilities=probabilities
        )
    elif mismatch is not None and mismatch >= t.TOOL_INTENT_MISMATCH_STEER:
        review = ToolCallReview(verdict=WARN, reason="intent_mismatch", probabilities=probabilities)
    elif off_task is not None and off_task >= t.TOOL_OFF_TASK_WARN:
        review = ToolCallReview(verdict=WARN, reason="off_task", probabilities=probabilities)
    else:
        review = ToolCallReview(verdict=ALLOW, reason="passed", probabilities=probabilities)

    if probabilities:
        get_decision_log().record(
            kind="tool_guardrail",
            verdict=review.verdict,
            reason=review.reason,
            probabilities=probabilities,
            tool_name=tool_name,
        )
    return review


# ----------------------------------------------------------------------
# Email search relevance filter
# ----------------------------------------------------------------------


@dataclass(frozen=True)
class SearchFilter:
    """Outcome of verifying an LLM's search-result selection."""

    kept: List[str]
    dropped: List[str] = field(default_factory=list)
    applied: bool = False


# Verify an LLM's chosen search results against the original request
async def filter_search_results(
    *,
    request: str,
    selected_ids: Sequence[str],
    candidates: Mapping[str, Mapping[str, Any]],
) -> SearchFilter:
    """Drop selected results Jev is confident do not answer the request.

    ``candidates`` maps message id to a mapping with ``from``/``subject``/``body``
    (or ``sender``/``clean_text``) keys. Ids missing from it are always kept —
    this filter only ever removes results it could actually read.
    """

    settings = get_settings()
    ordered = [message_id for message_id in selected_ids if message_id in candidates]
    # Same cap the state builder applies, so question keys and candidate
    # indexes cannot drift apart.
    ordered = ordered[: s.search_candidate_limit()]
    if not settings.jev_search_filter_enabled or not is_enabled() or len(ordered) < 2:
        # With a single result there is nothing to discriminate between, and
        # dropping it would turn a hit into an empty answer.
        return SearchFilter(kept=list(selected_ids))

    response = await ask(
        state=s.search_state(
            request=request,
            candidates=[candidates[message_id] for message_id in ordered],
        ),
        questions=q.search_relevance_questions(len(ordered)),
        purpose="search_relevance",
    )
    if response is None:
        return SearchFilter(kept=list(selected_ids))

    dropped: List[str] = []
    for index, message_id in enumerate(ordered):
        value = noul(response, q.relevance_key(index))
        if value is not None and value <= t.SEARCH_RELEVANCE_DROP:
            dropped.append(message_id)

    if not dropped:
        return SearchFilter(kept=list(selected_ids), applied=True)

    kept = [message_id for message_id in selected_ids if message_id not in dropped]
    # Counted among the ids that were actually scored: an id the filter could
    # not read (an LLM-hallucinated message id, say) is not evidence that the
    # filter left a usable result behind.
    scored_survivors = [message_id for message_id in ordered if message_id not in dropped]
    if len(scored_survivors) < t.SEARCH_MIN_SURVIVORS:
        # Everything scored low. That is a signal about the query, not about
        # any one result, so the LLM's selection stands.
        logger.info(
            "Skipping search relevance filter; every result scored low",
            extra={"candidates": len(ordered)},
        )
        return SearchFilter(kept=list(selected_ids))

    logger.info(
        "Search relevance filter dropped low-relevance results",
        extra={"dropped": len(dropped), "kept": len(kept)},
    )
    return SearchFilter(kept=kept, dropped=dropped, applied=True)


__all__ = [
    "ALLOW",
    "QUARANTINE",
    "WARN",
    "STEER",
    "EmailScreening",
    "HOLD",
    "SKIP",
    "SURFACE",
    "SearchFilter",
    "ToolCallReview",
    "UNDECIDED",
    "filter_search_results",
    "record_screening",
    "review_tool_call",
    "screen_email",
]
