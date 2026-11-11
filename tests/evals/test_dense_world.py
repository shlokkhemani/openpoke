"""Task 12c: the dense-person stress roster (``evals.world.dense``), its queries, and the shared word rules
(``evals.textwords``). Offline; nothing is written under server/data.

Interface assumed (brief 2026-11-09):
- ``build_dense_world(base, seed="7:dense") -> DenseWorld`` with ``people`` (work, personal), ``agents``,
  ``by_person_topic``, ``topics`` (48) and ``topic_meta[topic] -> TopicMeta(short, phrase, reply, kind)``;
- ``split_topics(dense, seed="7:dense:q") -> {"dev": tuple, "test": tuple}``;
- ``dense_queries(dense, paraphrases, split="dev", seed="7:dense:q")``; ``TEMPLATES[kind]`` template pools
  using ``{first}`` / ``{topic}`` placeholders; ``load_paraphrases(path, dense) -> (items, dropped_at_load)``;
- ``evals.textwords.content_words(text) -> set[str]`` (lowercase, split on non-letters keeping digits, stopwords
  dropped, one trailing plural ``s`` stripped).
"""
import copy
import hashlib
import json
import re
from pathlib import Path

import pytest

from evals.caseset import load_frozen_cases
from evals.retrieval_eval import _norm
from evals.world import dense as dense_mod
from evals.world.dense import build_dense_world, dense_queries, load_paraphrases, split_topics
from evals.world.generate import (
    DOMAINS, EMAIL_TOPICS, FIRST_NAMES, LAST_NAMES, ONE_OFF_DOCS, RESERVED_FIRST_NAMES, WORLD_PATH,
)
from evals.world.roster import FACT_RE, load_world
from evals.paraphrase import _EXTRA_FIRST_NAMES
from evals.textwords import content_words

CASES_DIR = Path("evals/cases/v1")
TOPICS = tuple(t[0] for t in EMAIL_TOPICS) + tuple(d[0] for d in ONE_OFF_DOCS[:18])


@pytest.fixture(scope="module")
def base():
    return load_world(WORLD_PATH)


@pytest.fixture(scope="module")
def dense(base):
    return build_dense_world(base)


@pytest.fixture(scope="module")
def paras(dense):
    return {t: f"zzq{i:02d} wobble" for i, t in enumerate(dense.topics)}


def _names(dense):
    return [c.display_name for c in dense.people]


def _name_words(dense):
    return {w.casefold() for n in _names(dense) for w in n.split()}


# ---- textwords ---------------------------------------------------------------------------------
def test_content_words_rules():
    assert content_words("The Vendor contracts, and Q4 plans!") == {"vendor", "contract", "q4", "plan"}
    assert content_words("about the of and to") == set()
    assert content_words("budget") == content_words("budgets")


# ---- 1. dense world -----------------------------------------------------------------------------
def test_deterministic_same_seed_same_world(base):
    a, b = build_dense_world(base), build_dense_world(base)
    assert list(a.agents) == list(b.agents)
    assert a.agents == b.agents and a.people == b.people and a.topics == b.topics
    assert a.by_person_topic == b.by_person_topic
    assert build_dense_world(base, seed="7:other").agents != a.agents


def test_two_people_48_topics_each(dense):
    assert len(dense.people) == 2 and len(dense.agents) == 96
    assert dense.topics == TOPICS and len(set(dense.topics)) == 48
    work, personal = dense.people
    assert work.email.split("@")[1] in DOMAINS and work.email.split("@")[1] != "gmail.com"
    assert personal.email.endswith("@gmail.com")
    assert work.role == personal.role == "to"
    for p in dense.people:
        topics = [t for (e, t) in dense.by_person_topic if e == p.email]
        assert sorted(topics) == sorted(TOPICS)
    assert len(dense.by_person_topic) == 96
    assert set(dense.by_person_topic.values()) == set(dense.agents)
    for t in TOPICS:
        meta = dense.topic_meta[t]
        assert meta.kind == ("email" if t in {e[0] for e in EMAIL_TOPICS} else "doc")


