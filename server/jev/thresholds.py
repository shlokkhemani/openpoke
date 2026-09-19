"""All Jev decision thresholds, in one reviewable place.

TypeSafe's own guidance is to keep the questions and the threshold constants
together so a reviewer can audit the policy without reading the call sites:
https://docs.typesafe.ai/agent-skill

Two things to know before tuning these numbers:

* ``Noul`` answers carry **no** ``confidence`` field. The probability itself is
  the signal, and values near ``0.5`` are the uncertain region, so every noul
  gate below is a two-sided band rather than a single cut point.
  https://docs.typesafe.ai/primitives/noul
* Jev is calibrated across a population of answers, not per answer, so the
  right cut points depend on your own data. Treat these as conservative
  defaults and re-sweep them against a labelled sample before relying on them.
  https://docs.typesafe.ai/introduction/machine-learning-primer
"""

from __future__ import annotations

from typing import Final

# ----------------------------------------------------------------------
# Email screening (server/services/gmail/importance_classifier.py)
# ----------------------------------------------------------------------

# Above this the email is important enough to skip straight to summarisation.
EMAIL_IMPORTANT_HIGH: Final[float] = 0.75
# Below this the email is confidently unimportant and never reaches an LLM.
EMAIL_IMPORTANT_LOW: Final[float] = 0.25
# Security codes (OTP, login alerts) are surfaced on a looser bar because a
# missed one is far more costly to the user than a false positive.
EMAIL_SECURITY_CODE: Final[float] = 0.60
# Bulk/marketing mail is dropped without an LLM call once we are this sure.
EMAIL_AUTOMATED_BULK: Final[float] = 0.85
# Email bodies that try to steer the assistant are never auto-surfaced.
# Lifted from the RAG passage cookbook, which uses 0.70 for the same question.
# https://docs.typesafe.ai/cookbooks/classifying_rag_passages
EMAIL_PROMPT_INJECTION: Final[float] = 0.70

# ----------------------------------------------------------------------
# Execution-agent tool guardrail (server/agents/execution_agent/runtime.py)
# ----------------------------------------------------------------------

# Gated per action, not globally: the consequence of a wrong `send email` is
# not the consequence of a wrong `list drafts`.
# https://docs.typesafe.ai/patterns/confidence-routing
#
# Three rungs, not one gate. Only an irreversible call is ever held; everything
# else is told to the agent and allowed to run. The shape is taken from
# pi-warden (https://github.com/DevMortimer/pi-warden), whose calibration replay
# over 17,160 guarded tool calls is the only public measurement of this kind:
#
#   * Its off-task signal ranked worst of four by AUC against user regret (0.51,
#     versus 0.74 for "does this mutate state"), and off-task caused 56 of 139
#     replay holds with zero user complaints. It therefore stopped holding on
#     off-task entirely. We follow that: off-task steers, it never holds.
#   * Its intent-mismatch signal was also weak (AUC 0.57). We keep a hold on it,
#     but only for a call that cannot be undone.
#
# Those numbers come from one user's sessions with model-generated labels, and
# the data is not public, so treat them as the best available evidence rather
# than as settled. Ours are not calibrated at all yet; see docs/EVALUATION.md.
TOOL_INTENT_MISMATCH_HOLD: Final[float] = 0.85
TOOL_INTENT_MISMATCH_STEER: Final[float] = 0.60
TOOL_OFF_TASK_STEER: Final[float] = 0.85
TOOL_OFF_TASK_WARN: Final[float] = 0.60
# The bar at which the model's own `irreversible` answer makes a call count as
# irreversible. It applies to *every* tool, not only the ones named below: the
# allow-list and this threshold are two independent routes to the same verdict,
# because a tool rename should not silently disarm the rung.
TOOL_IRREVERSIBLE_HOLD: Final[float] = 0.70

# Tools whose effects the user cannot take back. Matched case-insensitively and
# ignoring separators, because this list is an enumeration and enumerations go
# stale: the same shape of allow-list has been publicly bypassed in other agent
# tools, and a tool renamed from GMAIL_SEND_EMAIL to send_email would otherwise
# drop off it silently. The model's `irreversible` answer above is the
# independent second route for anything not named here.
IRREVERSIBLE_TOOLS: Final[frozenset[str]] = frozenset(
    {
        "GMAIL_SEND_EMAIL",
        "GMAIL_REPLY_TO_THREAD",
        "GMAIL_SEND_DRAFT",
        "GMAIL_DELETE_MESSAGE",
        "GMAIL_DELETE_DRAFT",
        "GMAIL_MOVE_TO_TRASH",
        "GMAIL_TRASH_MESSAGE",
        "SEND_EMAIL",
        "SEND_MESSAGE",
        "REPLY_TO_EMAIL",
        "FORWARD_EMAIL",
        "DELETE_EMAIL",
        "DELETE_FILE",
        "CANCEL_CALENDAR_EVENT",
    }
)

_NORMALIZED_IRREVERSIBLE: Final[frozenset[str]] = frozenset(
    "".join(ch for ch in name.lower() if ch.isalnum()) for name in IRREVERSIBLE_TOOLS
)


def is_named_irreversible(tool_name: str) -> bool:
    """Return ``True`` when ``tool_name`` is on the irreversible allow-list.

    Case and separators are ignored so that ``GMAIL_SEND_EMAIL``,
    ``gmail.send_email`` and ``sendEmail`` all match the same entry.
    """

    if not tool_name:
        return False
    return "".join(ch for ch in tool_name.lower() if ch.isalnum()) in _NORMALIZED_IRREVERSIBLE

# ----------------------------------------------------------------------
# Email search relevance filter
# (server/agents/execution_agent/tasks/search_email/tool.py)
# ----------------------------------------------------------------------

# Drop a selected message when Jev is this sure it does not answer the query.
SEARCH_RELEVANCE_DROP: Final[float] = 0.25
# Never filter a result set down to nothing on a probability alone; below this
# many survivors the filter is discarded and the LLM's selection stands.
SEARCH_MIN_SURVIVORS: Final[int] = 1

__all__ = [
    "EMAIL_IMPORTANT_HIGH",
    "EMAIL_IMPORTANT_LOW",
    "EMAIL_SECURITY_CODE",
    "EMAIL_AUTOMATED_BULK",
    "EMAIL_PROMPT_INJECTION",
    "TOOL_INTENT_MISMATCH_HOLD",
    "TOOL_INTENT_MISMATCH_STEER",
    "TOOL_OFF_TASK_STEER",
    "TOOL_OFF_TASK_WARN",
    "TOOL_IRREVERSIBLE_HOLD",
    "IRREVERSIBLE_TOOLS",
    "is_named_irreversible",
    "SEARCH_RELEVANCE_DROP",
    "SEARCH_MIN_SURVIVORS",
]
