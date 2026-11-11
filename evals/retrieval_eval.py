"""Layer-1 retrieval eval: does ``search_agents`` surface the agents the IA needs at each roster size?

Offline, no LLM, free. Each query's roster is loaded into a temporary ``AgentStore`` (required agents plus a
prefix of the world's filler order, grown N = 10 -> 30 -> ...), the query the IA would see is built with
``build_query``, and the candidates are scored: recall, all-found, person cover, list length and MRR, per
group x kind x N x K (one configuration: BM25 + embeddings, RRF).
"""
from __future__ import annotations

import json
import random
import time
from collections import defaultdict
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, Optional, Sequence

from evals.caseset import read_manifest, sha256_file
from evals.expand import expand
from evals.product_history import productize
from evals.harness.full_roster import description_coverage
from evals.harness.load_world import CachedEmbedder, load_into_store
from evals.textwords import content_words
from evals.caseset import CASES_DIR
from evals.schema import AgentDef, Case, format_outcome, load_cases
from evals.world.generate import EXAMPLES, WORLD_PATH
from evals.world.roster import World, load_world
from server.services.agents import embeddings as _embeddings
from server.services.agents.retrieval import RetrievalConfig, build_query, search_agents
from server.services.agents.store import AgentStore

KS = (5, 10, 20)
SPLITS = ("dev", "test")
HEADLINE_K = 20
# Dev cases whose last exchange references an agent id; their last exchange becomes the history of queries whose own last exchange references none.
UNRELATED_DONORS = ("trigger-006", "amb-person-007")

_DEFAULT = RetrievalConfig()


# ---------------------------------------------------------------- metrics

def recall(ranked: Sequence[Sequence[str]], expected: Sequence[set[str]]) -> float:
    """Mean over queries of |returned & expected| / |expected|; an empty expected set is an error."""
    if any(not e for e in expected):
        raise ValueError("expected set is empty")
    return sum(len(set(r) & e) / len(e) for r, e in zip(ranked, expected)) / len(expected)


def all_found(ranked: Sequence[Sequence[str]], expected: Sequence[set[str]]) -> float:
    return sum(e <= set(r) for r, e in zip(ranked, expected)) / len(expected)


def _first_hit(ranked: Sequence[str], expected: set[str]) -> Optional[int]:
    return next((i for i, a in enumerate(ranked, 1) if a in expected), None)


def mrr(ranked: Sequence[Sequence[str]], expected: Sequence[set[str]]) -> float:
    total = 0.0
    for r, e in zip(ranked, expected):
        hit = _first_hit(r, e)
        total += 1.0 / hit if hit else 0.0
    return total / len(expected)


def recall_at(ranked: Sequence[Sequence[str]], expected: Sequence[set[str]], k: int) -> float:
    return recall([list(r)[:k] for r in ranked], expected)


def _person_cover(returned: Sequence[str], people: Sequence[frozenset[str]]) -> Optional[float]:
    if not people:
        return None
    got = set(returned)
    return sum(bool(p & got) for p in people) / len(people)


def name_overlap_rank(agents: Sequence[AgentDef], query: str, seed_key: str) -> list[str]:
    """Baseline: agents ordered by the number of distinct content words shared by (name words + contact first
    names) and the query; ties broken by an RNG seeded with ``seed_key``."""
    q = content_words(query)

    def score(a: AgentDef) -> int:
        words = content_words(a.name)
        for c in a.contacts:
            words |= content_words(c.display_name.split()[0]) if c.display_name.split() else set()
        return len(words & q)

    order = list(agents)
    random.Random(seed_key).shuffle(order)
    return [a.id for a in sorted(order, key=lambda a: -score(a))]


# ---------------------------------------------------------------- queries

@dataclass
class RQuery:
    id: str
    case_id: str
    group: str            # frozen | original | unrelated_history | template
    kind: str             # target | both_candidates | set | lookalikes
    query: str
    message: str
    expected: set[str]
    required: tuple[AgentDef, ...]
    referenced: bool
    outcome: str
    people: tuple[frozenset[str], ...] = field(default_factory=tuple)
    extra_agents: tuple[AgentDef, ...] = field(default_factory=tuple)  # donor agents loaded into the roster