def test_ids_format_and_no_collision_with_base(dense, base):
    assert all(re.fullmatch(r"ag_[a-z2-7]{8}", i) for i in dense.agents)
    assert not set(dense.agents) & set(base.agents)
    assert all(a.id == i for i, a in dense.agents.items())


def test_agents_names_descriptions_contacts(dense):
    for (email, topic), aid in dense.by_person_topic.items():
        a = dense.agents[aid]
        person = next(p for p in dense.people if p.email == email)
        f = person.display_name.split()[0]
        assert a.contacts == (type(person)(email, person.display_name, "to"),)
        assert a.triggers == ()
        meta = dense.topic_meta[topic]
        if meta.kind == "email":
            assert a.name in {f"Email {f} re {topic}", f"Email {f} about {topic}", f"Follow up with {f} on {topic}",
                              f"Find emails from {f} about {topic}"}
            if a.name.startswith("Find emails"):
                assert re.fullmatch(rf"Searched the inbox for emails from {re.escape(person.display_name)} about "
                                    rf"{re.escape(meta.phrase)} and listed [2-9] matches\. .+", a.description)
            else:
                assert a.description.startswith(f"Emailed {person.display_name} about {meta.phrase}. {f} replied "
                                                f"{meta.reply}. ")
        else:
            assert a.name in {f"Send {f} the {topic}", f"Email {f} the {topic}"}
            assert a.description.startswith(f"Sent {person.display_name} {meta.phrase}. {f} acknowledged it. ")
        assert FACT_RE.search(a.description)
    verbs = {a.name.split(" ")[0] for a in dense.agents.values()}
    assert len(verbs) >= 3  # the seeded RNG draws several verb forms


def test_fact_tokens_unique_and_absent_from_base_descriptions(dense, base):
    tokens = [FACT_RE.search(a.description).group(0) for a in dense.agents.values()]
    assert len(set(tokens)) == 96
    base_text = " ".join(a.description for a in base.agents.values())
    assert not [t for t in tokens if t in base_text]


def test_new_names_absent_from_base_tables_and_v1_cases(dense, base):
    words = _name_words(dense)
    assert len(words) == 4
    pool: set[str] = set()
    for n in [c.display_name for c in base.contacts]:
        pool |= {w.casefold() for w in n.split()}
    for table in (FIRST_NAMES, LAST_NAMES, RESERVED_FIRST_NAMES, _EXTRA_FIRST_NAMES):
        pool |= {w.casefold() for w in table}
    assert not words & pool, words & pool
    text = []
    for c in load_frozen_cases(CASES_DIR):
        text += [c.message, c.original_message or ""]
        text += [t.text for t in c.ia_history]
        for a in c.required_agents:
            text += [a.name, a.description] + [x.display_name for x in a.contacts]
    blob = " ".join(text).casefold()
    for w in words:
        assert not re.search(rf"(?<![a-z]){re.escape(w)}(?![a-z])", blob), w


def test_build_does_not_mutate_base(base):
    before = copy.deepcopy(base)
    build_dense_world(base)
    assert base == before


def test_world_json_and_case_manifest_untouched(base):
    sha = hashlib.sha256(WORLD_PATH.read_bytes()).hexdigest()
    build_dense_world(base)
    assert hashlib.sha256(WORLD_PATH.read_bytes()).hexdigest() == sha
    assert load_frozen_cases(CASES_DIR)


# ---- 2. queries ---------------------------------------------------------------------------------
KINDS = ("target_exact", "target_para", "topic_noname", "history_pull")


def _by_kind(qs):
    return {k: [q for q in qs if q.kind == k] for k in KINDS}


def _topic(q):
    return q.case_id.removeprefix("dense:")


def test_split_is_sha_ordered_and_halved(dense):
    s = split_topics(dense)
    order = sorted(dense.topics, key=lambda t: hashlib.sha256(f"7:dense:q|{t}".encode()).hexdigest())
    assert s["dev"] == tuple(order[:24]) and s["test"] == tuple(order[24:])
    assert not set(s["dev"]) & set(s["test"]) and len(s["dev"]) == len(s["test"]) == 24


