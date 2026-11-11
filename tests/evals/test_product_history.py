"""Task 16b: ``evals.product_history.productize`` replaces off-product chatter with agent-backed exchanges."""
import dataclasses
import re
from pathlib import Path

import pytest

from evals.expand import MAX_REQUIRED, _topic, _trig
from evals.schema import Case, Outcome, Turn, load_cases, validate_cases
from evals.world.generate import WORLD_PATH
from evals.world.roster import World, load_world

REPO = Path(__file__).resolve().parents[2]
V1 = REPO / "evals" / "cases" / "v1"

OFF = frozenset({
    "What's the weather like this weekend?",
    "Is it going to rain in Seattle tomorrow?",
    "How long is the flight from Vancouver to Toronto?",
    "Convert 20 miles to kilometres.",
    "What's on my calendar tomorrow?",
    "Do I have anything on Friday afternoon?",
    "Thanks. Also, what's on my calendar tomorrow?",
})
THANKS = (Turn("user", "Thanks, that's all for now."), Turn("assistant", "You're welcome. I'm here if anything comes up."))
LEADS = {
    "summary": ("Anything new in my inbox?", "Did anything come in overnight?", "Any updates I should know about?"),
    "reminder": ("Did any of my reminders go off?", "Anything I need to do today?", "What's on my plate today?"),
}
PRONOUNS = {"she", "he", "her", "him", "his", "they", "them", "their"}
# Context agent ids per case as of 16b (before leads); 16b2 must not change them.
GOLDEN_CONTEXT = {
    'amb-person-001': ['ag_tvsjosvs'],
    'amb-person-002': [],
    'amb-person-003': ['ag_ajpksisi'],
    'amb-person-004': [],
    'amb-person-005': ['ag_5awxogls'],
    'amb-person-006': ['ag_jrt3ym3y'],
    'amb-person-007': ['ag_zcnht4xa'],
    'broad-person-001': ['ag_72oxneof'],
    'broad-person-002': ['ag_dyqa7hai'],
    'broad-person-003': ['ag_7itnrndm', 'ag_w6proags'],
    'broad-person-004': ['ag_hn3twdnz', 'ag_2sb7la67'],
    'broad-person-005': [],
    'broad-person-006': ['ag_7rwmrgrt'],
    'clear-person-001': ['ag_oho5z2l5'],
    'clear-person-002': ['ag_3j47yivk'],
    'clear-person-003': ['ag_ft33ftgo'],
    'clear-person-004': ['ag_w3t6uzbi'],
    'clear-person-005': ['ag_m4l43mia'],
    'clear-person-006': ['ag_2qo7jbyv'],
    'followup-001': ['ag_orcr36a4'],
    'followup-002': ['ag_5camm5ov'],
    'followup-003': ['ag_65mdheqo'],
    'followup-004': ['ag_vwf5arsr', 'ag_42wz3cre'],
    'followup-005': ['ag_upxeow5g'],
    'followup-006': ['ag_mtagzkm7'],
    'multi-intent-001': [],
    'multi-intent-002': ['ag_e6zme236'],
    'multi-intent-003': ['ag_dgikgrv6', 'ag_25isscvz'],
    'multi-intent-004': ['ag_42wz3cre'],
    'multi-intent-005': ['ag_zi77ifox'],
    'multi-intent-006': ['ag_m57q5oei'],
    'multi-person-001': ['ag_73nyuwxg'],
    'multi-person-002': ['ag_avxydnpv', 'ag_t4622w3n'],
    'multi-person-003': ['ag_tsekgzdv', 'ag_6qcrp7gd'],
    'multi-person-004': ['ag_y36jj43i', 'ag_iqbteomv'],
    'multi-person-005': ['ag_2qo7jbyv', 'ag_frroukm2'],
    'multi-person-006': ['ag_qtqviwbs'],
    'newtask-001': ['ag_rpbud4dj'],
    'newtask-002': ['ag_bzxcbyn5'],
    'newtask-003': [],
    'newtask-004': [],
    'newtask-005': [],
    'newtask-006': ['ag_uz7igbah'],
    'trigger-001': ['ag_rolwliox'],
    'trigger-002': [],
    'trigger-003': [],
    'trigger-004': [],
    'trigger-005': ['ag_o7ne3kk4'],
    'trigger-006': [],
}
# Independent of the implementation's tokenizer: words of >= 4 letters minus these.
STOP = frozenset("""this that with from have your what about when where which would could should their there
them they then than will into over also just some more most only very each both been being does done
update updates reminder reminders summary summaries replied reply news any anything again still ever""".split())


