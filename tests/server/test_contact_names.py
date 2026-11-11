"""Phase 2 fix 3 (review I3): parse "Name <addr>" recipients; fill names from email headers."""

import asyncio
import json
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest

from server.agents.execution_agent import agent as agent_module
from server.agents.execution_agent import runtime as runtime_module
from server.agents.execution_agent.runtime import ExecutionAgentRuntime
from server.services.agents import contacts as contacts_module
from server.services.agents import store as store_module
from server.services.agents.contacts import contacts_from_tool_call, record_contacts_from_tool_call
from server.services.agents.store import AgentRecord, AgentStore, ContactRecord
from server.services.execution import log_store as log_store_module
from server.services.execution.log_store import ExecutionAgentLogStore

T1 = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
OK = {"successful": True, "error": None, "data": {"id": "r-1"}}


def make_store(tmp_path):
    s = AgentStore(tmp_path / "a.db")
    s.insert_agent(AgentRecord("ag_1", "Offsite", "", T1, None, None))
    return s


def triples(contacts):
    return [(c.email, c.display_name, c.role) for c in contacts]


def _search_email(sender, recipient, subject="Offsite dates", mid="m-1"):
    from server.agents.execution_agent.tasks.search_email.schemas import GmailSearchEmail

    return GmailSearchEmail(
        id=mid, thread_id="t-" + mid, query="offsite", subject=subject, sender=sender,
        recipient=recipient, timestamp=T1, clean_text="see you there",
    ).model_dump(exclude_none=True)


# --- (b) parsing recipient args ---------------------------------------------------------------

def test_named_address_parsed():
    out = contacts_from_tool_call("gmail_create_draft",
        {"recipient_email": "Alice Chen <Alice.Chen@x.io>", "subject": "s", "body": "b"}, OK)
    assert triples(out) == [("alice.chen@x.io", "Alice Chen", "to")]


def test_bare_address_unchanged():  # guard: passes before the fix too
    out = contacts_from_tool_call("gmail_create_draft",
        {"recipient_email": "bob@x.io", "subject": "s", "body": "b"}, OK)
    assert triples(out) == [("bob@x.io", "", "to")]


def test_string_without_address_skipped():
    out = contacts_from_tool_call("gmail_create_draft",
        {"recipient_email": "Alice Chen", "cc": ["not an address"], "subject": "s", "body": "b"}, OK)
    assert out == []


def test_mixed_forms_in_lists():
    out = contacts_from_tool_call("gmail_reply_to_thread", {
        "thread_id": "t", "message_body": "m",
        "recipient_email": "carol@acme.com",
        "extra_recipients": ["Dan Park <Dan.Park@acme.com>", "nobody", '"Wu, Eve" <eve@acme.com>'],
        "cc": ["Frank Li <frank@acme.com>", "gina@acme.com"],
    }, OK)
    assert triples(out) == [
        ("carol@acme.com", "", "to"),
        ("dan.park@acme.com", "Dan Park", "to"),
        ("eve@acme.com", "Wu, Eve", "to"),
        ("frank@acme.com", "Frank Li", "cc"),
        ("gina@acme.com", "", "cc"),
    ]


def test_named_recipient_recorded_bare_and_findable(tmp_path):
    s = make_store(tmp_path)
    record_contacts_from_tool_call(s, "ag_1", "gmail_create_draft",
        {"recipient_email": "Alice Chen <Alice.Chen@x.io>", "subject": "s", "body": "b"}, OK)
    assert triples(s.contacts_for("ag_1")) == [("alice.chen@x.io", "Alice Chen", "to")]
    assert s.agents_for_email("alice.chen@x.io") == ["ag_1"]


# --- store: a later named record fills an empty name ------------------------------------------

