"""Task 8: description updater, search index refresh, subject extraction."""

import asyncio
from datetime import datetime, timezone

import numpy as np
import pytest

from evals.harness.fake_llm import FakeLLM
from server.openrouter_client import OpenRouterError
from server.services.agents.contacts import extract_subjects
from server.services.agents.descriptions import DescriptionUpdater, RunFacts
from server.services.agents.index import refresh_search_index
from server.services.agents.store import AgentRecord, AgentStore, ContactRecord
from server.services.triggers.models import TriggerRecord

T1 = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
AGENT_ID = "ag_abcd2345"


def make(tmp_path, name="Northwind budget", description="old description"):
    s = AgentStore(tmp_path / "a.db")
    s.insert_agent(AgentRecord(AGENT_ID, name, description, T1, None, None))
    return s, s.get(AGENT_ID)


class FakeEmbedder:
    def __init__(self):
        self.calls = []

    def embed(self, texts):
        self.calls.append(list(texts))
        return np.array([[1.0, 2.0, 3.0]] * len(texts), dtype=np.float32)


def trigger(payload, status="active"):
    return TriggerRecord(id=1, agent_id=AGENT_ID, payload=payload, status=status,
                         created_at="2026-11-01T00:00:00Z", updated_at="2026-11-01T00:00:00Z")


# --- DescriptionUpdater ---------------------------------------------------------------------

def test_update_uses_llm_output(tmp_path):
    s, a = make(tmp_path)
    u = DescriptionUpdater(s, FakeLLM.text("  Emailed Alice Chen the budget; waiting on sign-off.\n"), "m")
    out = asyncio.run(u.update(a.id, "email alice chen the budget", "Sent."))
    assert out == "Emailed Alice Chen the budget; waiting on sign-off."
    assert s.get(a.id).description == out


def test_fallback_on_error(tmp_path):
    s, a = make(tmp_path, description="")
    u = DescriptionUpdater(s, FakeLLM.raising(OpenRouterError("500")), "m")
    assert asyncio.run(u.update(a.id, "x" * 500, "done")) == "x" * 300
    assert s.get(a.id).description == "x" * 300


def test_empty_llm_output_falls_back(tmp_path):
    s, a = make(tmp_path, description="")
    u = DescriptionUpdater(s, FakeLLM.text("   \n "), "m")
    assert asyncio.run(u.update(a.id, "email alice", "done")) == "email alice"
    assert s.get(a.id).description == "email alice"


def test_existing_description_kept_on_llm_error(tmp_path):
    s, a = make(tmp_path, description="Emailing Alice Chen re Q3 budget")
    u = DescriptionUpdater(s, FakeLLM.raising(OpenRouterError("500")), "m")
    text, fell_back = asyncio.run(u.update_checked(a.id, "any reply from her?", "done"))
    assert (text, fell_back) == ("Emailing Alice Chen re Q3 budget", True)
    assert s.get(a.id).description == "Emailing Alice Chen re Q3 budget"
    assert asyncio.run(u.update(a.id, "any reply from her?", "done")) == "Emailing Alice Chen re Q3 budget"


def test_existing_description_kept_on_empty_output(tmp_path):
    s, a = make(tmp_path, description="Emailing Alice Chen re Q3 budget")
    u = DescriptionUpdater(s, FakeLLM.text("  \n"), "m")
    assert asyncio.run(u.update_checked(a.id, "any reply?", "done")) == ("Emailing Alice Chen re Q3 budget", True)
    assert s.get(a.id).description == "Emailing Alice Chen re Q3 budget"


def test_kept_description_does_not_call_update_description(tmp_path, monkeypatch):
    s, a = make(tmp_path, description="kept")
    calls = []
    monkeypatch.setattr(s, "update_description", lambda *args: calls.append(args))
    u = DescriptionUpdater(s, FakeLLM.raising(OpenRouterError("500")), "m")
    asyncio.run(u.update(a.id, "x", "done"))
    assert calls == []


def test_kept_description_still_refreshes_index(tmp_path):
    s, a = make(tmp_path, description="kept description")
    u = DescriptionUpdater(s, FakeLLM.raising(OpenRouterError("500")), "m",
                           triggers=lambda aid: [trigger("water the ficus")])
    asyncio.run(u.update(a.id, "x", "done"))
    assert [i for i, _ in s.fts_search("ficus", 5)] == [a.id]
    assert [i for i, _ in s.fts_search("kept", 5)] == [a.id]


def test_empty_or_missing_description_still_falls_back_to_instructions(tmp_path):
    for i, description in enumerate(("", "   ")):
        (tmp_path / str(i)).mkdir()
        s, a = make(tmp_path / str(i), description=description)
        u = DescriptionUpdater(s, FakeLLM.raising(OpenRouterError("500")), "m")
        assert asyncio.run(u.update_checked(a.id, "email alice", "done")) == ("email alice", True)
        assert s.get(a.id).description == "email alice"


def test_search_text_rebuilt(tmp_path):
    s, a = make(tmp_path)
    s.add_contacts(a.id, [ContactRecord("alice.chen@northwind.io", "Alice Chen", "to")])
    u = DescriptionUpdater(s, FakeLLM.text("Waiting on Alice's sign-off."), "m")
    asyncio.run(u.update(a.id, "i", "r"))
    assert [i for i, _ in s.fts_search("sign-off", 5)] == [a.id]
    assert [i for i, _ in s.fts_search("alice.chen", 5)] == [a.id]


