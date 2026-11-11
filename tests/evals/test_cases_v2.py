"""Task 16c: ``build-cases-v2``, manifest, ``freeze_case_set(frozen_on=)``, dense names, retrieval template productizing.

Builds only into tmp_path; never touches ``evals/cases/v2``.
"""
import dataclasses
import json
from pathlib import Path

import pytest

from evals import caseset
from evals import retrieval_eval as re_mod
from evals import run as run_mod
from evals.caseset import (CaseSetError, V1_DIR, freeze_case_set, load_frozen_cases, read_manifest, sha256_file,
                           verify_case_set)
from evals.paraphrase import check_paraphrase
from evals.product_history import OFF_PRODUCT
from evals.retrieval_eval import expected_for, template_queries
from evals.schema import case_to_dict, load_cases, save_case, validate_cases
from evals.world import dense
from evals.world.generate import EXAMPLES, WORLD_PATH
from evals.world.roster import load_world

V1 = V1_DIR


@pytest.fixture(scope="module")
def world():
    return load_world(WORLD_PATH)


@pytest.fixture(scope="module")
def v1_cases():
    return load_frozen_cases(V1)


@pytest.fixture(scope="module")
def v2_dir(tmp_path_factory):
    out = tmp_path_factory.mktemp("v2") / "v2"
    run_mod.build_cases_v2(src=V1, out_dir=out)
    return out


@pytest.fixture(scope="module")
def v2_cases(v2_dir):
    return load_cases(v2_dir)


def _strip(c, *keys):
    d = case_to_dict(c)
    return {k: v for k, v in d.items() if k not in keys}


def _copy_set(src, dst):
    dst.mkdir()
    for p in src.glob("*.json"):
        (dst / p.name).write_bytes(p.read_bytes())
    return dst


def test_v2_dir_constant():
    assert caseset.V2_DIR == V1_DIR.parent / "v2"


def test_invariance_and_changed_list(v1_cases, v2_cases, v2_dir):
    assert len(v2_cases) == 49
    v1 = {c.id: c for c in v1_cases}
    differing = []
    for c in v2_cases:
        assert _strip(c, "ia_history", "context_agents") == _strip(v1[c.id], "ia_history")
        if case_to_dict(c)["ia_history"] != case_to_dict(v1[c.id])["ia_history"]:
            differing.append(c.id)
    changed = read_manifest(v2_dir)["changed"]
    assert len(changed) == 38
    assert changed == sorted(changed) == sorted(differing)


def test_no_off_product_lines(v2_cases):
    bad = [(c.id, t.text) for c in v2_cases for t in c.ia_history if t.text in OFF_PRODUCT]
    assert bad == []


def test_manifest_contents(v1_cases, v2_dir):
    m, v1m = read_manifest(v2_dir), read_manifest(V1)
    assert m["version"] == "v2" and m["generator"] == "evals.product_history"
    assert m["derived_from"] == {"dir": "evals/cases/v1", "manifest_sha256": sha256_file(V1 / "MANIFEST.json")}
    assert m["world_sha256"] == sha256_file(WORLD_PATH)
    assert m["n_cases"] == 49 and len(m["cases"]) == 49
    assert [e["id"] for e in m["cases"]] == sorted(e["id"] for e in m["cases"])
    assert set(m["cases"][0]) == {"id", "category", "split", "source", "file", "sha256"}
    assert m["paraphrase"] == v1m["paraphrase"] and m["amendments"] == v1m["amendments"]
    assert "frozen" not in m and "frozen_on" not in m
    assert (v2_dir / "MANIFEST.json").read_text().endswith("}\n")
    assert verify_case_set(v2_dir) == []


def test_freeze_records_given_date_and_loads(v2_dir, tmp_path):
    d = _copy_set(v2_dir, tmp_path / "f")
    m = freeze_case_set(d, frozen_on="2026-11-09")
    assert m["frozen"] is True and m["frozen_on"] == "2026-11-09"
    assert read_manifest(d)["frozen_on"] == "2026-11-09"
    assert len(load_frozen_cases(d)) == 49
    # an existing frozen_on wins
    m2 = freeze_case_set(d, frozen_on="2030-01-01")
    assert m2["frozen_on"] == "2026-11-09"


def test_freeze_defaults_to_FROZEN_ON_without_argument(v2_dir, tmp_path):
    d = _copy_set(v2_dir, tmp_path / "g")
    assert freeze_case_set(d)["frozen_on"] == caseset.FROZEN_ON


def test_freeze_cli_passes_todays_utc_date(v2_dir, tmp_path):
    from datetime import datetime, timezone
    d = _copy_set(v2_dir, tmp_path / "h")
    assert run_mod.main(["freeze-cases", "--dir", str(d)]) == 0
    assert read_manifest(d)["frozen_on"] == datetime.now(timezone.utc).date().isoformat()