def _norm(name: str) -> str:
    return " ".join(name.split()).casefold()


def _names_of(a: AgentDef) -> set[str]:
    return {_norm(c.display_name) for c in a.contacts}


def expected_for(case: Case, world: World) -> tuple[str, set[str]]:
    """(kind, expected ids) from ``acceptable[0]``'s kind. May be empty (the caller skips those)."""
    o = case.acceptable[0]
    required = case.required_agents
    if o.kind == "reuse":
        return "target", set(o.agent_ids)
    if o.kind == "answer_set":
        return "set", set(o.agent_ids)
    if o.kind == "dispatch":
        reuse = {s.reuse_id for s in o.slots if s.reuse_id}
        if reuse:
            return "set", reuse
    if o.kind == "clarify":
        names = {_norm(n) for n in case.clarify_should_name}
        if not names:
            return "both_candidates", {a.id for a in required if a.contacts}
        for raw in case.clarify_should_name:
            if not any(_norm(raw) in _names_of(a) for a in required):
                raise ValueError(f"{case.id}: clarify_should_name {raw!r} matches no required agent")
        req_ids = {a.id for a in required}
        for aid in world.filler_order:
            if aid not in req_ids and names & _names_of(world.agents[aid]):
                raise ValueError(f"{case.id}: filler agent {aid} has a contact named like clarify name "
                                 f"{sorted(names & _names_of(world.agents[aid]))}")
        return "both_candidates", {a.id for a in required if names & _names_of(a)}
    # create, or a dispatch with only create slots
    if case.expect_person:
        n = _norm(case.expect_person)
        return "lookalikes", {a.id for a in required if n in _names_of(a)}
    return "lookalikes", {a.id for a in required}


def _people(case: Case, kind: str, expected: set[str]) -> tuple[frozenset[str], ...]:
    if kind != "both_candidates":
        return ()
    names = {_norm(n) for n in case.clarify_should_name}
    agents = [a for a in case.required_agents if a.id in expected]
    if not names:
        names = set().union(*(_names_of(a) for a in agents)) if agents else set()
    groups = [frozenset(a.id for a in agents if n in _names_of(a)) for n in sorted(names)]
    return tuple(g for g in groups if g)


def _history(case: Case) -> list[tuple]:
    return [(t.role, t.text, t.agent_id) for t in case.ia_history]


def _make(case: Case, world: World, *, qid: str, group: str, message: str) -> Optional[RQuery]:
    kind, expected = expected_for(case, world)
    if not expected:
        return None
    return RQuery(
        id=qid, case_id=case.id, group=group, kind=kind,
        query=build_query(message, _history(case), _DEFAULT.history_turns), message=message,
        expected=expected, required=tuple(case.required_agents), extra_agents=tuple(case.context_agents),
        referenced=any(t.agent_id for t in case.ia_history[-_DEFAULT.history_turns:]),
        outcome=format_outcome(case.acceptable[0]), people=_people(case, kind, expected))


def unrelated_history_variants(frozen: Sequence[RQuery], cases: Sequence[Case]) -> list[RQuery]:
    """Frozen queries whose own last exchange references no agent id, with the last exchange of a donor case as the
    only history before the message (fixed round-robin over the eligible queries sorted by case id;
    donors themselves are excluded)."""
    by_id = {c.id: c for c in cases}
    donors = [by_id[d] for d in UNRELATED_DONORS]
    eligible = sorted((q for q in frozen if q.group == "frozen" and not q.referenced and q.case_id not in UNRELATED_DONORS),
                      key=lambda q: q.case_id)
    out = []
    for i, q in enumerate(eligible):
        donor = donors[i % len(donors)]
        last = donor.ia_history[-_DEFAULT.history_turns:]
        ids = {t.agent_id for t in last if t.agent_id}
        extra = tuple(a for a in (*donor.required_agents, *donor.context_agents) if a.id in ids)
        out.append(replace(
            q, id=f"{q.id}:unrelated", group="unrelated_history", referenced=True, extra_agents=extra,
            query=build_query(q.message, _history(donor), _DEFAULT.history_turns)))
    return out