@pytest.fixture(scope="module")
def ph():
    from evals import product_history
    return product_history


@pytest.fixture(scope="module")
def world():
    return load_world(WORLD_PATH)


@pytest.fixture(scope="module")
def v1():
    return load_cases(V1)


@pytest.fixture(scope="module")
def prod(ph, world, v1):
    return {c.id: ph.productize(c, world, c.id) for c in v1}


def _words(s):
    return set(re.findall(r"[a-z0-9']+", s.lower().replace("’", "'")))


def _content(s):
    return {w for w in re.findall(r"[a-z]{4,}", s.lower()) if w not in STOP}


def _is_off(t):
    return t.role == "user" and t.text in OFF


def _pairs(history):
    """Indexes of off-product user turns (each pair is that turn plus the assistant turn after it)."""
    return [i for i, t in enumerate(history) if _is_off(t)]


def _kept(history):
    out, i = [], 0
    while i < len(history):
        if _is_off(history[i]):
            i += 2 if i + 1 < len(history) and history[i + 1].role == "assistant" else 1
        else:
            out.append(history[i])
            i += 1
    return out


def _subsequence_rest(kept, new):
    """Greedy: the turns of ``new`` that are not matched, in order, to the ``kept`` list."""
    rest, k = [], 0
    for t in new:
        if k < len(kept) and t == kept[k]:
            k += 1
        else:
            rest.append(t)
    return k == len(kept), rest


def _new_turns(c, p):
    ok, rest = _subsequence_rest(_kept(c.ia_history), p.ia_history)
    assert ok, f"{c.id}: kept turns missing or reordered"
    return rest


def _blocks(rest):
    """Split new turns into exchanges of three turns: user, agent, assistant (both shapes)."""
    assert len(rest) % 3 == 0, rest
    return [rest[i:i + 3] for i in range(0, len(rest), 3)]


def _forbidden(c):
    names, emails = set(), set()
    people = {ct.display_name for a in c.required_agents for ct in a.contacts}
    people |= set(c.clarify_should_name)
    if c.expect_person:
        people.add(c.expect_person)
    for n in people:
        names |= {w.lower() for w in n.split()}
    for a in c.required_agents:
        emails |= {ct.email.lower() for ct in a.contacts}
    return names, emails


def _topic_words(c):
    words = _content(c.message) | _content(c.original_message or "")
    for a in c.required_agents:
        t = _topic(a)
        if t:
            words |= _content(t.key) | _content(t.theme)
        g = _trig(a)
        if g:
            words |= _content(g.label) | _content(g.group)
    return words


def _synthetic(world, req, history, message="Please handle it."):
    return Case(id="syn-001", category="email_followup", split="dev", source="template", severity="normal",
                required_agents=list(req), ia_history=history, message=message,
                acceptable=[Outcome("reuse", (req[0].id,))])


# ------------------------------------------------------------------ 1 / constants

def test_constants(ph):
    assert ph.OFF_PRODUCT == OFF and isinstance(ph.OFF_PRODUCT, frozenset)
    assert ph.GENERIC_KEPT == frozenset({"Thanks, that's all for now.", "What day is the first of next month?"})


def test_off_product_lines_gone_and_38_changed(v1, prod):
    assert len(v1) == 49
    changed = 0
    for c in v1:
        p = prod[c.id]
        assert not any(t.text in OFF for t in p.ia_history), c.id
        changed += p != c
    assert changed == 38


# ------------------------------------------------------------------ 2 / order and length

def test_kept_turns_in_order_and_length_arithmetic(v1, prod):
    for c in v1:
        p = prod[c.id]
        rest = _new_turns(c, p)
        blocks = _blocks(rest)
        n_pairs = len(_pairs(c.ia_history))
        assert len(blocks) == n_pairs, c.id
        assert all([t.role for t in b] == ["user", "agent", "assistant"] for b in blocks), c.id
        assert len(p.ia_history) == len(c.ia_history) - 2 * n_pairs + 3 * n_pairs, c.id


def test_exchange_sits_in_the_position_of_the_pair(v1, prod):
    for c in v1:
        p = prod[c.id]
        # every non-off turn before the first off pair is untouched at the same index
        first = (_pairs(c.ia_history) or [len(c.ia_history)])[0]
        assert p.ia_history[:first] == c.ia_history[:first], c.id


# ------------------------------------------------------------------ 3 / shapes

def _shape(a):
    return "trigger" if _trig(a) is not None else "email"


