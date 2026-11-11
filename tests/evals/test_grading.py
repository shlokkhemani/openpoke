from dataclasses import replace
from pathlib import Path
from statistics import mean

import pytest

from evals.baselines import always_ask, always_create, always_reuse_top, oracle
from evals.grading import RunRecord, ToolCall, classify, grade
from evals.schema import AgentDef, Case, Outcome, Trigger, load_cases
from evals.world.roster import load_world, roster_for

EX = Path("evals/cases/examples")
WORLD = load_world(Path("evals/world/world.json"))
CASES = {c.id: c for c in load_cases(EX)}


def by_id(case_id: str) -> Case:
    return CASES[case_id]


def record(calls=(), user_messages=(), final_text="", case_id="t", mode="full") -> RunRecord:
    return RunRecord(
        case_id=case_id, mode=mode, n=30, run_idx=0, calls=list(calls),
        user_messages=list(user_messages), final_text=final_text,
        prompt_tokens=0, completion_tokens=0, latency_s=0.0, round_trips=1, error=None,
    )


def agent(aid: str, name: str) -> AgentDef:
    return AgentDef(id=aid, name=name, description=f"{name} task")


def reuse_case(aid: str, category: str = "email_followup") -> Case:
    return Case(
        id="synthetic", category=category, split="dev", source="test", severity="normal",
        required_agents=[], ia_history=[], message="follow up", acceptable=[Outcome("reuse", (aid,))],
    )


def create_call(name: str, instructions: str = "do the thing") -> ToolCall:
    return ToolCall("send_message_to_agent", {"name": name, "instructions": instructions})


def reuse_call(aid: str, instructions: str = "do the thing") -> ToolCall:
    return ToolCall("send_message_to_agent", {"agent_id": aid, "instructions": instructions})


def roster(case: Case) -> list[AgentDef]:
    return roster_for(case, WORLD, 30)


def g(case_id: str, rec: RunRecord, mode: str = "full"):
    case = by_id(case_id)
    return grade(case, rec, roster(case), mode)


# ------------------------------------------------------------ brief tests

def test_oracle_scores_100_on_examples():
    for case in load_cases(EX):
        r = roster_for(case, WORLD, 30)
        assert grade(case, oracle(case, r), r, "full").passed, case.id


def test_trivial_baselines_fail_somewhere():
    cases = load_cases(EX)
    for base in (always_create, always_ask):
        rate = mean(grade(c, base(c, r := roster_for(c, WORLD, 30)), r, "full").passed for c in cases)
        assert rate < 0.5


def test_assume_and_proceed_fails_clarify():
    rec = record(calls=[ToolCall("send_message_to_user", {"message": "I'll assume Alice Chen"}),
                        ToolCall("send_message_to_agent", {"name": "Offsite", "instructions": "email Alice Chen"})])
    assert not g("amb-person-001", rec).passed


def test_create_to_wrong_person_fails():
    rec = record(calls=[create_call("Offsite", "Email Alice Park about the offsite call on Thursday")])
    res = g("clear-person-001", rec)
    assert not res.passed and res.person_ok is False


def test_ack_then_dispatch_is_not_clarify():
    rec = record(calls=[ToolCall("send_message_to_user", {"message": "On it"}),
                        reuse_call("ag_nightly_digest", "move the digest to 8pm")])
    res = g("trigger-001", rec)
    assert res.passed and res.outcome_kind == "reuse" and res.flags == set()


def test_trigger_wrong_create_flagged():
    res = g("trigger-001", record(calls=[create_call("Evening recap")]))
    assert not res.passed
    assert {"duplicate_create", "trigger_duplicate"} <= res.flags


def test_broad_set_from_facts_only():
    rec = record(user_messages=["MR-2291 is open, renewal at $2,150, and P14 is yours"])
    res = g("broad-person-001", rec)
    assert res.passed and res.set_recall == 1.0 and res.set_precision is None
    assert res.outcome_kind == "answer_set" and "over_clarify" not in res.flags


def test_legacy_duplicate_name_is_structural():   # Review Focus 1
    r = [agent("ag_1", "Email Alice"), agent("ag_2", "Email Alice")]
    rec = record(calls=[ToolCall("send_message_to_agent", {"agent_name": "Email Alice", "instructions": "x"})])
    res = grade(reuse_case("ag_1"), rec, r, "legacy")
    assert not res.passed and res.structural


