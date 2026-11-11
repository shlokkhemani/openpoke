"""Template-driven expansion of the hand-written examples into the v1 eval set (scope §1a).

``expand(world, examples, seed)`` fills category templates from the seeded world. Every generated
case is labelled by construction, and safe at every roster size N:

- if the answer depends on a person, every world agent linked to that person's contacts (and, for
  first-name cases, to any contact sharing the first name) is in ``required_agents``;
- a trigger target either has no same-label twin or is named by its schedule, with all twins
  required; no filler agent is a second valid target for the message.

All randomness comes from ``random.Random`` instances derived from ``seed`` (one per category), so
the output is byte-identical across runs and one category's templates never perturb another's.
"""
from __future__ import annotations

import random
import re
from dataclasses import dataclass
from typing import Optional, Sequence

from evals.schema import AgentDef, Case, Contact, Outcome, Slot, Turn, validate_cases
from evals.world.generate import (
    EMAIL_TOPICS, ONE_OFF_DOCS, REMINDERS, RESERVED_FIRST_NAMES, SEARCH_TOPICS, SUMMARY_SOURCES,
    _schedule_phrase,
)
from evals.world.roster import FACT_RE, World, roster_for

MAX_REQUIRED = 10
PREFIX = {
    "email_followup": "followup", "new_task_lookalike": "newtask", "ambiguous_person": "amb-person",
    "clear_person": "clear-person", "trigger_management": "trigger",
    "broad_question_person": "broad-person", "multi_person": "multi-person", "multi_intent": "multi-intent",
}

# --------------------------------------------------------------------- phrase tables
# Noun phrases that paraphrase a topic. None repeats a six-word run of the descriptions.

THREAD_PARA = {
    "vendor contract": ("the supplier agreement", "the contract markup from the vendor"),
    "Q4 roadmap": ("the plan for next quarter", "the roadmap comments"),
    "budget approval": ("the sign-off on the marketing spend", "the go-ahead for the ad budget"),
    "offer letter": ("the countersigned offer", "the job offer paperwork"),
    "conference travel": ("the trip to the conference", "travel arrangements for the conference"),
    "kitchen quote": ("the estimate for redoing the kitchen", "the price for the kitchen remodel"),
    "insurance claim": ("the claim with the insurer", "my coverage claim"),
    "tax documents": ("the paperwork for taxes", "last year's tax forms"),
    "project deadline": ("pushing the due date back a week", "the deadline extension"),
    "design review": ("the feedback on the design deck", "comments on the design slides"),
    "moving boxes": ("lending me the packing boxes", "the cardboard boxes for the move"),
    "contract renewal": ("extending the freelance agreement", "the freelance contract extension"),
    "onboarding checklist": ("the new hire's setup list", "getting the new employee set up"),
    "invoice dispute": ("the invoice we disagreed about", "the billing disagreement"),
    "wedding rsvp": ("the wedding invitation reply", "whether they have a seat at the wedding"),
    "dentist appointment": ("moving the dentist visit", "the dental appointment change"),
    "research paper": ("notes on the paper draft", "feedback on the research draft"),
    "car service": ("the car maintenance booking", "getting the car serviced"),
    "team offsite": ("the plan for the team retreat", "the offsite schedule"),
    "warranty replacement": ("the replacement monitor under warranty", "getting the screen replaced"),
    "reference letter": ("the recommendation letter for grad school", "the grad school recommendation"),
    "catering order": ("the food order for the launch party", "catering for the launch"),
    "password reset": ("getting back into the shared login", "access to the shared account"),
    "lab results": ("the medical test results", "the bloodwork appointment"),
    "security audit": ("what the security review found", "the findings from the security review"),
    "price increase": ("the rate hike", "the new higher price"),
    "podcast interview": ("booking the podcast recording", "the podcast guest slot"),
    "flight change": ("moving the flight home", "the rebooked return flight"),
    "deposit refund": ("getting the deposit back", "the returned deposit"),
    "parent-teacher meeting": ("the meeting with the teacher", "the school conference time"),
}
DOC_PARA = {
    "slide deck": ("the presentation", "the slides"),
    "resume": ("my updated CV", "the CV"),
    "meeting notes": ("the minutes from the call", "the write-up of the meeting"),
    "expense report": ("the expenses write-up", "the reimbursement report"),
    "signed NDA": ("the confidentiality agreement", "the non-disclosure form"),
    "project timeline": ("the new schedule for the project", "the revised plan dates"),
    "photos": ("the weekend trip pictures", "the pictures from the trip"),
    "receipt": ("the proof of purchase", "the equipment receipt"),
    "w-9 form": ("the W-9 paperwork", "the tax form I filled in"),
    "agenda": ("the plan for next week's call", "the call outline"),
    "reading list": ("the book list", "the list of things to read"),
    "budget sheet": ("the household spending spreadsheet", "the home budget spreadsheet"),
    "invoice": ("the bill for my freelance work", "my freelance bill"),
    "proposal": ("the proposal draft", "the pitch document"),
    "address": ("my new address", "the updated mailing details"),
    "recipe": ("the lasagna instructions", "the pasta recipe"),
    "itinerary": ("the travel plan for the trip", "the trip schedule"),
    "press kit": ("the media kit", "the press materials"),
    "lease copy": ("the copy of my lease", "the rental agreement copy"),
    "transcript": ("the interview write-up", "the written record of the interview"),
}
SEARCH_PARA = {
    "the shipping delay": ("the late delivery", "the delayed shipment"),
    "the refund": ("getting reimbursed", "the money back"),
    "the conference schedule": ("the conference agenda", "the session timetable"),
    "the new pricing": ("the updated rates", "the revised price list"),
    "the interview loop": ("the interview rounds", "the hiring process stages"),
    "the apartment viewing": ("the flat tour", "seeing the apartment"),
    "the quarterly report": ("the report for the quarter", "the quarter-end figures"),
    "the school form": ("the form from school", "the school paperwork"),
    "the flight confirmation": ("the booking confirmation for the flight", "the airline booking details"),
    "the contract draft": ("the draft agreement", "the agreement draft"),
    "the birthday plans": ("the party planning", "the birthday arrangements"),
    "the tax return": ("the filing for taxes", "the annual tax filing"),
}
REMINDER_PARA = {
    "Vitamins": ("the vitamins nudge", "my supplement reminder"),
    "Water plants": ("the plant watering ping", "the houseplant reminder"),
    "Stretch": ("the stretching prompt", "my stretch break reminder"),
    "Stand-up prep": ("the stand-up notes nudge", "the prompt to prep for stand-up"),
    "Pay rent": ("the rent payment reminder", "the nudge to pay rent"),
    "Backup": ("the laptop backup nudge", "the reminder to back up my laptop"),
    "Journal": ("the journaling prompt", "my diary reminder"),
    "Medication": ("the evening pills reminder", "my medication alert"),
    "Trash day": ("the garbage bins reminder", "the nudge about the trash"),
    "Gym": ("the gym bag reminder", "the reminder to pack for the gym"),
    "Inbox zero": ("the inbox cleanup nudge", "the reminder to empty my inbox"),
    "Call mom": ("the reminder to phone my mother", "the nudge to call my mom"),
    "Language practice": ("the Spanish lesson reminder", "the language study nudge"),
    "Review PRs": ("the pull request review reminder", "the code review nudge"),
    "Expense receipts": ("the receipts filing reminder", "the nudge to file my receipts"),
    "Meal prep": ("the meal planning reminder", "the weekly menu nudge"),
    "Laundry": ("the laundry nudge", "the washing reminder"),
    "Read": ("the reading time reminder", "the nudge to read"),
    "Update roadmap": ("the roadmap update nudge", "the reminder to refresh the roadmap doc"),
    "Check savings": ("the savings balance reminder", "the nudge to look at my savings"),
    "Pet meds": ("the dog medicine reminder", "the pet medication nudge"),
    "Timesheet": ("the timesheet reminder", "the hours submission nudge"),
    "Car registration": ("the vehicle registration reminder", "the nudge to renew the car's registration"),
    "Domain renewal": ("the domain expiry reminder", "the website domain renewal nudge"),
    "Passport": ("the passport expiry check", "the reminder about my passport"),
    "Mom's birthday": ("my mother's birthday gift reminder", "the nudge about mom's birthday"),
    "Anniversary": ("the anniversary dinner reminder", "the reminder to book our anniversary dinner"),
    "Quarterly taxes": ("the estimated tax payment reminder", "the quarterly tax nudge"),
    "Dentist checkup": ("the dentist booking reminder", "the nudge to schedule a checkup"),
    "Subscription audit": ("the subscriptions review reminder", "the nudge to review what I subscribe to"),
    "Water filter": ("the filter replacement reminder", "the nudge to swap the water filter"),
    "Smoke alarm": ("the smoke detector test reminder", "the nudge to test the alarms"),
    "Insurance review": ("the policy review reminder", "the insurance check-in nudge"),
    "Weekly planning": ("the weekly planning ritual reminder", "the nudge to plan my week"),
    "Bike service": ("the bike tune-up reminder", "the nudge to service the bike"),
    "Standing desk": ("the desk height reminder", "the standing desk nudge"),
}
SUMMARY_PARA = {
    "newsletter": ("the newsletter roundup", "my newsletters digest"),
    "calendar": ("the upcoming events digest", "my calendar rundown"),
    "GitHub": ("the GitHub notifications roundup", "my repo activity digest"),
    "expense": ("the card and receipts recap", "my spending email recap"),
    "recruiting": ("the recruiting roundup", "the recruiter emails digest"),
    "travel": ("the travel confirmations recap", "my trip bookings digest"),
    "support ticket": ("the support tickets roundup", "the helpdesk email digest"),
    "bank alert": ("the bank alerts digest", "my card alerts recap"),
    "shipping": ("the package updates digest", "my deliveries recap"),
    "school": ("the school emails recap", "the kids' school digest"),
    "receipt": ("the purchases recap", "my receipts digest"),
}
# Topics that would read as the same thread; a target needs a unique theme among a person's agents.
THEMES = {
    ("thread", "vendor contract"): "contract", ("thread", "contract renewal"): "contract",
    ("doc", "signed NDA"): "contract", ("search", "the contract draft"): "contract",
    ("thread", "budget approval"): "budget", ("doc", "budget sheet"): "budget",
    ("thread", "invoice dispute"): "invoice", ("doc", "invoice"): "invoice",
    ("thread", "conference travel"): "conference", ("search", "the conference schedule"): "conference",
    ("thread", "flight change"): "travel", ("doc", "itinerary"): "travel",
    ("search", "the flight confirmation"): "travel",
    ("thread", "deposit refund"): "refund", ("search", "the refund"): "refund",
    ("thread", "team offsite"): "agenda", ("doc", "agenda"): "agenda",
    ("thread", "price increase"): "pricing", ("search", "the new pricing"): "pricing",
    ("thread", "tax documents"): "tax", ("search", "the tax return"): "tax", ("doc", "w-9 form"): "tax",
    ("thread", "podcast interview"): "interview", ("doc", "transcript"): "interview",
    ("search", "the interview loop"): "interview",
    ("thread", "project deadline"): "project", ("doc", "project timeline"): "project",
    ("thread", "offer letter"): "letter", ("thread", "reference letter"): "letter",
    ("thread", "warranty replacement"): "warranty",
    ("doc", "receipt"): "receipt", ("doc", "expense report"): "receipt",
}
LABEL_GROUP = {"expense": "receipts", "receipt": "receipts"}  # summaries that cover the same mail