def test_build_is_deterministic(v2_dir, tmp_path):
    other = tmp_path / "again"
    run_mod.build_cases_v2(src=V1, out_dir=other)
    a = sorted(p.name for p in v2_dir.glob("*.json"))
    assert a == sorted(p.name for p in other.glob("*.json"))
    for n in a:
        assert (v2_dir / n).read_bytes() == (other / n).read_bytes(), n


def test_build_removes_stale_json(tmp_path):
    out = tmp_path / "o"
    out.mkdir()
    (out / "stale.json").write_text("{}")
    run_mod.build_cases_v2(src=V1, out_dir=out)
    assert not (out / "stale.json").exists()


def test_build_prints_summary_line(tmp_path, capsys):
    out = tmp_path / "p"
    run_mod.build_cases_v2(src=V1, out_dir=out)
    line = capsys.readouterr().out.strip()
    assert line.startswith(f"Wrote {out}: 49 cases, 38 changed, ")
    assert line.endswith(f"context agents. Review, then: python -m evals.run freeze-cases --dir {out}")


def test_refuses_frozen_out_dir_without_force(v2_dir, tmp_path):
    d = _copy_set(v2_dir, tmp_path / "fr")
    freeze_case_set(d, frozen_on="2026-11-09")
    with pytest.raises(CaseSetError, match="frozen"):
        run_mod.build_cases_v2(src=V1, out_dir=d)
    run_mod.build_cases_v2(src=V1, out_dir=d, force_unfreeze=True)
    assert not caseset.is_frozen(d)


def test_refuses_unfrozen_src(v2_dir, tmp_path):
    with pytest.raises(CaseSetError):
        run_mod.build_cases_v2(src=v2_dir, out_dir=tmp_path / "x")


def test_offline_checks_on_built_set(world, v1_cases, v2_cases, v2_dir):
    assert validate_cases(v2_cases) == []
    v1 = {c.id: c for c in v1_cases}
    for c in v2_cases:
        if c.original_message:
            def probs(case):
                return check_paraphrase(dataclasses.replace(case, message=case.original_message), case.message, world)
            assert probs(c) == probs(v1[c.id]), c.id
        assert expected_for(c, world) == expected_for(v1[c.id], world), c.id
    dense.assert_names_clear(dense.PEOPLE, world, cases_dir=v2_dir)


def test_assert_names_clear_scans_context_agents(world, v2_cases, tmp_path):
    with_ctx = next(c for c in v2_cases if c.context_agents)
    ag = with_ctx.context_agents[0]
    name = dense.PEOPLE[0].display_name
    bad = dataclasses.replace(ag, description=f"{ag.description} Asked {name} about it.")
    d = tmp_path / "ctx"
    d.mkdir()
    save_case(dataclasses.replace(with_ctx, context_agents=[bad, *with_ctx.context_agents[1:]]), d / "c.json")
    with pytest.raises(ValueError, match="dense person names"):
        dense.assert_names_clear(dense.PEOPLE, world, cases_dir=d)


def test_template_queries_use_context_agents_and_clean_text(world, v2_cases, monkeypatch):
    examples = load_cases(EXAMPLES)
    seen = {}
    real = re_mod.productize  # AttributeError until wired
    def spy(case, w, key):
        out = real(case, w, key)
        seen[key] = out
        return out
    monkeypatch.setattr(re_mod, "productize", spy)
    a = template_queries(world, examples, v2_cases, n_template=20)
    b = template_queries(world, examples, v2_cases, n_template=20)
    assert len(a.queries) == 20 and a == b
    for q in a.queries:
        case = seen[q.id]
        req = {x.id for x in q.required}
        want = {t.agent_id for t in case.ia_history if t.role == "agent"} - req
        assert {x.id for x in q.extra_agents} == want
        assert not any(line in q.query for line in OFF_PRODUCT)
    assert any(q.extra_agents for q in a.queries)


def test_template_queries_drop_on_productize_value_error(world, v2_cases, monkeypatch):
    examples = load_cases(EXAMPLES)
    def boom(case, w, key):
        raise ValueError("no")
    monkeypatch.setattr(re_mod, "productize", boom)
    ts = template_queries(world, examples, v2_cases, n_template=5, max_seeds=2)
    assert ts.queries == [] and ts.dropped > 0


def test_cli_build_cases_v2(tmp_path, capsys):
    out = tmp_path / "cli"
    assert run_mod.main(["build-cases-v2", "--src", str(V1), "--out", str(out)]) == 0
    assert len(list(out.glob("C*.json"))) + len(list(out.glob("*.json"))) >= 49
    assert (out / "MANIFEST.json").exists()
    assert "Wrote" in capsys.readouterr().out


def test_default_case_set_is_v2_and_build_default_stays_v1():
    import inspect

    from evals.caseset import CASES_DIR, V2_DIR
    from evals.run import build_cases

    assert caseset.CASES_DIR == V2_DIR == CASES_DIR
    cases = load_frozen_cases(CASES_DIR)
    assert len(cases) == 49
    assert read_manifest(CASES_DIR)["version"] == "v2"
    assert inspect.signature(build_cases).parameters["out_dir"].default == V1_DIR
