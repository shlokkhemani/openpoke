"""Task 8: evals.run regen-descriptions (FakeLLM and tmp paths only; the paid command is never run)."""

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from evals.harness.fake_llm import FakeLLM

ROOT = Path(__file__).resolve().parents[2]
WORLD = ROOT / "evals" / "world" / "world.json"


# --- regen-descriptions ---------------------------------------------------------------------

@pytest.fixture
def mini_world(tmp_path):
    w = json.loads(WORLD.read_text(encoding="utf-8"))
    ids = [i for i, a in w["agents"].items() if a["contacts"]][:1] + [i for i, a in w["agents"].items() if not a["contacts"]][:1]
    mini = {"contacts": [], "filler_order": [], "uses": {},
            "agents": {i: w["agents"][i] for i in ids}, "logs": {i: w["logs"][i] for i in ids}}
    path = tmp_path / "world.json"
    path.write_text(json.dumps(mini), encoding="utf-8")
    return SimpleNamespace(path=path, ids=ids, out=tmp_path / "descriptions.regen.json", world=mini)


def _sha(p):
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def _regen(mini, *extra):
    from evals.run import main
    return main(["regen-descriptions", "--world", str(mini.path), "--out", str(mini.out), *extra])


def test_regen_without_yes_prints_estimate_and_writes_nothing(mini_world, monkeypatch, capsys):
    from evals import regen_descriptions as rd
    fake = FakeLLM.text("should not be called")
    monkeypatch.setattr(rd, "default_llm", lambda: fake)
    before = _sha(mini_world.path)
    code = _regen(mini_world)
    out = capsys.readouterr().out
    assert code != 0
    assert "Estimated cost" in out and "--yes" in out
    assert fake.requests == []
    assert not mini_world.out.exists()
    assert _sha(mini_world.path) == before


def test_regen_with_yes_writes_descriptions_and_leaves_world_untouched(mini_world, monkeypatch):
    from evals import regen_descriptions as rd
    fake = FakeLLM.text("Regenerated description.")
    monkeypatch.setattr(rd, "default_llm", lambda: fake)
    before = _sha(mini_world.path)
    assert _regen(mini_world, "--yes", "--max-cost", "5") == 0
    data = json.loads(mini_world.out.read_text(encoding="utf-8"))
    assert set(data) == {"model", "generated_on", "descriptions"}
    assert data["descriptions"] == {i: "Regenerated description." for i in mini_world.ids}
    assert len(fake.requests) == len(mini_world.ids)
    assert _sha(mini_world.path) == before


def test_regen_prompt_uses_first_request_last_response_and_contacts(mini_world, monkeypatch):
    from evals import regen_descriptions as rd
    fake = FakeLLM.text("d")
    monkeypatch.setattr(rd, "default_llm", lambda: fake)
    assert _regen(mini_world, "--yes") == 0
    with_contacts = mini_world.ids[0]
    log = mini_world.world["logs"][with_contacts]
    first_req = next(t for k, t in log if k == "agent_request")
    last_resp = [t for k, t in log if k == "agent_response"][-1]
    email = mini_world.world["agents"][with_contacts]["contacts"][0]["email"]
    prompt = str(fake.requests[0]["messages"])
    assert first_req in prompt and last_resp in prompt and email in prompt


def test_regen_does_not_touch_server_data(mini_world, monkeypatch):
    from evals import regen_descriptions as rd
    monkeypatch.setattr(rd, "default_llm", lambda: FakeLLM.text("d"))
    data_dir = ROOT / "server" / "data"
    before = sorted(p.name for p in data_dir.glob("*")) if data_dir.exists() else []
    _regen(mini_world, "--yes")
    assert (sorted(p.name for p in data_dir.glob("*")) if data_dir.exists() else []) == before


# --- fix round 1: fallbacks, cap, spend accounting ---------------------------------------------

class NoUsageLLM(FakeLLM):
    async def __call__(self, **kwargs):
        response = await super().__call__(**kwargs)
        response.pop("usage")
        return response


def test_regen_cap_trips_stops_calls_writes_nothing(mini_world, monkeypatch, capsys):
    from evals import regen_descriptions as rd

    class Pricey(FakeLLM):
        PROMPT_TOKENS = 1_000_000  # one call costs far more than the cap

    fake = Pricey.text("A description.")
    monkeypatch.setattr(rd, "default_llm", lambda: fake)
    code = _regen(mini_world, "--yes", "--max-cost", "0.05")
    out = capsys.readouterr().out
    assert code != 0
    assert len(fake.requests) == 1  # nothing is called once the cap is reached
    assert not mini_world.out.exists()
    assert "1 succeeded" in out and "0 fell back" in out and "1 skipped" in out


def test_regen_api_error_writes_nothing_and_prints_counts(mini_world, monkeypatch, capsys):
    from evals import regen_descriptions as rd
    from server.openrouter_client import OpenRouterError

    fake = FakeLLM.raising(OpenRouterError("500"))
    monkeypatch.setattr(rd, "default_llm", lambda: fake)
    code = _regen(mini_world, "--yes", "--max-cost", "5")
    out = capsys.readouterr().out
    assert code != 0
    assert not mini_world.out.exists()
    assert "0 succeeded" in out and "2 fell back" in out and "0 skipped" in out


def test_regen_empty_output_counts_as_fallback(mini_world, monkeypatch, capsys):
    from evals import regen_descriptions as rd

    monkeypatch.setattr(rd, "default_llm", lambda: FakeLLM.text("  "))
    assert _regen(mini_world, "--yes", "--max-cost", "5") != 0
    assert not mini_world.out.exists()
    assert "2 fell back" in capsys.readouterr().out


def test_regen_counts_estimate_when_usage_missing(mini_world, tmp_path):
    import asyncio
    from evals import regen_descriptions as rd
    from evals.world.roster import load_world

    w = json.loads(mini_world.path.read_text(encoding="utf-8"))
    src = w["agents"][mini_world.ids[1]]
    w["agents"] = {"a1": {**src, "id": "a1"}, "a2": {**src, "id": "a2"}}
    w["logs"] = {"a1": w["logs"][mini_world.ids[1]], "a2": w["logs"][mini_world.ids[1]]}
    twin = tmp_path / "twin.json"
    twin.write_text(json.dumps(w), encoding="utf-8")
    world = load_world(twin)
    _, _, _, usd = rd.estimate(world, "anthropic/claude-haiku-5.5")
    llm = NoUsageLLM.text("A description.")
    result = asyncio.run(rd.regenerate(world, llm, "anthropic/claude-haiku-5.5", max_cost=usd * 0.75))
    assert len(llm.requests) == 1  # the first call was counted at its estimate, so the second would cross the cap
    assert (result.succeeded, result.fell_back, result.skipped) == (1, 0, 1)
