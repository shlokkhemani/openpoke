import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pytest

from server.services.agents import store as store_module
from server.services.agents.migration import migrate_from_roster
from server.services.agents.search_text import build_search_text, describe_schedule
from server.services.agents.store import (
    AgentRecord,
    AgentStore,
    ContactRecord,
    get_agent_store,
)
from server.services.triggers.models import TriggerRecord

T1 = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)
T2 = datetime(2026, 11, 2, 15, 30, tzinfo=timezone.utc)


def make_store(tmp_path):
    return AgentStore(tmp_path / "a.db")


def trig(rrule, payload, status, start_time=None):
    return TriggerRecord(
        id=1,
        agent_id="x",
        payload=payload,
        start_time=start_time,
        recurrence_rule=rrule,
        status=status,
        created_at="2026-11-01T00:00:00Z",
        updated_at="2026-11-01T00:00:00Z",
    )


def make_agent(name="Digest", description=""):
    return AgentRecord(
        id="ag_test",
        name=name,
        description=description,
        created_at=T1,
        last_user_activity_at=None,
        last_run_at=None,
    )


# ---- store: ids, records ----

def test_names_not_unique_ids_are(tmp_path):
    s = make_store(tmp_path)
    a, b = s.create_agent("Email Alice"), s.create_agent("Email Alice")
    assert a.id != b.id and re.fullmatch(r"ag_[a-z2-7]{8}", a.id)
    assert [x.id for x in s.list_agents()].count(a.id) == 1
    assert len(s.list_agents()) == 2


def test_get_roundtrip_and_missing(tmp_path):
    s = make_store(tmp_path)
    a = s.create_agent("Digest", "daily summary")
    got = s.get(a.id)
    assert got.name == "Digest" and got.description == "daily summary"
    assert got.last_user_activity_at is None and got.last_run_at is None
    assert s.get("ag_nope0000") is None


def test_insert_agent_keeps_given_id(tmp_path):
    s = make_store(tmp_path)
    rec = AgentRecord("ag_chen_budget", "Budget", "d", T1, None, None)
    s.insert_agent(rec)
    assert s.get("ag_chen_budget") == rec


def test_update_description(tmp_path):
    s = make_store(tmp_path)
    a = s.create_agent("Digest")
    s.update_description(a.id, "now sends weekly")
    assert s.get(a.id).description == "now sends weekly"


# ---- record_use ----

def test_user_vs_trigger_timestamps(tmp_path):
    s = make_store(tmp_path)
    a = s.create_agent("Digest")
    s.record_use(a.id, "trigger", T1)
    assert s.get(a.id).last_user_activity_at is None
    assert s.get(a.id).last_run_at == T1
    s.record_use(a.id, "user", T2)
    assert s.get(a.id).last_user_activity_at == T2
    assert s.get(a.id).last_run_at == T2


def test_agent_source_updates_last_run_only(tmp_path):
    s = make_store(tmp_path)
    a = s.create_agent("Digest")
    s.record_use(a.id, "agent", T1)
    got = s.get(a.id)
    assert got.last_run_at == T1 and got.last_user_activity_at is None


# ---- contacts ----

def test_contacts_lowercased_and_deduped(tmp_path):  # Review Focus 4
    s = make_store(tmp_path)
    a = s.create_agent("Email Alice")
    s.add_contacts(a.id, [ContactRecord("Alice.Chen@Northwind.io", "Alice Chen", "to")] * 2)
    assert s.contacts_for(a.id) == [ContactRecord("alice.chen@northwind.io", "Alice Chen", "to")]


def test_agents_for_email_case_insensitive(tmp_path):
    s = make_store(tmp_path)
    a, b = s.create_agent("A"), s.create_agent("B")
    s.add_contacts(a.id, [ContactRecord("bob@x.io", "Bob", "to")])
    s.add_contacts(b.id, [ContactRecord("bob@x.io", "Bob", "cc")])
    assert sorted(s.agents_for_email("BOB@x.io")) == sorted([a.id, b.id])
    assert s.agents_for_email("nobody@x.io") == []


def test_find_contacts_by_name_full_and_first_case_insensitive(tmp_path):
    s = make_store(tmp_path)
    a = s.create_agent("A")
    s.add_contacts(a.id, [
        ContactRecord("alice.chen@x.io", "Alice Chen", "to"),
        ContactRecord("bob@x.io", "Bob Stone", "to"),
    ])
    alice = ContactRecord("alice.chen@x.io", "Alice Chen", "to")
    assert s.find_contacts_by_name("alice chen") == [alice]
    assert s.find_contacts_by_name("ALICE") == [alice]
    assert s.find_contacts_by_name("Zed") == []