ASKS = (  # asks that match no world topic theme; {s}/{is}/{poss} take the person's pronoun
    "whether {is} free for coffee next week", "if {s} can recommend a good plumber",
    "whether I can borrow a drill this weekend", "for a couple of book recommendations",
    "if {is} coming to the barbecue on Saturday", "which restaurant {s} would suggest for a team dinner",
    "what the hiking guide was that {s} mentioned", "if {s} would like to join the running club on Sundays",
    "when {is} next in town", "if {s} can feed the cat while I'm away in March",
    "what time {poss} kids' recital starts", "whether {s} can introduce me to someone in sales",
    "whether I can borrow a ladder this weekend", "for the name of {poss} hairdresser",
)
PRONOUNS = {"they": {"s": "they", "is": "they're", "poss": "their"},
            "she": {"s": "she", "is": "she's", "poss": "her"},
            "he": {"s": "he", "is": "he's", "poss": "his"}}


def _ask(rng: random.Random, who: str = "they") -> str:
    return rng.choice(ASKS).format(**PRONOUNS[who])


NEW_SEARCH_TOPICS = ("the book club", "the cabin booking", "the garden fence", "the piano lessons",
                     "the school fundraiser", "the parking permit")
NEW_SOURCES = ("Slack mentions", "Jira ticket updates", "Figma comments", "Linear issues",
               "Notion page comments", "Substack posts")
NEW_WHENS = ("every Friday at 4pm", "every weekday at 8am", "every Sunday evening", "every morning at 7am",
             "once a week on Monday", "every Wednesday at noon")
NEW_REMINDERS = (  # (thing, filler reminder subject it resembles without being the same task)
    ("walk the dog", "Pet meds"), ("back up my phone photos", "Backup"),
    ("pay the credit card bill", "Pay rent"), ("call my sister", "Call mom"),
    ("check the tire pressure", "Car registration"), ("send the weekly team update", "Update roadmap"),
    ("renew the gym membership", "Gym"),
)
REMINDER_WHENS = ("every Saturday morning", "daily at 8am", "every Sunday at 6pm", "every weekday at 7am",
                  "on the 1st of every month")
NEW_TIMES = ("6am", "7:30am", "noon", "5pm", "8pm", "10pm")

