"""Task 12c: ``python -m evals.run stress-paraphrase`` (FakeLLM only; the paid command is never run).

Interface assumed: ``evals.stress_paraphrase`` with ``default_llm()``, ``default_model()``, ``leaks(paraphrase,
forbidden) -> set[str]``, ``forbidden_words(dense, topic) -> set[str]``; hidden CLI flag ``--out PATH`` (default
``STRESS_DIR / "dense_paraphrases.json"``). The LLM is called as ``llm(model=, system=, messages=[...])``.
"""
import hashlib
import json
import re

import pytest

from evals import run as run_mod
from evals.harness.fake_llm import FakeLLM
from evals.pricing import HAIKU
from evals.world.dense import build_dense_world
from evals.world.generate import WORLD_PATH
from evals.world.roster import load_world

CLEAN = "zzq wobble"


@pytest.fixture(scope="module")
def dense():
    return build_dense_world(load_world(WORLD_PATH))


def _install(monkeypatch, llm):
    from evals import stress_paraphrase as sp
    monkeypatch.setattr(sp, "default_llm", lambda: llm)
    monkeypatch.setattr(sp, "default_model", lambda: HAIKU)
    return sp


class Scripted(FakeLLM):
    """Reply by prompt: ``rules`` maps a substring of the user prompt to a reply string or an Exception."""

    def __init__(self, rules=None, usage=None):
        super().__init__([])
        self.rules, self.usage = rules or {}, usage

    async def __call__(self, **kw):
        self.requests.append(kw)
        text = kw["messages"][-1]["content"]
        for key, reply in self.rules.items():
            if key in text:
                if isinstance(reply, Exception):
                    raise reply
                if callable(reply):
                    reply = reply(sum(key in r["messages"][-1]["content"] for r in self.requests))
                    if isinstance(reply, Exception):
                        raise reply
                return self._resp(reply)
        return self._resp(CLEAN)

    def _resp(self, text):
        return {"choices": [{"message": {"role": "assistant", "content": text}}],
                "usage": self.usage or {"prompt_tokens": 100, "completion_tokens": 20}}

    def calls_for(self, key):
        return sum(key in r["messages"][-1]["content"] for r in self.requests)


def _main(path, *extra):
    return run_mod.main(["stress-paraphrase", "--out", str(path), *extra])


def test_leaks_rules():
    from evals.stress_paraphrase import leaks
    assert leaks("Vendor contracts", {"vendor", "contract"}) == {"vendor", "contract"}
    assert leaks("the new thing", {"the", "and"}) == set()
    assert leaks("budgets", {"budget"}) == {"budget"} and leaks("budget", {"budgets"}) == {"budget"}
    assert leaks("my Q4 plan", {"q4"}) == {"q4"}
    assert leaks("zzq wobble", {"vendor"}) == set()


def test_forbidden_words_cover_topic_words_and_every_dense_agent_minus_names(dense):
    from evals.stress_paraphrase import forbidden_words
    f = forbidden_words(dense, "vendor contract")
    assert {"vendor", "contract", "redline", "legal", "reviewing"} <= f   # short, phrase, reply
    names = {w.casefold() for p in dense.people for w in p.display_name.split()}
    assert not f & names
    # words of the other-topic agents are not needed, but every same-topic agent's text is covered
    from evals.textwords import content_words
    for p in dense.people:
        a = dense.agents[dense.by_person_topic[(p.email, "vendor contract")]]
        assert content_words(a.name + " " + a.description) - names <= f
    doc = forbidden_words(dense, "slide deck")
    assert {"slide", "deck", "final"} <= doc


def test_refuses_without_yes_and_prints_estimate(tmp_path, monkeypatch, capsys):
    fake = FakeLLM.text(CLEAN)
    _install(monkeypatch, fake)
    out = tmp_path / "p.json"
    assert _main(out) == 2
    printed = capsys.readouterr().out
    assert "Estimated cost" in printed and "--yes" in printed
    assert fake.requests == [] and not out.exists()


def test_refuses_when_estimate_exceeds_max_cost(tmp_path, monkeypatch, capsys):
    fake = FakeLLM.text(CLEAN)
    _install(monkeypatch, fake)
    assert _main(tmp_path / "p.json", "--yes", "--max-cost", "0.0001") == 1
    assert fake.requests == [] and not (tmp_path / "p.json").exists()


def test_output_file_shape_and_spend_from_usage(tmp_path, monkeypatch):
    fake = Scripted()
    sp = _install(monkeypatch, fake)
    out = tmp_path / "p.json"
    assert _main(out, "--yes") == 0
    assert len(fake.requests) == 48 and all(r["model"] == HAIKU for r in fake.requests)
    data = json.loads(out.read_text(encoding="utf-8"))
    assert set(data) == {"model", "generated_on", "prompt_sha256", "seed", "tokens", "cost_usd", "items", "dropped",
                         "errors", "skipped_budget"}
    assert data["model"] == HAIKU and re.fullmatch(r"\d{4}-\d{2}-\d{2}", data["generated_on"])
    assert re.fullmatch(r"[0-9a-f]{64}", data["prompt_sha256"]) and data["seed"] == "7:dense"
    assert data["tokens"] == {"prompt": 4800, "completion": 960}
    assert data["cost_usd"] == pytest.approx(48 * (100 * 0.10 + 20 * 0.50) / 1e6)
    assert len(data["items"]) == 48 and set(data["items"].values()) == {CLEAN}
    assert data["dropped"] == [] and data["errors"] == [] and data["skipped_budget"] == []
    assert out.read_text(encoding="utf-8").endswith("\n") and json.loads(out.read_text()) == data
    sys_prompt = fake.requests[0]["system"]
    assert isinstance(sys_prompt, str) and sys_prompt


