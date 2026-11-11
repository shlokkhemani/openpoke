"""Seeded generator for the one synthetic user the whole eval suite shares.

Run ``python -m evals.world.generate`` to (re)write ``evals/world/world.json``. Everything
random comes from ``random.Random`` instances derived from the seed: no global RNG, no
``hash()`` of strings, no wall clock, so the output is byte-identical across runs.
"""
from __future__ import annotations

import sys
from pathlib import Path

import random

from evals.schema import AgentDef, Contact, Trigger, load_cases
from evals.world.roster import World, save_world

SEED = 7
HERE = Path(__file__).parent
EXAMPLES = HERE.parent / "cases" / "examples"
WORLD_PATH = HERE / "world.json"

# Every contact in the example anchors (identity: lowercased email). Always in the pool.
FIXED_CONTACTS = (
    Contact("alice.chen@northwind.io", "Alice Chen", "to"),
    Contact("alice.park@gmail.com", "Alice Park", "to"),
    Contact("dana@maplerentals.com", "Dana Whitfield", "to"),
    Contact("maintenance@maplerentals.com", "Maple Rentals Maintenance", "to"),
    Contact("bob.martinez@northwind.io", "Bob Martinez", "to"),
)
# Required collisions beyond the anchors: two Sams, one person with two addresses.
COLLISION_CONTACTS = (
    Contact("sam.rivera@northwind.io", "Sam Rivera", "to"),
    Contact("sam.okafor@gmail.com", "Sam Okafor", "to"),
    Contact("priya.raman@northwind.io", "Priya Raman", "to"),
    Contact("priya.raman@gmail.com", "Priya Raman", "to"),
)
RESERVED_FIRST_NAMES = frozenset(c.display_name.split()[0] for c in FIXED_CONTACTS)

FIRST_NAMES = (
    "Aaron Amara Andre Beatriz Caleb Carmen Chloe Daniel Devon Elena Emil Farah Felix Gita Hana Hugo "
    "Imani Ivan Jamal Jasmine Jonas Josefina Kai Kemal Lena Liam Lucia Marcus Maya Mei Nadia Nikhil "
    "Noor Omar Owen Paloma Quinn Rafael Renee Ruth Sana Sergio Talia Theo Uma Vikram Wendy Xavier "
    "Yara Zane Tomas Ingrid Leila Mateo Greta Anil Colin Dmitri Esther Fiona Gabriel Helena Isaac"
).split()
LAST_NAMES = (
    "Abara Bianchi Castillo Dubois Eriksen Fontaine Gallagher Haddad Ibrahim Jankowski Kowalski Lindqvist "
    "Moreau Nakamura Okonkwo Petrov Quintero Rossi Sandoval Tanaka Underwood Vasquez Walsh Yilmaz Zielinski "
    "Brennan Choudhury Delgado Estrada Fitzgerald Grewal Hoffmann Iyer Johansson Kaplan Laurent Mbeki "
    "O'Brien Pereira Ramos Silva Torres Varga Weber Zhang"
).split()
DOMAINS = ("gmail.com", "northwind.io", "outlook.com", "fastmail.com", "acme-corp.com", "studiolune.co")
N_GENERATED_CONTACTS = 71  # 5 fixed + 4 collision + 71 = 80

CODE_ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
ID_ALPHABET = "abcdefghijklmnopqrstuvwxyz234567"

# ------------------------------------------------------------------ content pools