def test_id_and_name_together_is_invalid():   # Review Focus 3
    rec = record(calls=[ToolCall("send_message_to_agent", {"agent_id": "ag_x", "name": "y", "instructions": "z"})])
    r = [agent("ag_x", "X")]
    res = grade(reuse_case("ag_x"), rec, r, "full")
    assert "invalid_call" in res.flags and not res.passed
    c = classify(rec.calls, r, "full")
    assert c.reused == set() and c.created == 0 and len(c.invalid) == 1


# ----------------------------------------------------------- extra tests

def test_unknown_id_and_missing_target_are_invalid():
    r = [agent("ag_x", "X")]
    calls = [reuse_call("ag_nope"), ToolCall("send_message_to_agent", {"instructions": "z"})]
    c = classify(calls, r, "hybrid")
    assert c.reused == set() and c.created == 0 and len(c.invalid) == 2


def test_invalid_call_alone_does_not_count_as_clarify():
    rec = record(calls=[ToolCall("send_message_to_user", {"message": "Alice Chen or Alice Park?"}),
                        reuse_call("ag_not_in_roster")])
    res = g("amb-person-001", rec)
    assert not res.passed and "invalid_call" in res.flags
    assert res.outcome_kind == "invalid" and "over_clarify" not in res.flags


def test_non_dispatch_tools_ignored():
    calls = [ToolCall("wait", {}), ToolCall("search_agents", {"query": "alice"}),
             ToolCall("send_message_to_user", {"message": "hi"})]
    c = classify(calls, [agent("ag_x", "X")], "full")
    assert c.reused == set() and c.created == 0 and c.invalid == [] and c.instructions == []


def test_clarify_passes_and_scores_names():
    ok = g("amb-person-001", record(user_messages=["Do you mean Alice Chen or Alice Park?"]))
    assert ok.passed and ok.outcome_kind == "clarify" and ok.clarify_named_ok is True
    partial = g("amb-person-001", record(user_messages=["Which Alice? Alice Chen?"]))
    assert partial.passed and partial.clarify_named_ok is False


def test_clarify_needs_a_user_message():
    res = g("amb-person-001", record())
    assert not res.passed and res.outcome_kind == "none"


def test_reuse_does_not_need_person():
    # Amended 2026-11-07 (evals/results/changes.md): the reused agent already holds the thread and the
    # address, so a reuse passes whatever its wording; person_ok is still reported, for information.
    good = g("followup-001", record(calls=[reuse_call("ag_dana_repair", "Check for a reply from Dana Whitfield")]))
    assert good.passed and good.person_ok is True
    by_email = g("followup-001", record(calls=[reuse_call("ag_dana_repair", "check DANA@maplerentals.com reply")]))
    assert by_email.passed and by_email.person_ok is True
    first_name = g("followup-001", record(calls=[reuse_call("ag_dana_repair", "check whether Dana replied")]))
    assert first_name.passed and first_name.person_ok is False
    missing = g("followup-001", record(calls=[reuse_call("ag_dana_repair", "check for a reply")]))
    assert missing.passed and missing.person_ok is False and missing.outcome_kind == "reuse"
    legacy = by_id("followup-001")
    r = roster(legacy)
    name = next(a.name for a in r if a.id == "ag_dana_repair")
    rec = record(calls=[ToolCall("send_message_to_agent", {"agent_name": name, "instructions": "ask Dana"})])
    assert grade(legacy, rec, r, "legacy").passed


def test_create_still_needs_person():
    rec = record(calls=[create_call("Offsite", "Email Alice about the offsite call on Thursday")])
    res = g("clear-person-001", rec)
    assert not res.passed and res.person_ok is False


def test_person_ok_none_without_dispatch_or_expectation():
    assert g("followup-001", record(user_messages=["hm"])).person_ok is None
    assert g("trigger-001", record(calls=[reuse_call("ag_nightly_digest")])).person_ok is None


def test_wrong_reuse_flagged():
    res = g("trigger-001", record(calls=[reuse_call("ag_log_hours", "move to 8")]))
    assert not res.passed and "wrong_reuse" in res.flags and "duplicate_create" not in res.flags


