"""Agent specificity: topic tasks must not be absorbed by channel agents.

Regression: Nanoleaf deal requests were routed into a general "Email Inbox
Watcher" because both shared the word "emails".
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from server.services.execution import roster as roster_mod
from server.services.execution.roster import (
    AgentRecord,
    AgentRoster,
    _topic_tokens,
)

NOW = datetime.now(timezone.utc)

NANOLEAF_REQUEST = (
    "Give me a summary of the nanoleaf emails and deals, "
    "I am specifically looking for the Triangle panels"
)


def _record(name: str, instructions: str = "", *, general: bool = False) -> AgentRecord:
    stamp = (NOW - timedelta(minutes=5)).isoformat(timespec="seconds")
    return AgentRecord(
        name=name,
        created_at=stamp,
        last_active_at=stamp,
        last_instructions=instructions,
        general_purpose=general,
    )


@pytest.fixture
def roster(tmp_path, monkeypatch):
    r = AgentRoster(tmp_path / "roster.json")
    monkeypatch.setattr(roster_mod, "_agent_roster", r)
    return r


# --------------------------------------------------------------------------
# Channel words must not create topical meaning
# --------------------------------------------------------------------------

def test_channel_words_are_not_topics() -> None:
    topics = _topic_tokens("summarize the emails in my inbox and send a summary")

    assert topics == set(), f"channel vocabulary leaked into topics: {topics}"


def test_nanoleaf_request_keeps_only_real_topics() -> None:
    topics = _topic_tokens(NANOLEAF_REQUEST)

    assert "nanoleaf" in topics
    assert "triangle" in topics
    assert "emails" not in topics
    assert "deals" not in topics
    assert "summary" not in topics


# --------------------------------------------------------------------------
# The regression itself
# --------------------------------------------------------------------------

def test_nanoleaf_request_does_not_reuse_the_inbox_watcher(roster) -> None:
    """The core bug: a topic request must not land on the channel agent."""
    roster._records.append(
        _record(
            "Email Inbox Watcher",
            "Monitor the inbox and summarize incoming email across the channel",
            general=True,
        )
    )

    chosen = roster.find_reusable_agent(NANOLEAF_REQUEST, "")

    assert chosen is None, "a topic request must create its own agent"


def test_nanoleaf_request_does_not_reuse_a_non_general_channel_agent(roster) -> None:
    """Even a non-general agent sharing only 'email' must not be reused."""
    roster._records.append(_record("Email Summary Agent", "summarize inbox emails"))

    assert roster.find_reusable_agent(NANOLEAF_REQUEST, "") is None


def test_generic_inbox_request_reuses_the_general_agent(roster) -> None:
    """The watcher still earns its place for genuinely channel-wide work."""
    roster._records.append(
        _record("Email Inbox Watcher", "Monitor the inbox and summarize email", general=True)
    )

    chosen = roster.find_reusable_agent("summarize my incoming emails please", "")

    assert chosen is not None
    assert chosen.name == "Email Inbox Watcher"


def test_topic_agent_is_reused_for_the_same_topic(roster) -> None:
    roster._records.append(_record("Nanoleaf Triangle Deals", "find nanoleaf triangle deals"))

    chosen = roster.find_reusable_agent(
        "were there any more nanoleaf triangle panels on sale?", ""
    )

    assert chosen is not None
    assert chosen.name == "Nanoleaf Triangle Deals"


def test_general_agent_never_wins_a_topic_match(roster) -> None:
    """A general agent must lose to a topic agent, even with shared words."""
    roster._records.append(
        _record("Email Watcher", "monitor email about unusual whales", general=True)
    )
    roster._records.append(_record("Unusual Whales Updates", "track unusual whales news"))

    chosen = roster.find_reusable_agent("any news about unusual whales?", "")

    assert chosen is not None
    assert chosen.name == "Unusual Whales Updates"


def test_topic_request_with_no_match_creates_new_agent(roster) -> None:
    roster._records.append(
        _record("Email Inbox Watcher", "summarize incoming email", general=True)
    )

    assert roster.find_reusable_agent("find my vercel job offer emails", "") is None


def test_transcript_mention_still_wins(roster) -> None:
    """Explicit reference to an agent in conversation overrides topic matching."""
    roster._records.append(_record("Nanoleaf Triangle Deals", "find nanoleaf deals"))

    chosen = roster.find_reusable_agent(
        "do that again", "earlier the Nanoleaf Triangle Deals agent found it"
    )

    assert chosen is not None
    assert chosen.name == "Nanoleaf Triangle Deals"


# --------------------------------------------------------------------------
# Prompt selection must not surface channel agents for topic work
# --------------------------------------------------------------------------

def test_inbox_watcher_is_not_recalled_by_topic_words(roster) -> None:
    roster._records.append(
        _record("Email Inbox Watcher", "monitor and summarize email", general=True)
    )

    # A topic request with no matching topic agent shows nothing, so the model
    # is pushed to create a specific agent rather than reuse the channel one.
    selected = roster.select_for_prompt(NANOLEAF_REQUEST, "")
    assert selected == [], "a topic request must not surface the channel agent"

    # Add a real topic agent; it must appear.
    roster._records.append(_record("Nanoleaf Triangle Deals", "find nanoleaf triangle deals"))
    selected = roster.select_for_prompt(NANOLEAF_REQUEST, "")
    assert selected and selected[0].name == "Nanoleaf Triangle Deals"


def test_generic_request_still_surfaces_the_general_agent(roster) -> None:
    roster._records.append(
        _record("Email Inbox Watcher", "monitor and summarize email", general=True)
    )

    selected = roster.select_for_prompt("summarize my incoming emails", "")

    assert [r.name for r in selected] == ["Email Inbox Watcher"]


# --------------------------------------------------------------------------
# general_purpose persistence
# --------------------------------------------------------------------------

def test_general_purpose_persists_across_reload(tmp_path) -> None:
    path = tmp_path / "roster.json"
    r = AgentRoster(path)
    r.touch("Email Inbox Watcher", "monitor inbox", general_purpose=True)

    reloaded = AgentRoster(path)
    record = reloaded.get_records()[0]

    assert record.general_purpose is True


def test_general_purpose_defaults_to_false(tmp_path) -> None:
    r = AgentRoster(tmp_path / "roster.json")
    r.touch("Nanoleaf Triangle Deals", "find nanoleaf deals")

    assert r.get_records()[0].general_purpose is False


def test_touch_can_promote_to_general(roster) -> None:
    roster.touch("Inbox Watcher", "monitor inbox")
    assert roster.get_records()[0].general_purpose is False

    roster.touch("Inbox Watcher", "monitor inbox", general_purpose=True)

    assert roster.get_records()[0].general_purpose is True