EMAIL_TOPICS = (  # (short name, what it was about, what came back)
    ("vendor contract", "the vendor contract redlines", "that legal is still reviewing it"),
    ("Q4 roadmap", "the Q4 roadmap draft", "that they will send comments by Thursday"),
    ("budget approval", "approval for the marketing budget", "that finance needs one more sign-off"),
    ("offer letter", "the signed offer letter", "that it arrived and looks fine"),
    ("conference travel", "booking travel for the conference", "that the flights are held until Friday"),
    ("kitchen quote", "the quote for the kitchen renovation", "that the revised number is coming tomorrow"),
    ("insurance claim", "the status of the insurance claim", "that an adjuster has been assigned"),
    ("tax documents", "the tax documents for last year", "that the accountant has what is needed"),
    ("project deadline", "moving the project deadline by a week", "that the new date works"),
    ("design review", "feedback on the design review slides", "that two slides need rework"),
    ("moving boxes", "borrowing the moving boxes", "that they can drop them off on Saturday"),
    ("contract renewal", "renewing the freelance contract", "that the renewal terms are attached"),
    ("onboarding checklist", "the onboarding checklist for the new hire", "that the laptop ships Monday"),
    ("invoice dispute", "the disputed invoice", "that the charge will be reversed"),
    ("wedding rsvp", "the RSVP for the wedding", "that a seat has been reserved"),
    ("dentist appointment", "rescheduling the dentist appointment", "that Tuesday at 3pm is open"),
    ("research paper", "comments on the research paper draft", "that the methods section needs detail"),
    ("car service", "booking the car service", "that the slot is confirmed"),
    ("team offsite", "the agenda for the team offsite", "that the venue is confirmed"),
    ("warranty replacement", "the warranty replacement for the monitor", "that a new unit will ship"),
    ("reference letter", "a reference letter for the grad program", "that the letter will be ready next week"),
    ("catering order", "the catering order for the launch party", "that the menu is locked in"),
    ("password reset", "the shared account password reset", "that access has been restored"),
    ("lab results", "the lab results appointment", "that the results are available in the portal"),
    ("security audit", "the security audit findings", "that remediation is underway"),
    ("price increase", "the announced price increase", "that the old rate holds until January"),
    ("podcast interview", "scheduling the podcast interview", "that the recording is set for next Wednesday"),
    ("flight change", "changing the return flight", "that the fare difference is small"),
    ("deposit refund", "the security deposit refund", "that the refund was processed"),
    ("parent-teacher meeting", "the parent-teacher meeting time", "that Thursday afternoon works"),
)
ONE_OFF_DOCS = (  # (doc, description phrase)
    ("slide deck", "the final slide deck"), ("resume", "an updated resume"),
    ("meeting notes", "the notes from yesterday's meeting"), ("expense report", "the expense report"),
    ("signed NDA", "the signed NDA"), ("project timeline", "the revised project timeline"),
    ("photos", "the photos from the weekend trip"), ("receipt", "the receipt for the equipment purchase"),
    ("w-9 form", "the completed W-9 form"), ("agenda", "the agenda for next week's call"),
    ("reading list", "the reading list"), ("budget sheet", "the household budget sheet"),
    ("invoice", "the freelance invoice"), ("proposal", "the draft proposal"),
    ("address", "the new mailing address"), ("recipe", "the lasagna recipe"),
    ("itinerary", "the trip itinerary"), ("press kit", "the press kit"),
    ("lease copy", "a copy of the lease"), ("transcript", "the transcript from the interview"),
)
SEARCH_TOPICS = (
    "the shipping delay", "the refund", "the conference schedule", "the new pricing", "the interview loop",
    "the apartment viewing", "the quarterly report", "the school form", "the flight confirmation",
    "the contract draft", "the birthday plans", "the tax return",
)
REMINDERS = (  # (subject, thing to do)
    ("Vitamins", "take their vitamins"), ("Water plants", "water the plants"), ("Stretch", "do a ten minute stretch"),
    ("Stand-up prep", "write notes for stand-up"), ("Pay rent", "pay the rent"), ("Backup", "run the laptop backup"),
    ("Journal", "write in their journal"), ("Medication", "take the evening medication"),
    ("Trash day", "put the trash bins out"), ("Gym", "pack the gym bag"), ("Inbox zero", "clear the inbox"),
    ("Call mom", "call their mother"), ("Language practice", "do the daily Spanish lesson"),
    ("Review PRs", "review open pull requests"), ("Expense receipts", "file the expense receipts"),
    ("Meal prep", "plan the week's meals"), ("Laundry", "start the laundry"), ("Read", "read for twenty minutes"),
    ("Update roadmap", "update the roadmap doc"), ("Check savings", "check the savings account"),
    ("Pet meds", "give the dog his medicine"), ("Timesheet", "submit the timesheet"),
    ("Car registration", "renew the car registration"), ("Domain renewal", "renew the domain name"),
    ("Passport", "check the passport expiry date"), ("Mom's birthday", "send a birthday gift to their mother"),
    ("Anniversary", "book a dinner for the anniversary"), ("Quarterly taxes", "pay the quarterly estimated taxes"),
    ("Dentist checkup", "book the dentist checkup"), ("Subscription audit", "review the monthly subscriptions"),
    ("Water filter", "replace the water filter"), ("Smoke alarm", "test the smoke alarms"),
    ("Insurance review", "review the insurance policies"), ("Weekly planning", "plan the week ahead"),
    ("Bike service", "take the bike in for service"), ("Standing desk", "reset the standing desk height"),
)
REMINDER_SCHEDULES = (
    "daily at 9pm", "daily at 9pm", "daily at 7am", "daily at 8am", "daily at 12pm", "daily at 6pm",
    "weekdays at 8pm", "weekdays at 9am", "weekdays at 5pm", "weekly on Monday at 8am",
    "weekly on Friday at 4pm", "weekly on Sunday at 6pm", "weekly on Wednesday at 10am",
    "monthly on the 1st at 9am", "monthly on the 15th at 9am", "yearly on March 3", "yearly on September 18",
)
# The general inbox / important-unread-emails recap is deliberately absent: it belongs to the
# anchor ag_nightly_digest, and a filler twin would be a second valid target at large N.
SUMMARY_SOURCES = (  # (label, what is summarised, payload noun)
    ("newsletter", "the newsletters that arrived", "newsletters"),
    ("calendar", "the upcoming calendar events", "upcoming calendar events"),
    ("GitHub", "the GitHub notification emails", "GitHub notifications"),
    ("expense", "the card and receipt emails", "receipt emails"),
    ("recruiting", "the recruiting email threads", "recruiting emails"),
    ("travel", "the travel confirmation emails", "travel confirmations"),
    ("support ticket", "the support ticket emails", "support ticket emails"),
    ("bank alert", "the bank and card alert emails", "bank alerts"),
    ("shipping", "the package and shipping updates", "shipping updates"),
    ("school", "the emails from the kids' school", "school emails"),
    ("receipt", "the purchase receipts", "purchase receipts"),
)
SUMMARY_SCHEDULES = (
    "daily at 9pm", "daily at 9pm", "daily at 7am", "daily at 6pm", "weekdays at 6pm", "weekdays at 8am",
    "weekly on Monday at 8am", "weekly on Friday at 5pm", "weekly on Sunday at 7pm", "monthly on the 1st at 9am",
)
PERIOD_DAYS = {"daily": 1, "weekdays": 1, "weekly": 7, "monthly": 30, "yearly": 365}