def test_reuse_plus_extra_existing_id_fails():
    rec = record(calls=[reuse_call("ag_nightly_digest"), reuse_call("ag_weekly_digest")])
    res = g("trigger-001", rec)
    assert not res.passed and "wrong_reuse" in res.flags


def test_reuse_on_create_case_is_wrong_reuse():
    rec = record(calls=[reuse_call("ag_dana_repair", "Ask Dana Whitfield about painting")])
    res = g("newtask-001", rec)
    assert not res.passed and "wrong_reuse" in res.flags


def test_two_creates_fail_create_case():
    rec = record(calls=[create_call("A", "email Alice Chen"), create_call("B", "email Alice Chen")])
    assert not g("clear-person-001", rec).passed


def test_over_clarify_flagged():
    res = g("trigger-001", record(user_messages=["Which recap do you mean?"]))
    assert not res.passed and res.outcome_kind == "clarify" and "over_clarify" in res.flags
    # asking on a clarify case is not over-clarifying
    assert "over_clarify" not in g("amb-person-001", record(user_messages=["Which Alice?"])).flags


def test_multiple_acceptable_outcomes_any_match():
    base = by_id("broad-person-001")
    case = replace(base, acceptable=[Outcome("clarify"), *base.acceptable])
    r = roster(base)
    asked = grade(case, record(user_messages=["Which Dana thing do you mean?"]), r, "full")
    assert asked.passed and asked.outcome_kind == "clarify" and "over_clarify" not in asked.flags
    answered = grade(case, record(user_messages=["MR-2291, $2,150 and P14"]), r, "full")
    assert answered.passed and answered.outcome_kind == "answer_set"
    created = grade(case, record(calls=[create_call("Dana")]), r, "full")
    assert not created.passed


def test_answer_set_precision_with_extra_agent():
    calls = [reuse_call(a) for a in ("ag_dana_repair", "ag_dana_lease", "ag_dana_parking", "ag_maple_packages")]
    res = g("broad-person-001", record(calls=calls))
    assert not res.passed
    assert res.set_recall == 1.0 and res.set_precision == pytest.approx(0.75)
    assert "wrong_reuse" in res.flags


def test_answer_set_mixed_messages_and_facts():
    rec = record(calls=[reuse_call("ag_dana_lease")], final_text="Repair  ticket mr-2291 open;\nspot p14.")
    res = g("broad-person-001", rec)
    assert res.passed and res.set_recall == 1.0 and res.set_precision == 1.0


def test_answer_set_partial_recall_fails():
    res = g("broad-person-001", record(user_messages=["MR-2291 is still open"]))
    assert not res.passed and res.set_recall == pytest.approx(1 / 3)


def test_answer_set_fact_from_unexpected_agent_does_not_add_recall():
    res = g("broad-person-001", record(user_messages=["package room door lock is fixed"]))
    assert not res.passed and res.set_recall == 0.0


def test_legacy_unique_name_reuse():
    case = by_id("followup-001")
    r = roster(case)
    rec = record(calls=[ToolCall("send_message_to_agent",
                                 {"agent_name": "  email LANDLORD re dishwasher ", "instructions": "Ask Dana Whitfield"})],
                 mode="legacy")
    c = classify(rec.calls, r, "legacy")
    assert c.reused == {"ag_dana_repair"} and c.created == 0
    res = grade(case, rec, r, "legacy")
    assert res.passed and not res.structural


def test_legacy_unknown_name_creates_once_per_name():
    r = [agent("ag_1", "Email Alice")]
    calls = [ToolCall("send_message_to_agent", {"agent_name": "Offsite", "instructions": "a"}),
             ToolCall("send_message_to_agent", {"agent_name": "offsite", "instructions": "b"})]
    c = classify(calls, r, "legacy")
    assert c.created == 1 and c.reused == set() and c.instructions == ["a", "b"]


def test_unknown_mode_raises():
    with pytest.raises(ValueError):
        classify([], [], "bogus")