def test_find_contacts_by_name_accented(tmp_path):
    s = make_store(tmp_path)
    a = s.create_agent("A")
    s.add_contacts(a.id, [ContactRecord("jose@x.io", "José Ruiz", "to")])
    assert [c.email for c in s.find_contacts_by_name("josé")] == ["jose@x.io"]
    assert [c.email for c in s.find_contacts_by_name("JOSÉ ruiz")] == ["jose@x.io"]


# ---- FTS ----

def test_fts_handles_punctuation(tmp_path):  # Review Focus 4
    s = make_store(tmp_path)
    a = s.create_agent("Email Jose")
    s.set_search_text(a.id, "Email José O'Brien re: \"Q3\" budget")
    assert s.fts_search('O\'Brien "Q3" AND OR NEAR(', 5)[0][0] == a.id


def test_fts_no_tokens_returns_empty(tmp_path):
    s = make_store(tmp_path)
    a = s.create_agent("A")
    s.set_search_text(a.id, "something")
    assert s.fts_search('"" ()', 5) == []


def test_fts_ranks_better_match_first_and_respects_limit(tmp_path):
    s = make_store(tmp_path)
    a, b = s.create_agent("A"), s.create_agent("B")
    s.set_search_text(a.id, "budget budget budget report")
    s.set_search_text(b.id, "lunch plans with report")
    hits = s.fts_search("budget report", 5)
    assert [h[0] for h in hits][0] == a.id and len(hits) == 2
    assert len(s.fts_search("budget report", 1)) == 1


def test_fts_replaces_old_search_text(tmp_path):
    s = make_store(tmp_path)
    a = s.create_agent("A")
    s.set_search_text(a.id, "alpha")
    s.set_search_text(a.id, "beta")
    assert s.fts_search("alpha", 5) == []
    assert s.fts_search("beta", 5)[0][0] == a.id


def test_fts_accent_insensitive(tmp_path):
    s = make_store(tmp_path)
    a = s.create_agent("A")
    s.set_search_text(a.id, "Email José")
    assert s.fts_search("jose", 5)[0][0] == a.id


# ---- embeddings ----

def test_embeddings_empty_store(tmp_path):
    # Documented choice: empty store returns ([], array of shape (0,)).
    ids, mat = make_store(tmp_path).embeddings()
    assert ids == [] and isinstance(mat, np.ndarray) and mat.shape[0] == 0


def test_embeddings_roundtrip_float32(tmp_path):
    s = make_store(tmp_path)
    a, b = s.create_agent("A"), s.create_agent("B")
    s.create_agent("C")  # no embedding: excluded
    va = np.array([1.0, 2.0, 3.0], dtype=np.float32)
    vb = np.array([0.5, 0.25, -1.0], dtype=np.float32)
    s.set_embedding(a.id, va)
    s.set_embedding(b.id, vb)
    ids, mat = s.embeddings()
    assert sorted(ids) == sorted([a.id, b.id])
    assert mat.dtype == np.float32 and mat.shape == (2, 3)
    by_id = dict(zip(ids, mat))
    assert np.array_equal(by_id[a.id], va) and np.array_equal(by_id[b.id], vb)


def test_clear_empties_everything(tmp_path):
    s = make_store(tmp_path)
    a = s.create_agent("A")
    s.add_contacts(a.id, [ContactRecord("a@x.io", "A", "to")])
    s.set_search_text(a.id, "hello")
    s.set_embedding(a.id, np.ones(3, dtype=np.float32))
    s.clear()
    assert s.list_agents() == [] and s.contacts_for(a.id) == []
    assert s.fts_search("hello", 5) == []
    assert s.embeddings()[0] == []


def _two_dims(tmp_path):
    s = make_store(tmp_path)
    ids = {n: s.create_agent(n).id for n in "ABCD"}
    s.set_embedding(ids["A"], np.ones(3, dtype=np.float32))
    s.set_embedding(ids["B"], np.ones(3, dtype=np.float32))
    s.set_embedding(ids["C"], np.ones(5, dtype=np.float32))
    s.set_embedding(ids["D"], np.ones(5, dtype=np.float32))
    return s, ids


