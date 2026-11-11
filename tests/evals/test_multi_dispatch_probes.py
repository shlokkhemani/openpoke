"""Regression inputs from the Task 5b review (/tmp/rev5b/r1, r2, r5): realistic IA instructions run
through the grader on the generated multi-dispatch cases at N=300. Ruling R23: slots are graded on
structure, so every correct wording passes and wording never decides a merge."""
from pathlib import Path

import pytest

from evals.expand import expand
from evals.grading import RunRecord, ToolCall, grade
from evals.schema import load_cases
from evals.world.roster import load_world, roster_for

WORLD = load_world(Path("evals/world/world.json"))
CASES = {c.id: c for c in expand(WORLD, load_cases(Path("evals/cases/examples")))}


def cr(name, ins):
    return ToolCall("send_message_to_agent", {"name": name, "instructions": ins})


def ru(aid, ins):
    return ToolCall("send_message_to_agent", {"agent_id": aid, "instructions": ins})


def say(msg):
    return ToolCall("send_message_to_user", {"message": msg})


def run(cid, calls):
    c = CASES[cid]
    r = roster_for(c, WORLD, 300)
    return grade(c, RunRecord("x", "full", 300, 0, list(calls), [], "", 0, 0, 0.0, 1, None), r, "full")


# ---- multi-intent-001: Kemal email (create) + dinner reminder (create)
R1 = "Set a reminder for 8pm tomorrow to leave for dinner"
E1 = "Email Kemal Kowalski that tomorrow's dinner has moved to 9pm"
KEMAL_EMAILS = [
    "Send Kemal Kowalski a note saying dinner tomorrow is now at 9pm",
    "Draft an email to kemal.kowalski@fastmail.com letting him know tomorrow's dinner moved to 9pm",
    "Reach out to Kemal Kowalski and tell him dinner tomorrow is now at 9pm",
    "Ping Kemal Kowalski: tomorrow's dinner has moved to 9pm",
    "Notify Kemal Kowalski that tomorrow's dinner is at 9pm now",
    "Email Kemal Kowalski: dinner tomorrow moved to 9 PM.",
    "Send an email to Kemal Kowalski (kemal.kowalski@fastmail.com) informing him tomorrow's dinner is now 9:00 PM",
    "Contact Kemal Kowalski to say tomorrow's dinner has been pushed to 9pm",
    "Shoot Kemal Kowalski a quick note that dinner tomorrow is at 9pm instead",
    "Send Kemal Kowalski a quick update that dinner tomorrow has moved to 21:00",
    "Compose and send to Kemal Kowalski: 'Hi Kemal, dinner tomorrow is moving to 9pm.'",
    "Let Kemal Kowalski know dinner tomorrow is now at 9pm",
    "Send a message to Kemal Kowalski: dinner tomorrow moved from 8 to 9pm",
    "Email Kemal Kowalski that dinner moved from 8pm to 9pm",
]
KEMAL_REMINDERS = [
    "Set a reminder for 8pm tomorrow to leave for dinner",
    "At 8pm tomorrow, nudge the user to leave for dinner",
    "Remind the user at 20:00 tomorrow to leave for dinner",
    "Create a one-time reminder: tomorrow 8:00 PM - leave for dinner",
    "Remind me tomorrow at 8 p.m. to leave for dinner",
    "Tomorrow at 8pm, notify the user that it's time to leave for dinner",
    "Schedule a reminder tomorrow at 8pm: time to leave for dinner",
    "Remind me at 8pm tomorrow to leave for 9pm dinner with Kemal Kowalski",
    "Remind the user at 8pm tomorrow to leave for dinner with Kemal Kowalski at 9pm. Let them know it's at 9pm.",
    "Message the user at 8pm tomorrow reminding them to leave for dinner with Kemal Kowalski at 9pm",
    "Send the user a reminder tomorrow at 8pm to leave for the 9pm dinner",
    "Set an alarm for 8pm tomorrow to leave for dinner",
    "Remind the user tomorrow evening at 8 to head out for dinner",
    "Set a reminder tomorrow at 8 tonight to leave for dinner",
]
KEMAL_MERGED = [
    "Email Kemal Kowalski that dinner moved to 9pm, and remind me at 8pm tomorrow to leave for dinner",
    "Tell Kemal Kowalski dinner is at 9pm tomorrow. Also set a reminder at 8pm to leave for dinner.",
    "Two things: 1) email kemal.kowalski@fastmail.com dinner is 9pm; 2) remind me at 20:00 to leave for dinner",
    "Notify Kemal Kowalski dinner moved to 9pm and create a reminder for 8pm to leave for dinner",
]


