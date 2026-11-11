import re
from collections import Counter, defaultdict
from pathlib import Path

from evals.clock import days_ago
from evals.schema import load_cases
from evals.world.generate import RESERVED_FIRST_NAMES, example_anchors, generate_world
from evals.world.roster import extract_fact, load_world, roster_for, save_world

EX = Path("evals/cases/examples")
WORLD = Path("evals/world/world.json")
LOG_TAGS = {"agent_request", "agent_action", "tool_response", "agent_response"}


def test_same_seed_same_world():
    assert generate_world(7) == generate_world(7)


def test_different_seed_differs():
    assert generate_world(7) != generate_world(8)


def test_world_contents():
    w = generate_world(7)
    assert len(w.agents) >= 300
    first = Counter(c.display_name.split()[0] for c in w.contacts)
    assert first["Alice"] >= 2 and first["Sam"] >= 2
    emails_by_name = defaultdict(set)
    for c in w.contacts:
        emails_by_name[c.display_name].add(c.email)
    assert any(len(v) == 2 for v in emails_by_name.values())
    daily = [a for a in w.agents.values() if any("daily" in t.schedule for t in a.triggers)]
    assert len(daily) >= 15
    assert 70 <= len(w.contacts) <= 90
    assert len({c.email.lower() for c in w.contacts}) == len(w.contacts)


def test_contact_pool_has_example_contacts_even_without_anchors():
    emails = {c.email.lower() for c in generate_world(7).contacts}
    for c in example_anchors():
        for ct in c.contacts:
            assert ct.email.lower() in emails


def test_anchor_agents_present_unchanged():
    anchors = [a for c in load_cases(EX) for a in c.required_agents]
    w = generate_world(7, anchors=anchors)
    for a in anchors:
        assert w.agents[a.id] == a
    assert not set(a.id for a in anchors) & set(w.filler_order)
    assert len(w.filler_order) == 300


def test_filler_ids_format():
    w = generate_world(7)
    for aid in w.filler_order:
        assert re.fullmatch(r"ag_[a-z2-7]{8}", aid)


def test_reserved_first_names_unused_by_filler():
    assert {"Alice", "Dana", "Bob", "Maple"} <= RESERVED_FIRST_NAMES
    w = generate_world(7)
    for aid in w.filler_order:
        for c in w.agents[aid].contacts:
            assert c.display_name.split()[0] not in RESERVED_FIRST_NAMES


def test_filler_has_duplicate_names_and_sams():
    w = generate_world(7)
    names = Counter(w.agents[i].name for i in w.filler_order)
    assert any(n > 1 for n in names.values())
    sams = {c.email for i in w.filler_order for c in w.agents[i].contacts if c.display_name.startswith("Sam ")}
    assert len(sams) == 2


def test_schedules_and_statuses():
    w = generate_world(7)
    scheds = [t.schedule for a in w.agents.values() for t in a.triggers]
    assert any(s.startswith("weekly on") for s in scheds)
    assert any(s.startswith("monthly on the") for s in scheds)
    assert any(s.startswith("yearly on") for s in scheds)
    assert any(s.startswith("weekdays at") for s in scheds)
    statuses = Counter(t.status for a in w.agents.values() for t in a.triggers)
    assert statuses["paused"] >= 1 and statuses["active"] > 10 * statuses["paused"] / 2


def test_rosters_nested_and_sized():
    case = load_cases(EX)[0]
    w = load_world(WORLD)
    for n in (10, 30, 100, 300):
        r = roster_for(case, w, n)
        assert len(r) == n
        assert len({a.id for a in r}) == n
        assert {a.id for a in case.required_agents} <= {a.id for a in r}
    small = {a.id for a in roster_for(case, w, 10)}
    assert small <= {a.id for a in roster_for(case, w, 30)}
    assert [a.id for a in roster_for(case, w, 30)] == [a.id for a in roster_for(case, w, 30)]


def test_roster_filler_is_prefix_of_filler_order():
    case = load_cases(EX)[0]
    w = load_world(WORLD)
    req = {a.id for a in case.required_agents}
    k = len(req)
    r = roster_for(case, w, 30)
    assert {a.id for a in r} - req == set(w.filler_order[: 30 - k])


def test_filler_unique_facts_are_unique():
    w = generate_world(7)
    facts = [extract_fact(a.description) for a in w.agents.values()]
    assert len(facts) == len(set(facts))
    for aid in w.filler_order:
        d = w.agents[aid].description
        assert extract_fact(d) != d and extract_fact(d) in d


def test_extract_fact_returns_whole_description_for_anchor():
    a = load_cases(EX)[0].required_agents[0]
    assert extract_fact(a.description) == a.description


def test_logs_and_uses_consistent():
    w = generate_world(7)
    for aid, a in w.agents.items():
        log = w.logs[aid]
        assert 3 <= len(log) <= 6
        assert all(tag in LOG_TAGS for tag, _ in log)
        uses = w.uses[aid]
        assert uses and all(src in {"user", "trigger", "agent"} for _, src in uses)
        user_days = [d for d, s in uses if s == "user"]
        assert min(user_days) == a.last_user_activity_days_ago
        if a.last_run_days_ago is not None:
            assert min(d for d, _ in uses) == a.last_run_days_ago
    trig = [a for a in w.agents.values() if a.triggers]
    assert all(a.last_run_days_ago is not None for a in trig)


def test_user_activity_spread():
    w = generate_world(7)
    days = [w.agents[i].last_user_activity_days_ago for i in w.filler_order]
    assert min(days) <= 1 and max(days) >= 100 and max(days) <= 120


def test_save_load_roundtrip(tmp_path):
    w = generate_world(7, anchors=example_anchors())
    p = tmp_path / "w.json"
    save_world(w, p)
    assert load_world(p) == w
    save_world(w, tmp_path / "w2.json")
    assert p.read_bytes() == (tmp_path / "w2.json").read_bytes()


def test_committed_world_matches_generator():
    assert load_world(WORLD) == generate_world(7, anchors=example_anchors())


def test_no_filler_summarises_general_inbox():
    w = generate_world(7)
    for aid in w.filler_order:
        a = w.agents[aid]
        text = (a.name + " " + a.description).lower()
        assert "important unread" not in text
        assert "inbox summary" not in a.name.lower()


def test_filler_facts_follow_the_topic():
    w = generate_world(7)
    for aid in w.filler_order:
        a = w.agents[aid]
        d = a.description
        assert "$" not in d and "amount" not in d.lower(), d
        if "invoice" in d.lower() or "INV-" in d:
            assert "invoice" in a.name.lower(), (a.name, d)
    github = [w.agents[i] for i in w.filler_order if w.agents[i].name.endswith("GitHub summary")]
    assert github and all("PR-" in a.description for a in github)
    travel = [w.agents[i] for i in w.filler_order if "travel summary" in w.agents[i].name]
    assert travel and all("CONF-" in a.description for a in travel)
    for aid in w.filler_order:
        a = w.agents[aid]
        if "password reset" in a.name or "security audit" in a.name:
            assert "#Q-" in a.description