def test_counts_per_kind_and_split(dense, paras):
    for split in ("dev", "test"):
        qs = dense_queries(dense, paras, split)
        by = _by_kind(qs)
        assert [len(by[k]) for k in KINDS] == [48, 48, 24, 48], split
        assert {q.group for q in qs} == {"dense"}
        assert {_topic(q) for q in qs} == set(split_topics(dense)[split])
        assert len({q.id for q in qs}) == len(qs)
        assert all(q.case_id.startswith("dense:") for q in qs)
    dev_t, test_t = ({_topic(q) for q in dense_queries(dense, paras, s)} for s in ("dev", "test"))
    assert not dev_t & test_t and len(dev_t) == len(test_t) == 24


def test_missing_paraphrase_topics_are_skipped_for_para_kinds(dense, paras):
    gone = split_topics(dense)["dev"][0]
    qs = dense_queries(dense, {t: p for t, p in paras.items() if t != gone}, "dev")
    by = _by_kind(qs)
    assert [len(by[k]) for k in KINDS] == [48, 46, 23, 46]
    assert gone not in {_topic(q) for q in by["target_para"] + by["topic_noname"] + by["history_pull"]}


def test_every_query_requires_all_96_and_is_well_formed(dense, paras):
    ids = set(dense.agents)
    for q in dense_queries(dense, paras, "dev"):
        assert {a.id for a in q.required} == ids and len(q.required) == 96
        assert q.extra_agents == () and q.expected <= ids and q.outcome
        assert q.message in q.query


def test_target_exact_contains_the_short_topic(dense, paras):
    for q in _by_kind(dense_queries(dense, paras, "dev"))["target_exact"]:
        t = _topic(q)
        assert dense.topic_meta[t].short.casefold() in q.message.casefold()
        (aid,) = q.expected
        assert aid in {dense.by_person_topic[(p.email, t)] for p in dense.people}
        person = next(p for p in dense.people if dense.by_person_topic[(p.email, t)] == aid)
        assert person.display_name.split()[0] in q.message
        assert q.people == (frozenset({_norm(person.display_name)}),)
        assert q.referenced is False and "Thanks, that's all for now." in q.query


def test_target_para_message_shares_no_content_word_with_expected_agent(dense, paras):
    names = _name_words(dense)
    for q in _by_kind(dense_queries(dense, paras, "dev"))["target_para"]:
        t = _topic(q)
        (aid,) = q.expected
        a = dense.agents[aid]
        assert paras[t] in q.message
        assert a.contacts[0].display_name.split()[0] in q.message
        shared = content_words(q.message) & content_words(a.name + " " + a.description)
        assert shared <= names, (q.message, shared - names)


def test_topic_noname_expects_both_same_topic_agents_and_names_no_one(dense, paras):
    names = _name_words(dense)
    for q in _by_kind(dense_queries(dense, paras, "dev"))["topic_noname"]:
        t = _topic(q)
        assert q.expected == {dense.by_person_topic[(p.email, t)] for p in dense.people}
        assert paras[t] in q.message
        assert not content_words(q.query) & names
        assert q.people == tuple(frozenset({_norm(p.display_name)}) for p in dense.people)


def test_history_pull_last_exchange_references_the_other_persons_agent(dense, paras):
    for q in _by_kind(dense_queries(dense, paras, "dev"))["history_pull"]:
        t = _topic(q)
        (aid,) = q.expected
        (other_id,) = {dense.by_person_topic[(p.email, t)] for p in dense.people} - {aid}
        other = dense.agents[other_id]
        full = other.contacts[0].display_name
        assert q.referenced is True and q.query.startswith(f"{other_id} ")
        assert other_id not in q.expected and aid not in q.query
        assert paras[t] in q.message
        # Ruling R4': topic-free last exchange
        lines = q.query.splitlines()
        assert lines[0] == f"{other_id} {full} got back to you." and lines[1] == f"{full} got back to you."