# Planted facts: one code-style kind per topic, so the sentence reads naturally for the agent
# ("Order ORD-48213 covers it." on a delivery, never an invoice on a GitHub digest).
# kind -> (token prefix, digit/code format, sentence templates)
FACT_KINDS = {
    "ticket": ("#Q-", "d5", ("Ticket #Q-{} was opened for it.", "Support case #Q-{} tracks it.")),
    "conf": ("CONF-", "code", ("The confirmation code is CONF-{}.", "Confirmation CONF-{} was issued.")),
    "order": ("ORD-", "d5", ("The order number is ORD-{}.", "Order ORD-{} covers it.")),
    "invoice": ("INV-", "d5", ("Invoice INV-{} is attached.", "The paperwork is filed under INV-{}.")),
    "pr": ("PR-", "d4", ("The pull request is PR-{}.", "See PR-{} for the change.")),
    "ref": ("REF-", "d5", ("Reference number REF-{} is on file.", "It is filed under reference REF-{}.")),
    "msg": ("MSG-", "d5", ("Thread MSG-{} holds the full exchange.", "The thread is saved as MSG-{}.")),
    "rem": ("RMD-", "d5", ("It is saved as reminder RMD-{}.", "The reminder id is RMD-{}.")),
    "digest": ("DGT-", "d5", ("The latest digest is DGT-{}.", "The most recent one is DGT-{}.")),
    "rx": ("RX-", "d6", ("The prescription number is RX-{}.", "Prescription RX-{} is on file.")),
}
# Topic key -> fact kind. Keys are the short name / doc / topic / subject / label used by the templates.
TOPIC_KIND = {
    # email threads (EMAIL_TOPICS)
    "vendor contract": "ref", "Q4 roadmap": "msg", "budget approval": "ref", "offer letter": "ref",
    "conference travel": "conf", "kitchen quote": "ref", "insurance claim": "ref", "tax documents": "ref",
    "project deadline": "msg", "design review": "msg", "moving boxes": "msg", "contract renewal": "ref",
    "onboarding checklist": "order", "invoice dispute": "invoice", "wedding rsvp": "conf",
    "dentist appointment": "conf", "research paper": "msg", "car service": "conf", "team offsite": "conf",
    "warranty replacement": "ticket", "reference letter": "msg", "catering order": "order",
    "password reset": "ticket", "lab results": "ref", "security audit": "ticket", "price increase": "ref",
    "podcast interview": "conf", "flight change": "conf", "deposit refund": "ref",
    "parent-teacher meeting": "conf",
    # one-off documents (ONE_OFF_DOCS)
    "slide deck": "msg", "resume": "msg", "meeting notes": "msg", "expense report": "ref", "signed NDA": "ref",
    "project timeline": "msg", "photos": "msg", "receipt": "order", "w-9 form": "ref", "agenda": "msg",
    "reading list": "msg", "budget sheet": "msg", "invoice": "invoice", "proposal": "msg", "address": "msg",
    "recipe": "msg", "itinerary": "conf", "press kit": "msg", "lease copy": "ref", "transcript": "msg",
    # inbox searches (SEARCH_TOPICS)
    "the shipping delay": "order", "the refund": "ref", "the conference schedule": "msg",
    "the new pricing": "msg", "the interview loop": "msg", "the apartment viewing": "conf",
    "the quarterly report": "ref", "the school form": "ref", "the flight confirmation": "conf",
    "the contract draft": "ref", "the birthday plans": "msg", "the tax return": "ref",
    # reminders (REMINDERS subjects); anything not listed is a plain reminder id
    "Review PRs": "pr", "Car registration": "ref", "Domain renewal": "ref", "Passport": "ref",
    "Quarterly taxes": "ref", "Insurance review": "ref", "Timesheet": "ref", "Expense receipts": "ref",
    "Pay rent": "ref", "Subscription audit": "ref", "Anniversary": "conf", "Dentist checkup": "conf",
    "Bike service": "conf", "Mom's birthday": "order", "Water filter": "order", "Medication": "rx",
    "Pet meds": "rx", "Vitamins": "rx",
    # summaries (SUMMARY_SOURCES labels); anything not listed is a plain digest id
    "GitHub": "pr", "support ticket": "ticket", "travel": "conf", "shipping": "order", "receipt": "order",
    "expense": "ref", "bank alert": "ref",
}