@pytest.mark.parametrize("email", KEMAL_EMAILS)
def test_kemal_email_wordings_pass(email):
    assert run("multi-intent-001", [cr("Email Kemal", email), cr("Dinner reminder", R1)]).passed


@pytest.mark.parametrize("reminder", KEMAL_REMINDERS)
def test_kemal_reminder_wordings_pass(reminder):
    assert run("multi-intent-001", [cr("Email Kemal", E1), cr("Dinner reminder", reminder)]).passed


@pytest.mark.parametrize("merged", KEMAL_MERGED)
def test_kemal_merged_alone_fails_merged_intents(merged):
    g = run("multi-intent-001", [cr("Kemal dinner", merged)])
    assert not g.passed and g.flags == {"merged_intents"}


def test_kemal_email_only_is_dropped():
    g = run("multi-intent-001", [cr("Email Kemal", E1)])
    assert not g.passed and g.flags == {"dropped_intent"}


# ---- multi-intent-002..006
E2 = "Tell Omar Underwood the user will be home Saturday morning to take delivery of the new monitor"
E3 = "Email Wendy Lindqvist and ask if she can water the plants while the user is away next week"
E4 = "Reply to Rafael Yilmaz confirming Tuesday at 3pm works for the dentist"
E5 = "Email Jamal Kowalski that Friday's team lunch is moving to 1pm"
PASSING = [
    *[("multi-intent-003", [cr("Email Wendy", E3), ru("ag_zwz6nrue", r)]) for r in (
        "Move this reminder to 7pm", "Change the reminder time to 7pm daily", "Update the schedule to 7pm instead of 6pm",
        "Please reschedule to 7pm", "Change the time to 19:00", "Shift the garbage bins reminder from 6pm to 7pm",
        "Reschedule the trash reminder to 7 PM going forward", "From now on remind the user at 7pm instead of 6pm")],
    *[("multi-intent-003", [cr("Email Wendy", e), ru("ag_zwz6nrue", "Move this reminder to 7pm")]) for e in (
        "Send Wendy Lindqvist a message asking if she could water the plants while I'm away next week",
        "Ask Wendy Lindqvist whether she can water my plants next week while I'm away",
        "Reach out to wendy.lindqvist@acme-corp.com to see if she can water the plants next week",
        "Draft a note to Wendy Lindqvist: could she water my plants while I'm away next week?",
        "Send Wendy Lindqvist a request to water my plants next week",
        "Check with Wendy Lindqvist if she can water the plants next week")],
    *[("multi-intent-004", [ru("ag_xawuqnhy", e), ru("ag_pwqhcleb", "Move this reminder to 6pm")]) for e in (
        E4, "Let Rafael Yilmaz know Tuesday at 3 PM works", "Confirm with Rafael Yilmaz that Tuesday 3pm works",
        "Tell Rafael Tuesday at 3pm works for the dentist", "Send Rafael Yilmaz a confirmation: Tuesday 15:00 is good",
        "Write back to Rafael Yilmaz: Tuesday at 3pm works for me", E4 + ". I'll get a reminder at 6pm.")],
    *[("multi-intent-004", [ru("ag_xawuqnhy", E4), ru("ag_pwqhcleb", r)]) for r in (
        "Change the reminder time to 6pm", "Move to 6pm", "Update the schedule to fire at 6 PM on weekdays",
        "Push the reminder to 18:00", "Move the dentist booking reminder from 5pm to 6pm",
        "Move this reminder to 6pm; the dentist appointment with Rafael Yilmaz is Tuesday at 3pm",
        "Move this reminder to 6pm and let the user know the appointment with Rafael Yilmaz is Tuesday 3pm")],
    *[("multi-intent-002", [ru("ag_c6obzuoh", E2), cr("Desk reminder", r)]) for r in (
        "Remind the user at 9:30am on Saturday to clear space on their desk",
        "Saturday 9:30 AM reminder: clear desk space for the monitor delivery",
        "Remind the user Saturday at 09:30 to clear the desk before Omar Underwood's delivery",
        "Remind the user Saturday at half past nine to clear space on the desk",
        "Message the user at 9:30am Saturday reminding them to clear the desk for Omar Underwood's delivery")],
    *[("multi-intent-002", [ru("ag_c6obzuoh", e), cr("Desk reminder", "Remind the user at 9:30am on Saturday")]) for e in (
        "Send Omar Underwood a note that I'll be home Saturday morning for the monitor delivery",
        "Reply to Omar Underwood: I'll be home Saturday morning to receive the replacement monitor",
        "Let Omar know I'll be home Saturday morning for the delivery",
        "Confirm with Omar Underwood that Saturday morning works for delivery")],
    *[("multi-intent-005", [cr("Email Jamal", E5), cr("Table reminder", r)]) for r in (
        "Remind the user at 12:30pm on Friday to book the table", "Remind the user Friday at 12:30 to book the table",
        "Remind the user on Friday at half twelve to book the table", "Remind the user Friday 12.30pm to reserve the table",
        "Remind the user on Friday at 12:30 PM to book a table for the team lunch at 1pm")],
    *[("multi-intent-005", [cr("Email Jamal", e), cr("Table reminder", "Remind the user at 12:30pm on Friday")]) for e in (
        "Email Jamal Kowalski that Friday's team lunch is now at 13:00",
        "Let Jamal Kowalski know the Friday team lunch moved to 1 o'clock",
        "Email Jamal Kowalski that Friday's team lunch moves to 1pm; a reminder is set for 12:30pm to book the table")],
    ("multi-intent-006", [cr("Email Greta", "Email Greta Silva asking if she can lend her bike pump this weekend"),
                          ru("ag_wyehdpnc", "Move this reminder to 8pm")]),
    # multi_person: context mentions of the other person are never merges
    ("multi-person-002", [cr("Lunch Colin", "Ask Colin Estrada if he's free for lunch on Thursday"),
                          cr("Lunch Carmen", "Ask Carmen Brennan if she's free for lunch on Thursday")]),
    ("multi-person-002", [cr("Lunch Colin", "Email Colin Estrada asking if he's free for lunch Thursday; Carmen Brennan is invited too"),
                          cr("Lunch Carmen", "Email Carmen Brennan asking if she's free for lunch Thursday; Colin Estrada is invited too")]),
    ("multi-person-002", [cr("Lunch Colin", "Email Colin Estrada asking if he's free for lunch Thursday with Carmen Brennan"),
                          cr("Lunch Carmen", "Ask Carmen Brennan if she's free for lunch on Thursday")]),
    ("multi-person-002", [cr("Lunch Colin", "Ask Colin Estrada if he's free to grab a bite Thursday midday"),
                          cr("Lunch Carmen", "Ask Carmen Brennan if she's free for lunch on Thursday")]),
    ("multi-person-001", [ru("ag_3w3vngdn", "Check whether Aaron Castillo has had a chance to look at the pitch document"),
                          cr("Plumber", "Ask Theo Brennan if he can recommend a good plumber")]),
    ("multi-person-001", [ru("ag_3w3vngdn", "Follow up with Aaron: has he looked at the pitch doc?"),
                          cr("Plumber", "Ask Theo Brennan for a plumbing recommendation")]),
    ("multi-person-004", [ru("ag_g2fqxn3g", "Follow up with Paloma Zielinski on the new hire setup"),
                          ru("ag_zwldc5g3", "Check whether Mateo Petrov has looked at the updated resume")]),
    # partial ambiguity
    ("multi-person-003", [say("Which Alice do you mean: Alice Chen or Alice Park?")]),
    ("multi-person-003", [cr("Coffee with Sam", "Ask Sam Rivera whether he's free for coffee next week"),
                          say("Which Alice do you mean: Alice Chen or Alice Park?")]),
    ("multi-person-003", [cr("Coffee with Sam", "Email sam.rivera@northwind.io asking if he's free for coffee next week"),
                          say("Which Alice?")]),
]
FAILING = [  # (case, calls, flag expected or None)
    ("multi-intent-003", [cr("Email Wendy", E3), cr("Trash 7pm", "Remind the user at 7pm to put the trash bins out")],
     "trigger_duplicate"),
    ("multi-intent-006", [cr("Email Greta", "Email Greta Silva asking about her bike pump"),
                          ru("ag_rhrccm3w", "Move this reminder to 8pm")], "wrong_reuse"),
    ("multi-person-002", [cr("Lunch", "Email Colin Estrada and Carmen Brennan asking if they're free for lunch Thursday")],
     "merged_intents"),
    ("multi-person-002", [ru("ag_jhev7ddl", "Ask Colin Estrada about lunch"), ru("ag_4x2pe36i", "Ask Carmen Brennan about lunch")],
     "wrong_reuse"),
    ("multi-person-001", [ru("ag_vuijx4e4", "Check whether Aaron Castillo has looked at the pitch document"),
                          cr("Plumber", "Ask Theo Brennan for a plumber")], "wrong_reuse"),
    ("multi-person-001", [cr("Two asks", "Check whether Aaron Castillo has looked at the pitch document and ask "
                                         "Theo Brennan for a plumber recommendation")], "merged_intents"),
    ("multi-person-004", [ru("ag_g2fqxn3g", "Follow up with Paloma Zielinski on the new hire setup and check whether "
                                            "Mateo Petrov looked at the CV")], "merged_intents"),
    ("multi-person-003", [cr("Coffee with Sam", "Ask Sam Rivera whether he's free for coffee next week")], None),
    ("multi-person-003", [cr("Coffee with Sam", "Ask Sam Rivera whether he's free for coffee next week"),
                          say("Done, I've asked Sam Rivera.")], None),
    ("multi-person-003", [cr("Coffee with Sam", "Ask Sam Rivera whether he's free for coffee next week"),
                          cr("Coffee Alice", "Ask Alice Chen if she's free for coffee next week"), say("Which Alice?")], None),
    ("multi-person-003", [cr("Coffee", "Ask Sam Rivera and Alice whether they're free for coffee next week"),
                          say("Which Alice?")], "ambiguous_dispatch"),
    ("multi-person-003", [ru("ag_m7s4pnzj", "Ask Sam Rivera whether he's free for coffee"), say("Which Alice?")],
     "wrong_reuse"),
]


@pytest.mark.parametrize("cid,calls", PASSING)
def test_realistic_correct_wordings_pass(cid, calls):
    g = run(cid, calls)
    assert g.passed and g.flags == set(), (cid, calls, g.flags)


@pytest.mark.parametrize("cid,calls,flag", FAILING)
def test_wrong_routing_fails(cid, calls, flag):
    g = run(cid, calls)
    assert not g.passed, (cid, calls)
    if flag:
        assert flag in g.flags, (cid, g.flags)


@pytest.mark.parametrize("merged", KEMAL_MERGED)
def test_merged_plus_separate_dispatch_is_not_caught(merged):
    """Known limit of structural grading (R23): a merged dispatch next to a separate dispatch for
    the same part fills both slots, so it passes. Recorded here so a change in this is deliberate."""
    assert run("multi-intent-001", [cr("Kemal dinner", merged), cr("Email Kemal", E1)]).passed
    assert run("multi-intent-001", [cr("Kemal dinner", merged), cr("Rem", R1)]).passed
