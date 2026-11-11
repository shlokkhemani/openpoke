"""Task 7: contacts captured from successful Gmail tool calls."""

from datetime import datetime, timezone

from server.services.agents.contacts import record_contacts_from_tool_call
from server.services.agents.store import AgentRecord, AgentStore

T1 = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)


def make_store(tmp_path):
    s = AgentStore(tmp_path / "a.db")
    s.insert_agent(AgentRecord("ag_1", "Digest", "", T1, None, None))
    return s


def pairs(s, agent_id="ag_1"):
    return {(c.email, c.role) for c in s.contacts_for(agent_id)}


def test_draft_recipients_recorded(tmp_path):
    s = make_store(tmp_path)
    record_contacts_from_tool_call(s, "ag_1", "gmail_create_draft",
        {"recipient_email": "Alice.Chen@northwind.io", "cc": ["bob@x.io"], "bcc": ["secret@x.io"], "subject": "s", "body": "b"},
        {"data": {"id": "r-123"}})
    assert {(c.email, c.role) for c in s.contacts_for("ag_1")} == {("alice.chen@northwind.io", "to"), ("bob@x.io", "cc")}


def test_draft_extra_recipients_are_to(tmp_path):
    s = make_store(tmp_path)
    record_contacts_from_tool_call(s, "ag_1", "gmail_create_draft",
        {"recipient_email": "a@x.io", "extra_recipients": ["Extra@Y.io", "z@y.io"], "subject": "s", "body": "b"},
        {"data": {"id": "r-1"}})
    assert pairs(s) == {("a@x.io", "to"), ("extra@y.io", "to"), ("z@y.io", "to")}


def test_draft_bcc_ignored(tmp_path):
    s = make_store(tmp_path)
    record_contacts_from_tool_call(s, "ag_1", "gmail_create_draft",
        {"recipient_email": "a@x.io", "bcc": ["hidden@x.io", "h2@x.io"], "subject": "s", "body": "b"},
        {"data": {"id": "r-1"}})
    assert pairs(s) == {("a@x.io", "to")}


def test_reply_records_same_fields(tmp_path):
    s = make_store(tmp_path)
    record_contacts_from_tool_call(s, "ag_1", "gmail_reply_to_thread",
        {"thread_id": "t-1", "recipient_email": "Carol@acme.com", "extra_recipients": ["dan@acme.com"],
         "cc": ["eve@acme.com"], "bcc": ["mallory@acme.com"], "message_body": "hi"},
        {"successful": True, "error": None, "data": {"id": "m-9"}})
    assert pairs(s) == {("carol@acme.com", "to"), ("dan@acme.com", "to"), ("eve@acme.com", "cc")}


def test_forward_records_recipient_as_to(tmp_path):
    s = make_store(tmp_path)
    record_contacts_from_tool_call(s, "ag_1", "gmail_forward_email",
        {"message_id": "m-1", "recipient_email": "Fwd@Partner.org", "additional_text": "fyi"},
        {"data": {"id": "m-2"}})
    assert pairs(s) == {("fwd@partner.org", "to")}


def test_execute_draft_records_nothing(tmp_path):
    s = make_store(tmp_path)
    record_contacts_from_tool_call(s, "ag_1", "gmail_execute_draft", {"draft_id": "r-123"}, {"data": {"id": "m-1"}})
    assert s.contacts_for("ag_1") == []


def test_non_gmail_tool_records_nothing(tmp_path):
    s = make_store(tmp_path)
    record_contacts_from_tool_call(s, "ag_1", "createTrigger",
        {"payload": "email a@x.io", "recipient_email": "a@x.io"}, {"trigger": {"id": 1}})
    record_contacts_from_tool_call(s, "ag_1", "gmail_get_contacts",
        {"recipient_email": "b@x.io"}, {"data": {"connections": []}})
    assert s.contacts_for("ag_1") == []


def test_failed_tool_records_nothing(tmp_path):
    s = make_store(tmp_path)
    # Tool returned an error payload (e.g. Gmail not connected).
    record_contacts_from_tool_call(s, "ag_1", "gmail_create_draft",
        {"recipient_email": "a@x.io", "subject": "s", "body": "b"},
        {"error": "Gmail not connected. Please connect Gmail in settings first."})
    # Composio reported the call as unsuccessful.
    record_contacts_from_tool_call(s, "ag_1", "gmail_reply_to_thread",
        {"thread_id": "t", "recipient_email": "b@x.io", "message_body": "m"},
        {"successful": False, "error": "quota exceeded", "data": {}})
    assert s.contacts_for("ag_1") == []


def test_exceptions_are_swallowed(tmp_path):
    class BrokenStore:
        def add_contacts(self, agent_id, contacts):
            raise RuntimeError("db is locked")

    # Must not raise: contact capture never breaks a run.
    record_contacts_from_tool_call(BrokenStore(), "ag_1", "gmail_create_draft",
        {"recipient_email": "a@x.io", "subject": "s", "body": "b"}, {"data": {"id": "r"}})
    # Malformed args must not raise either.
    s = make_store(tmp_path)
    record_contacts_from_tool_call(s, "ag_1", "gmail_create_draft", None, {"data": {}})