def test_shape_rules_per_category(v1, prod):
    seen_other = set()
    for c in v1:
        p = prod[c.id]
        shapes = [_shape(a) for a in p.context_agents]
        if c.category == "ambiguous_person":
            assert set(shapes) <= {"trigger"}, c.id
        elif c.category == "trigger_management":
            assert set(shapes) <= {"email"}, c.id
        else:
            seen_other |= set(shapes)
    assert seen_other == {"email", "trigger"}


def test_exchange_texts_follow_the_templates(v1, prod):
    n_email = n_trig = 0
    for c in v1:
        p = prod[c.id]
        for u, ag, asst in _blocks(_new_turns(c, p)):
            a = next(x for x in p.context_agents if x.id == ag.agent_id)
            assert (u.role, ag.role, asst.role) == ("user", "agent", "assistant")
            assert ag.agent_name == a.name
            g = _trig(a)
            if g is None:
                n_email += 1
                t = _topic(a)
                assert t is not None and t.kind == "thread"
                names = [ct.display_name for ct in a.contacts]
                assert any(u.text.startswith(f"Any news from {n} on ") for n in names), u.text
                assert ag.text.startswith("Update on ")
                assert any(f"{n.split()[0]} replied {t.reply}." in ag.text for n in names), ag.text
                assert t.reply in asst.text
            else:
                n_trig += 1
                assert u.text in LEADS[g.kind], (g.kind, u.text)
                assert asst.text == ag.text
    assert n_email and n_trig


def test_every_agent_turn_follows_a_user_turn_and_every_changed_case_has_one(v1, prod):
    for c in v1:
        p = prod[c.id]
        for i, t in enumerate(p.ia_history):
            if t.role == "agent" and t.agent_id in {a.id for a in p.context_agents}:
                assert i > 0 and p.ia_history[i - 1].role == "user", (c.id, i)
        if p != c:
            assert any(t.role == "user" for t in p.ia_history), c.id


def test_ambiguous_person_leads_name_no_one(v1, prod):
    n = 0
    for c in v1:
        if c.category != "ambiguous_person":
            continue
        for u, ag, _ in _blocks(_new_turns(c, prod[c.id])):
            n += 1
            assert not re.findall(r"\b[A-Z][a-z]+", u.text[1:]), u.text  # no capitalised name mid-line
            assert not (_words(u.text) & PRONOUNS), u.text
    assert n


def test_context_agent_ids_unchanged_from_16b(v1, prod):
    assert {c.id: [a.id for a in prod[c.id].context_agents] for c in v1} == GOLDEN_CONTEXT


# ------------------------------------------------------------------ 4 / guards

def test_context_agents_are_fresh_world_fillers(v1, world, prod):
    for c in v1:
        p = prod[c.id]
        ids = [a.id for a in p.context_agents]
        assert len(ids) == len(set(ids)), c.id
        required = {a.id for a in c.required_agents}
        for a in p.context_agents:
            assert a.id in world.filler_order and a.id not in required, (c.id, a.id)
            assert world.agents[a.id] == a
        # each contact person at most once per case
        people = [ct.display_name.lower() for a in p.context_agents for ct in a.contacts]
        assert len(people) == len(set(people)), c.id


def test_no_forbidden_names_emails_or_topic_words(v1, prod):
    for c in v1:
        p = prod[c.id]
        names, emails = _forbidden(c)
        topic = _topic_words(c)
        for a in p.context_agents:
            for ct in a.contacts:
                assert ct.email.lower() not in emails, (c.id, ct.email)
                assert not ({w.lower() for w in ct.display_name.split()} & names), (c.id, ct.display_name)
        for t in _new_turns(c, p):
            assert not (_words(t.text) & names), (c.id, t.text, _words(t.text) & names)
            assert not any(e in t.text.lower() for e in emails), (c.id, t.text)
            assert not (_content(t.text) & topic), (c.id, t.text, _content(t.text) & topic)
        for a in p.context_agents:
            t = _topic(a)
            own = _content(a.name) | (_content(t.key) | _content(t.theme) if t else set())
            g = _trig(a)
            if g:
                own |= _content(g.label) | _content(g.group)
            assert not (own & topic), (c.id, a.id, own & topic)


# ------------------------------------------------------------------ 5 / ids

def test_agent_turns_reference_required_or_context_and_context_is_exactly_new_turns(v1, prod):
    for c in v1:
        p = prod[c.id]
        allowed = {a.id for a in p.required_agents} | {a.id for a in p.context_agents}
        ids = [t.agent_id for t in p.ia_history if t.role == "agent"]
        assert set(ids) <= allowed, c.id
        new_ids = [t.agent_id for t in _new_turns(c, p) if t.role == "agent"]
        assert [a.id for a in p.context_agents] == new_ids, c.id  # history order, no extras


