"""Task 10: triggers keyed by agent id, startup migration, scheduler dispatch by id."""

import asyncio
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

from server.routes import chat as chat_module
from server.services import trigger_scheduler as scheduler_module
from server.services import triggers as triggers_pkg
from server.services.agents import store as store_module
from server.services.agents.store import AgentStore
from server.services.triggers.service import TriggerService
from server.services.triggers.store import TriggerStore

REPO = Path(__file__).resolve().parents[2]
RRULE = "RRULE:FREQ=DAILY"
OLD_SCHEMA = """
CREATE TABLE triggers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    agent_name TEXT NOT NULL,
    payload TEXT NOT NULL,
    start_time TEXT,
    next_trigger TEXT,
    recurrence_rule TEXT,
    timezone TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    last_error TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
"""
OLD_INDEX = "CREATE INDEX idx_triggers_agent_next ON triggers (agent_name, next_trigger);"
OLD_ROW = (
    "INSERT INTO triggers (agent_name, payload, start_time, next_trigger, recurrence_rule, timezone,"
    " status, last_error, created_at, updated_at)"
    " VALUES ('ag_old', 'ping', '2026-11-01T12:00:00Z', '2026-11-02T12:00:00Z', NULL, 'UTC',"
    " 'active', 'boom', '2026-11-01T00:00:00Z', '2026-11-01T00:00:00Z')"
)


def _columns(db: Path):
    with sqlite3.connect(db) as conn:
        return [r[1] for r in conn.execute("PRAGMA table_info(triggers)")]


def _index_columns(db: Path):
    with sqlite3.connect(db) as conn:
        return [r[2] for r in conn.execute("PRAGMA index_info(idx_triggers_agent_next)")]


def _old_db(path: Path, index: bool = True) -> Path:
    with sqlite3.connect(path) as conn:
        conn.execute(OLD_SCHEMA)
        if index:
            conn.execute(OLD_INDEX)
        conn.execute(OLD_ROW)
    return path


@pytest.fixture
def agents(tmp_path, monkeypatch):
    store = AgentStore(tmp_path / "agents.db")
    monkeypatch.setattr(store_module, "_store", store)
    return store


def _agent(store: AgentStore, name="Budget"):
    return store.create_agent(name, "tracks spending")


def _service(tmp_path) -> TriggerService:
    return TriggerService(TriggerStore(tmp_path / "triggers.db"))


# --- migration -------------------------------------------------------------

def test_old_db_column_renamed(tmp_path):
    db = _old_db(tmp_path / "triggers.db")
    store = TriggerStore(db)
    assert "agent_id" in _columns(db) and "agent_name" not in _columns(db)
    rec = store.fetch_one(1, "ag_old")
    assert rec is not None
    assert (rec.agent_id, rec.payload, rec.last_error, rec.next_trigger) == (
        "ag_old", "ping", "boom", "2026-11-02T12:00:00Z")


def test_migration_index_is_on_agent_id_next_trigger(tmp_path):
    db = _old_db(tmp_path / "triggers.db")
    TriggerStore(db)
    assert _index_columns(db) == ["agent_id", "next_trigger"]


def test_migration_recreates_missing_index(tmp_path):
    db = _old_db(tmp_path / "triggers.db", index=False)
    TriggerStore(db)
    assert _index_columns(db) == ["agent_id", "next_trigger"]


def test_migration_idempotent_and_fresh_db_noop(tmp_path):
    db = _old_db(tmp_path / "triggers.db")
    TriggerStore(db)
    TriggerStore(db)  # second open: no-op, no error
    assert _columns(db).count("agent_id") == 1
    assert TriggerStore(db).list_for_agent("ag_old")[0].payload == "ping"
    fresh = tmp_path / "fresh.db"
    TriggerStore(fresh)
    assert "agent_id" in _columns(fresh) and "agent_name" not in _columns(fresh)
    assert _index_columns(fresh) == ["agent_id", "next_trigger"]


def test_migration_failure_leaves_db_unchanged(tmp_path):
    # A table squatting on the index name makes the final CREATE INDEX fail after the rename.
    db = _old_db(tmp_path / "triggers.db", index=False)
    with sqlite3.connect(db) as conn:
        conn.execute("CREATE TABLE idx_triggers_agent_next (x INTEGER)")
    with pytest.raises(sqlite3.Error):
        TriggerStore(db)
    cols = _columns(db)
    assert "agent_name" in cols and "agent_id" not in cols
    with sqlite3.connect(db) as conn:
        assert conn.execute("SELECT agent_name, payload FROM triggers").fetchall() == [("ag_old", "ping")]


# --- store / service scoped by agent_id ------------------------------------

