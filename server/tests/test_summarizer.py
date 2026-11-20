"""Conversation summarizer and working-memory persistence."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from server.config import Settings
from server.openrouter_client import OpenRouterError
from server.services.conversation.summarization import summarizer
from server.services.conversation.summarization.state import LogEntry, SummaryState
from server.services.conversation.summarization.working_memory_log import WorkingMemoryLog
from server.tests.conftest import completion


def _settings(monkeypatch: pytest.MonkeyPatch, *, threshold: int = 3, tail: int = 0) -> None:
    """Pin summarization thresholds so tests do not depend on defaults."""
    base = Settings()
    base.conversation_summary_threshold = threshold
    base.conversation_summary_tail_size = tail
    monkeypatch.setattr(summarizer, "get_settings", lambda: base)


def _seed(conversation_log, count: int) -> None:
    for index in range(count):
        conversation_log.record_user_message(f"message {index}")


async def test_below_threshold_makes_no_model_call(
    scripted_llm, conversation_log, monkeypatch: pytest.MonkeyPatch
) -> None:
    _settings(monkeypatch, threshold=10)
    fake = scripted_llm(summarizer, [])
    _seed(conversation_log, 3)

    assert await summarizer.summarize_conversation() is False
    assert fake.calls == []


async def test_summarization_advances_index_and_persists(
    scripted_llm, conversation_log, monkeypatch: pytest.MonkeyPatch
) -> None:
    _settings(monkeypatch, threshold=3)
    fake = scripted_llm(summarizer, [completion("Brief summary of the first three messages.")])
    _seed(conversation_log, 3)

    assert await summarizer.summarize_conversation() is True

    fake.assert_drained()
    state = summarizer.get_working_memory_log().load_summary_state()
    assert state.summary_text == "Brief summary of the first three messages."
    assert state.last_index == 2


async def test_disabled_when_threshold_is_zero(
    scripted_llm, conversation_log, monkeypatch: pytest.MonkeyPatch
) -> None:
    _settings(monkeypatch, threshold=0)
    fake = scripted_llm(summarizer, [])
    _seed(conversation_log, 50)

    assert await summarizer.summarize_conversation() is False
    assert fake.calls == []


async def test_empty_content_retries_once_then_raises(
    scripted_llm, conversation_log, monkeypatch: pytest.MonkeyPatch
) -> None:
    _settings(monkeypatch, threshold=2)
    fake = scripted_llm(summarizer, [completion(""), completion("")])
    _seed(conversation_log, 2)

    with pytest.raises(OpenRouterError):
        await summarizer.summarize_conversation()

    fake.assert_drained()
    assert len(fake.calls) == 2


async def test_empty_first_response_is_retried_successfully(
    scripted_llm, conversation_log, monkeypatch: pytest.MonkeyPatch
) -> None:
    _settings(monkeypatch, threshold=2)
    fake = scripted_llm(summarizer, [completion(""), completion("Recovered summary.")])
    _seed(conversation_log, 2)

    assert await summarizer.summarize_conversation() is True

    fake.assert_drained()
    assert summarizer.get_working_memory_log().load_summary_state().summary_text == "Recovered summary."


async def test_prompt_carries_previous_summary(
    scripted_llm, conversation_log, monkeypatch: pytest.MonkeyPatch
) -> None:
    _settings(monkeypatch, threshold=1)
    working_memory = summarizer.get_working_memory_log()
    working_memory.write_summary_state(
        SummaryState(
            summary_text="Earlier: user booked a flight to Tokyo.",
            last_index=-1,
            updated_at=datetime.now(timezone.utc),
        )
    )
    fake = scripted_llm(summarizer, [completion("Merged summary.")])
    conversation_log.record_user_message("and a hotel")

    await summarizer.summarize_conversation()

    payload = fake.calls[0]["messages"][0]["content"]
    assert "Earlier: user booked a flight to Tokyo." in payload
    assert "and a hotel" in payload


def test_working_memory_round_trip(data_dir) -> None:
    log = WorkingMemoryLog(data_dir / "conversation" / "memory.log")
    state = SummaryState(
        summary_text="Timeline & Commitments:\n- 2026-11-20 09:00 — Standup",
        last_index=7,
        updated_at=datetime(2026, 11, 19, 23, 0, tzinfo=timezone.utc),
        unsummarized_entries=[
            LogEntry(tag="user_message", payload="hello", index=8, timestamp="2026-11-19 23:00:00"),
            LogEntry(tag="poke_reply", payload="hi", index=9, timestamp="2026-11-19 23:00:05"),
        ],
    )

    log.write_summary_state(state)
    loaded = log.load_summary_state()

    assert loaded.summary_text == state.summary_text
    assert loaded.last_index == 7
    assert [entry.payload for entry in loaded.unsummarized_entries] == ["hello", "hi"]
    assert loaded.updated_at == state.updated_at


def test_working_memory_renders_summary_and_tail(data_dir) -> None:
    log = WorkingMemoryLog(data_dir / "conversation" / "memory.log")
    log.write_summary_state(
        SummaryState(
            summary_text="Prefers terse replies.",
            last_index=1,
            unsummarized_entries=[
                LogEntry(tag="user_message", payload="thanks", index=2, timestamp="2026-11-19 23:01:00")
            ],
        )
    )

    rendered = log.render_transcript()

    assert "<conversation_summary>Prefers terse replies.</conversation_summary>" in rendered
    assert "thanks" in rendered


def test_working_memory_escapes_html(data_dir) -> None:
    log = WorkingMemoryLog(data_dir / "conversation" / "memory.log")
    log.write_summary_state(
        SummaryState(
            summary_text="Budget is < 500 & rising",
            last_index=0,
            unsummarized_entries=[],
        )
    )

    rendered = log.render_transcript()

    assert "&lt; 500 &amp; rising" in rendered