def case_queries(cases: Sequence[Case], world: World, split: str = "dev") -> list[RQuery]:
    """Frozen, original and unrelated-history queries of the cases in ``split``."""
    if split not in SPLITS:
        raise ValueError(f"unknown split {split!r} (choose from {', '.join(SPLITS)})")
    chosen = sorted((c for c in cases if c.split == split), key=lambda c: c.id)
    frozen, original = [], []
    for c in chosen:
        q = _make(c, world, qid=c.id, group="frozen", message=c.message)
        if q:
            frozen.append(q)
        if c.original_message and c.original_message != c.message:
            o = _make(c, world, qid=f"{c.id}:original", group="original", message=c.original_message)
            if o:
                original.append(o)
    unrelated = unrelated_history_variants(frozen, cases)
    return frozen + original + unrelated


@dataclass
class TemplateSet:
    queries: list[RQuery]
    seeds: list[int]
    skipped_seeds: list[int]
    dropped: int = 0


def template_queries(world: World, examples: list[Case], cases: Sequence[Case], n_template: int = 300,
                     first_seed: int = 100, max_seeds: int = 200) -> TemplateSet:
    """Template-expanded queries from seeds ``first_seed``, ``first_seed + 1`` ... until ``n_template`` are kept."""
    frozen_msgs = {c.message for c in cases} | {c.original_message for c in cases if c.original_message}
    test_keys = {(frozenset(a.id for a in c.required_agents), format_outcome(c.acceptable[0]))
                 for c in cases if c.split == "test"}
    queries: list[RQuery] = []
    seeds: list[int] = []
    skipped: list[int] = []
    dropped = 0
    seen = set(frozen_msgs)
    for seed in range(first_seed, first_seed + max_seeds):
        if len(queries) >= n_template:
            break
        try:
            generated = expand(world, examples, seed)
        except Exception:  # noqa: BLE001 - a bad seed is skipped and listed
            skipped.append(seed)
            continue
        seeds.append(seed)
        for c in generated:
            if c.source != "template":
                continue
            key = (frozenset(a.id for a in c.required_agents), format_outcome(c.acceptable[0]))
            if c.message in seen or key in test_keys:
                dropped += 1
                continue
            qid = f"t{seed}:{c.id}"
            try:
                q = _make(productize(c, world, qid), world, qid=qid, group="template", message=c.message)
            except ValueError:
                q = None
            if q is None:
                dropped += 1
                continue
            seen.add(c.message)
            queries.append(q)
    return TemplateSet(queries, seeds, skipped, dropped)


def retrieval_queries(cases: Sequence[Case], world: World, split: str = "dev", queries: str = "all",
                      n_template: int = 300, examples: Optional[list[Case]] = None) -> list[RQuery]:
    if queries not in ("frozen", "template", "all"):
        raise ValueError(f"unknown queries {queries!r}")
    out: list[RQuery] = []
    if queries in ("frozen", "all"):
        out += case_queries(cases, world, split)
    if queries in ("template", "all"):
        ex = examples if examples is not None else load_cases(EXAMPLES)
        out += template_queries(world, ex, cases, n_template).queries
    return out


# ---------------------------------------------------------------- evaluation