def test_list_scoped_to_agent_id(tmp_path, agents):
    svc = _service(tmp_path)
    svc.create_trigger(agent_id="ag_1", payload="one")
    svc.create_trigger(agent_id="ag_2", payload="two")
    assert [t.payload for t in svc.list_triggers(agent_id="ag_1")] == ["one"]
    assert svc.list_triggers(agent_id="ag_1")[0].agent_id == "ag_1"
    assert [t.payload for t in svc.get_due_triggers(
        before=datetime(2100, 1, 1, tzinfo=timezone.utc), agent_id="ag_2")] == ["two"]


def test_update_and_complete_by_agent_id(tmp_path, agents):
    svc = _service(tmp_path)
    t = svc.create_trigger(agent_id="ag_1", payload="one")
    assert svc.update_trigger(t.id, agent_id="ag_2", payload="x") is None
    assert svc.update_trigger(t.id, agent_id="ag_1", payload="new").payload == "new"
    svc.mark_as_completed(t.id, agent_id="ag_1")
    assert svc.list_triggers(agent_id="ag_1")[0].status == "completed"


# --- search text refresh ----------------------------------------------------

def test_trigger_change_updates_search_text(tmp_path, agents):
    a = _agent(agents)
    svc = _service(tmp_path)
    svc.create_trigger(
        agent_id=a.id, payload="pay rent reminder", recurrence_rule="FREQ=DAILY",
        start_time="2030-01-01T21:00:00", timezone_name="America/Vancouver")
    ids = [i for i, _ in agents.fts_search("pay rent reminder", 5)]
    assert ids == [a.id]
    assert [i for i, _ in agents.fts_search("daily at 9pm", 5)] == [a.id]


def test_trigger_update_and_complete_refresh_search_text(tmp_path, agents):
    a = _agent(agents)
    svc = _service(tmp_path)
    t = svc.create_trigger(agent_id=a.id, payload="water plants")
    assert agents.fts_search("water", 5)
    svc.update_trigger(t.id, agent_id=a.id, payload="feed cat")
    assert agents.fts_search("cat", 5) and not agents.fts_search("water", 5)
    svc.mark_as_completed(t.id, agent_id=a.id)
    assert not agents.fts_search("cat", 5)  # completed triggers drop out of the text


def test_search_refresh_failure_never_fails_trigger_op(tmp_path, agents, monkeypatch):
    a = _agent(agents)
    monkeypatch.setattr(agents, "set_search_text", lambda *args: (_ for _ in ()).throw(RuntimeError("fts down")))
    svc = _service(tmp_path)
    t = svc.create_trigger(agent_id=a.id, payload="still created")
    assert svc.list_triggers(agent_id=a.id)[0].id == t.id


def test_trigger_for_unknown_agent_is_still_created(tmp_path, agents):
    svc = _service(tmp_path)
    assert svc.create_trigger(agent_id="ag_ghost", payload="x").agent_id == "ag_ghost"


# --- tools -------------------------------------------------------------------

def test_trigger_tools_bound_with_agent_id():
    from server.agents.execution_agent.tools import triggers as trigger_tools

    registry = trigger_tools.build_registry("ag_1")
    for name in ("createTrigger", "updateTrigger", "listTriggers"):
        assert registry[name].keywords == {"agent_id": "ag_1"}


def test_tool_registry_bound_by_agent_id():
    from server.agents.execution_agent.tools import get_tool_registry

    registry = get_tool_registry(agent_id="ag_1")
    assert registry["createTrigger"].keywords == {"agent_id": "ag_1"}


def test_no_stale_agent_name_comments():
    runtime = (REPO / "server/agents/execution_agent/runtime.py").read_text(encoding="utf-8")
    registry = (REPO / "server/agents/execution_agent/tools/registry.py").read_text(encoding="utf-8")
    assert "until Task 10" not in runtime and "until Task 10" not in registry
    assert "get_tool_registry(agent_name" not in runtime
    assert "agent_name" not in registry  # ExecutionResult.agent_name in runtime.py is a real field


# --- scheduler ----------------------------------------------------------------

class _FakeManager:
    calls = []
    success = True

    async def execute_agent(self, agent_id, instructions, request_id=None):
        type(self).calls.append((agent_id, instructions))
        return SimpleNamespace(success=type(self).success, error=None if type(self).success else "bad", response="r")


@pytest.fixture
def sched(tmp_path, agents, monkeypatch):
    _FakeManager.calls = []
    _FakeManager.success = True
    monkeypatch.setattr(scheduler_module, "ExecutionBatchManager", _FakeManager)
    svc = _service(tmp_path)
    monkeypatch.setattr(triggers_pkg, "_trigger_service", svc)  # TriggerScheduler() reads the default service
    scheduler = scheduler_module.TriggerScheduler()
    assert scheduler._service is svc
    return scheduler, svc