def test_reuse_top_baseline_by_recency():
    case = by_id("trigger-001")
    r = roster(case)
    ranked = [a.id for a in sorted(r, key=lambda a: a.last_user_activity_days_ago)]
    rec = always_reuse_top(case, r, ranked)
    assert classify(rec.calls, r, "full").reused == {ranked[0]}
    assert grade(case, always_reuse_top(case, r, ["ag_nightly_digest"]), r, "full").passed


def test_always_ask_passes_only_clarify_cases():
    for case in load_cases(EX):
        r = roster(case)
        passed = grade(case, always_ask(case, r), r, "full").passed
        assert passed == any(o.kind == "clarify" for o in case.acceptable), case.id


# ------------------------------------------------- multi-dispatch turns (Task 5b, ruling R23)

from evals.grading import FLAGS, mentions_time  # noqa: E402
from evals.schema import Contact, Slot, single_slot  # noqa: E402


def dispatch(*slots, ask=False) -> Outcome:
    slots = tuple(slots)
    return Outcome("dispatch", tuple(s.reuse_id for s in slots if s.reuse_id), slots, ask)


def multi_case(acceptable, agents, category="multi_intent", message="", **kw) -> Case:
    return Case(id="multi", category=category, split="test", source="test", severity="high",
                required_agents=list(agents), ia_history=[], message=message, acceptable=list(acceptable), **kw)


def ask(text):
    return ToolCall("send_message_to_user", {"message": text})


KARAN = AgentDef("ag_karan_trip", "Email Karan re trip", "Emailed Karan Mehta about the ski trip.",
                 contacts=(Contact("karan.mehta@acme.io", "Karan Mehta", "to"),))
DINNER_REMINDER = AgentDef("ag_dinner_rem", "Dinner reminder", "Reminds the user about dinner.",
                           triggers=(Trigger("daily at 7pm", "Remind the user about dinner", "active"),))
# "Email Karan Mehta that tomorrow's dinner moved to 9:00 PM, and remind me about it at 8:00 PM tomorrow"
KARAN_CASE = multi_case([dispatch(Slot("create", ("@person:Karan Mehta",)), Slot("create"))], [KARAN])


def test_new_flags_allowed():
    assert {"dropped_intent", "merged_intents", "ambiguous_dispatch"} <= FLAGS


def test_karan_split_passes_merged_fails():
    split = record(calls=[create_call("Email Karan re dinner", "Tell Karan Mehta dinner moved to 9pm"),
                          create_call("Dinner reminder", "Remind me at 8 PM tomorrow about dinner")])
    merged = record(calls=[create_call("Karan dinner", "Email Karan Mehta it's 9pm now and remind me at 20:00")])
    ok = grade(KARAN_CASE, split, [KARAN], "full")
    assert ok.passed and ok.outcome_kind == "dispatch" and ok.flags == set()
    assert (ok.slots_filled, ok.slots_total) == (2, 2)
    bad = grade(KARAN_CASE, merged, [KARAN], "full")
    assert not bad.passed and bad.flags == {"merged_intents"} and (bad.slots_filled, bad.slots_total) == (1, 2)


def test_karan_split_any_order_any_wording():
    rec = record(calls=[create_call("Reminder", "Set an alarm for 8pm tomorrow to leave"),
                        create_call("Email", "Draft a note to karan.mehta@acme.io: we're on at nine now")])
    assert grade(KARAN_CASE, rec, [KARAN], "full").passed


def test_context_mentions_are_not_merges():
    rec = record(calls=[create_call("Email", "Tell Karan Mehta dinner moved from 8pm to 9pm; I'll get a reminder"),
                        create_call("Reminder", "Remind me at 8pm to leave for dinner with Karan Mehta at 9pm")])
    assert grade(KARAN_CASE, rec, [KARAN], "full").passed


def test_email_only_is_dropped_intent():
    rec = record(calls=[create_call("Email Karan re dinner", "Tell Karan Mehta dinner moved from 8pm to 9pm")])
    res = grade(KARAN_CASE, rec, [KARAN], "full")
    assert not res.passed and res.flags == {"dropped_intent"} and res.slots_filled == 1


def test_email_plus_reminder_cue_in_one_dispatch_is_merged():
    for text in ("Email Karan Mehta: dinner is at 9pm. Also nudge me at 8pm.",
                 "Tell Karan Mehta dinner moved to 9pm and set an alarm for 8pm"):
        res = grade(KARAN_CASE, record(calls=[create_call("Kemal", text)]), [KARAN], "full")
        assert not res.passed and res.flags == {"merged_intents"}, text