NEUTRAL = (
    ("What's the weather like this weekend?", "Mostly sunny on Saturday, with showers likely on Sunday afternoon."),
    ("What's on my calendar tomorrow?", "A team lunch at noon and a one-on-one at 3:30."),
    ("How long is the flight from Vancouver to Toronto?", "About four and a half hours, nonstop."),
    ("Convert 20 miles to kilometres.", "20 miles is about 32 kilometres."),
    ("Thanks, that's all for now.", "You're welcome. I'm here if anything comes up."),
    ("Do I have anything on Friday afternoon?", "Nothing scheduled. Your calendar is clear after 1pm."),
    ("What day is the first of next month?", "It falls on a Monday."),
    ("Is it going to rain in Seattle tomorrow?", "Light rain in the morning, clearing by noon."),
)
GENDER = {"Elena": "she", "Farah": "she", "Helena": "she", "Daniel": "he", "Rafael": "he", "Sam": "they"}
OBJECT = {"they": "them", "she": "her", "he": "him"}


# --------------------------------------------------------------------------- indexes

@dataclass(frozen=True)
class _Topic:
    kind: str  # thread | doc | search
    key: str
    theme: str
    reply: str = ""

    def para(self, rng: random.Random) -> str:
        table = {"thread": THREAD_PARA, "doc": DOC_PARA, "search": SEARCH_PARA}[self.kind]
        return rng.choice(table[self.key])


def _topic(a: AgentDef) -> Optional[_Topic]:
    d = a.description
    if d.startswith("Emailed "):
        for short, core, reply in EMAIL_TOPICS:
            if f" about {core}. " in d:
                return _Topic("thread", short, THEMES.get(("thread", short), short), reply)
    elif d.startswith("Sent "):
        for doc, phrase in ONE_OFF_DOCS:
            if f" {phrase}. " in d:
                return _Topic("doc", doc, THEMES.get(("doc", doc), doc))
    elif d.startswith("Searched the inbox"):
        for topic in SEARCH_TOPICS:
            if f" about {topic} and " in d:
                return _Topic("search", topic, THEMES.get(("search", topic), topic))
    return None


@dataclass(frozen=True)
class _Trig:
    agent: AgentDef
    kind: str  # reminder | summary
    label: str
    group: str

    @property
    def schedule(self) -> str:
        return self.agent.triggers[0].schedule

    @property
    def status(self) -> str:
        return self.agent.triggers[0].status


def _trig(a: AgentDef) -> Optional[_Trig]:
    if not a.triggers:
        return None
    if a.name.endswith(" reminder") and a.name[:-9] in REMINDER_PARA:
        return _Trig(a, "reminder", a.name[:-9], a.name[:-9])
    if a.name.endswith(" summary"):
        label = a.name.split(" ", 1)[1].removesuffix(" summary")
        if label in SUMMARY_PARA:
            return _Trig(a, "summary", label, LABEL_GROUP.get(label, label))
    return None


class _Index:
    def __init__(self, world: World) -> None:
        self.world = world
        self.by_email: dict[str, list[AgentDef]] = {}
        for a in world.agents.values():
            for c in a.contacts:
                self.by_email.setdefault(c.email.lower(), []).append(a)
        self.by_first: dict[str, list[Contact]] = {}
        for c in world.contacts:
            self.by_first.setdefault(c.display_name.split()[0], []).append(c)
        self.trigs = [t for aid in world.filler_order if (t := _trig(world.agents[aid]))]

    def group(self, first: str) -> list[Contact]:
        return self.by_first[first]

    def group_agents(self, first: str) -> list[AgentDef]:
        seen: dict[str, AgentDef] = {}
        for c in self.by_first[first]:
            for a in self.by_email.get(c.email.lower(), []):
                seen[a.id] = a
        return sorted(seen.values(), key=lambda a: a.id)

    def person_agents(self, name: str) -> list[AgentDef]:
        seen: dict[str, AgentDef] = {}
        for c in self.by_first[name.split()[0]]:
            if c.display_name == name:
                for a in self.by_email.get(c.email.lower(), []):
                    seen[a.id] = a
        return sorted(seen.values(), key=lambda a: a.id)

    def single_person(self, first: str) -> bool:
        return len({c.display_name for c in self.by_first[first]}) == 1

    def has_cc(self, first: str) -> bool:
        emails = {c.email.lower() for c in self.by_first[first]}
        return any(c.role == "cc" and c.email.lower() in emails
                   for a in self.group_agents(first) for c in a.contacts)

    def people(self) -> list[str]:
        """Display names of contacts that are not example anchors, in world order."""
        out: list[str] = []
        for c in self.world.contacts:
            if c.display_name.split()[0] not in RESERVED_FIRST_NAMES and c.display_name not in out:
                out.append(c.display_name)
        return out


def _ref(idx: _Index, name: str, rng: random.Random) -> str:
    """How the user refers to a person: first name only if that identifies a single person."""
    first = name.split()[0]
    return first if idx.single_person(first) and rng.random() < 0.6 else name


# ----------------------------------------------------------------------- shared pieces

def _neutral(rng: random.Random, k: Optional[int] = None) -> list[Turn]:
    k = k or rng.choice((1, 1, 2))
    out: list[Turn] = []
    for u, a in rng.sample(NEUTRAL, k):
        out += [Turn("user", u), Turn("assistant", a)]
    return out


def _person_exchange(topic: _Topic, name: str, rng: random.Random) -> list[Turn]:
    first = name.split()[0]
    np_ = topic.para(rng)
    user = rng.choice((f"Did {name} get back about {np_}?", f"Any news from {name} on {np_}?",
                       f"What did {name} say about {np_}?"))
    asst = rng.choice((f"{first} replied {topic.reply}. Nothing else is needed from you right now.",
                       f"Yes. {first} wrote back {topic.reply}.",
                       f"Not much yet. {first} replied {topic.reply}."))
    return [Turn("user", user), Turn("assistant", asst)]


def _acts(agents: Sequence[AgentDef]) -> list[AgentDef]:
    return sorted(agents, key=lambda a: (a.last_user_activity_days_ago, a.id))


def _case(cid: str, category: str, split: str, severity: str, required: Sequence[AgentDef],
          history: list[Turn], message: str, acceptable: list[Outcome], **kw) -> Case:
    uniq = list({a.id: a for a in required}.values())
    if len(uniq) > MAX_REQUIRED:
        raise ValueError(f"{cid}: {len(uniq)} required agents exceeds {MAX_REQUIRED}")
    return Case(id=cid, category=category, split=split, source="template", severity=severity,
                required_agents=uniq, ia_history=history, message=message, acceptable=acceptable, **kw)


def _tail_ok(world: World, required: Sequence[AgentDef], target: AgentDef, tail: bool) -> bool:
    """Long-tail targets sit outside the 20 most recently used agents at N=100 and N=300."""
    stub = Case("x", "email_followup", "test", "template", "normal", list(required), [], "",
                [Outcome("reuse", (target.id,))])
    ranks = []
    for n in (100, 300):
        act = {a.id: a.last_user_activity_days_ago for a in roster_for(stub, world, n)}
        ranks.append(sum(1 for v in act.values() if v < act[target.id]))
    return min(ranks) >= 20 if tail else max(ranks) < 20


def _ids(prefix: str, examples: Sequence[Case]) -> int:
    nums = [int(m.group(1)) for c in examples if (m := re.fullmatch(rf"{re.escape(prefix)}-(\d+)", c.id))]
    return max(nums, default=0)


# ----------------------------------------------------------------------- email follow-up