# ---------------------------------------------------------------------- helpers

def _first(c: Contact) -> str:
    return c.display_name.split()[0]


def _fact_kind(topic: str, default: str) -> str:
    return TOPIC_KIND.get(topic, default)


def _fact_value(rng: random.Random, fmt: str) -> str:
    if fmt == "code":
        return "".join(rng.choice(CODE_ALPHABET) for _ in range(6))
    return str(rng.randint(10 ** (int(fmt[1]) - 1), 10 ** int(fmt[1]) - 1))


def _make_fact(rng: random.Random, used: set[str], kind: str) -> str:
    """A fact sentence of the given kind with a not-yet-used token."""
    prefix, fmt, sentences = FACT_KINDS[kind]
    while True:
        v = _fact_value(rng, fmt)
        if prefix + v not in used:
            used.add(prefix + v)
            return rng.choice(sentences).format(v)


def _burn_legacy_fact_draws(rng: random.Random, used: set[str]) -> None:
    """Consume exactly the draws the pre-5c random-kind fact used to take from the filler stream.

    Facts now come from their own stream; replaying the old draws keeps every filler id, name,
    contact, timestamp and the filler order byte-identical to the world before the change.
    """
    codes = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"
    kinds = ("amount", "conf", "invoice", "ticket")
    kind = rng.choice(kinds)
    while True:
        if kind in ("ticket", "invoice"):
            v = str(rng.randint(10000, 99999))
        elif kind == "amount":
            v = f"{rng.randint(20, 9999):,}.{rng.randint(0, 99):02d}"
        else:
            v = "".join(rng.choice(codes) for _ in range(6))
        token = {"ticket": f"#Q-{v}", "invoice": f"INV-{v}", "amount": f"${v}", "conf": f"CONF-{v}"}[kind]
        if token not in used:
            used.add(token)
            rng.choice((0, 1))
            return
        kind = rng.choice(kinds)


def _agent_id(rng: random.Random, used: set[str]) -> str:
    while True:
        aid = "ag_" + "".join(rng.choice(ID_ALPHABET) for _ in range(8))
        if aid not in used:
            used.add(aid)
            return aid