def test_nothing_dispatched_is_dropped():
    res = grade(KARAN_CASE, record(user_messages=["Sure!"]), [KARAN], "full")
    assert not res.passed and "dropped_intent" in res.flags and "over_clarify" in res.flags


def test_extra_dispatch_fails():
    rec = record(calls=[create_call("Email", "Tell Karan Mehta dinner moved to 9pm"),
                        create_call("Reminder", "Remind me at 8 PM tomorrow about dinner"),
                        create_call("Calendar", "Move the dinner on the calendar")])
    res = grade(KARAN_CASE, rec, [KARAN], "full")
    assert not res.passed and not res.flags & {"merged_intents", "dropped_intent"}


def test_reuse_slot_person_is_not_checked():
    # A one-slot dispatch with @person on a reuse slot (single_slot of reuse + expect_person).
    case = multi_case([dispatch(Slot("reuse(ag_karan_trip)", ("@person:Karan Mehta",)))], [KARAN],
                      category="email_followup")
    assert grade(case, record(calls=[reuse_call("ag_karan_trip", "ask Karan")]), [KARAN], "full").passed


def test_create_slot_needs_its_person():
    rec = record(calls=[create_call("Email", "Tell Karan dinner moved to 9pm"),
                        create_call("Reminder", "Remind me at 8 PM")])
    assert not grade(KARAN_CASE, rec, [KARAN], "full").passed


@pytest.mark.parametrize("text", ["9pm", "9 pm", "9:00 PM", "9.00 pm", "9 p.m.", "21:00", "at 9", "9 o'clock",
                                  "9 o’clock", "move it to 9 instead", "9PM.", "at 9 to eat"])
def test_time_normalisation_accepts(text):
    assert mentions_time(f"Dinner is at {text}" if not text.startswith(("at", "move")) else text, "21:00"), text


@pytest.mark.parametrize("text", ["8pm", "9am", "9:30pm", "21:30", "at 9 people", "$9.00", "9 days", "19:00",
                                  "dinner for 9", "at 9, then 8pm", "2026-11-01T21:00", "09:00", "21.00"])
def test_time_normalisation_rejects(text):
    assert not mentions_time(text, "21:00"), text


def test_time_normalisation_other_forms():
    assert mentions_time("at noon", "12:00") and mentions_time("12pm", "12:00") and mentions_time("12am", "00:00")
    assert mentions_time("midnight", "00:00") and mentions_time("7:30am", "07:30") and mentions_time("12:30pm", "12:30")
    assert mentions_time("12.30pm", "12:30") and mentions_time("at 7.30pm", "19:30")
    assert mentions_time("09:00", "09:00") and mentions_time("9:00", "09:00") and mentions_time("9:00", "21:00")
    assert not mentions_time("12:30pm", "00:30") and not mentions_time("noon", "00:00")
    # a bare number counts only when it is the only time in the text
    assert mentions_time("remind me at 8", "20:00") and not mentions_time("at 8, after the 9pm call", "20:00")


# Partial ambiguity: "Ask Alice and Sam Rivera whether they're free for coffee next week."
ALICE_SAM = [WORLD.agents[a] for a in ("ag_chen_budget", "ag_park_dinner", "ag_m7s4pnzj", "ag_5f4xuzfg", "ag_ernemqtn")]
PARTIAL = multi_case(
    [Outcome("clarify"), dispatch(Slot("create", ("@person:Sam Rivera",)), ask=True)],
    ALICE_SAM, category="multi_person", clarify_should_name=["Alice Chen", "Alice Park"])
SAM = create_call("Coffee with Sam", "Ask Sam Rivera if he's free for coffee next week")


def g_partial(calls=(), user_messages=()):
    return grade(PARTIAL, record(calls=calls, user_messages=user_messages), ALICE_SAM, "full")