def test_fallback_also_rebuilds_search_text(tmp_path):
    s, a = make(tmp_path, description="")
    u = DescriptionUpdater(s, FakeLLM.raising(OpenRouterError("500")), "m")
    asyncio.run(u.update(a.id, "chase the zebra invoice", "r"))
    assert [i for i, _ in s.fts_search("zebra", 5)] == [a.id]


def test_search_text_includes_injected_triggers(tmp_path):
    s, a = make(tmp_path)
    u = DescriptionUpdater(s, FakeLLM.text("desc"), "m", triggers=lambda agent_id: [trigger("water the ficus")])
    asyncio.run(u.update(a.id, "i", "r"))
    assert [i for i, _ in s.fts_search("ficus", 5)] == [a.id]


def test_run_facts_reach_the_prompt(tmp_path):
    s, a = make(tmp_path)
    llm = FakeLLM.text("ok")
    asyncio.run(DescriptionUpdater(s, llm, "m").update(a.id, "i", "r",
        RunFacts([ContactRecord("alice.chen@northwind.io", "Alice Chen", "to")], ["Q3 budget"])))
    prompt = str(llm.requests[0]["messages"])
    assert "alice.chen@northwind.io" in prompt and "Q3 budget" in prompt
    assert "Alice Chen <alice.chen@northwind.io>" in prompt


def test_prompt_carries_previous_description_instructions_and_response(tmp_path):
    s, a = make(tmp_path, description="Tracks the Northwind budget thread")
    llm = FakeLLM.text("ok")
    asyncio.run(DescriptionUpdater(s, llm, "model-x").update(a.id, "ping Alice again", "Alice replied: approved"))
    req = llm.requests[0]
    assert req["model"] == "model-x"
    msgs = req["messages"]
    assert "Tracks the Northwind budget thread" in str(msgs)
    assert "ping Alice again" in str(msgs) and "Alice replied: approved" in str(msgs)
    assert req.get("tools") in (None, [])
    assert "system" in req or msgs[0]["role"] == "system"


def test_subjects_deduped_and_capped(tmp_path):
    s, a = make(tmp_path)
    llm = FakeLLM.text("ok")
    subjects = ["S0", "S1", "S0"] + [f"S{i}" for i in range(2, 15)]
    asyncio.run(DescriptionUpdater(s, llm, "m").update(a.id, "i", "r", RunFacts([], subjects)))
    prompt = str(llm.requests[0]["messages"])
    assert prompt.count("S0") == 1
    assert "S9" in prompt and "S10" not in prompt  # first 10 unique, in order


def test_update_without_facts_is_fine(tmp_path):
    s, a = make(tmp_path)
    assert asyncio.run(DescriptionUpdater(s, FakeLLM.text("ok"), "m").update(a.id, "i", "r", None)) == "ok"


# --- refresh_search_index -------------------------------------------------------------------

def test_refresh_without_embedder_rebuilds_text_only(tmp_path):
    s, a = make(tmp_path, description="chases invoices")
    s.add_contacts(a.id, [ContactRecord("bob@x.io", "Bob Lee", "to")])
    refresh_search_index(s, a.id, [trigger("renew passport")])
    assert [i for i, _ in s.fts_search("invoices", 5)] == [a.id]
    assert [i for i, _ in s.fts_search("passport", 5)] == [a.id]
    assert [i for i, _ in s.fts_search("bob@x.io", 5)] == [a.id]
    assert s.embeddings()[0] == []


def test_refresh_with_embedder_sets_embedding(tmp_path):
    s, a = make(tmp_path, description="chases invoices")
    emb = FakeEmbedder()
    refresh_search_index(s, a.id, [], embedder=emb)
    ids, mat = s.embeddings()
    assert ids == [a.id] and mat.shape == (1, 3)
    assert len(emb.calls) == 1 and "chases invoices" in emb.calls[0][0]


def test_updater_refreshes_embedding_when_embedder_given(tmp_path):
    s, a = make(tmp_path)
    DescriptionUpdater(s, FakeLLM.text("fresh text"), "m", embedder=FakeEmbedder())
    asyncio.run(DescriptionUpdater(s, FakeLLM.text("fresh text"), "m", embedder=FakeEmbedder()).update(a.id, "i", "r"))
    assert s.embeddings()[0] == [a.id]


# --- subject extraction ---------------------------------------------------------------------

@pytest.mark.parametrize("tool", ["gmail_create_draft", "gmail_reply_to_thread", "gmail_forward_email"])
def test_subject_arg_of_successful_send_calls(tool):
    assert extract_subjects(tool, {"subject": "Q3 budget", "recipient_email": "a@x.io"}, {"data": {"id": "1"}}) == ["Q3 budget"]


def test_subjects_not_taken_from_failed_calls():
    assert extract_subjects("gmail_create_draft", {"subject": "Q3"}, {"error": "boom"}) == []
    assert extract_subjects("gmail_create_draft", {"subject": "Q3"}, {"successful": False, "error": None}) == []


def test_subjects_from_search_style_results():
    result = {"successful": True, "error": None, "data": {"drafts": [
        {"id": "d1", "message": {"subject": "Lease renewal"}}, {"id": "d2", "message": {"subject": "Invoice 42"}}]}}
    assert extract_subjects("gmail_list_drafts", {}, result) == ["Lease renewal", "Invoice 42"]


def test_extract_subjects_never_raises():
    assert extract_subjects("gmail_create_draft", None, None) == []
    assert extract_subjects("gmail_list_drafts", {}, object()) == []
    assert extract_subjects("send_message_to_user", {"subject": "x"}, {"ok": True}) == []