def test_later_named_record_fills_empty_name_keeps_first_role_never_overwrites(tmp_path):
    s = make_store(tmp_path)
    s.add_contacts("ag_1", [ContactRecord("alice@x.io", "", "to"), ContactRecord("bob@x.io", "Bob Ray", "to")])
    s.add_contacts("ag_1", [ContactRecord("Alice@X.io", "Alice Chen", "cc"), ContactRecord("bob@x.io", "Robert", "cc")])
    assert triples(s.contacts_for("ag_1")) == [
        ("alice@x.io", "Alice Chen", "to"),  # filled, first role kept
        ("bob@x.io", "Bob Ray", "to"),  # existing name never overwritten
    ]


def test_fill_contact_names_only_empty_names_only_existing_rows(tmp_path):
    s = make_store(tmp_path)
    s.add_contacts("ag_1", [ContactRecord("alice@x.io", "", "to"), ContactRecord("bob@x.io", "Bob Ray", "cc")])
    s.add_contacts("ag_2", [ContactRecord("alice@x.io", "", "to")])
    s.fill_contact_names("ag_1", {"Alice@X.io": "Alice Chen", "bob@x.io": "Robert", "zed@x.io": "Zed"})
    assert triples(s.contacts_for("ag_1")) == [("alice@x.io", "Alice Chen", "to"), ("bob@x.io", "Bob Ray", "cc")]
    assert triples(s.contacts_for("ag_2")) == [("alice@x.io", "", "to")]  # other agents untouched


# --- (c) names from headers the agent already sees ---------------------------------------------

def _fill(store, tool_name, result, agent_id="ag_1"):
    contacts_module.record_contact_names_from_tool_call(store, agent_id, tool_name, result)


def test_recorded_contact_gets_name_from_search_sender(tmp_path):
    s = make_store(tmp_path)
    s.add_contacts("ag_1", [ContactRecord("alice.chen@x.io", "", "to")])
    _fill(s, "task_email_search", [_search_email("Alice Chen <Alice.Chen@x.io>", "Me <me@y.io>")])
    assert triples(s.contacts_for("ag_1")) == [("alice.chen@x.io", "Alice Chen", "to")]


def test_recorded_contact_gets_name_from_search_recipient(tmp_path):
    s = make_store(tmp_path)
    s.add_contacts("ag_1", [ContactRecord("dan@acme.com", "", "to")])
    _fill(s, "task_email_search", [_search_email("Me <me@y.io>", "Dan Park <dan@acme.com>, Eve <eve@acme.com>")])
    assert triples(s.contacts_for("ag_1")) == [("dan@acme.com", "Dan Park", "to")]


def test_unrecorded_sender_is_not_added(tmp_path):
    s = make_store(tmp_path)
    s.add_contacts("ag_1", [ContactRecord("alice.chen@x.io", "", "to")])
    _fill(s, "task_email_search", [
        _search_email("Mallory Spam <mallory@spam.io>", "Me <me@y.io>", mid="m-2"),
        _search_email("Alice Chen <alice.chen@x.io>", "Me <me@y.io>", mid="m-3"),
    ])
    assert [c.email for c in s.contacts_for("ag_1")] == ["alice.chen@x.io"]
    assert s.agents_for_email("mallory@spam.io") == []


def test_existing_name_not_overwritten_by_header(tmp_path):
    s = make_store(tmp_path)
    s.add_contacts("ag_1", [ContactRecord("alice.chen@x.io", "Alice Chen", "to")])
    _fill(s, "task_email_search", [_search_email("A. Chen <alice.chen@x.io>", "Me <me@y.io>")])
    assert triples(s.contacts_for("ag_1")) == [("alice.chen@x.io", "Alice Chen", "to")]


def test_gmail_read_result_headers_fill_names(tmp_path):
    s = make_store(tmp_path)
    s.add_contacts("ag_1", [ContactRecord("alice.chen@x.io", "", "to")])
    _fill(s, "gmail_list_drafts", {"successful": True, "error": None, "data": {"drafts": [
        {"id": "d-1", "message": {"sender": "Me <me@y.io>", "recipient": "Alice Chen <alice.chen@x.io>"}}]}})
    assert triples(s.contacts_for("ag_1")) == [("alice.chen@x.io", "Alice Chen", "to")]