def test_embeddings_with_dim_returns_only_that_length(tmp_path):
    s, ids = _two_dims(tmp_path)
    got, mat = s.embeddings(dim=5)
    assert sorted(got) == sorted([ids["C"], ids["D"]]) and mat.shape == (2, 5)
    got, mat = s.embeddings(3)
    assert sorted(got) == sorted([ids["A"], ids["B"]]) and mat.shape == (2, 3)


def test_embeddings_none_picks_most_common_length(tmp_path):
    s, ids = _two_dims(tmp_path)
    s.set_embedding(ids["D"], np.ones(3, dtype=np.float32))  # now 3 rows of length 3, 1 of length 5
    got, mat = s.embeddings()
    assert len(got) == 3 and mat.shape == (3, 3)


def test_embeddings_none_tie_goes_to_smaller_length(tmp_path):
    s, ids = _two_dims(tmp_path)
    got, mat = s.embeddings()
    assert sorted(got) == sorted([ids["A"], ids["B"]]) and mat.shape == (2, 3)


def test_embeddings_no_row_of_requested_dim_is_2d_empty(tmp_path):
    s, _ = _two_dims(tmp_path)
    got, mat = s.embeddings(dim=9)
    assert got == [] and mat.shape == (0, 9) and mat.dtype == np.float32


def test_embeddings_empty_store_is_2d(tmp_path):
    got, mat = make_store(tmp_path).embeddings()
    assert got == [] and mat.shape == (0, 0) and mat.dtype == np.float32
    got, mat = make_store(tmp_path).embeddings(dim=4)
    assert got == [] and mat.shape == (0, 4)


def test_fts_orphan_rows_do_not_use_up_limit(tmp_path):
    s = make_store(tmp_path)
    real = s.create_agent("Real")
    s.set_search_text(real.id, "budget report lunch plans")
    for i in range(3):
        s.set_search_text(f"ag_deleted_{i}", "budget budget budget budget")
    hits = s.fts_search("budget", 1)
    assert [h[0] for h in hits] == [real.id]


# ---- search text / schedule ----

def test_search_text_includes_active_triggers_only():
    text = build_search_text(
        make_agent(),
        [],
        [trig("FREQ=DAILY;BYHOUR=21", "summarise email", "active"),
         trig("FREQ=WEEKLY", "old", "paused")],
    )
    assert "daily at 9pm" in text and "summarise email" in text and "old" not in text


def test_search_text_includes_name_description_contacts():
    agent = make_agent("Budget Chen", "tracks the Q3 budget")
    text = build_search_text(agent, [ContactRecord("alice@x.io", "Alice Chen", "to")], [])
    for piece in ("Budget Chen", "tracks the Q3 budget", "Alice Chen", "alice@x.io"):
        assert piece in text


def test_unusual_rrule_kept_raw():
    assert describe_schedule("FREQ=YEARLY;BYMONTH=3;BYMONTHDAY=3", None) == "FREQ=YEARLY;BYMONTH=3;BYMONTHDAY=3"


@pytest.mark.parametrize("rule", [
    "FREQ=DAILY;INTERVAL=2;BYHOUR=9",
    "FREQ=MONTHLY;BYHOUR=9",
    "FREQ=WEEKLY;BYSETPOS=1;BYDAY=MO",
    "FREQ=WEEKLY;BYMONTH=3",
    "FREQ=DAILY;BYMONTHDAY=3",
])
def test_unsupported_rules_returned_unchanged(rule):
    assert describe_schedule(rule, None) == rule


@pytest.mark.parametrize("rule", [
    "FREQ=WEEKLY;BYDAY=1MO",
    "FREQ=WEEKLY;BYDAY=-1FR;BYHOUR=9",
    "FREQ=WEEKLY;BYDAY=+2TU",
    "FREQ=WEEKLY;BYDAY=MO,2WE",
    "FREQ=DAILY;BYHOUR=9,17",
    "FREQ=DAILY;BYHOUR=9;BYMINUTE=0,30",
    "FREQ=WEEKLY;BYDAY=MO;BYHOUR=9,17;BYMINUTE=0",
])
def test_inexact_schedules_returned_raw(rule):
    assert describe_schedule(rule, None) == rule


def test_simple_schedules_keep_their_text():
    assert describe_schedule("FREQ=WEEKLY;BYDAY=MO;BYHOUR=9", None) == "weekly on Monday at 9am"
    assert describe_schedule("FREQ=DAILY;BYHOUR=17", None) == "daily at 5pm"