def _aggregate(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    buckets: dict[tuple, list[dict[str, Any]]] = defaultdict(list)
    for r in rows:
        buckets[(r["group"], r["kind"], r["n"], r["k"])].append(r)
    cells = []
    for (group, kind, n, k), rs in sorted(buckets.items()):
        covers = [r["person_cover"] for r in rs if r["person_cover"] is not None]
        extras = [r["extra_referenced"] for r in rs if r["extra_referenced"] is not None]
        cnt = len(rs)
        cells.append({
            "group": group, "kind": kind, "n": n, "k": k, "count": cnt,
            "recall": sum(r["recall"] for r in rs) / cnt,
            "all_found": sum(r["all_found"] for r in rs) / cnt,
            "person_cover": sum(covers) / len(covers) if covers else None,
            "mean_len": sum(r["len"] for r in rs) / cnt,
            "mrr": sum(r["rr"] for r in rs) / cnt,
            "baseline": sum(r["baseline_recall"] for r in rs) / cnt,
            "trivial": n <= k,
            "extra_referenced": sum(extras) / len(extras) if extras else None,
        })
    return cells


def evaluate(queries: Sequence[RQuery], world: World, sizes: Sequence[int], embedder,
             descriptions: Optional[dict[str, str]] = None, ks: Sequence[int] = KS) -> dict[str, Any]:
    cfg = _DEFAULT
    sizes = sorted(set(sizes))
    groups: dict[frozenset[str], list[RQuery]] = {}
    for q in queries:
        groups.setdefault(frozenset(a.id for a in (*q.required, *q.extra_agents)), []).append(q)
    rows: list[dict[str, Any]] = []
    skipped = 0
    with TemporaryDirectory(prefix="retrieval-eval-") as tmp:
        for gi, qs in enumerate(groups.values()):
            required = sorted({a.id: a for a in (*qs[0].required, *qs[0].extra_agents)}.values(), key=lambda a: a.id)
            req_ids = {a.id for a in required}
            fillers = [world.agents[i] for i in world.filler_order if i not in req_ids]
            store: Optional[AgentStore] = None
            loaded = 0  # fillers inserted so far
            for n in sizes:
                if n < len(required):
                    skipped += len(qs)
                    continue
                if n - len(required) > len(fillers):
                    raise ValueError(f"world has too few agents for roster size {n}")
                if store is None:
                    store = AgentStore(Path(tmp) / f"s{gi}.db")
                    load_into_store(required, world, store, embedder, descriptions)
                want = n - len(required)
                load_into_store(fillers[loaded:want], world, store, embedder, descriptions)
                loaded = want
                in_store = [*required, *fillers[:loaded]]
                for q in qs:
                    base_ids = name_overlap_rank(in_store, q.query, q.id)
                    full = [c.agent_id for c in search_agents(store, embedder, q.query, len(store.list_agents()), cfg, message=q.message)]
                    full_hit = _first_hit(full, q.expected)
                    rr = 1.0 / full_hit if full_hit else 0.0
                    for k in ks:
                        got = search_agents(store, embedder, q.query, k, cfg, message=q.message)
                        ids = [c.agent_id for c in got]
                        extra = None
                        if q.group == "unrelated_history":
                            extra = float(any("referenced" in c.reasons and c.agent_id not in q.expected
                                              for c in got))
                        rows.append({
                            "id": q.id, "case_id": q.case_id, "group": q.group, "kind": q.kind,
                            "n": n, "k": k, "referenced": q.referenced,
                            "expected": sorted(q.expected),
                            "returned": [{"id": c.agent_id, "reasons": list(c.reasons)} for c in got],
                            "first_hit_rank": _first_hit(ids, q.expected),
                            "recall": recall([ids], [q.expected]),
                            "all_found": float(q.expected <= set(ids)),
                            "person_cover": _person_cover(ids, q.people),
                            "len": len(ids), "rr": rr, "extra_referenced": extra,
                            "baseline_recall": recall([base_ids[:k]], [q.expected]),
                            "full_first_hit_rank": full_hit,
                        })
    return {"cells": _aggregate(rows),
            "cells_unreferenced": _aggregate([r for r in rows if not r["referenced"]]),
            "rows": rows, "skipped_n_below_required": skipped,
            "sizes": sizes, "ks": list(ks)}


# ---------------------------------------------------------------- output

def _headline(result: dict[str, Any], split: str, sizes: Sequence[int]) -> str:
    vals = []
    for n in sizes:
        cs = [c for c in result["cells"] if c["group"] == "frozen" and c["n"] == n and c["k"] == HEADLINE_K
              and c["kind"] != "lookalikes"]
        tot = sum(c["count"] for c in cs)
        # both_candidates: the IA needs one agent per person in order to ask, so person_cover is the measure
        score = sum((c["person_cover"] if c["kind"] == "both_candidates" and c["person_cover"] is not None
                     else c["recall"]) * c["count"] for c in cs)
        vals.append(f"{score / tot:.2f}" if tot else "–")
    return f"{split} recall@{HEADLINE_K} (rrf) at N={'/'.join(map(str, sizes))}: {'/'.join(vals)}"


def _fmt(x: Optional[float]) -> str:
    return "–" if x is None else f"{x:.2f}"


def render_report(summary: dict[str, Any], result: dict[str, Any]) -> str:
    kcols = " | ".join(f"recall@{k}" for k in KS)
    out = [f"# Retrieval eval: {summary['purpose'] or 'retrieval'}", "",
           f"- command: `{summary['command']}`", f"- split: {summary['split']}; embedder: {summary['embedder']}; "
           f"descriptions: {summary['descriptions']['source']}", f"- counts: {summary['counts']}",
           f"- {summary['headline']}", "", f"Cells marked `*` have N <= K and are trivially 1.0. all_found, "
           f"person_cover, mean_len and extra_referenced are at K={HEADLINE_K}; mrr is on the full fused ranking. "
           "Referenced ids from the last exchange are always appended.", ""]
    by: dict[tuple, dict[int, dict]] = defaultdict(dict)
    for c in result["cells"]:
        by[(c["group"], c["kind"], c["n"])][c["k"]] = c
    for group in sorted({g for g, *_ in by}):
        out += [f"## {group}", "", f"| kind | N | count | {kcols} | base@{HEADLINE_K} | all_found@{HEADLINE_K} | "
                f"person_cover@{HEADLINE_K} | mean_len@{HEADLINE_K} | mrr | extra_referenced@{HEADLINE_K} |",
                "|" + "---|" * (len(KS) + 9)]
        for (g, kind, n), ks in sorted(by.items()):
            if g != group:
                continue
            cells = [f"{ks[k]['recall']:.2f}{'*' if ks[k]['trivial'] else ''}" if k in ks else "–" for k in KS]
            kh = ks.get(HEADLINE_K)
            out.append(f"| {kind} | {n} | {(kh or next(iter(ks.values())))['count']} | " + " | ".join(cells)
                       + f" | {_fmt(kh and kh['baseline'])} | {_fmt(kh and kh['all_found'])} | {_fmt(kh and kh['person_cover'])} | "
                       f"{_fmt(kh and kh['mean_len'])} | {_fmt(next(iter(ks.values()))['mrr'])} | "
                       f"{_fmt(kh and kh['extra_referenced'])} |")
        out.append("")
    out += [f"## recall@{HEADLINE_K} without referenced queries (frozen group)", "",
            f"| kind | N | recall@{HEADLINE_K} |", "|---|---|---|"]
    for c in result["cells_unreferenced"]:
        if c["group"] == "frozen" and c["k"] == HEADLINE_K:
            out.append(f"| {c['kind']} | {c['n']} | {c['recall']:.2f} |")
    return "\n".join(out) + "\n"


def _median(xs: list[int]) -> Optional[float]:
    xs = sorted(xs)
    if not xs:
        return None
    mid = len(xs) // 2
    return float(xs[mid]) if len(xs) % 2 else (xs[mid - 1] + xs[mid]) / 2


def _dense_headline(result: dict[str, Any], split: str) -> str:
    sizes = sorted({c["n"] for c in result["cells"]})
    rec, base = [], []
    for n in sizes:
        c = next((c for c in result["cells"] if c["kind"] == "target_para" and c["n"] == n and c["k"] == HEADLINE_K), None)
        rec.append(_fmt(c and c["recall"]))
        base.append(_fmt(c and c["baseline"]))
    return (f"dense {split} target_para recall@{HEADLINE_K} at N={'/'.join(map(str, sizes))}: "
            f"{'/'.join(rec)} (base@{HEADLINE_K} {'/'.join(base)})")


def render_dense_report(summary: dict[str, Any], result: dict[str, Any]) -> str:
    kcols = " | ".join(f"recall@{k}" for k in KS)
    p = summary["paraphrases"]
    out = [f"# Retrieval eval (dense stress roster): {summary['purpose'] or 'retrieval-dense'}", "",
           f"- command: `{summary['command']}`", f"- split: {summary['split']}; embedder: {summary['embedder']}; "
           f"descriptions: {summary['descriptions']['source']}", f"- counts: {summary['counts']}",
           f"- paraphrase file sha256: {p['sha256']}; dropped at load: {[d['topic'] for d in p['dropped_at_load']]}; "
           f"topics without a paraphrase: {p['skipped_topics']}",
           f"- {summary['headline']}", "",
           f"Two contacts own 48 agents each (96 in all); base@{HEADLINE_K} is the name-overlap baseline. "
           f"median rank is the median rank of the first expected agent in the full fused ranking.", ""]
    ranks: dict[tuple, list[int]] = defaultdict(list)
    for r in result["rows"]:
        if r["k"] == HEADLINE_K and r["full_first_hit_rank"] is not None:
            ranks[(r["kind"], r["n"])].append(r["full_first_hit_rank"])
    by: dict[tuple, dict[int, dict]] = defaultdict(dict)
    for c in result["cells"]:
        by[(c["kind"], c["n"])][c["k"]] = c
    out += [f"| kind | N | count | {kcols} | base@{HEADLINE_K} | mrr | median rank |", "|" + "---|" * (len(KS) + 6)]
    for (kind, n), ks in sorted(by.items()):
        kh = ks.get(HEADLINE_K)
        med = _median(ranks.get((kind, n), []))
        out.append(f"| {kind} | {n} | {next(iter(ks.values()))['count']} | "
                   + " | ".join(_fmt(ks[k]['recall']) if k in ks else "–" for k in KS)
                   + f" | {_fmt(kh and kh['baseline'])} | {_fmt(next(iter(ks.values()))['mrr'])} | "
                   f"{'–' if med is None else f'{med:g}'} |")
    return "\n".join(out) + "\n"


def run(*, split: str, sizes: list[int], embedder_name: str, descriptions_source: str, queries: str,
        purpose: str, command: str, out_root: Path, experiments: Optional[Path] = None,
        cases_dir: Path = CASES_DIR, n_template: int = 300, world_kind: str = "base",
        paraphrases_path: Optional[Path] = None, dense_topic_limit: Optional[int] = None) -> int:
    from evals import regen_descriptions
    from evals.caseset import CaseSetError, load_frozen_cases
    from evals.report_run import EXPERIMENTS_HEADER, _cell
    from evals.routing_run import _run_dir, git_note, load_descriptions

    if split not in SPLITS:
        print(f"unknown split {split!r} (choose from {', '.join(SPLITS)})")
        return 1
    if embedder_name not in ("hashing", "fastembed"):
        print(f"unknown embedder {embedder_name!r} (choose hashing or fastembed)")
        return 1
    if world_kind not in ("base", "dense"):
        print(f"unknown world {world_kind!r} (choose base or dense)")
        return 1
    dense_mode = world_kind == "dense"
    para_path = None
    if dense_mode:
        from evals import stress_paraphrase

        para_path = Path(paraphrases_path) if paraphrases_path else stress_paraphrase.OUT_PATH
        if not para_path.exists():
            print(f"{para_path} is missing: run `python -m evals.run stress-paraphrase --yes` first (dense_paraphrases.json).")
            return 1
        descriptions_source = "world (forced for dense)"
    timings: dict[str, float] = {}
    t0 = time.monotonic()
    try:
        cases = load_frozen_cases(Path(cases_dir))
    except CaseSetError as e:
        print(e)
        return 1
    world = load_world(WORLD_PATH)
    if descriptions_source.startswith("world"):
        descriptions: dict[str, str] = {}
        desc_sha = None
    else:
        path = Path(regen_descriptions.OUT_PATH)
        try:
            descriptions = load_descriptions(path)
        except ValueError as e:
            print(str(e).replace("mode 'full' needs", "the retrieval eval needs"))
            return 1
        desc_sha = sha256_file(path)
    covered, total = description_coverage(world.agents, descriptions)
    inner = _embeddings.HashingEmbedder() if embedder_name == "hashing" else _embeddings.FastEmbedder()
    embedder = CachedEmbedder(inner)
    timings["load_s"] = time.monotonic() - t0

    t1 = time.monotonic()
    qs: list[RQuery] = []
    seeds: dict[str, Any] = {"used": [], "skipped": [], "count": 0, "dropped": 0}
    n_frozen_cases = sum(c.split == split for c in cases)
    para_info: dict[str, Any] = {}
    if dense_mode:
        from evals.world.dense import build_dense_world, dense_queries, load_paraphrases, split_topics

        dense = build_dense_world(world)
        items, dropped_at_load = load_paraphrases(para_path, dense)
        topics = split_topics(dense)[split][:dense_topic_limit]
        qs = [q for q in dense_queries(dense, items, split) if q.case_id.removeprefix("dense:") in set(topics)]
        para_info = {"file": para_path.name, "sha256": sha256_file(para_path), "dropped_at_load": dropped_at_load,
                     "skipped_topics": [t for t in topics if t not in items]}
    if not dense_mode and queries in ("frozen", "all"):
        qs += case_queries(cases, world, split)
    if not dense_mode and queries in ("template", "all"):
        ts = template_queries(world, load_cases(EXAMPLES), cases, n_template)
        qs += ts.queries
        seeds = {"used": ts.seeds, "skipped": ts.skipped_seeds, "count": len(ts.queries), "dropped": ts.dropped}
    timings["queries_s"] = time.monotonic() - t1

    t2 = time.monotonic()
    result = evaluate(qs, world, sizes, embedder, descriptions)
    timings["evaluate_s"] = time.monotonic() - t2

    now = datetime.now(timezone.utc)
    run_dir = _run_dir(Path(out_root), now, purpose or ("retrieval-dense" if dense_mode else "retrieval"))
    counts = {g: sum(q.group == g for q in qs) for g in ("frozen", "original", "unrelated_history", "template")}
    counts["frozen_cases_in_split"] = n_frozen_cases if queries != "template" else 0
    counts["skipped_empty_expected"] = (n_frozen_cases - counts["frozen"]) if queries != "template" else 0
    if dense_mode:
        counts = {"dense": len(qs), **{k: sum(q.kind == k for q in qs) for k in
                                       ("target_exact", "target_para", "topic_noname", "history_pull")}}
    counts["referenced"] = sum(q.referenced for q in qs)
    counts["skipped_n_below_required"] = result["skipped_n_below_required"]
    summary = {
        "purpose": purpose, "command": command, "date_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "run_folder": run_dir.name, "git": git_note(), "split": split, "sizes": sorted(set(sizes)),
        "queries": queries, "embedder": embedder_name,
        "case_set_sha256": sha256_file(Path(cases_dir) / "MANIFEST.json") if read_manifest(cases_dir) else None,
        "descriptions": {"source": descriptions_source, "sha256": desc_sha, "covered": covered, "total": total},
        "seeds": seeds, "counts": counts, "timings": timings,
        "headline": (_dense_headline(result, split) if dense_mode
                     else _headline(result, split, sorted(set(sizes)))),
    }
    if dense_mode:
        summary["world"] = "dense"
        summary["paraphrases"] = para_info
    t3 = time.monotonic()
    run_dir.mkdir(parents=True)
    (run_dir / "retrieval.json").write_text(json.dumps({
        "config": asdict(_DEFAULT), "ks": list(KS), "split": split, "sizes": sorted(set(sizes)),
        "cells": result["cells"], "cells_unreferenced": result["cells_unreferenced"],
        "skipped_n_below_required": result["skipped_n_below_required"]}, indent=1) + "\n", encoding="utf-8")
    with (run_dir / "queries.jsonl").open("w", encoding="utf-8") as fh:
        for r in result["rows"]:
            fh.write(json.dumps({k: v for k, v in r.items() if k not in ("recall", "all_found", "person_cover",
                                                                         "len", "rr")}) + "\n")
    (run_dir / "report.md").write_text(
        (render_dense_report if dense_mode else render_report)(summary, result), encoding="utf-8")
    timings["write_s"] = time.monotonic() - t3
    (run_dir / "summary.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")

    exp = Path(experiments) if experiments else Path(out_root) / "EXPERIMENTS.md"
    if not exp.exists():
        exp.parent.mkdir(parents=True, exist_ok=True)
        exp.write_text(EXPERIMENTS_HEADER, encoding="utf-8")
    row = [summary["date_utc"][:10], run_dir.name, purpose or "–", summary["headline"], "$0 (offline)"]
    with exp.open("a", encoding="utf-8") as fh:
        fh.write("| " + " | ".join(_cell(x) for x in row) + " |\n")
    print(f"Wrote {run_dir}: {summary['headline']} ({len(qs)} queries, no LLM calls, $0)")
    return 0
