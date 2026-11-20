"""Roster selection: migration, cap, recall, archiving, and prompt escaping."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from server.agents.interaction_agent import agent as interaction_agent
from server.services.execution.roster import (
    MAX_PROMPT_AGENTS,
    AgentRecord,
    AgentRoster,
)


def _record(name: str, *, days_ago: float, instructions: str = "", **kwargs) -> AgentRecord:
    """Build a record whose activity is *days_ago* before now."""
    stamp = (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat(timespec="seconds")
    return AgentRecord(
        name=name,
        created_at=stamp,
        last_active_at=stamp,
        last_instructions=instructions,
        **kwargs,
    )


def test_legacy_string_roster_migrates(tmp_path: Path) -> None:
    path = tmp_path / "roster.json"
    path.write_text(json.dumps(["Email Summary Agent", "Q3 Budget Analysis"]), encoding="utf-8")

    roster = AgentRoster(path)

    assert [record.name for record in roster.get_records()] == [
        "Email Summary Agent",
        "Q3 Budget Analysis",
    ]


def test_legacy_migration_is_persisted_as_records(tmp_path: Path) -> None:
    path = tmp_path / "roster.json"
    path.write_text(json.dumps(["Email Summary Agent"]), encoding="utf-8")

    AgentRoster(path)

    stored = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(stored[0], dict)
    assert stored[0]["name"] == "Email Summary Agent"


def test_prompt_selection_respects_cap(roster) -> None:
    for index in range(40):
        roster._records.append(_record(f"Agent {index}", days_ago=index * 0.1, use_count=1))

    selected = roster.select_for_prompt("what is on my calendar", "")

    assert len(selected) == MAX_PROMPT_AGENTS


def test_transcript_mention_beats_recency(roster) -> None:
    roster._records.append(_record("Email to Alice", days_ago=5))
    for index in range(10):
        roster._records.append(_record(f"Fresh Agent {index}", days_ago=0.01 * index))

    selected = roster.select_for_prompt("send it", "earlier we discussed email to alice")

    assert selected[0].name == "Email to Alice"


def test_dormant_agent_is_recalled_by_words(roster) -> None:
    """Regression: archived agents must stay recallable, not silently dropped."""
    roster._records.append(_record("Tokyo Restaurant Search", days_ago=30, instructions="search restaurants"))
    roster._records.append(_record("Email to Alice", days_ago=1))

    selected = roster.select_for_prompt("find restaurants near Tokyo again", "")

    names = [record.name for record in selected]
    assert "Tokyo Restaurant Search" in names


def test_recent_fill_excludes_archived_agents(roster) -> None:
    roster._records.append(_record("Dormant Agent", days_ago=30))
    roster._records.append(_record("Active Agent", days_ago=0))
    roster.save()

    roster.load()

    assert roster.get_agents() == ["Active Agent"]


def test_idle_agent_is_archived_on_load(tmp_path: Path) -> None:
    path = tmp_path / "roster.json"
    path.write_text(
        json.dumps([_record("Stale Agent", days_ago=8).to_dict()]), encoding="utf-8"
    )

    roster = AgentRoster(path)

    assert roster.get_records(include_archived=True)[0].archived is True
    assert roster.get_agents() == []


def test_touch_unarchives_and_updates_activity(roster) -> None:
    roster._records.append(_record("Stale Agent", days_ago=30, archived=True))
    roster.save()

    is_new = roster.touch("Stale Agent", "do the thing again")

    reloaded = roster.get_records(include_archived=True)[0]
    assert is_new is False
    assert reloaded.archived is False
    assert reloaded.use_count == 1
    assert reloaded.last_instructions == "do the thing again"


def test_touch_creates_unknown_agent(roster) -> None:
    assert roster.touch("Brand New Agent", "start work") is True
    assert roster.get_all_names() == ["Brand New Agent"]


def test_touch_keeps_previous_instruction_when_blank(roster) -> None:
    roster.touch("Agent A", "first request")

    roster.touch("Agent A", "   ")

    record = roster.get_records()[0]
    assert record.last_instructions == "first request"
    assert record.use_count == 2


def test_long_instructions_are_truncated(roster) -> None:
    roster.touch("Agent A", "x" * 500)

    snippet = roster.get_records()[0].last_instructions
    assert len(snippet) <= 80
    assert snippet.endswith("…")


def test_render_escapes_agent_names(roster) -> None:
    roster._records.append(_record('Email "Alice" <urgent>', days_ago=0))
    roster.save()

    rendered = interaction_agent._render_active_agents("email", "")

    assert 'name="Email &quot;Alice&quot; &lt;urgent&gt;"' in rendered


def test_render_includes_last_request(roster) -> None:
    roster._records.append(_record("Email to Alice", days_ago=0, instructions="reply about contract"))
    roster.save()

    rendered = interaction_agent._render_active_agents("email alice", "")

    assert 'name="Email to Alice"' in rendered
    assert 'last_request="reply about contract"' in rendered


def test_render_returns_none_placeholder_when_empty(roster) -> None:
    rendered = interaction_agent._render_active_agents("hi", "")

    assert rendered == "None"


def test_prompt_contains_agents_and_turn(roster) -> None:
    roster.touch("Email to Alice", "reply to Alice")

    messages = interaction_agent.prepare_message_with_history(
        "reply to alice", "<user_message>hi</user_message>"
    )

    content = messages[0]["content"]
    assert "<active_agents>" in content
    assert 'name="Email to Alice"' in content
    assert "<new_user_message>" in content