def test_render_candidate_keeps_raw_rule_for_inexact_schedule():
    text = build_search_text(make_agent(), [], [trig("FREQ=WEEKLY;BYDAY=1MO;BYHOUR=9", "payroll", "active")])
    assert "FREQ=WEEKLY;BYDAY=1MO;BYHOUR=9" in text and "weekly on" not in text


def test_byhour_form_daily():
    assert describe_schedule("FREQ=DAILY;BYHOUR=21", None) == "daily at 9pm"


def test_byhour_weekly_single_day():
    assert describe_schedule("FREQ=WEEKLY;BYDAY=MO;BYHOUR=8", None) == "weekly on Monday at 8am"


def test_dtstart_multiline_daily():
    rule = "DTSTART;TZID=America/Vancouver:20261101T210000\nRRULE:FREQ=DAILY"
    assert describe_schedule(rule, "2026-11-02T05:00:00Z") == "daily at 9pm"


def test_dtstart_multiline_weekly_two_byday():
    rule = "DTSTART;TZID=America/Toronto:20261101T121500\nRRULE:FREQ=WEEKLY;BYDAY=MO,WE"
    assert describe_schedule(rule, None) == "weekly on Monday, Wednesday at 12:15pm"


def test_byhour_takes_precedence_over_dtstart():
    rule = "DTSTART;TZID=America/Toronto:20261101T060000\nRRULE:FREQ=DAILY;BYHOUR=21"
    assert describe_schedule(rule, None) == "daily at 9pm"


def test_start_time_fallback():
    assert describe_schedule("FREQ=DAILY", "2026-11-01T21:00:00Z") == "daily at 9pm"


def test_minutes_formatting():
    assert describe_schedule("FREQ=DAILY;BYHOUR=21;BYMINUTE=30", None) == "daily at 9:30pm"


def test_midnight_and_noon():
    assert describe_schedule("FREQ=DAILY;BYHOUR=0", None) == "daily at 12am"
    assert describe_schedule("FREQ=DAILY;BYHOUR=12", None) == "daily at 12pm"
    assert describe_schedule("FREQ=DAILY;BYHOUR=12;BYMINUTE=15", None) == "daily at 12:15pm"


def test_no_time_available_omits_at():
    assert describe_schedule("FREQ=DAILY", None) == "daily"
    assert describe_schedule("FREQ=WEEKLY;BYDAY=MO", None) == "weekly on Monday"


# ---- migration / singleton ----

def test_migrate_from_roster_not_implemented():
    with pytest.raises(NotImplementedError, match="see design §4.7"):
        migrate_from_roster()


def test_get_agent_store_singleton_and_path(monkeypatch, tmp_path):
    created = []

    class StubStore:
        def __init__(self, db_path):
            created.append(Path(db_path))

    monkeypatch.setattr(store_module, "AgentStore", StubStore)
    monkeypatch.setattr(store_module, "_store", None, raising=False)
    # The autouse conftest fixture redirects the default path; restore the real value (StubStore never creates it).
    real_default = Path(store_module.__file__).resolve().parent.parent.parent / "data" / "agents.db"
    monkeypatch.setattr(store_module, "_DEFAULT_DB_PATH", real_default)
    first, second = get_agent_store(), get_agent_store()
    assert first is second and len(created) == 1
    assert created[0].parts[-3:] == ("server", "data", "agents.db")
    assert not created[0].exists()


# ---- FTS: stopwords never reach BM25 (Task 16e) ----

def test_fts_query_drops_stopwords():
    assert store_module._fts_query("Is it going to rain in Seattle?") == '"going" OR "rain" OR "Seattle"'


def test_fts_query_stopwords_case_insensitive_keeps_original_case():
    assert store_module._fts_query("The plan IS done") == '"plan" OR "done"'


def test_fts_only_stopwords_is_empty(tmp_path):
    s = make_store(tmp_path)
    a = s.create_agent("A")
    s.set_search_text(a.id, "the of and everything")
    assert store_module._fts_query("the of and") == ""
    assert s.fts_search("the of and", 5) == []


def test_fts_stopword_in_query_does_not_match_unrelated_agent(tmp_path):
    s = make_store(tmp_path)
    sam = s.create_agent("Email Sam re vendor contract", "Handles the vendor contract thread")
    rent = s.create_agent("Pay rent reminder", "Reminds about the rent payment")
    s.set_search_text(sam.id, "Email Sam re vendor contract Handles the vendor contract thread")
    s.set_search_text(rent.id, "Pay rent reminder Reminds about the rent payment")
    assert [i for i, _ in s.fts_search("Ask Sam if the contract is done", 5)] == [sam.id]