def _activity(rng: random.Random) -> int:
    """Days since the user last touched the agent: recent bulk plus a long tail, 0..120."""
    if rng.random() < 0.55:
        return min(120, int(rng.expovariate(1 / 18)))
    return rng.randint(0, 120)


def _period(schedule: str) -> int:
    return PERIOD_DAYS[schedule.split()[0]]


def _schedule_phrase(schedule: str) -> str:
    kind, _, rest = schedule.partition(" ")
    if kind == "daily":
        return "every day " + rest
    if kind == "weekdays":
        return "every weekday " + rest
    if kind == "weekly":
        return "every " + rest.removeprefix("on ")
    if kind == "monthly":
        day, _, at = rest.removeprefix("on the ").partition(" at ")
        return f"on the {day} of every month at {at}"
    return "every year " + rest


def _cadence_word(schedule: str) -> str:
    kind = schedule.split()[0]
    if kind == "daily":
        return "Nightly" if schedule.endswith("pm") else "Morning"
    return {"weekdays": "Weekday", "weekly": "Weekly", "monthly": "Monthly", "yearly": "Yearly"}[kind]


def _trigger_uses(rng: random.Random, schedule: str, user_days: float) -> list[tuple[float, str]]:
    period = _period(schedule)
    kind = schedule.split()[0]
    if kind in ("daily", "weekdays"):
        last = rng.choice((0, 0, 0, 1)) if kind == "daily" else rng.randint(0, 3)
        runs = rng.randint(5, 8)
    elif kind == "weekly":
        last, runs = rng.randint(0, 6), rng.randint(3, 5)
    elif kind == "monthly":
        last, runs = rng.randint(0, 29), rng.randint(2, 3)
    else:
        last, runs = rng.randint(0, 364), 1
    return [(float(last + k * period), "trigger") for k in range(runs)]


# ------------------------------------------------------------------------- logs

def _pick_log(rng: random.Random, first: tuple[str, str], middle: list[tuple[str, str]], last: tuple[str, str]):
    c = rng.randint(3, 6)
    idx = sorted(rng.sample(range(len(middle)), c - 2))
    return [first] + [middle[i] for i in idx] + [last]


def _log_email(rng, instruction: str, contact: Contact, short: str, desc: str):
    e = contact.email
    mid = [
        ("agent_action", f"Drafting an email to {e}"),
        ("tool_response", f"GMAIL_CREATE_EMAIL_DRAFT: Draft created for {e}, subject: {short.capitalize()}"),
        ("agent_action", "Sending the draft"),
        ("tool_response", f"GMAIL_SEND_DRAFT: Message sent to {e}"),
        ("tool_response", f"GMAIL_FETCH_EMAILS: 1 new message from {e} in the thread"),
    ]
    return _pick_log(rng, ("agent_request", instruction), mid[:4], ("agent_response", desc))


def _log_search(rng, instruction: str, query: str, desc: str):
    mid = [
        ("agent_action", f"Searching the inbox for {query}"),
        ("tool_response", f"GMAIL_FETCH_EMAILS: {rng.randint(2, 9)} messages matched"),
        ("agent_action", "Reading the top matching threads"),
        ("tool_response", "GMAIL_FETCH_EMAILS: fetched message bodies for the top threads"),
    ]
    return _pick_log(rng, ("agent_request", instruction), mid, ("agent_response", desc))


def _log_trigger(rng, payload: str, desc: str, fetch: bool):
    mid = [("agent_action", "Trigger fired, starting the run")]
    if fetch:
        mid += [("agent_action", "Fetching recent emails"),
                ("tool_response", f"GMAIL_FETCH_EMAILS: {rng.randint(3, 40)} messages in range")]
    else:
        mid += [("agent_action", "Composing the reminder")]
    mid += [("agent_action", "Sending the message to the user"),
            ("tool_response", "send_message_to_user: delivered")]
    mid = mid[:4] if len(mid) > 4 else mid
    while len(mid) < 4:
        mid.append(("agent_action", "Checking the result"))
    return _pick_log(rng, ("agent_request", payload), mid, ("agent_response", desc))


# ---------------------------------------------------------------------- contacts

