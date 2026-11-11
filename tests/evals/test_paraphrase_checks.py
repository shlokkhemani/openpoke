import dataclasses
from pathlib import Path

from evals.expand import expand
from evals.paraphrase import check_paraphrase
from evals.schema import load_cases
from evals.world.roster import load_world

WORLD = load_world(Path("evals/world/world.json"))
CASES = expand(WORLD, load_cases(Path("evals/cases/examples")))
BY_ID = {c.id: c for c in CASES}


def test_ambiguous_check_rejects_added_surname():
    assert check_paraphrase(BY_ID["amb-person-001"], "Email Alice Chen about the offsite call", WORLD)


def test_ambiguous_check_rejects_added_email():
    assert check_paraphrase(BY_ID["amb-person-001"], "Email alice.park@gmail.com about the offsite call", WORLD)


def test_clear_person_check_rejects_dropped_surname():
    assert check_paraphrase(BY_ID["clear-person-001"], "Email Alice about the offsite call", WORLD)


def test_clear_person_accepts_email_instead_of_name():
    msg = "Write to alice.chen@northwind.io asking about an offsite planning call Thursday"
    assert check_paraphrase(BY_ID["clear-person-001"], msg, WORLD) == []


def test_valid_rewrite_passes():
    msg = "Could you ask Alice whether Thursday works for an offsite planning call?"
    assert check_paraphrase(BY_ID["amb-person-001"], msg, WORLD) == []


def test_new_person_rejected():
    msg = "Could you ask Alice and Dana whether Thursday works for an offsite planning call?"
    assert check_paraphrase(BY_ID["amb-person-001"], msg, WORLD)


def test_dropped_first_name_rejected():
    assert check_paraphrase(BY_ID["amb-person-001"], "Could you check whether she is free Thursday?", WORLD)


def test_pronoun_case_must_not_introduce_a_name():
    assert check_paraphrase(BY_ID["amb-person-004"], "Email Alice Chen about Thursday", WORLD)
    assert check_paraphrase(BY_ID["amb-person-004"], "Ask her whether she can do an offsite call on Thursday", WORLD) == []


def test_copied_description_wording_rejected():
    msg = "Please send Alice Chen the Q3 budget spreadsheet and asked for sign-off by Friday"
    assert check_paraphrase(BY_ID["clear-person-001"], msg, WORLD)


def test_numbers_must_be_preserved():
    trig = next(c for c in CASES if c.id == "trigger-001")
    assert check_paraphrase(trig, "Can you push my evening email recap to 9 instead?", WORLD)
    assert check_paraphrase(trig, "Could you move my evening email recap to 8 instead?", WORLD) == []


def test_empty_or_multiline_rejected():
    c = BY_ID["trigger-001"]
    assert check_paraphrase(c, "   ", WORLD)
    assert check_paraphrase(c, "Sure!\nMove my evening email recap to 8", WORLD)


TRIG = next(c for c in CASES if c.category == "trigger_management" and c.source == "template")


def _with(message):
    return dataclasses.replace(TRIG, message=message)


def test_cadence_change_rejected_weekday_to_every_day():
    c = _with("Pause the stand-up notes nudge that goes out every weekday at 6pm.")
    bad = c.message.replace("every weekday at 6pm", "every day at 6pm")
    assert check_paraphrase(c, bad, WORLD)
    assert check_paraphrase(c, c.message.replace("every weekday", "on weekdays"), WORLD) == []


def test_time_and_weekday_names_must_be_preserved():
    c = BY_ID["trigger-001"]  # example: "push ... to 8 instead"
    assert check_paraphrase(c, "Can you push my evening email recap to 8pm instead?", WORLD)
    t = _with("Turn off the bank alerts digest that goes out every Friday at 5pm.")
    assert check_paraphrase(t, t.message.replace("Friday", "Thursday"), WORLD)
    assert check_paraphrase(t, t.message.replace("5pm", "6pm"), WORLD)


def test_invented_person_rejected():
    c = BY_ID["amb-person-001"]
    assert check_paraphrase(c, "Could you ask Jordan whether Alice can do Thursday?", WORLD)
    assert check_paraphrase(c, "Could you ask Alice whether Priya Smith can join Thursday?", WORLD)
    assert check_paraphrase(c, "Jordan, can you ask Alice about the offsite call on Thursday?", WORLD)
    assert check_paraphrase(c, "Could you ask Alice whether Thursday works for an offsite planning call?", WORLD) == []


def test_sentence_initial_ordinary_word_not_flagged():
    c = BY_ID["amb-person-001"]
    assert check_paraphrase(c, "Please ask Alice if she is free Thursday for an offsite planning call.", WORLD) == []


# ------------------------------------------------------------ multi-dispatch cases (Task 5b)

KEMAL = next(c for c in CASES if c.category == "multi_intent" and "Kemal Kowalski" in c.message)
LUNCH = next(c for c in CASES if c.category == "multi_person" and "lunch" in c.message)
PARTIAL = next(c for c in CASES if c.category == "multi_person" and c.message.startswith("Ask Alice and Sam"))


def test_multi_intent_valid_rewrite_passes():
    msg = ("Can you let Kemal Kowalski know by email that dinner tomorrow is now at 9pm, and remind me at 8pm "
           "tomorrow to head out for dinner?")
    assert check_paraphrase(KEMAL, msg, WORLD) == []


def test_paraphrase_drops_second_request_rejected():
    msg = "Email Kemal Kowalski that tomorrow's dinner has moved from 8pm to 9pm."
    problems = check_paraphrase(KEMAL, msg, WORLD)
    assert any("request" in p for p in problems), problems


