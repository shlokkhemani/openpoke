"""Dense-person stress roster: two heavy contacts that each own one agent per topic (96 agents), plus the queries
that test whether the right agent wins inside its own cluster. Built on top of the frozen base world, never
written back to it."""
from __future__ import annotations

import hashlib
import json
import random
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Mapping, Optional

from evals.schema import AgentDef, Contact, load_cases
from evals.textwords import content_words
from evals.world.generate import (
    DOMAINS, EMAIL_TOPICS, FIRST_NAMES, LAST_NAMES, ONE_OFF_DOCS, RESERVED_FIRST_NAMES, _activity, _agent_id,
    _fact_kind, _make_fact,
)
from evals.caseset import CASES_DIR
from evals.world.roster import FACT_RE, World

SEED = "7:dense"
QUERY_SEED = "7:dense:q"
N_DOC_TOPICS = 18
PEOPLE = (Contact("zephyrin.oduya@acme-corp.com", "Zephyrin Oduya", "to"),
          Contact("tavish.kellerman@gmail.com", "Tavish Kellerman", "to"))
EMAIL_VERBS = ("Email {f} re {short}", "Email {f} about {short}", "Follow up with {f} on {short}",
               "Find emails from {f} about {short}")
DOC_VERBS = ("Send {f} the {doc}", "Email {f} the {doc}")
NEUTRAL_HISTORY = (("user", "Thanks, that's all for now.", None),
                   ("assistant", "You're welcome. I'm here if anything comes up.", None))

TEMPLATES = {
    "target_exact": ("Did {first} get back to you about {topic}?", "Where do things stand with {first} on {topic}?",
                     "Has {first} come back on {topic} yet?", "Any word from {first} regarding {topic}?",
                     "How is {topic} going with {first}?"),
    "target_para": ("Did {first} get back to you about {topic}?", "Where do things stand with {first} on {topic}?",
                    "Has {first} come back on {topic} yet?", "Any word from {first} regarding {topic}?",
                    "How is {topic} going with {first}?"),
    "topic_noname": ("Any update on {topic}?", "How is {topic} going?", "Where are we on {topic}?",
                     "Remind me where {topic} ended up.", "Anything happening with {topic}?"),
    "history_pull": ("And {first} on {topic}?", "Same question for {first}: where is {topic}?",
                     "What about {first} and {topic}?", "Now check with {first} regarding {topic}.",
                     "Did {first} come back on {topic} too?"),
}


@dataclass(frozen=True)
class TopicMeta:
    short: str
    phrase: str
    reply: str      # "" for documents
    kind: str       # email | doc


@dataclass
class DenseWorld:
    people: tuple[Contact, Contact]
    agents: dict[str, AgentDef]
    by_person_topic: dict[tuple[str, str], str]
    topics: tuple[str, ...]
    topic_meta: dict[str, TopicMeta]
    seed: str = SEED


def _topics() -> dict[str, TopicMeta]:
    meta = {s: TopicMeta(s, core, reply, "email") for s, core, reply in EMAIL_TOPICS}
    meta.update({d: TopicMeta(d, phrase, "", "doc") for d, phrase in ONE_OFF_DOCS[:N_DOC_TOPICS]})
    return meta


def _words(text: str) -> set[str]:
    return {w.casefold() for w in re.findall(r"[^\W\d_]+(?:'[^\W\d_]+)?", text)}


def assert_names_clear(people, base: World, cases_dir: Path = CASES_DIR) -> None:
    """Raise if a dense person's first or last name is already used anywhere else (world, tables, v1 cases)."""
    from evals.paraphrase import _EXTRA_FIRST_NAMES
    mine = {w.casefold() for p in people for w in p.display_name.split()}
    used: set[str] = set()
    for c in base.contacts:
        used |= _words(c.display_name)
    for table in (FIRST_NAMES, LAST_NAMES, RESERVED_FIRST_NAMES, _EXTRA_FIRST_NAMES):
        used |= {w.casefold() for w in table}
    for c in load_cases(cases_dir):
        text = [c.message, c.original_message or "", *(t.text for t in c.ia_history)]
        for a in (*c.required_agents, *c.context_agents):
            text += [a.name, a.description, *(x.display_name for x in a.contacts)]
        used |= _words(" ".join(text))
    clash = mine & used
    if clash:
        raise ValueError(f"dense person names already used elsewhere: {sorted(clash)}")