def _build_contacts(rng: random.Random, anchors: list[AgentDef]) -> list[Contact]:
    contacts = list(FIXED_CONTACTS) + list(COLLISION_CONTACTS)
    seen = {c.email.lower() for c in contacts}
    for a in anchors:  # anchors may bring contacts beyond the fixed list
        for c in a.contacts:
            if c.email.lower() not in seen:
                seen.add(c.email.lower())
                contacts.append(c)
    reserved_for_gen = {_first(c) for c in contacts} | {"Sam", "Priya"}
    firsts = [f for f in FIRST_NAMES if f not in reserved_for_gen]
    names: set[tuple[str, str]] = set()
    while len(names) < N_GENERATED_CONTACTS:
        names.add((rng.choice(firsts), rng.choice(LAST_NAMES)))
    for f, l in sorted(names):
        email = f"{f.lower()}.{l.lower().replace(chr(39), '')}@{rng.choice(DOMAINS)}"
        if email in seen:
            continue
        seen.add(email)
        contacts.append(Contact(email, f"{f} {l}", "to"))
    return contacts


# ------------------------------------------------------------------------ filler

def _user_uses(rng: random.Random, act: int, allow_agent: bool = True) -> list[tuple[float, str]]:
    uses = [(float(act), "user")]
    d = act
    for _ in range(rng.choice((0, 0, 1, 1, 2, 3))):
        d += rng.randint(1, 30)
        uses.append((float(d), "user"))
    if allow_agent and rng.random() < 0.06:
        uses.append((float(act + rng.randint(0, 20)), "agent"))
    return uses


def _finish(w: World, agent: AgentDef, log, uses):
    w.agents[agent.id] = agent
    w.logs[agent.id] = log
    w.uses[agent.id] = sorted(uses, key=lambda u: (u[0], u[1]))


def _user_facing(rng, w, aid, name, desc, contacts, log):
    act = _activity(rng)
    uses = _user_uses(rng, act)
    _finish(w, AgentDef(aid, name, desc, tuple(contacts), (), float(act), float(act)), log, uses)


def _trigger_agent(rng, w, aid, name, desc, schedule, payload, log):
    act = rng.randint(15, 120)
    uses = _trigger_uses(rng, schedule, act) + _user_uses(rng, act, allow_agent=False)[:2]
    status = "paused" if rng.random() < 0.06 else "active"
    last_run = min(d for d, _ in uses)
    _finish(w, AgentDef(aid, name, desc, (), (Trigger(schedule, payload, status),), float(act), last_run), log, uses)


def _generate_filler(rng: random.Random, w: World, pool: list[Contact], used_ids: set[str], n: int,
                     fact_rng: random.Random) -> list[str]:
    used_facts: set[str] = set()
    legacy_used: set[str] = set()

    def fact(topic: str, default: str) -> str:
        _burn_legacy_fact_draws(rng, legacy_used)
        return _make_fact(fact_rng, used_facts, _fact_kind(topic, default))
    made: list[str] = []
    n_threads, n_oneoff, n_search = round(n * 0.37), round(n / 6), round(n * 0.13)
    n_remind = round(n / 6)
    n_summ = n - n_threads - n_oneoff - n_search - n_remind
    sams = [c for c in pool if c.display_name.startswith("Sam ")]

    def new():
        aid = _agent_id(rng, used_ids)
        made.append(aid)
        return aid

    # Email threads. The first two are deliberate same-name duplicates ("Email Sam re vendor contract").
    for i in range(n_threads):
        short, core, reply = EMAIL_TOPICS[0] if i < 2 else rng.choice(EMAIL_TOPICS)
        c = sams[i] if i < 2 else rng.choice(pool)
        f = _first(c)
        name = f"Email {f} re {short}" if i < 2 else rng.choice(
            (f"Email {f} re {short}", f"Email {f} about {short}", f"Follow up with {f} on {short}"))
        contacts = [c]
        if rng.random() < 0.12:
            cc = rng.choice(pool)
            if cc.email != c.email:
                contacts.append(Contact(cc.email, cc.display_name, "cc"))
        desc = (f"Emailed {c.display_name} about {core}. {f} replied {reply}. "
                f"{fact(short, 'ref')}")
        log = _log_email(rng, f"Email {c.display_name} ({c.email}) about {core}.", c, short, desc)
        _user_facing(rng, w, new(), name, desc, contacts, log)

    for _ in range(n_oneoff):
        doc, phrase = rng.choice(ONE_OFF_DOCS)
        c = rng.choice(pool)
        f = _first(c)
        desc = f"Sent {c.display_name} {phrase}. {f} acknowledged it. {fact(doc, 'ref')}"
        log = _log_email(rng, f"Send {c.display_name} ({c.email}) {phrase}.", c, doc, desc)
        _user_facing(rng, w, new(), rng.choice((f"Send {f} the {doc}", f"Email {f} the {doc}")), desc, [c], log)

    for _ in range(n_search):
        topic = rng.choice(SEARCH_TOPICS)
        c = rng.choice(pool)
        f = _first(c)
        desc = (f"Searched the inbox for emails from {c.display_name} about {topic} and listed "
                f"{rng.randint(2, 9)} matches. {fact(topic, 'msg')}")
        log = _log_search(rng, f"Find emails from {c.display_name} about {topic}.", f"from:{c.email} {topic}", desc)
        _user_facing(rng, w, new(), f"Find emails from {f} about {topic.removeprefix('the ')}", desc, [c], log)

    for _ in range(n_remind):
        subject, thing = rng.choice(REMINDERS)
        sched = rng.choice(REMINDER_SCHEDULES)
        desc = f"Reminds the user {_schedule_phrase(sched)} to {thing}. {fact(subject, 'rem')}"
        payload = f"Remind the user to {thing}"
        _trigger_agent(rng, w, new(), f"{subject} reminder", desc, sched, payload,
                       _log_trigger(rng, payload, desc, fetch=False))

    for _ in range(n_summ):
        label, what, noun = rng.choice(SUMMARY_SOURCES)
        sched = rng.choice(SUMMARY_SCHEDULES)
        desc = (f"{_schedule_phrase(sched).capitalize()}, summarises {what} and sends the summary to "
                f"the user. {fact(label, 'digest')}")
        payload = f"Summarise the {noun}"
        _trigger_agent(rng, w, new(), f"{_cadence_word(sched)} {label} summary", desc, sched, payload,
                       _log_trigger(rng, payload, desc, fetch=True))
    return made