def test_partial_ambiguity_both_acceptable():
    asked = g_partial(user_messages=["Which Alice: Alice Chen or Alice Park?"])
    assert asked.passed and asked.outcome_kind == "clarify" and asked.clarify_named_ok
    res = g_partial([SAM, ask("Asked Sam. Which Alice do you mean?")])
    assert res.passed and res.outcome_kind == "dispatch" and "over_clarify" not in res.flags
    assert res.clarify_named_ok is False  # scored separately: the question named neither Alice in full
    by_email = create_call("Coffee", "Email sam.rivera@northwind.io about coffee next week")
    assert g_partial([by_email, ask("Which Alice?")]).passed


def test_partial_ambiguity_ack_is_not_a_question():
    assert not g_partial([SAM, ask("Done, I've asked Sam Rivera.")]).passed
    assert not g_partial(user_messages=["Done, I've asked Sam Rivera."]).passed
    assert not g_partial([SAM]).passed


def test_partial_ambiguity_dispatching_alice_fails():
    alice = create_call("Coffee with Alice", "Ask Alice Chen if she's free for coffee next week")
    for calls in ([SAM, alice, ask("Which Alice?")], [alice, ask("Which Alice?")], [alice]):
        assert not g_partial(calls).passed, calls
    res = g_partial([SAM, alice, ask("Which Alice?")])
    assert "ambiguous_dispatch" not in res.flags  # Alice Chen named in full: an extra dispatch, not ambiguous


def test_ambiguous_dispatch_fires():
    merged = create_call("Coffee", "Ask Sam Rivera and Alice whether they're free for coffee next week")
    res = g_partial([merged, ask("Which Alice?")])
    assert not res.passed and "ambiguous_dispatch" in res.flags
    ctx = create_call("Coffee", "Ask Sam Rivera if he's free for coffee next week (Alice may join)")
    assert "ambiguous_dispatch" in g_partial([ctx, ask("Which Alice?")]).flags
    clean = g_partial([SAM, ask("Which Alice?")])
    assert clean.passed and "ambiguous_dispatch" not in clean.flags
    emailed = create_call("Coffee", "Ask Sam Rivera if he's free; cc alice.park@gmail.com")
    assert "ambiguous_dispatch" not in g_partial([emailed, ask("Which Alice?")]).flags


SHARAN = AgentDef("ag_sharan", "Email Sharan re lunch", "Asked Sharan Rao about lunch on Friday.",
                  contacts=(Contact("sharan@x.io", "Sharan Rao", "to"),))
KHUSHI = AgentDef("ag_khushi", "Email Khushi re offsite", "Emailed Khushi Shah about the offsite.",
                  contacts=(Contact("khushi@y.io", "Khushi Shah", "to"),))
# "ask Sharan about lunch and tell Khushi I'm inviting him": Sharan has a lunch thread, Khushi doesn't
TWO_PEOPLE = multi_case([dispatch(Slot("reuse(ag_sharan)"), Slot("create", ("@person:Khushi Shah",)))],
                        [SHARAN, KHUSHI], category="multi_person")


def test_sharan_khushi_khushi_may_name_sharan():
    good = record(calls=[reuse_call("ag_sharan", "Ask him whether lunch is still on"),
                         create_call("Email Khushi", "Tell Khushi Shah I'm inviting Sharan Rao to lunch")])
    assert grade(TWO_PEOPLE, good, [SHARAN, KHUSHI], "full").passed


def test_multi_person_one_agent_for_both_is_merged():
    r = [SHARAN, KHUSHI]
    for calls in ([create_call("Lunch", "Ask Sharan Rao about lunch and tell Khushi Shah I'm inviting him")],
                  [reuse_call("ag_sharan", "Ask Sharan about lunch; also tell khushi@y.io I'm inviting him")]):
        res = grade(TWO_PEOPLE, record(calls=calls), r, "full")
        assert not res.passed and res.flags == {"merged_intents"}, calls
    only_sharan = grade(TWO_PEOPLE, record(calls=[reuse_call("ag_sharan", "Ask about lunch")]), r, "full")
    assert not only_sharan.passed and only_sharan.flags == {"dropped_intent"}


def test_multi_person_create_instead_of_reuse_is_duplicate():
    dup = record(calls=[create_call("Sharan", "Ask Sharan Rao about lunch"),
                        create_call("Khushi", "Tell Khushi Shah I'm inviting him")])
    res = grade(TWO_PEOPLE, dup, [SHARAN, KHUSHI], "full")
    assert not res.passed and "duplicate_create" in res.flags and "trigger_duplicate" not in res.flags