FOLLOWUP_TEMPLATES = {
    "thread": ("Has {p} replied about {np} yet?", "Any word from {p} on {np}?",
               "What did {p} say about {np}?", "Can you nudge {p} about {np}? It's been a while.",
               "Check if {p} ever got back to me regarding {np}.",
               "Follow up with {p} on {np}, I haven't heard anything."),
    "doc": ("Did {p} ever confirm getting {np}?", "Has {p} acknowledged {np} yet?",
            "Check whether {p} saw {np} I sent.", "Remind {p} about {np} I sent over, please."),
    "search": ("Check my inbox again for anything new from {p} on {np}.",
               "Has {p} sent anything new in my inbox on {np}?", "Look again for messages from {p} regarding {np}."),
}


def _followups(idx: _Index, rng: random.Random, plan: Sequence[tuple[str, bool]], ids: "_Counter") -> list[Case]:
    world = idx.world
    pool: list[tuple[str, AgentDef, _Topic, list[AgentDef]]] = []
    for name in idx.people():
        first = name.split()[0]
        group = idx.group_agents(first)
        if idx.has_cc(first) or not 2 <= len(group) <= 8:
            continue
        topics = {a.id: _topic(a) for a in group}
        if any(t is None for t in topics.values()):
            continue
        for a in idx.person_agents(name):
            t = topics[a.id]
            if sum(topics[o.id].theme == t.theme for o in group) == 1:
                pool.append((name, a, t, group))
    rng.shuffle(pool)
    out: list[Case] = []
    used: set[str] = set()
    for split, tail in plan:
        for name, a, t, group in pool:
            if name in used:
                continue
            ok = _tail_ok(world, group, a, tail)
            if ok and tail and a.last_user_activity_days_ago <= min(g.last_user_activity_days_ago for g in group):
                ok = False  # long-tail targets are never the person's freshest agent
            if ok:
                break
        else:
            raise ValueError("no email_followup candidate left")
        used.add(name)
        msg = rng.choice(FOLLOWUP_TEMPLATES[t.kind]).format(p=_ref(idx, name, rng), np=t.para(rng))
        kind = "long-tail" if tail else "fresh"
        notes = (f"Reuse the {t.kind} agent '{a.name}'. The message names {name} and paraphrases the topic "
                 f"('{t.key}'); {name}'s other agents have different topics, so only the topic separates "
                 f"them ({kind}: user activity {a.last_user_activity_days_ago:g} days ago).")
        out.append(_case(ids.next(), "email_followup", split, "normal", group, _neutral(rng), msg,
                         [Outcome("reuse", (a.id,))], expect_person=name, notes=notes))
    return out


class _Counter:
    def __init__(self, prefix: str, start: int) -> None:
        self.prefix, self.n = prefix, start

    def next(self) -> str:
        self.n += 1
        return f"{self.prefix}-{self.n:03d}"


# ----------------------------------------------------------------------- new task, lookalike

def _newtasks(idx: _Index, rng: random.Random, plan: Sequence[tuple[str, str]], ids: _Counter) -> list[Case]:
    world = idx.world
    people = []
    for name in idx.people():
        first = name.split()[0]
        group = idx.group_agents(first)
        if not idx.has_cc(first) and 2 <= len(group) <= 7 and all(_topic(a) for a in group):
            people.append((name, group))
    rng.shuffle(people)
    used: set[str] = set()

    def person(need_search: bool = False):
        for name, group in people:
            if name in used or (need_search and not any(_topic(a).kind == "search" for a in group)):
                continue
            used.add(name)
            return name, group
        if need_search:
            return person()
        raise ValueError("no new_task_lookalike person left")

    summaries = [t for t in idx.trigs if t.kind == "summary"]
    reminders = [t for t in idx.trigs if t.kind == "reminder"]
    out: list[Case] = []
    for split, variant in plan:
        cid = ids.next()
        if variant == "email":
            name, group = person()
            ask = _ask(rng)
            msg = rng.choice((f"Email {{p}} and ask {ask}.", f"Can you write to {{p}} asking {ask}?",
                              f"Drop {{p}} a line and ask {ask}.")).format(p=_ref(idx, name, rng))
            out.append(_case(cid, "new_task_lookalike", split, "normal", group, _neutral(rng), msg,
                             [Outcome("create")], expect_person=name,
                             notes=f"Same person ({name}), brand-new thread: create, not a reuse of any of "
                                   f"their {len(group)} existing agents. Lookalikes share the contact."))
        elif variant == "search":
            name, group = person(need_search=True)
            topic = rng.choice(NEW_SEARCH_TOPICS)
            msg = rng.choice((f"Look through my inbox for anything {{p}} sent about {topic}.",
                              f"Search my email for messages from {{p}} about {topic}.")).format(p=_ref(idx, name, rng))
            out.append(_case(cid, "new_task_lookalike", split, "normal", group, _neutral(rng), msg,
                             [Outcome("create")], expect_person=name,
                             notes=f"A new inbox search about a topic none of {name}'s agents covers: create. "
                                   f"Keyword lookalikes: the person's existing agents, some of them searches."))
        elif variant == "summary":
            src, when = rng.choice(NEW_SOURCES), rng.choice(NEW_WHENS)
            msg = rng.choice((f"Can you send me a summary of my {src} {when}?",
                              f"Set up a digest of my {src} {when}.",
                              f"I want a recap of my {src} {when}.")
                             )
            look = [t.agent for t in rng.sample(summaries, 3)]
            out.append(_case(cid, "new_task_lookalike", split, "normal", look, _neutral(rng), msg,
                             [Outcome("create")],
                             notes=f"A recurring summary of a source no existing agent covers ({src}): create. "
                                   "Lookalikes are existing scheduled summaries sharing 'summary' and cadence."))
        else:  # reminder
            thing, resembles = rng.choice(NEW_REMINDERS)
            when = rng.choice(REMINDER_WHENS)
            msg = rng.choice((f"Remind me to {thing} {when}.", f"Can you set a reminder to {thing} {when}?",
                              f"Please nudge me to {thing} {when}."))
            like = [t.agent for t in reminders if t.label == resembles][:2] or [
                t.agent for t in rng.sample(reminders, 2)]
            like += [t.agent for t in rng.sample(reminders, 2)]
            out.append(_case(cid, "new_task_lookalike", split, "normal", like, _neutral(rng), msg,
                             [Outcome("create")],
                             notes=f"A new reminder ('{thing}') that resembles the existing '{resembles}' reminder "
                                   "only in vocabulary: create. Reusing a reminder agent would add a second duty to it."))
    return out


# ---------------------------------------------------------------------- ambiguous / clear

def _thread_agent(idx: _Index, contacts_name: str, rng: random.Random,
                  unique: bool = False, kinds: tuple[str, ...] = ("thread",)) -> tuple[AgentDef, _Topic]:
    group = idx.group_agents(contacts_name.split()[0])
    options = []
    for a in idx.person_agents(contacts_name):
        t = _topic(a)
        if t and t.kind in kinds and (
                not unique or sum((_topic(o) or t).theme == t.theme for o in group) == 1):
            options.append((a, t))
    if not options:
        raise ValueError(f"no thread agent for {contacts_name}")
    return rng.choice(options)