def build_dense_world(base: World, seed: str = SEED) -> DenseWorld:
    assert_names_clear(PEOPLE, base)
    assert PEOPLE[0].email.split("@")[1] in DOMAINS and PEOPLE[1].email.endswith("@gmail.com")
    rng, fact_rng = random.Random(seed), random.Random(seed + ":facts")
    used_ids = set(base.agents)
    used_facts = set(FACT_RE.findall(" ".join(a.description for a in base.agents.values())))
    meta = _topics()
    agents: dict[str, AgentDef] = {}
    by_pt: dict[tuple[str, str], str] = {}
    for person in PEOPLE:
        full, f = person.display_name, person.display_name.split()[0]
        for topic, m in meta.items():
            aid = _agent_id(rng, used_ids)
            if m.kind == "email":
                verb = rng.choice(EMAIL_VERBS)
                name = verb.format(f=f, short=topic)
                if verb.startswith("Find"):
                    desc = (f"Searched the inbox for emails from {full} about {m.phrase} and listed "
                            f"{rng.randint(2, 9)} matches. {_make_fact(fact_rng, used_facts, _fact_kind(topic, 'msg'))}")
                else:
                    desc = (f"Emailed {full} about {m.phrase}. {f} replied {m.reply}. "
                            f"{_make_fact(fact_rng, used_facts, _fact_kind(topic, 'ref'))}")
            else:
                name = rng.choice(DOC_VERBS).format(f=f, doc=topic)
                desc = (f"Sent {full} {m.phrase}. {f} acknowledged it. "
                        f"{_make_fact(fact_rng, used_facts, _fact_kind(topic, 'ref'))}")
            act = _activity(rng)
            agents[aid] = AgentDef(aid, name, desc, (Contact(person.email, full, "to"),), (), float(act), float(act))
            by_pt[(person.email, topic)] = aid
    return DenseWorld(PEOPLE, agents, by_pt, tuple(meta), meta, seed)


# ------------------------------------------------------------------ split and paraphrases

def split_topics(dense: DenseWorld, seed: str = QUERY_SEED) -> dict[str, tuple[str, ...]]:
    order = sorted(dense.topics, key=lambda t: hashlib.sha256(f"{seed}|{t}".encode()).hexdigest())
    half = len(order) // 2
    return {"dev": tuple(order[:half]), "test": tuple(order[half:])}


def load_paraphrases(path: Path, dense: DenseWorld) -> tuple[dict[str, str], list[dict]]:
    """(usable items, items moved out because they leak against the current dense world)."""
    from evals.stress_paraphrase import forbidden_words, leaks

    items = json.loads(Path(path).read_text(encoding="utf-8")).get("items", {})
    kept: dict[str, str] = {}
    dropped: list[dict] = []
    for topic, para in items.items():
        if topic not in dense.topic_meta:
            continue
        bad = leaks(para, forbidden_words(dense, topic))
        if bad or not para.strip():
            dropped.append({"topic": topic, "paraphrase": para, "leaked": sorted(bad)})
        else:
            kept[topic] = para
    return kept, dropped


# ------------------------------------------------------------------ queries

def dense_queries(dense: DenseWorld, paraphrases: Mapping[str, str], split: str = "dev", seed: str = QUERY_SEED):
    from evals.retrieval_eval import _DEFAULT, RQuery, _norm, build_query

    if split not in ("dev", "test"):
        raise ValueError(f"unknown split {split!r}")
    rng = random.Random(seed)
    required = tuple(dense.agents.values())
    out = []

    def add(topic, kind, suffix, message, history, expected, people, outcome=None):
        out.append(RQuery(
            id=f"dense:{topic}:{kind}:{suffix}", case_id=f"dense:{topic}", group="dense", kind=kind,
            query=build_query(message, history, _DEFAULT.history_turns), message=message, expected=set(expected),
            required=required, referenced=any(h[2] for h in history[-_DEFAULT.history_turns:]),
            outcome=outcome or f"dense {kind}", people=tuple(people)))

    for topic in split_topics(dense, seed)[split]:
        meta = dense.topic_meta[topic]
        para = paraphrases.get(topic)
        ids = [dense.by_person_topic[(p.email, topic)] for p in dense.people]
        for i, p in enumerate(dense.people):
            first, who = p.display_name.split()[0], (frozenset({_norm(p.display_name)}),)
            msg = rng.choice(TEMPLATES["target_exact"]).format(first=first, topic="the " + meta.short)
            add(topic, "target_exact", str(i), msg, NEUTRAL_HISTORY, {ids[i]}, who)
            tp, tn, th = (rng.choice(TEMPLATES[k]) for k in ("target_para", "topic_noname", "history_pull"))
            if para is None:
                continue
            add(topic, "target_para", str(i), tp.format(first=first, topic=para), NEUTRAL_HISTORY, {ids[i]}, who)
            other = dense.people[1 - i]
            text = f"{other.display_name} got back to you."   # Ruling R4': no topic words in the history
            history = (("agent", text, ids[1 - i]), ("assistant", text, None))
            add(topic, "history_pull", str(i), th.format(first=first, topic=para), history, {ids[i]}, who)
        if para is not None:
            msg = rng.choice(TEMPLATES["topic_noname"]).format(topic=para)
            add(topic, "topic_noname", "both", msg, NEUTRAL_HISTORY, set(ids),
                [frozenset({_norm(p.display_name)}) for p in dense.people])
    return out
