"""Trigger provenance, visibility scoping, and legacy backfill."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

import server.agents.execution_agent.tools.triggers as tr
from server.services.reminders import REMINDER_OWNER_ID, is_reminder_owner
from server.services.reminders.backfill import backfill_legacy_triggers
from server.services.triggers import TriggerService, TriggerStore


class _NullLog:
    def record_action(self, *args, **kwargs):
        return None


@pytest.fixture
def triggers(tmp_path, monkeypatch):
    """Isolated trigger service wired into the tool module."""
    service = TriggerService(TriggerStore(tmp_path / "triggers.db"))
    monkeypatch.setattr(tr, "_TRIGGER_SERVICE", service)
    monkeypatch.setattr(tr, "_LOG_STORE", _NullLog())
    return service


# --------------------------------------------------------------------------
# Provenance
# --------------------------------------------------------------------------

def test_creating_a_reminder_records_the_creator(triggers) -> None:
    """The reserved owner id must not erase who asked for the reminder."""
    registry = tr.build_registry("Email Summary Agent")

    created = registry["createTrigger"](payload="remind me to send the contract")

    assert created["created_by"] == "Email Summary Agent"
    records = triggers.list_triggers(agent_name=REMINDER_OWNER_ID)
    assert len(records) == 1
    assert records[0].created_by == "Email Summary Agent"
    assert records[0].agent_name == REMINDER_OWNER_ID


def test_two_agents_keep_distinct_provenance(triggers) -> None:
    tr.build_registry("Email Summary Agent")["createTrigger"](payload="email reminder")
    tr.build_registry("Budget Analysis")["createTrigger"](payload="budget reminder")

    records = triggers.list_triggers(agent_name=REMINDER_OWNER_ID)
    creators = sorted(r.created_by for r in records)

    assert creators == ["Budget Analysis", "Email Summary Agent"]


# --------------------------------------------------------------------------
# Visibility scoping
# --------------------------------------------------------------------------

def test_agent_sees_only_its_own_reminders(triggers) -> None:
    """Regression: reminders used to be a shared, fully visible table."""
    tr.build_registry("Email Summary Agent")["createTrigger"](payload="email reminder")
    tr.build_registry("Budget Analysis")["createTrigger"](payload="budget reminder")

    email_view = tr.build_registry("Email Summary Agent")["listTriggers"]()
    budget_view = tr.build_registry("Budget Analysis")["listTriggers"]()

    assert len(email_view["triggers"]) == 1
    assert len(budget_view["triggers"]) == 1
    assert email_view["triggers"][0]["payload"] == "email reminder"
    assert budget_view["triggers"][0]["payload"] == "budget reminder"


def test_agent_cannot_update_another_agents_reminder(triggers) -> None:
    """Regression: any agent could previously pause anyone's reminder."""
    created = tr.build_registry("Email Summary Agent")["createTrigger"](
        payload="email reminder"
    )

    result = tr.build_registry("Budget Analysis")["updateTrigger"](
        trigger_id=created["trigger_id"], status="paused"
    )

    assert "error" in result
    assert "not found" in result["error"]

    # And the reminder really is untouched
    records = triggers.list_triggers(agent_name=REMINDER_OWNER_ID)
    assert records[0].status == "active"


def test_agent_can_update_its_own_reminder(triggers) -> None:
    registry = tr.build_registry("Email Summary Agent")
    created = registry["createTrigger"](payload="email reminder")

    updated = registry["updateTrigger"](
        trigger_id=created["trigger_id"], payload="email reminder, edited"
    )

    assert updated["trigger_id"] == created["trigger_id"]


def test_shared_trigger_is_visible_to_everyone(triggers) -> None:
    triggers.create_trigger(
        agent_name=REMINDER_OWNER_ID,
        payload="team-wide reminder",
        created_by="Email Summary Agent",
        shared=True,
    )

    budget_view = tr.build_registry("Budget Analysis")["listTriggers"]()

    assert len(budget_view["triggers"]) == 1
    assert budget_view["triggers"][0]["shared"] is True


def test_shared_trigger_can_be_updated_by_another_agent(triggers) -> None:
    record = triggers.create_trigger(
        agent_name=REMINDER_OWNER_ID,
        payload="team-wide reminder",
        created_by="Email Summary Agent",
        shared=True,
    )

    result = tr.build_registry("Budget Analysis")["updateTrigger"](
        trigger_id=record.id, status="paused"
    )

    assert "error" not in result


def test_unowned_legacy_row_is_not_visible_to_a_stranger(triggers) -> None:
    """A row owned by another agent with no provenance stays private."""
    triggers.create_trigger(
        agent_name="Call Mom Reminder",
        payload="remind me to call mom",
    )

    result = tr.build_registry("Budget Analysis")["listTriggers"]()

    assert result["triggers"] == []