def _any_thread_agent(idx: _Index, names: Sequence[str], rng: random.Random,
                      unique: bool = False) -> tuple[str, AgentDef, _Topic]:
    for x in rng.sample(list(names), len(names)):
        try:
            return (x, *_thread_agent(idx, x, rng, unique))
        except ValueError:
            continue
    raise ValueError(f"no thread agent among {list(names)}")


def _colliding_names(idx: _Index, first: str) -> list[str]:
    return sorted({c.display_name for c in idx.group(first)})


AMB_FIRST = ("Can you email {f} and ask {ask}?", "Send {f} a quick message asking {ask}.",
             "Ask {f} {ask}, by email please.")
AMB_STATUS = ("Has {f} replied yet?", "Did {f} ever get back to me?", "Any word from {f}?",
              "Did {f} answer my email?")
AMB_PRONOUN = ("Email {o} and ask {ask}.", "Send {o} a note asking {ask}.", "Can you ask {o} {ask}?")
AMB_REPLY = ("Reply to {o} and say thanks, that works for me.", "Tell {o} thanks, I'll take it from here.",
             "Send {o} a quick thank-you.")


def _ambiguous(idx: _Index, rng: random.Random, plan: Sequence[tuple[str, str, str]], ids: _Counter) -> list[Case]:
    out: list[Case] = []
    for split, variant, first in plan:
        names = _colliding_names(idx, first)
        group = idx.group_agents(first)
        if len(names) < 2 or idx.has_cc(first):
            raise ValueError(f"{first} is not a clean collision set")
        who = GENDER.get(first, "they")
        o_ = OBJECT[who]
        ask = _ask(rng, who) if variant.startswith("pronoun") else _ask(rng)
        both = {"clarify_should_name": names}
        sev, cid = "high", ids.next()
        x, a, t = _any_thread_agent(idx, names, rng, unique=variant == "pronoun_reuse")
        about_x = _person_exchange(t, x, rng)
        if variant == "first":
            older = (about_x + _neutral(rng, 1)) if rng.random() < 0.5 else _neutral(rng)
            msg = rng.choice(AMB_FIRST).format(f=first, ask=ask)
            case = _case(cid, "ambiguous_person", split, sev, group, older, msg, [Outcome("clarify")], **both,
                         notes=f"First name only, and the last exchange doesn't name either {first}: ask before "
                               "any dispatch. Assume-and-proceed (or settling it by recency) fails.")
        elif variant == "status":
            msg = rng.choice(AMB_STATUS).format(f=first)
            case = _case(cid, "ambiguous_person", split, sev, group, _neutral(rng), msg, [Outcome("clarify")],
                         **both, notes=f"A status question about '{first}' with two people called {first}: "
                                       "answering for one of them, or reusing an agent, is a guess. Ask which one.")
        elif variant == "context":
            msg = rng.choice(AMB_FIRST).format(f=first, ask=ask)
            case = _case(cid, "ambiguous_person", split, sev, group, _neutral(rng, 1) + about_x, msg,
                         [Outcome("create")], expect_person=x,
                         notes=f"Exception to the first-name rule: the last exchange was about {x}, so {first} "
                               f"means {x}. A new ask, so create. Asking is over-clarification.")
        elif variant == "pronoun_create":
            msg = rng.choice(AMB_PRONOUN).format(o=o_, ask=ask)
            case = _case(cid, "ambiguous_person", split, sev, group, _neutral(rng, 1) + about_x, msg,
                         [Outcome("create")], expect_person=x,
                         notes=f"Pronoun only, no name: the last exchange was about {x}, so '{o_}' = {x}. "
                               "Create with no question. A guess by recency would pick the wrong person.")
        elif variant == "pronoun_reuse":
            reply = [Turn("agent", f"Update on {t.para(rng)}: {first} replied {t.reply}.", a.id, a.name),
                     Turn("assistant", f"{x} got back to you on that: {first} replied {t.reply}.")]
            msg = rng.choice(AMB_REPLY).format(o=o_)
            case = _case(cid, "ambiguous_person", split, sev, group, _neutral(rng, 1) + reply, msg,
                         [Outcome("reuse", (a.id,))], expect_person=x,
                         notes=f"The last exchange is the agent's own report ('{a.name}', with its id), so "
                               f"'{o_}' is {x} and the reply belongs in that thread: reuse it.")
        else:  # pronoun_clarify
            msg = rng.choice(AMB_PRONOUN).format(o=o_, ask=ask)
            case = _case(cid, "ambiguous_person", split, sev, group, about_x + _neutral(rng, 1), msg,
                         [Outcome("clarify")],
                         notes=f"Pronoun only, and the last exchange (not the earlier one about {x}) names no "
                               "one: nothing for the pronoun to resolve to, so ask who. No clarify_should_name: "
                               "the user may mean someone else entirely.")
        out.append(case)
    return out


def _clears(idx: _Index, rng: random.Random, plan: Sequence[tuple[str, str, Sequence[str]]], ids: _Counter) -> list[Case]:
    out: list[Case] = []
    asks = [a.format(**PRONOUNS["they"]) for a in rng.sample(ASKS, len(plan))]  # no ask used twice
    for (split, variant, prefs), ask in zip(plan, asks):
        cid = ids.next()
        built = None
        for name in prefs:
            first = name.split()[0]
            group = idx.group_agents(first)
            others = [n for n in _colliding_names(idx, first) if n != name]
            try:
                if variant == "create":
                    msg = rng.choice(("Email {p} and ask {ask}.", "Can you write to {p} asking {ask}?",
                                      "Send {p} a quick message asking {ask}.")).format(p=name, ask=ask)
                    built = _case(cid, "clear_person", split, "high", group, _neutral(rng), msg,
                                  [Outcome("create")], expect_person=name,
                                  notes=f"Full name given ({name}); another {first} exists, which is why this is a "
                                        "clear-person case: don't ask. A new ask, so create.")
                elif variant == "other_context":
                    y = others[0]
                    ya, yt = _thread_agent(idx, y, rng)
                    msg = rng.choice(("Email {p} and ask {ask}.", "Can you write to {p} asking {ask}?")
                                     ).format(p=name, ask=ask)
                    built = _case(cid, "clear_person", split, "high", group,
                                  _neutral(rng, 1) + _person_exchange(yt, y, rng), msg, [Outcome("create")],
                                  expect_person=name,
                                  notes=f"The last exchange was about {y}, but the message names {name} in full: "
                                        f"don't ask, and don't email {y}. A new ask, so create.")
                elif variant == "reuse":
                    a, t = _thread_agent(idx, name, rng, unique=True, kinds=("thread", "doc", "search"))
                    msg = rng.choice(("Any word from {p} on {np}?", "Has {p} replied about {np} yet?",
                                      "What did {p} say about {np}?")).format(p=name, np=t.para(rng))
                    built = _case(cid, "clear_person", split, "high", group, _neutral(rng), msg,
                                  [Outcome("reuse", (a.id,))], expect_person=name,
                                  notes=f"Full name ({name}) plus a topic that is unique among their agents: reuse "
                                        f"'{a.name}', don't ask which {first}.")
                else:  # two_addresses
                    msg = rng.choice(("Email {p} and ask {ask}.", "Can you message {p} asking {ask}?")
                                     ).format(p=name, ask=ask)
                    built = _case(cid, "clear_person", split, "high", group, _neutral(rng), msg,
                                  [Outcome("create")], expect_person=name,
                                  notes=f"{name} has two email addresses but is one person: don't ask which "
                                        "address or which person. A new ask, so create.")
            except (ValueError, IndexError):
                built = None
                continue
            break
        if built is None:
            raise ValueError(f"no clear_person candidate for {variant}: {prefs}")
        out.append(built)
    return out