def test_prompt_lists_forbidden_words(tmp_path, monkeypatch, dense):
    from evals.stress_paraphrase import forbidden_words
    fake = Scripted()
    _install(monkeypatch, fake)
    assert _main(tmp_path / "p.json", "--yes") == 0
    req = next(r for r in fake.requests if "vendor contract" in r["messages"][-1]["content"].lower())
    prompt = req["messages"][-1]["content"].lower()
    assert all(w in prompt for w in forbidden_words(dense, "vendor contract"))


def test_leaking_paraphrase_is_retried_once_then_dropped(tmp_path, monkeypatch):
    fake = Scripted({"vendor": "vendor paperwork"})
    _install(monkeypatch, fake)
    out = tmp_path / "p.json"
    assert _main(out, "--yes") == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert fake.calls_for("vendor") == 2 and len(fake.requests) == 49
    assert "vendor contract" not in data["items"] and len(data["items"]) == 47
    (d,) = data["dropped"]
    assert d["topic"] == "vendor contract" and d["paraphrase"] == "vendor paperwork" and "vendor" in d["leaked"]
    assert data["errors"] == []


def test_leak_then_clean_retry_is_kept(tmp_path, monkeypatch):
    fake = Scripted({"vendor": lambda n: "vendor paperwork" if n == 1 else "stuff wobble"})
    _install(monkeypatch, fake)
    out = tmp_path / "p.json"
    assert _main(out, "--yes") == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["items"]["vendor contract"] == "stuff wobble"
    assert data["dropped"] == []


def test_empty_paraphrase_is_retried_then_dropped(tmp_path, monkeypatch):
    fake = Scripted({"vendor": '  ""  '})
    _install(monkeypatch, fake)
    out = tmp_path / "p.json"
    assert _main(out, "--yes") == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert fake.calls_for("vendor") == 2 and "vendor contract" not in data["items"]
    assert [d["topic"] for d in data["dropped"]] == ["vendor contract"]


def test_quotes_are_stripped_like_paraphrase_clean(tmp_path, monkeypatch):
    fake = Scripted({"vendor": '"stuff wobble"'})
    _install(monkeypatch, fake)
    out = tmp_path / "p.json"
    assert _main(out, "--yes") == 0
    assert json.loads(out.read_text(encoding="utf-8"))["items"]["vendor contract"] == "stuff wobble"


def test_infrastructure_error_retried_once_then_recorded(tmp_path, monkeypatch):
    fake = Scripted({"vendor": RuntimeError("boom")})
    _install(monkeypatch, fake)
    out = tmp_path / "p.json"
    assert _main(out, "--yes") == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert fake.calls_for("vendor") == 2
    assert "vendor contract" not in data["items"] and len(data["items"]) == 47 and data["dropped"] == []
    assert {e["topic"] for e in data["errors"]} == {"vendor contract"}
    assert all({"topic", "attempt", "error"} <= set(e) for e in data["errors"])
    assert "boom" in data["errors"][0]["error"]


def test_infrastructure_error_then_success_is_not_an_error(tmp_path, monkeypatch):
    fake = Scripted({"vendor": lambda n: RuntimeError("flaky") if n == 1 else "stuff wobble"})
    _install(monkeypatch, fake)
    out = tmp_path / "p.json"
    assert _main(out, "--yes") == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["items"]["vendor contract"] == "stuff wobble" and data["errors"] == []


def test_stops_before_max_cost(tmp_path, monkeypatch):
    fake = Scripted(usage={"prompt_tokens": 1_000_000, "completion_tokens": 0})   # $0.10 per call
    _install(monkeypatch, fake)
    out = tmp_path / "p.json"
    assert _main(out, "--yes", "--max-cost", "0.25") == 0
    data = json.loads(out.read_text(encoding="utf-8"))
    assert len(fake.requests) == 3 and len(data["items"]) == 3
    assert len(data["skipped_budget"]) == 45 and data["cost_usd"] == pytest.approx(0.30)
    assert set(data["skipped_budget"]).isdisjoint(data["items"])


def test_refuses_to_overwrite_without_force(tmp_path, monkeypatch, capsys):
    fake = Scripted()
    _install(monkeypatch, fake)
    out = tmp_path / "p.json"
    out.write_text('{"frozen": true}\n', encoding="utf-8")
    assert _main(out, "--yes") == 1
    assert fake.requests == [] and out.read_text(encoding="utf-8") == '{"frozen": true}\n'
    assert _main(out, "--yes", "--force") == 0
    assert len(json.loads(out.read_text(encoding="utf-8"))["items"]) == 48


def test_default_output_path_is_the_stress_dir():
    from evals import stress_paraphrase as sp
    assert sp.STRESS_DIR.name == "stress" and sp.STRESS_DIR.parent.name == "world"
    assert sp.OUT_PATH == sp.STRESS_DIR / "dense_paraphrases.json"