def test_failed_or_foreign_results_fill_nothing(tmp_path):
    s = make_store(tmp_path)
    s.add_contacts("ag_1", [ContactRecord("alice.chen@x.io", "", "to")])
    _fill(s, "task_email_search", {"error": "Gmail not connected"})
    _fill(s, "gmail_list_drafts", {"successful": False, "error": "quota",
                                   "data": {"sender": "Alice Chen <alice.chen@x.io>"}})
    _fill(s, "createTrigger", {"trigger": {"sender": "Alice Chen <alice.chen@x.io>"}})
    assert triples(s.contacts_for("ag_1")) == [("alice.chen@x.io", "", "to")]


def test_header_fill_never_raises():
    class BrokenStore:
        def fill_contact_names(self, *args, **kwargs):
            raise RuntimeError("db is locked")

        def contacts_for(self, *args, **kwargs):
            raise RuntimeError("db is locked")

    _fill(BrokenStore(), "task_email_search", [_search_email("Alice Chen <alice.chen@x.io>", "Me <me@y.io>")])
    _fill(BrokenStore(), "task_email_search", None)


def test_find_contacts_by_name_finds_header_filled_contact(tmp_path):
    s = make_store(tmp_path)
    s.add_contacts("ag_1", [ContactRecord("alice.chen@x.io", "", "to")])
    _fill(s, "task_email_search", [_search_email("Alice Chen <alice.chen@x.io>", "Me <me@y.io>")])
    assert triples(s.find_contacts_by_name("Alice")) == [("alice.chen@x.io", "Alice Chen", "to")]


# --- runtime wiring ----------------------------------------------------------------------------

@pytest.fixture
def env(tmp_path, monkeypatch):
    store = make_store(tmp_path)
    logs = ExecutionAgentLogStore(tmp_path / "logs")
    monkeypatch.setattr(store_module, "_store", store)
    monkeypatch.setattr(agent_module, "get_execution_agent_logs", lambda: logs)
    monkeypatch.setattr(log_store_module, "_execution_agent_logs", logs)
    monkeypatch.setattr(runtime_module, "get_settings",
                        lambda: SimpleNamespace(openrouter_api_key="k", execution_agent_model="m"))
    return SimpleNamespace(store=store)


def _scripted(calls):
    state = {"n": 0}

    async def fake_llm(system_prompt, messages, with_tools):
        n = state["n"]
        state["n"] += 1
        if n < len(calls):
            name, args = calls[n]
            return {"choices": [{"message": {"content": "", "tool_calls": [
                {"id": f"c{n}", "type": "function", "function": {"name": name, "arguments": json.dumps(args)}}]}}]}
        return {"choices": [{"message": {"content": "Done."}}]}

    return fake_llm


def test_runtime_fills_name_of_drafted_contact_from_later_search(env):
    rt = ExecutionAgentRuntime("ag_1", store=env.store)
    rt.tool_registry = {
        "gmail_create_draft": lambda **kw: OK,
        "task_email_search": lambda **kw: [
            _search_email("Alice Chen <alice.chen@x.io>", "Me <me@y.io>"),
            _search_email("Mallory <mallory@spam.io>", "Me <me@y.io>", mid="m-2"),
        ],
    }
    rt._make_llm_call = _scripted([
        ("gmail_create_draft", {"recipient_email": "alice.chen@x.io", "subject": "Offsite", "body": "b"}),
        ("task_email_search", {"search_query": "offsite"}),
    ])
    assert asyncio.run(rt.execute("draft then search")).success
    assert triples(env.store.contacts_for("ag_1")) == [("alice.chen@x.io", "Alice Chen", "to")]