# --------------------------------------------------------------------------- triggers

TRIGGER_TEMPLATES = {
    "time": ("Can you move {np}{sc} to {time}?", "Please change {np}{sc} so it comes at {time} instead.",
             "Could {np}{sc} arrive at {time} from now on?"),
    "pause": ("Pause {np}{sc} for a while, I'm away.", "Hold off on {np}{sc} until I say so.",
              "Turn off {np}{sc} for now."),
    "stop": ("Stop {np}{sc} altogether, I don't need it any more.", "Cancel {np}{sc}.",
             "I'm done with {np}{sc}, shut it off."),
    "resume": ("Turn {np}{sc} back on.", "Start sending {np}{sc} again."),
    "freq": ("Make {np}{sc} weekly instead of daily.", "Switch {np}{sc} to once a week instead."),
}
CONTEXT_MESSAGES = ("stop sending me these", "I don't want these any more", "cancel this one",
                    "pause these for a week please", "can you make this come an hour later?")


def _trigger_report(t: _Trig, rng: random.Random) -> list[Turn]:
    a = t.agent
    if t.kind == "reminder":
        payload = a.triggers[0].payload.removeprefix("Remind the user to ")
        text = "Reminder: " + payload.replace(" their ", " your ").replace("their ", "your ") + "."
    else:
        text = (f"Here's your {t.label} summary: {rng.randint(2, 9)} new items, nothing that needs "
                "an answer today.")
    return [Turn("agent", text, a.id, a.name), Turn("assistant", text)]


def _triggers(idx: _Index, rng: random.Random, plan: Sequence[tuple[str, str, Optional[str]]], ids: _Counter) -> list[Case]:
    world = idx.world
    trigs = [t for t in idx.trigs if t.label != "recruiting"]
    twins_of = {t.agent.id: [o for o in idx.trigs if o.group == t.group and o.kind == t.kind and o is not t]
                for t in trigs}
    # A target is separable from its same-label twins by schedule and, except for "resume" (only two
    # paused agents exist, both with same-name twins), by name: identical names would make the legacy
    # roster unreadable for reasons unrelated to roster size.
    pool = [t for t in trigs if len(twins_of[t.agent.id]) <= 3
            and all(o.schedule != t.schedule for o in twins_of[t.agent.id])]
    strict = {t.agent.id for t in pool if all(o.agent.name != t.agent.name for o in twins_of[t.agent.id])}
    rng.shuffle(pool)
    used: set[str] = set()
    out: list[Case] = []
    for split, variant, kind in plan:
        for t in pool:
            if t.agent.id in used or (kind and t.kind != kind):
                continue
            if variant != "resume" and t.agent.id not in strict:
                continue
            if variant == "resume" and t.status != "paused":
                continue
            if variant != "resume" and t.status != "active":
                continue
            if variant == "freq" and not t.schedule.startswith("daily"):
                continue
            break
        else:
            raise ValueError(f"no trigger candidate for {variant}/{kind}")
        used.add(t.agent.id)
        twins = twins_of[t.agent.id]
        hour = t.schedule.rsplit(" at ", 1)[-1]
        others = [o for o in trigs if o is not t and o not in twins]
        rng.shuffle(others)  # same time of day first, then same kind of trigger, then anything
        others.sort(key=lambda o: (not o.schedule.endswith(f" at {hour}"), o.kind != t.kind))
        extras = [o.agent for o in others]
        required = [t.agent] + [o.agent for o in twins] + extras[:2]
        named_by_schedule = bool(twins) or rng.random() < 0.3
        para = rng.choice((REMINDER_PARA if t.kind == "reminder" else SUMMARY_PARA)[t.label])
        sc = f" that goes out {_schedule_phrase(t.schedule)}" if named_by_schedule else ""
        history = _neutral(rng, 1)
        if variant == "context":
            msg = rng.choice(CONTEXT_MESSAGES)
            history = history + _trigger_report(t, rng)
            how = ("The message names nothing; only the conversation (the agent's own message, tagged with its "
                   "id) identifies the target.")
        else:
            time = rng.choice([x for x in NEW_TIMES if x != hour])
            msg = rng.choice(TRIGGER_TEMPLATES[variant]).format(np=para, sc=sc, time=time)
            how = (f"Named by topic{' and schedule' if sc else ''}; "
                   + (f"{len(twins)} same-label twin(s) on other schedules are required lookalikes."
                      if twins else "no same-label twin exists in the world."))
        notes = (f"Trigger '{variant}' on '{t.agent.name}' ({_schedule_phrase(t.schedule)}, "
                 f"{t.status}; user last touched it {t.agent.last_user_activity_days_ago:g} days ago, so recency "
                 f"misses it). {how} A wrong create duplicates the trigger.")
        out.append(_case(ids.next(), "trigger_management", split, "high", required, history, msg,
                         [Outcome("reuse", (t.agent.id,))], notes=notes))
    return out


# ------------------------------------------------------------------------- broad question

BROAD_TEMPLATES = ("What's going on with {p}?", "Give me a rundown of everything with {p}.",
                   "Where do things stand with {p} right now?", "Catch me up on all my threads with {p}.",
                   "Anything outstanding with {p}?", "What's the latest on everything involving {p}?")


def _broad(idx: _Index, rng: random.Random, plan: Sequence[str], ids: _Counter) -> list[Case]:
    cands = []
    for name in idx.people():
        first = name.split()[0]
        agents = idx.person_agents(name)
        group = idx.group_agents(first)
        if idx.has_cc(first) or not 3 <= len(agents) <= 7 or len(group) > 8:
            continue
        facts = {a.id: m.group(0) for a in agents if (m := FACT_RE.search(a.description))
                 and not m.group(0).startswith("$")}
        stale = max(a.last_user_activity_days_ago for a in agents) >= 25
        cands.append((len(agents) - len(facts), not stale, name, agents, group, facts))
    rng.shuffle(cands)
    cands.sort(key=lambda c: c[:2])
    out: list[Case] = []
    for split, (_, _, name, agents, group, facts) in zip(plan, cands):
        themes = {(_topic(a) or _Topic("", "", "")).theme for a in agents} - {""}
        linked = {a.id for a in group}
        distractor = next((a for aid in idx.world.filler_order if aid not in linked
                           and (a := idx.world.agents[aid]) and (t := _topic(a)) and t.theme in themes
                           and not any(c.display_name.split()[0] == name.split()[0] for c in a.contacts)), None)
        required = list(group) + ([distractor] if distractor else [])
        msg = rng.choice(BROAD_TEMPLATES).format(p=_ref(idx, name, rng))
        missing = len(agents) - len(facts)
        notes = (f"Broad question about {name}: cover all {len(agents)} agents linked to them"
                 + (f" (two addresses)" if len({c.email for c in idx.group(name.split()[0]) if c.display_name == name}) > 1 else "")
                 + f". Covered = messaged OR unique fact in the reply (code-style facts; {missing} agent(s) have "
                 f"no code fact and must be messaged). Oldest agent: "
                 f"{max(a.last_user_activity_days_ago for a in agents):g} days since the user's last activity."
                 + (f" Distractor: '{distractor.name}' shares a topic but not the person." if distractor else ""))
        out.append(_case(ids.next(), "broad_question_person", split, "normal", required, _neutral(rng), msg,
                         [Outcome("answer_set", tuple(a.id for a in _acts(agents)))],
                         unique_facts={aid: f for aid, f in facts.items()}, notes=notes))
    if len(out) < len(plan):
        raise ValueError("not enough broad_question_person candidates")
    return out