REMINDER_CASE = multi_case([dispatch(Slot("create", ("@person:Karan Mehta",)), Slot("reuse(ag_dinner_rem)"))],
                           [KARAN, DINNER_REMINDER])


@pytest.mark.parametrize("text", ["push the reminder to 7pm", "Update the schedule to 7pm", "Please reschedule to 7pm",
                                  "Change the time to 19:00", "Move to 7"])
def test_reuse_reminder_any_wording_fills(text):
    rec = record(calls=[create_call("Email", "Let Karan Mehta know dinner moved to 9pm"), reuse_call("ag_dinner_rem", text)])
    assert grade(REMINDER_CASE, rec, [KARAN, DINNER_REMINDER], "full").passed


def test_multi_intent_second_reminder_is_trigger_duplicate():
    r = [KARAN, DINNER_REMINDER]
    dup = record(calls=[create_call("Email", "Tell Karan Mehta dinner moved to 9pm"),
                        create_call("Dinner reminder 2", "Remind me at 8pm about dinner")])
    res = grade(REMINDER_CASE, dup, r, "full")
    assert not res.passed and {"duplicate_create", "trigger_duplicate"} <= res.flags


def test_reminder_dispatched_through_the_email_thread_is_merged():
    case = multi_case([dispatch(Slot("reuse(ag_karan_trip)"), Slot("create"))], [KARAN])
    rec = record(calls=[reuse_call("ag_karan_trip", "Tell Karan dinner is at 9pm and remind me at 8pm")])
    res = grade(case, rec, [KARAN], "full")
    assert not res.passed and res.flags == {"merged_intents"}


def test_multi_dispatch_legacy_mode():
    r = [SHARAN, KHUSHI]
    rec = record(calls=[ToolCall("send_message_to_agent", {"agent_name": "Email Sharan re lunch",
                                                           "instructions": "Ask about lunch"}),
                        ToolCall("send_message_to_agent", {"agent_name": "Invite Khushi",
                                                           "instructions": "Tell Khushi Shah I'm inviting Sharan"})],
                 mode="legacy")
    assert grade(TWO_PEOPLE, rec, r, "legacy").passed


def test_repeat_calls_to_one_target_count_once():
    rec = record(calls=[reuse_call("ag_sharan", "Ask Sharan Rao"), reuse_call("ag_sharan", "also lunch"),
                        create_call("K", "Email Khushi Shah")])
    assert grade(TWO_PEOPLE, rec, [SHARAN, KHUSHI], "full").passed


# ------------------------------------------------------ single-slot equivalence

def _battery(case, roster):
    """Records exercising the old reuse/create paths: oracle, baselines and mutations of the oracle."""
    o = oracle(case, roster)
    ranked = [a.id for a in sorted(roster, key=lambda a: (a.last_user_activity_days_ago, a.id))]
    yield o
    yield always_create(case, roster)
    yield always_ask(case, roster)
    yield always_reuse_top(case, roster, ranked)
    yield always_reuse_top(case, roster, ranked[1:])
    yield record(calls=o.calls + o.calls)
    yield record(calls=o.calls + [create_call("Extra", case.message)])
    yield record(calls=[ToolCall(c.name, {**c.args, "instructions": "do it"}) for c in o.calls])
    yield record(calls=[ToolCall("send_message_to_user", {"message": "On it"}), *o.calls])
    yield record(calls=[reuse_call(a.id, case.message + " " + (case.expect_person or "")) for a in case.required_agents])
    yield record(calls=[create_call(case.expect_person or "X", "go")])
    yield record(calls=[reuse_call("ag_nope", "x"), *o.calls])
    yield record(calls=[ToolCall("send_message_to_agent", {"agent_name": a.name, "instructions": c.args["instructions"]})
                        for c in o.calls for a in roster if a.id == c.args.get("agent_id")])


def _fields(gr):
    return (gr.passed, gr.outcome_kind, gr.person_ok, gr.clarify_named_ok, gr.set_recall, gr.set_precision,
            gr.structural, gr.flags)