def test_owner_id_is_not_treated_as_an_agent() -> None:
    assert is_reminder_owner(REMINDER_OWNER_ID)
    assert is_reminder_owner(" reminders ")
    assert not is_reminder_owner("Budget Analysis")


# --------------------------------------------------------------------------
# Legacy backfill
# --------------------------------------------------------------------------

def _insert_legacy_row(db: Path, agent_name: str, payload: str) -> None:
    """Write a row using the pre-provenance schema."""
    conn = sqlite3.connect(db)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS triggers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            payload TEXT NOT NULL,
            start_time TEXT,
            next_trigger TEXT,
            timezone TEXT,
            recurrence_rule TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            last_error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        )
    """)
    conn.execute(
        "INSERT INTO triggers (agent_name, payload, next_trigger, status, created_at, updated_at)"
        " VALUES (?, ?, '2026-12-01T10:00:00Z', 'active',"
        " '2026-11-20T00:00:00Z', '2026-11-20T00:00:00Z')",
        (agent_name, payload),
    )
    conn.commit()
    conn.close()


def test_old_schema_gains_the_new_columns(tmp_path, monkeypatch) -> None:
    """Opening a pre-provenance database must migrate it in place."""
    db = tmp_path / "legacy.db"
    _insert_legacy_row(db, "Call Mom Reminder", "remind me to call mom")

    service = TriggerService(TriggerStore(db))
    monkeypatch.setattr(tr, "_TRIGGER_SERVICE", service)
    monkeypatch.setattr(tr, "_LOG_STORE", _NullLog())

    rows = service.list_all_triggers()

    assert len(rows) == 1, "existing rows must survive migration"
    assert rows[0].created_by is None, "legacy rows start without provenance"
    assert rows[0].shared is False


def test_backfill_moves_legacy_reminders_and_keeps_creator(tmp_path, monkeypatch) -> None:
    db = tmp_path / "legacy.db"
    _insert_legacy_row(db, "Call Mom Reminder", "remind me to call mom")

    service = TriggerService(TriggerStore(db))
    monkeypatch.setattr(tr, "_TRIGGER_SERVICE", service)
    monkeypatch.setattr(tr, "_LOG_STORE", _NullLog())

    report = backfill_legacy_triggers(service=service)

    assert report.migrated == 1
    rows = service.list_all_triggers()
    assert rows[0].agent_name == REMINDER_OWNER_ID
    assert rows[0].created_by == "Call Mom Reminder", "creator must be preserved"


def test_backfill_leaves_task_like_triggers_alone(tmp_path, monkeypatch) -> None:
    """A trigger that asks an agent to do work is not a simple reminder."""
    db = tmp_path / "legacy.db"
    _insert_legacy_row(db, "Email Summary Agent", "check if the contract was signed")

    service = TriggerService(TriggerStore(db))
    monkeypatch.setattr(tr, "_TRIGGER_SERVICE", service)
    monkeypatch.setattr(tr, "_LOG_STORE", _NullLog())

    report = backfill_legacy_triggers(service=service)

    assert report.migrated == 0
    assert report.skipped_task_like == 1
    assert service.list_all_triggers()[0].agent_name == "Email Summary Agent"


def test_backfill_is_idempotent(triggers) -> None:
    triggers.create_trigger(
        agent_name="Call Mom Reminder", payload="remind me to call mom"
    )

    first = backfill_legacy_triggers(service=triggers)
    second = backfill_legacy_triggers(service=triggers)

    assert first.migrated == 1
    assert second.migrated == 0, "a second run must not move anything again"
    assert second.skipped_already_owned == 1


def test_backfill_dry_run_writes_nothing(triggers) -> None:
    triggers.create_trigger(
        agent_name="Call Mom Reminder", payload="remind me to call mom"
    )

    report = backfill_legacy_triggers(service=triggers, dry_run=True)

    assert report.migrated == 1
    assert triggers.list_all_triggers()[0].agent_name == "Call Mom Reminder"


def test_backfill_can_include_task_like_when_asked(tmp_path, monkeypatch) -> None:
    db = tmp_path / "legacy.db"
    _insert_legacy_row(db, "Email Summary Agent", "check if the contract was signed")

    service = TriggerService(TriggerStore(db))
    monkeypatch.setattr(tr, "_TRIGGER_SERVICE", service)
    monkeypatch.setattr(tr, "_LOG_STORE", _NullLog())

    report = backfill_legacy_triggers(service=service, migrate_task_like=True)

    assert report.migrated == 1
    assert service.list_all_triggers()[0].agent_name == REMINDER_OWNER_ID