# ------------------------------------------------------------------- multi-dispatch turns
# Hand-worded specs (Siddharth reviews all 49 cases). Slots are structural (ruling R23): a target,
# plus @person on a create slot that starts a person's thread; no keywords or times. A spec slot
# with a person and no topic is a create naming them; with a topic, a reuse of their thread; with
# a reminder label, a reuse of that reminder; with nothing, a create (a new reminder).
# The generator resolves the agents, makes each
# named person's whole first-name group required (label safety, ruling R3), checks that every reuse
# target is the only one of its kind, and builds the slots.

@dataclass(frozen=True)
class _SlotSpec:
    person: Optional[str] = None    # full name: the slot's @person term
    topic: Optional[str] = None     # reuse this person's agent with this topic key
    reminder: Optional[str] = None  # reuse the reminder agent with this label


@dataclass(frozen=True)
class _MultiSpec:
    split: str
    message: str
    slots: tuple[_SlotSpec, ...]
    note: str
    ambiguous: Optional[str] = None  # a first name left ambiguous: ask, or dispatch the rest and ask
    reminder_lookalikes: tuple[tuple[str, Optional[str]], ...] = ()  # (label, schedule or None)
    topic_lookalikes: tuple[tuple[str, str], ...] = ()               # (person, topic key)


S = _SlotSpec
MULTI_PERSON = (
    _MultiSpec("test", "Can you check whether Aaron Castillo has had a chance to look at the pitch document, "
                       "and ask Theo Brennan if he can recommend a good plumber?",
               (S("Aaron Castillo", topic="proposal"), S("Theo Brennan")),
               "Two people, two agents: Aaron already has the thread for the proposal I sent him (reuse it); "
               "Theo has no thread about a plumber (create)."),
    _MultiSpec("test", "Ask Colin Estrada and Carmen Brennan if they're free for lunch on Thursday.",
               (S("Colin Estrada"), S("Carmen Brennan")),
               "The same question to two people, neither with a lunch thread: one new agent each, so a later "
               "'did Colin reply?' finds Colin's thread. Each agent may mention the co-invitee; a single "
               "agent emailing both (and no second dispatch) is merged_intents."),
    _MultiSpec("test", "Ask Alice and Sam Rivera whether they're free for coffee next week.",
               (S("Sam Rivera"),),
               "Partial ambiguity: Sam Rivera is named in full, 'Alice' could be Alice Chen or Alice Park. "
               "Either ask which Alice before dispatching anything, or create Sam's agent and ask about Alice; "
               "either way the question must say 'Alice' (an acknowledgement is not a question). A dispatch "
               "that uses 'Alice' without a surname is ambiguous_dispatch, and any agent for an Alice is an "
               "extra dispatch: both high-severity failures.", ambiguous="Alice"),
    _MultiSpec("test", "Follow up with Paloma Zielinski on getting the new employee set up, and check whether "
                       "Mateo Petrov has looked at my updated CV.",
               (S("Paloma Zielinski", topic="onboarding checklist"), S("Mateo Petrov", topic="resume")),
               "Two follow-ups, each on its person's existing thread: reuse both, one dispatch each. Sending "
               "both follow-ups through one thread (no second dispatch) is merged_intents."),
    _MultiSpec("dev", "Ask Liam Bianchi whether there's any news on the billing disagreement, and email Amara "
                      "Abara asking for the name of her hairdresser.",
               (S("Liam Bianchi", topic="invoice dispute"), S("Amara Abara")),
               "Liam's part continues his invoice thread (reuse); Amara's is a new ask (create)."),
    _MultiSpec("dev", "Ask Sam and Alice Chen if they'd like to join the running club on Sundays.",
               (S("Alice Chen"),),
               "Partial ambiguity the other way round: Alice Chen is named in full, 'Sam' could be Sam Rivera "
               "or Sam Okafor. Ask which Sam first, or create Alice Chen's agent and ask about Sam; the "
               "question must say 'Sam'. 'Sam' without a surname in a dispatch is ambiguous_dispatch.",
               ambiguous="Sam"),
)
MULTI_INTENT = (
    _MultiSpec("test", "Email Kemal Kowalski that tomorrow's dinner has moved to 9pm, and set a reminder for me "
                       "at 8pm tomorrow to leave for dinner.",
               (S("Kemal Kowalski"), S()),
               "An email and a reminder: two agents. Neither exists yet (Kemal's threads are about other "
               "things), so create both; one agent doing both is merged_intents. Reminder lookalikes share "
               "'dinner' or the evening hour.",
               reminder_lookalikes=(("Anniversary", None), ("Call mom", None))),
    _MultiSpec("test", "Tell Omar Underwood I'll be home on Saturday morning to take delivery of the new monitor, "
                       "and remind me at 9:30am on Saturday to clear space on my desk.",
               (S("Omar Underwood", topic="warranty replacement"),
                S()),
               "The email continues Omar's warranty thread (reuse); the one-off reminder is new (create), "
               "not a second duty for the standing desk reminders. Theo's warranty thread is the wrong person.",
               reminder_lookalikes=(("Standing desk", "daily at 9pm"), ("Standing desk", "weekdays at 5pm")),
               topic_lookalikes=(("Theo Brennan", "warranty replacement"),)),
    _MultiSpec("test", "Email Wendy Lindqvist and ask if she can water my plants while I'm away next week, and "
                       "move the garbage bins reminder to 7pm.",
               (S("Wendy Lindqvist"), S(reminder="Trash day")),
               "A new email to Wendy (create) and a change to the existing trash day reminder (reuse it; "
               "creating a second one is trigger_duplicate). Lookalikes: other 6pm reminders.",
               reminder_lookalikes=(("Gym", "daily at 6pm"), ("Medication", "daily at 6pm"))),
    _MultiSpec("test", "Let Rafael Yilmaz know that Tuesday at 3pm works for the dentist, and move the dentist "
                       "booking reminder to 6pm.",
               (S("Rafael Yilmaz", topic="dentist appointment"),
                S(reminder="Dentist checkup")),
               "Both parts have an agent already: Rafael's dentist thread and the dentist checkup reminder. "
               "Reuse both, one dispatch each.",
               reminder_lookalikes=(("Check savings", None), ("Standing desk", "weekdays at 5pm"))),
    _MultiSpec("dev", "Email Jamal Kowalski that Friday's team lunch is moving to 1pm, and remind me at 12:30pm "
                      "on Friday to book the table.",
               (S("Jamal Kowalski"), S()),
               "An email and a one-off reminder, both new: create two agents.",
               reminder_lookalikes=(("Anniversary", None), ("Water filter", "daily at 12pm"))),
    _MultiSpec("dev", "Email Greta Silva and ask if she can lend me her bike pump this weekend, and move my bike "
                      "tune-up reminder to 8pm.",
               (S("Greta Silva"), S(reminder="Bike service")),
               "A new email to Greta (create) and a change to the existing bike service reminder (reuse).",
               reminder_lookalikes=(("Call mom", None), ("Language practice", None))),
)
del S


