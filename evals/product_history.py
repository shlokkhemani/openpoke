"""Replace off-product chatter in a case's history with agent-backed exchanges (case set v2).

``productize(case, world, key)`` swaps every off-product user line (weather, calendar, flights, unit
conversion) and the assistant reply after it for one exchange backed by a *context agent*: a world
filler that neither names anyone nor touches any topic the case is about, so labels stay valid.
Pure and deterministic: one ``random.Random(f"v2:{key}")`` per call, no I/O.

Word rules (used by the guards on candidate agents and on their generated text):
- person words: whole words, case-insensitive, of every first name and surname of the required agents'
  contacts, ``clarify_should_name`` and ``expect_person``, plus those contacts' emails;
- content words: lowercase runs of 4+ letters not in ``STOP`` (a small list of function words and of
  the words the templates themselves contain, e.g. "update", "replied"). A candidate must share no
  content word with the case's message / original message, the required agents' topic key and theme,
  or trigger label and group.
"""
from __future__ import annotations

import dataclasses
import random
import re
from typing import Optional

from evals.expand import MAX_REQUIRED, _Index, _topic, _trig, _trigger_report
from evals.schema import AgentDef, Case, Turn, validate_cases
from evals.world.roster import World

OFF_PRODUCT = frozenset({
    "What's the weather like this weekend?",
    "Is it going to rain in Seattle tomorrow?",
    "How long is the flight from Vancouver to Toronto?",
    "Convert 20 miles to kilometres.",
    "What's on my calendar tomorrow?",
    "Do I have anything on Friday afternoon?",
    "Thanks. Also, what's on my calendar tomorrow?",
})
GENERIC_KEPT = frozenset({"Thanks, that's all for now.", "What day is the first of next month?"})
LEADS = {
    "summary": ("Anything new in my inbox?", "Did anything come in overnight?", "Any updates I should know about?"),
    "reminder": ("Did any of my reminders go off?", "Anything I need to do today?", "What's on my plate today?"),
}
THANKS = (Turn("user", "Thanks, that's all for now."), Turn("assistant", "You're welcome. I'm here if anything comes up."))

STOP = frozenset("""this that with from have your what about when where which would could should their there
them they then than will into over also just some more most only very each both been being does done
update updates reminder reminders summary summaries replied reply news any anything again still ever""".split())


def _content(s: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{4,}", s.lower()) if w not in STOP}


def _words(s: str) -> set[str]:
    return set(re.findall(r"[a-z0-9']+", s.lower().replace("’", "'")))


def _case_people(case: Case) -> tuple[set[str], set[str]]:
    people = {c.display_name for a in case.required_agents for c in a.contacts}
    people |= set(case.clarify_should_name)
    if case.expect_person:
        people.add(case.expect_person)
    names = {w.lower() for n in people for w in n.split()}
    emails = {c.email.lower() for a in case.required_agents for c in a.contacts}
    return names, emails


def _case_topic_words(case: Case) -> set[str]:
    words = _content(case.message) | _content(case.original_message or "")
    for a in case.required_agents:
        t, g = _topic(a), _trig(a)
        if t:
            words |= _content(t.key) | _content(t.theme)
        if g:
            words |= _content(g.label) | _content(g.group)
    return words


def _off_pairs(history: list[Turn]) -> list[tuple[int, int]]:
    """(start, length) of each off-product user turn with the assistant turn right after it."""
    out = []
    for i, t in enumerate(history):
        if t.role == "user" and t.text in OFF_PRODUCT:
            out.append((i, 2 if i + 1 < len(history) and history[i + 1].role == "assistant" else 1))
    return out


def productize(case: Case, world: World, key: str) -> Case:
    pairs = _off_pairs(case.ia_history)
    if not pairs:
        return case
    rng = random.Random(f"v2:{key}")
    lead_rng = random.Random(f"v2:{key}:lead")  # separate stream: leads never shift agent choices
    idx = _Index(world)
    names, emails = _case_people(case)
    topic = _case_topic_words(case)
    required = {a.id for a in case.required_agents}
    used_ids: set[str] = set()
    used_people: set[str] = set()
    budget = MAX_REQUIRED - len(case.required_agents)
    n_thanks = max(0, len(pairs) - budget)

    def ok_text(agent: AgentDef, turns: list[Turn]) -> bool:
        text = " ".join(t.text for t in turns) + " " + agent.name
        if _words(text) & names or any(e in text.lower() for e in emails):
            return False
        return not (_content(text) & topic)

    def attempt(shape: str, pool: list[AgentDef]) -> Optional[tuple[AgentDef, list[Turn]]]:
        cands = []
        for a in pool:
            if a.id in used_ids:
                continue
            if shape == "trigger":
                if _trig(a) is None:
                    continue
            else:
                tp = _topic(a)
                if tp is None or tp.kind != "thread" or not a.contacts:
                    continue
            if any(c.email.lower() in emails or {w.lower() for w in c.display_name.split()} & names
                   or c.display_name.lower() in used_people for c in a.contacts):
                continue
            cands.append(a)
        while cands:
            a = rng.choice(cands)
            cands.remove(a)
            if shape == "trigger":
                g = _trig(a)
                turns = _trigger_report(g, rng)
                leads = [x for x in lead_rng.sample(LEADS[g.kind], len(LEADS[g.kind]))
                         if not (_words(x) & names) and not (_content(x) & topic)]
                if not leads:
                    raise ValueError(f"{case.id}: no lead for trigger report of {a.id}")
                turns = [Turn("user", leads[0])] + turns
            else:
                tp = _topic(a)
                name = a.contacts[0].display_name
                first = name.split()[0]
                np_ = tp.para(rng)
                turns = [Turn("user", f"Any news from {name} on {np_}?"),
                         Turn("agent", f"Update on {np_}: {first} replied {tp.reply}.", a.id, a.name),
                         Turn("assistant", f"{first} replied {tp.reply}.")]
            if ok_text(a, turns) and not (_content(a.name) & topic):
                return a, turns
        return None

    pool = [world.agents[i] for i in world.filler_order if i not in required]
    new_history: list[Turn] = []
    context: list[AgentDef] = []
    pos = 0
    for n, (start, length) in enumerate(pairs):
        new_history += case.ia_history[pos:start]
        pos = start + length
        if n < n_thanks:
            new_history += THANKS
            continue
        if case.category == "ambiguous_person":
            shapes = ["trigger"]
        elif case.category == "trigger_management":
            shapes = ["email"]
        else:
            shapes = ["email", "trigger"]
            if rng.random() < 0.5:
                shapes.reverse()
        got = None
        for shape in shapes:
            got = attempt(shape, pool)
            if got:
                break
        if got is None:
            raise ValueError(f"{case.id}: no context agent for pair {n}")
        agent, turns = got
        used_ids.add(agent.id)
        used_people |= {c.display_name.lower() for c in agent.contacts}
        context.append(agent)
        new_history += turns
    new_history += case.ia_history[pos:]
    out = dataclasses.replace(case, ia_history=new_history, context_agents=context)
    problems = validate_cases([out])
    if problems:
        raise ValueError(f"{case.id}: productized case is invalid: {problems[0]}")
    return out