# ----------------------------------------------------------------------- anchors

def _add_anchor(rng: random.Random, w: World, a: AgentDef) -> None:
    if a.triggers:
        sched = a.triggers[0].schedule
        runs = [(float(a.last_run_days_ago or 0) + k * _period(sched), "trigger") for k in range(4)]
        log = _log_trigger(rng, a.triggers[0].payload, a.description, fetch=True)
        uses = runs + [(float(a.last_user_activity_days_ago), "user")]
    elif a.contacts:
        log = _log_email(rng, f"{a.name}.", a.contacts[0], a.name.lower(), a.description)
        uses = _user_uses(rng, int(a.last_user_activity_days_ago), allow_agent=False)
        uses[0] = (float(a.last_user_activity_days_ago), "user")
    else:
        log = _log_search(rng, f"{a.name}.", a.name.lower(), a.description)
        uses = [(float(a.last_user_activity_days_ago), "user")]
    _finish(w, a, log, uses)


def generate_world(seed: int = SEED, anchors: list[AgentDef] | None = None, n_filler: int = 300) -> World:
    anchors = list(anchors or [])
    w = World()
    w.contacts = _build_contacts(random.Random(f"{seed}:contacts"), anchors)

    anchor_rng = random.Random(f"{seed}:anchors")  # separate stream: filler never depends on anchors
    used_ids: set[str] = set()
    for a in anchors:
        if a.id not in w.agents:
            used_ids.add(a.id)
            _add_anchor(anchor_rng, w, a)

    reserved = set(RESERVED_FIRST_NAMES) | {_first(c) for a in anchors for c in a.contacts}
    pool = [c for c in w.contacts if _first(c) not in reserved]
    rng = random.Random(f"{seed}:filler")
    made = _generate_filler(rng, w, pool, used_ids, n_filler, random.Random(f"{seed}:facts"))
    rng.shuffle(made)
    w.filler_order = made
    return w


def example_anchors() -> list[AgentDef]:
    """Every required agent in evals/cases/examples, deduplicated by id."""
    out: dict[str, AgentDef] = {}
    for case in load_cases(EXAMPLES):
        for a in case.required_agents:
            out.setdefault(a.id, a)
    return list(out.values())


def main() -> int:
    w = generate_world(SEED, anchors=example_anchors())
    save_world(w, WORLD_PATH)
    print(f"wrote {WORLD_PATH}: {len(w.agents)} agents, {len(w.contacts)} contacts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