def _topic_agent(idx: _Index, person: str, key: str) -> AgentDef:
    group = idx.group_agents(person.split()[0])
    hits = [a for a in idx.person_agents(person) if (t := _topic(a)) and t.key == key]
    if len(hits) != 1:
        raise ValueError(f"{person} has {len(hits)} agents on {key!r}")
    theme = _topic(hits[0]).theme
    if sum((_topic(o) or _Topic("", "", "")).theme == theme for o in group) != 1:
        raise ValueError(f"{person}'s {key!r} agent shares its theme with another agent of the group")
    return hits[0]


def _reminder_agent(idx: _Index, label: str, schedule: Optional[str] = None, *, sole: bool = False) -> AgentDef:
    hits = [t for t in idx.trigs if t.kind == "reminder" and t.label == label
            and (schedule is None or t.schedule == schedule)]
    if len(hits) != 1:
        raise ValueError(f"{len(hits)} reminder agents for {label!r} {schedule or ''}")
    if sole and any(t.group == hits[0].group and t.kind == "reminder" and t is not hits[0] for t in idx.trigs):
        raise ValueError(f"reminder {label!r} has a same-subject twin")
    return hits[0].agent


def _multi(idx: _Index, rng: random.Random, category: str, specs: Sequence[_MultiSpec], ids: _Counter) -> list[Case]:
    out: list[Case] = []
    for spec in specs:
        required: list[AgentDef] = []
        slots: list[Slot] = []
        parts: list[str] = []
        firsts = [sl.person.split()[0] for sl in spec.slots if sl.person] + ([spec.ambiguous] if spec.ambiguous else [])
        for first in firsts:
            required += idx.group_agents(first)
        for sl in spec.slots:
            if sl.topic:
                target = _topic_agent(idx, sl.person, sl.topic)
            elif sl.reminder:
                target = _reminder_agent(idx, sl.reminder, sole=True)
            else:
                target = None
            if target is not None:
                required.append(target)
                parts.append(f"reuse '{target.name}'")
                slots.append(Slot(f"reuse({target.id})"))
            else:
                parts.append(f"create naming {sl.person}" if sl.person else "create (the reminder)")
                slots.append(Slot("create", (f"@person:{sl.person}",) if sl.person else ()))
        required += [_reminder_agent(idx, label, sched) for label, sched in spec.reminder_lookalikes]
        required += [_topic_agent(idx, person, key) for person, key in spec.topic_lookalikes]
        kw: dict = {}
        if spec.ambiguous:
            dispatch = Outcome("dispatch", tuple(s.reuse_id for s in slots if s.reuse_id), tuple(slots), True)
            acceptable = [Outcome("clarify"), dispatch]
            kw["clarify_should_name"] = _colliding_names(idx, spec.ambiguous)
            if len(kw["clarify_should_name"]) < 2:
                raise ValueError(f"{spec.ambiguous} is not ambiguous")
        else:
            acceptable = [Outcome("dispatch", tuple(s.reuse_id for s in slots if s.reuse_id), tuple(slots), False)]
        severity = "high" if spec.ambiguous or any(sl.reminder for sl in spec.slots) else "normal"
        notes = (f"{spec.note} Slots: {'; '.join(parts)}. Graded on structure: one dispatch per slot, each "
                 "to its slot's target, a create naming its person (full name or email); wording is not graded.")
        out.append(_case(ids.next(), category, spec.split, severity, required, _neutral(rng), spec.message,
                         acceptable, notes=notes, **kw))
    return out


# ------------------------------------------------------------------------------ expand

def expand(world: World, examples: list[Case], seed: int = 7) -> list[Case]:
    """The examples plus 38 generated cases (22 test, 16 dev), all validated.

    Test: 4 per category except ``ambiguous_person`` (the five hand-written Alice examples); the
    11 examples are all test. Dev: 2 per category. The plans below pick the variants kept when the
    set was trimmed to 33 test / 16 dev (scope §1a): every variant shape survives in one split or
    the other, long-tail and fresh reuse targets are both kept, and every ambiguous first name has
    a clear_person case naming one of its people in full (ruling R9).
    """
    idx = _Index(world)

    def rng(cat: str) -> random.Random:
        return random.Random(f"{seed}:expand:{cat}")

    def ctr(cat: str) -> _Counter:
        return _Counter(PREFIX[cat], _ids(PREFIX[cat], examples))

    cases = list(examples)
    T, D = "test", "dev"
    cases += _followups(idx, rng("email_followup"),
                        [(T, True), (T, True), (T, False), (D, True), (D, False)], ctr("email_followup"))
    cases += _newtasks(idx, rng("new_task_lookalike"),
                       [(T, "summary"), (T, "reminder"), (T, "search"), (D, "email"), (D, "reminder")],
                       ctr("new_task_lookalike"))
    cases += _ambiguous(idx, rng("ambiguous_person"),
                        [(D, "status", "Daniel"), (D, "pronoun_reuse", "Farah")], ctr("ambiguous_person"))
    cases += _clears(idx, rng("clear_person"),
                     [(T, "create", ("Sam Rivera",)), (T, "other_context", ("Elena Zielinski", "Elena Sandoval")),
                      (T, "two_addresses", ("Priya Raman",)),
                      (D, "reuse", ("Farah Moreau", "Rafael Yilmaz", "Elena Zielinski")),
                      (D, "create", ("Daniel Walsh", "Daniel Kaplan"))],
                     ctr("clear_person"))
    cases += _triggers(idx, rng("trigger_management"),
                       [(T, "stop", "reminder"), (T, "resume", None), (D, "time", "summary"),
                        (D, "context", "reminder")], ctr("trigger_management"))
    cases += _broad(idx, rng("broad_question_person"), [T] * 3 + [D] * 2, ctr("broad_question_person"))
    cases += _multi(idx, rng("multi_person"), "multi_person", MULTI_PERSON, ctr("multi_person"))
    cases += _multi(idx, rng("multi_intent"), "multi_intent", MULTI_INTENT, ctr("multi_intent"))

    problems = validate_cases(cases)
    if problems:
        raise ValueError("generated set failed validation:\n" + "\n".join(problems))
    return cases