def test_paraphrase_times_and_reminder_cues():
    moved = KEMAL.message.replace("8pm", "7pm")
    assert check_paraphrase(KEMAL, moved, WORLD)  # times are kept by the number/schedule checks
    alarm = KEMAL.message.replace("set a reminder for me", "set an alarm for me")
    assert check_paraphrase(KEMAL, alarm, WORLD) == []  # still a reminder request


def test_paraphrase_multi_person_dropped_person_rejected():
    first = LUNCH.message.split(" and ")[0].removeprefix("Ask ")
    msg = f"Ask {first} if they're free for lunch on Thursday."
    assert check_paraphrase(LUNCH, msg, WORLD)


def test_paraphrase_partial_ambiguity_no_alice_surname():
    assert check_paraphrase(PARTIAL, PARTIAL.message.replace("Alice", "Alice Park"), WORLD)


# ------------------------------------------------- request and pronoun kept (Task 5c)

THANKS = BY_ID["amb-person-007"]  # "Tell her thanks, I'll take it from here." -> reuse
PRIYA = BY_ID["clear-person-004"]  # names Priya Raman, uses "they"


def test_amb_person_007_rewrite_that_drops_the_request_rejected():
    problems = check_paraphrase(THANKS, "Thanks for that, I've got it from here.", WORLD)
    assert any("request" in p for p in problems), problems
    assert any("pronoun" in p for p in problems), problems


def test_amb_person_007_faithful_rewrite_passes():
    assert check_paraphrase(THANKS, "Please let her know thanks, I'll handle it from here.", WORLD) == []


def test_request_rewritten_as_statement_rejected():
    assert check_paraphrase(PRIYA, "I wonder when they're next in town, Priya Raman.", WORLD)
    msg = "Could you message Priya Raman and ask when they are next in town?"
    assert check_paraphrase(PRIYA, msg, WORLD) == []


def test_pronoun_changed_rejected():
    assert check_paraphrase(THANKS, "Tell him thanks, I'll take it from here.", WORLD)
    assert check_paraphrase(THANKS, "Tell them thanks, I'll take it from here.", WORLD)
    assert check_paraphrase(PRIYA, "Can you message Priya Raman asking when she is next in town?", WORLD)


def test_pronoun_dropped_when_relied_on_rejected_but_named_person_may_drop_it():
    assert check_paraphrase(THANKS, "Tell Alice thanks, I'll take it from here.", WORLD)
    # amb-person-001 names Alice, so the pronoun is not what identifies her
    msg = "Could you ask Alice whether Thursday works for an offsite planning call?"
    assert check_paraphrase(BY_ID["amb-person-001"], msg, WORLD) == []


def test_dispatching_label_must_still_ask_for_something():
    c = BY_ID["followup-002"]  # reuse; "Look again for messages from Priya regarding the annual tax filing."
    assert check_paraphrase(c, "I looked at the Priya tax filing thread earlier.", WORLD)
    assert check_paraphrase(c, "Check again for messages from Priya about the annual tax filing.", WORLD) == []


# ------------------------------------------------- wider request detection (Task 5c fix round 1)

import pytest

FAITHFUL = [
    ("clear-person-002", "Have Sam Rivera check whether I can borrow a drill this weekend."),
    ("clear-person-002", "Hit up Sam Rivera about borrowing a drill this weekend."),
    ("clear-person-002", "Drop Sam Rivera a line asking if I can borrow a drill this weekend."),
    ("clear-person-006", "Reach out to Daniel Walsh to find out whether they're coming to the barbecue on Saturday."),
    ("amb-person-004", "Shoot her an email asking if she's free for an offsite planning call Thursday"),
    ("amb-person-007", "Mind pinging her to say thanks? I'll take it from here."),
    ("trigger-003", "Kill the nudge to look at my savings that goes out every weekday at 5pm."),
    ("trigger-003", "Drop the weekday 5pm nudge to look at my savings."),
    ("followup-004", "Chase Quinn Nakamura on the findings from the security review, I haven't heard anything."),
    ("newtask-002", "I'd love a recap of my Figma comments every weekday at 8am."),
    ("trigger-006", "Can this come an hour later?"),
    ("trigger-002", "I don't want these anymore."),
    ("trigger-002", "No more of these."),
    ("multi-person-002", "Are Colin Estrada and Carmen Brennan free for lunch on Thursday?"),
]


@pytest.mark.parametrize("case_id,rewrite", FAITHFUL)
def test_faithful_request_rewrites_pass(case_id, rewrite):
    case = next(c for c in load_cases(Path("evals/cases/v1")) + load_cases(Path("evals/cases/examples"))
                if c.id == case_id)
    assert check_paraphrase(case, rewrite, WORLD) == [], rewrite


def test_bare_please_does_not_make_a_request():
    bad = "Thanks to her, I will take it from here, please."
    assert check_paraphrase(THANKS, bad, WORLD)
    assert check_paraphrase(THANKS, "I need to go, thanks to her.", WORLD)


def test_identity_rewrite_passes_on_every_v1_case():
    for c in load_cases(Path("evals/cases/v1")):
        assert check_paraphrase(c, c.message, WORLD) == [], (c.id, c.message)


def test_possessive_of_known_name_and_added_pronoun_on_named_person_pass():
    c = BY_ID["clear-person-003"]
    assert check_paraphrase(c, "Write Elena Zielinski and ask if she has a couple of book recs.", WORLD) == []
    f = next(x for x in load_cases(Path("evals/cases/v1")) if x.id == "followup-002")
    assert check_paraphrase(f, "Have another look for Priya's emails about the annual tax filing.", WORLD) == []