def test_history_pull_history_carries_no_topic_words_and_is_topic_independent(dense, paras):
    from evals.stress_paraphrase import forbidden_words
    names = _name_words(dense)
    seen = set()
    for q in _by_kind(dense_queries(dense, paras, "dev"))["history_pull"]:
        t = _topic(q)
        (aid,) = q.expected
        (other_id,) = {dense.by_person_topic[(p.email, t)] for p in dense.people} - {aid}
        lines = q.query.splitlines()
        text = lines[0].removeprefix(other_id + " ") + " " + lines[1]
        words = content_words(text) - names
        assert not words & forbidden_words(dense, t), (t, words & forbidden_words(dense, t))
        seen.add(frozenset(words))
    assert len(seen) == 1


DETERMINER_RE = re.compile(r"\b(the|that|my|those|these|this|a|an)\s+(the|that|my|those|these|this|a|an)\b", re.I)


def test_no_doubled_determiner_in_any_message(dense):
    dets = ("the ", "that ", "my ", "those ", "these ", "a ", "an ")
    paras_det = {t: dets[i % len(dets)] + f"zzq{i:02d} wobble" for i, t in enumerate(dense.topics)}
    for split in ("dev", "test"):
        for q in dense_queries(dense, paras_det, split):
            assert not DETERMINER_RE.search(q.message), q.message
    for kind, pool in dense_mod.TEMPLATES.items():
        for tpl in pool:
            assert "{topic}" in tpl
            assert not re.search(r"\b(the|that|my|those|these|this|a|an)\s+\{topic\}", tpl, re.I), (kind, tpl)


def test_target_exact_fills_topic_with_the_plus_short(dense, paras):
    for q in _by_kind(dense_queries(dense, paras, "dev"))["target_exact"]:
        assert f"the {dense.topic_meta[_topic(q)].short}" in q.message


# ---- tokenizer keeps one-character tokens ---------------------------------------------------------
def test_one_character_tokens_are_kept_and_contractions_leave_none():
    assert content_words("that W-9 thing") & content_words("w-9 form")
    assert "9" in content_words("w-9 form") and "w" in content_words("w-9 form")
    cw = content_words("that's you're I'm it's we'll a")
    assert not [w for w in cw if len(w) == 1], cw
    assert not [w for w in content_words("that's all") if len(w) == 1]


def test_w9_paraphrase_leaks_and_is_dropped_at_load(dense, tmp_path):
    from evals.stress_paraphrase import forbidden_words, leaks
    assert leaks("that W-9 thing", forbidden_words(dense, "w-9 form"))
    p = tmp_path / "dense_paraphrases.json"
    p.write_text(json.dumps({"items": {"w-9 form": "that W-9 thing", "Q4 roadmap": "zzq wobble"}}))
    items, dropped = load_paraphrases(p, dense)
    assert items == {"Q4 roadmap": "zzq wobble"}
    assert [d["topic"] for d in dropped] == ["w-9 form"]


def test_template_pools_are_big_enough_and_do_not_leak(dense):
    pool_words: set[str] = set()
    for a in dense.agents.values():
        pool_words |= content_words(a.name + " " + a.description)
    pool_words -= _name_words(dense)
    for kind in ("target_exact", "target_para", "topic_noname", "history_pull"):
        templates = dense_mod.TEMPLATES[kind]
        assert len(templates) >= 4, kind
        for tpl in templates:
            frame = re.sub(r"\{\w+\}", " ", tpl)
            assert not content_words(frame) & pool_words, (kind, tpl, content_words(frame) & pool_words)


def test_queries_are_deterministic(dense, paras):
    def snap():
        return [(q.id, q.case_id, q.kind, q.query, sorted(q.expected)) for q in dense_queries(dense, paras, "dev")]
    assert snap() == snap()


# ---- load-time paraphrase re-check ---------------------------------------------------------------
def test_load_paraphrases_moves_leaking_items_out(dense, tmp_path):
    p = tmp_path / "dense_paraphrases.json"
    p.write_text(json.dumps({"items": {"vendor contract": "vendor stuff", "Q4 roadmap": "zzq wobble"}}))
    items, dropped = load_paraphrases(p, dense)
    assert items == {"Q4 roadmap": "zzq wobble"}
    assert [d["topic"] for d in dropped] == ["vendor contract"]
    assert "vendor" in dropped[0]["leaked"] and dropped[0]["paraphrase"] == "vendor stuff"