def test_scheduler_dispatches_by_agent_id(sched, agents):
    scheduler, svc = sched
    a = _agent(agents)
    t = svc.create_trigger(agent_id=a.id, payload="do it")
    asyncio.run(scheduler._execute_trigger(t))
    assert [c[0] for c in _FakeManager.calls] == [a.id]
    assert "do it" in _FakeManager.calls[0][1]


def test_trigger_run_records_trigger_use(sched, agents):
    scheduler, svc = sched
    a = _agent(agents)
    at = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
    agents.record_use(a.id, "user", at)
    before = agents.get(a.id)
    t = svc.create_trigger(agent_id=a.id, payload="do it")
    asyncio.run(scheduler._execute_trigger(t))
    after = agents.get(a.id)
    assert after.last_user_activity_at == before.last_user_activity_at == at
    assert after.last_run_at > at


def test_unknown_agent_id_is_skipped_with_last_error(sched, agents):
    scheduler, svc = sched
    t = svc.create_trigger(agent_id="Budget Agent", payload="legacy name row")  # pre-Task-7 name
    asyncio.run(scheduler._execute_trigger(t))
    assert _FakeManager.calls == []
    assert agents.list_agents() == []
    got = svc.list_triggers(agent_id="Budget Agent")[0]
    assert got.last_error == "unknown agent id"
    assert got.status == "active"
    assert got.next_trigger == t.next_trigger  # not advanced or cleared


# --- DELETE /chat/history ------------------------------------------------------

def test_clear_history_clears_agent_store(tmp_path, agents, monkeypatch):
    import server.services as services

    class _Clearable:
        def __init__(self):
            self.cleared = False

        def clear(self):
            self.cleared = True

        clear_all = clear

    fakes = {k: _Clearable() for k in ("log", "exec")}
    monkeypatch.setattr(chat_module, "get_conversation_log", lambda: fakes["log"])
    monkeypatch.setattr(chat_module, "get_trigger_service", lambda: _service(tmp_path))
    monkeypatch.setattr(services, "get_execution_agent_logs", lambda: fakes["exec"])
    a = _agent(agents)
    agents.set_search_text(a.id, "budget text")
    chat_module.clear_history()
    assert agents.list_agents() == []
    assert agents.fts_search("budget", 5) == []


# --- no real triggers.db touched at import --------------------------------------

def test_import_server_does_not_open_triggers_db():
    code = (
        "import sqlite3, sys\n"
        "opened = []\n"
        "real = sqlite3.connect\n"
        "def spy(database, *a, **k):\n"
        "    opened.append(str(database))\n"
        "    return real(database, *a, **k)\n"
        "sqlite3.connect = spy\n"
        "import server.server\n"
        "bad = [p for p in opened if p.endswith('triggers.db')]\n"
        "print('OPENED', bad)\n"
        "sys.exit(1 if bad else 0)\n"
    )
    proc = subprocess.run([sys.executable, "-c", code], cwd=REPO, capture_output=True, text=True)
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_get_trigger_service_builds_lazily_for_default_path(tmp_path, monkeypatch):
    db = tmp_path / "lazy" / "triggers.db"
    monkeypatch.setattr(triggers_pkg, "_default_db_path", db)
    monkeypatch.setattr(triggers_pkg, "_trigger_service", None)
    assert not db.exists()
    service = triggers_pkg.get_trigger_service()
    assert db.exists()
    assert triggers_pkg.get_trigger_service() is service


# --- unknown-id marker is written once (P2-R12) ---------------------------------

def test_unknown_agent_id_warns_and_writes_marker_only_once_across_polls(sched, agents, monkeypatch):
    scheduler, svc = sched
    t = svc.create_trigger(agent_id="Legacy Name", payload="old row")
    warnings, debugs, failures = [], [], []

    class _SpyLogger:
        def __getattr__(self, name):
            return lambda msg, *a, **k: {"warning": warnings, "debug": debugs}.get(name, []).append(msg)

    monkeypatch.setattr(scheduler_module, "logger", _SpyLogger())
    real_record_failure = svc.record_failure
    monkeypatch.setattr(svc, "record_failure", lambda trig, err: (failures.append(err), real_record_failure(trig, err)))

    async def poll_twice():
        await scheduler._poll_once()
        await asyncio.sleep(0.1)
        first = svc.list_triggers(agent_id="Legacy Name")[0]
        await scheduler._poll_once()
        await asyncio.sleep(0.1)
        return first

    first = asyncio.run(poll_twice())
    second = svc.list_triggers(agent_id="Legacy Name")[0]
    assert failures == ["unknown agent id"]
    assert len(warnings) == 1
    assert len(debugs) == 1  # second poll: silent skip at debug level
    assert (second.updated_at, second.last_error) == (first.updated_at, first.last_error) == (first.updated_at, "unknown agent id")
    assert _FakeManager.calls == [] and agents.list_agents() == []
    assert second.status == "active" and second.next_trigger == t.next_trigger