def test_single_slot_equivalence():
    from evals.expand import expand

    cases = [c for c in expand(WORLD, load_cases(EX))
             if len(c.acceptable) == 1 and c.acceptable[0].kind in ("reuse", "create")]
    assert sum(c.source == "hand" for c in cases) == 7 and len(cases) >= 20
    checked = 0
    for case in cases:
        one_slot = replace(case, acceptable=[single_slot(case.acceptable[0], case.expect_person)])
        for n in (10, 300):
            r = roster_for(case, WORLD, n)
            for rec in _battery(case, r):
                for mode in ("full", "legacy"):
                    a, b = grade(case, rec, r, mode), grade(one_slot, rec, r, mode)
                    assert _fields(a) == _fields(b), (case.id, n, mode, rec.calls)
                    assert a.slots_total is None and b.slots_total == 1
                    checked += 1
    assert checked > 1000


def test_legacy_rules_dispatches_are_graded_by_name():
    roster = [agent("ag_a", "Email Alice"), agent("ag_b", "Email Alice"), agent("ag_c", "Remind me")]
    calls = [ToolCall("send_message_to_agent", {"agent_name": "Remind me", "instructions": "x"}),
             ToolCall("send_message_to_agent", {"agent_name": "Email Alice", "instructions": "y"})]
    for mode in ("legacy", "legacy_rules"):
        c = classify(calls, roster, mode)
        assert c.reused == {"ag_c"} and c.ambiguous_names == ["Email Alice"] and not c.invalid
    # id-based modes treat an agent_name call as invalid
    assert classify(calls, roster, "full").invalid


# ------------------------------------------------ Task F2: a text-only final reply is a user message
V1 = {c.id: c for c in load_cases(Path("evals/cases/v1"))}
BOTH_DANIELS = "Do you mean Daniel Walsh or Daniel Kaplan?"


def g_v1(rec: RunRecord, mode: str = "full"):
    case = V1["amb-person-006"]
    return grade(case, rec, roster_for(case, WORLD, 30), mode)


def test_text_only_final_reply_counts_as_clarify():
    res = g_v1(record(final_text=BOTH_DANIELS))
    assert res.passed and res.outcome_kind == "clarify" and res.clarify_named_ok is True


def test_final_text_ignored_when_user_messages_exist():
    res = g_v1(record(user_messages=["Which Daniel?"], final_text=BOTH_DANIELS))
    assert res.passed and res.outcome_kind == "clarify" and res.clarify_named_ok is False


def test_blank_final_text_is_still_none():
    for text in ("", "   \n"):
        res = g_v1(record(final_text=text))
        assert not res.passed and res.outcome_kind == "none"


def test_dispatch_plus_text_only_final_reply_stays_a_dispatch():
    res = g_v1(record(calls=[create_call("Email Daniel Walsh")], final_text=BOTH_DANIELS))
    assert not res.passed and res.outcome_kind == "create"


def test_text_only_final_reply_counts_in_legacy_mode():
    res = g_v1(record(final_text=BOTH_DANIELS, mode="legacy"), mode="legacy")
    assert res.passed and res.outcome_kind == "clarify" and res.clarify_named_ok is True


# --- clarify_named_ok accepts a surname (Task 16g) ---

def test_surname_only_question_names_both_candidates():
    res = g_v1(record(user_messages=["Which Daniel, Kaplan or Walsh?"]))
    assert res.passed and res.outcome_kind == "clarify" and res.clarify_named_ok is True


def test_mixed_full_name_and_surname_names_both_candidates():
    res = g_v1(record(user_messages=["Do you mean Daniel Kaplan or Walsh?"]))
    assert res.clarify_named_ok is True


def test_only_one_surname_is_not_enough():
    res = g_v1(record(user_messages=["Which Daniel, Kaplan?"]))
    assert res.clarify_named_ok is False


def test_surname_must_match_as_a_whole_word():
    res = g("amb-person-001", record(user_messages=["Which Alice? Alice Chen, or the one in the parking group?"]))
    assert res.clarify_named_ok is False  # "parking" is not "Park"


def test_surname_match_is_case_insensitive():
    res = g("amb-person-001", record(user_messages=["which alice, CHEN or park?"]))
    assert res.clarify_named_ok is True