def test_all_other_fields_unchanged(v1, prod):
    for c in v1:
        p = prod[c.id]
        assert dataclasses.replace(p, ia_history=c.ia_history, context_agents=c.context_agents) == c
        if p == c:
            assert p.context_agents == []


# ------------------------------------------------------------------ 6 / determinism

def test_deterministic_key_sensitive_and_order_independent(ph, v1, world, prod):
    again = {c.id: ph.productize(c, world, c.id) for c in v1}
    assert again == prod
    reversed_run = {c.id: ph.productize(c, world, c.id) for c in reversed(v1)}
    assert reversed_run == prod
    changed = [c for c in v1 if prod[c.id] != c]
    assert any(ph.productize(c, world, c.id + "-other") != prod[c.id] for c in changed)


# ------------------------------------------------------------------ 7 / size cap

def test_required_plus_context_within_cap(v1, prod):
    for c in v1:
        p = prod[c.id]
        assert len(p.required_agents) + len(p.context_agents) <= MAX_REQUIRED, c.id


def test_older_pair_becomes_thanks_when_cap_would_be_exceeded(ph, world):
    req = [world.agents[i] for i in world.filler_order[:9]]
    hist = [Turn("user", "What's on my calendar tomorrow?"), Turn("assistant", "A team lunch at noon."),
            Turn("user", "Convert 20 miles to kilometres."), Turn("assistant", "About 32 kilometres.")]
    c = _synthetic(world, req, hist)
    p = ph.productize(c, world, "syn-001")
    assert tuple(p.ia_history[:2]) == THANKS
    rest = p.ia_history[2:]
    assert len(rest) == 3 and any(t.role == "agent" for t in rest)
    assert not any(t.text in OFF for t in p.ia_history)
    assert len(p.context_agents) == 1 and len(p.required_agents) + 1 == MAX_REQUIRED
    assert validate_cases([p]) == []


def test_cap_with_three_pairs_keeps_only_older_as_thanks(ph, world):
    req = [world.agents[i] for i in world.filler_order[:8]]
    hist = [Turn("user", "What's on my calendar tomorrow?"), Turn("assistant", "A"),
            Turn("user", "Convert 20 miles to kilometres."), Turn("assistant", "B"),
            Turn("user", "Do I have anything on Friday afternoon?"), Turn("assistant", "C")]
    p = ph.productize(_synthetic(world, req, hist), world, "syn-002")
    assert tuple(p.ia_history[:2]) == THANKS
    assert len(p.required_agents) + len(p.context_agents) <= MAX_REQUIRED
    assert len(p.context_agents) == 2


# ------------------------------------------------------------------ 8 / identity, edge cases

def test_case_without_off_product_pair_is_returned_equal(ph, v1, world):
    plain = [c for c in v1 if not _pairs(c.ia_history)]
    assert len(plain) == 11
    for c in plain:
        assert ph.productize(c, world, c.id) == c


def test_off_product_user_turn_without_assistant_does_not_crash(ph, world):
    req = [world.agents[world.filler_order[0]]]
    c = _synthetic(world, req, [Turn("user", "What's the weather like this weekend?")])
    p = ph.productize(c, world, "lone")
    assert not any(t.text in OFF for t in p.ia_history)
    assert len(p.ia_history) == 3 and len(p.context_agents) == 1


def test_no_candidate_raises_value_error(ph):
    empty = World()
    req = []
    c = Case(id="x-001", category="email_followup", split="dev", source="template", severity="normal",
             required_agents=req, ia_history=[Turn("user", "Convert 20 miles to kilometres."),
                                              Turn("assistant", "About 32 kilometres.")],
             message="Hi", acceptable=[Outcome("create")])
    with pytest.raises(ValueError, match=r"x-001: no context agent for pair \d"):
        ph.productize(c, empty, "x-001")


# ------------------------------------------------------------------ 9 / validation

def test_productized_cases_validate_alone_and_together(v1, prod):
    for c in v1:
        assert validate_cases([prod[c.id]]) == [], c.id
    assert validate_cases([prod[c.id] for c in v1]) == []


# ------------------------------------------------------------------ 10 / spot check

def test_multi_person_006_last_exchange_is_agent_backed_and_names_nobody_in_the_message(v1, prod):
    c = next(x for x in v1 if x.id == "multi-person-006")
    p = prod[c.id]
    assert p.ia_history[-2].role == "agent" and p.ia_history[-1].role == "assistant"
    assert p.ia_history[-2].agent_id in {a.id for a in p.context_agents}
    words = set().union(*(_words(t.text) for t in p.ia_history))
    assert "sam" not in words and "alice" not in words
