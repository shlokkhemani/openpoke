import asyncio
from pathlib import Path

from evals.expand import expand
from evals.harness.fake_llm import FakeLLM
from evals.paraphrase import ParaphraseReport, paraphrase
from evals.pricing import HAIKU
from evals.schema import load_cases
from evals.world.roster import load_world

WORLD = load_world(Path("evals/world/world.json"))
CASES = expand(WORLD, load_cases(Path("evals/cases/examples")))
MODEL = HAIKU


class ScriptedLLM:
    """Replies with the scripted strings (or raises scripted exceptions), then repeats the last."""

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    async def __call__(self, **kw):
        self.calls.append(kw)
        r = self.replies[min(len(self.calls) - 1, len(self.replies) - 1)]
        if isinstance(r, Exception):
            raise r
        return {"choices": [{"message": {"role": "assistant", "content": r}}],
                "usage": {"prompt_tokens": 100, "completion_tokens": 20}}


def one_template(category="trigger_management"):
    return next(c for c in CASES if c.source == "template" and c.category == category)


def run(cases, llm, report=None):
    return asyncio.run(paraphrase(cases, MODEL, llm, world=WORLD, report=report))


def test_hand_cases_are_never_sent_to_the_model():
    hand = [c for c in CASES if c.source == "hand"]
    llm = ScriptedLLM(["x"])
    out = run(hand, llm)
    assert llm.calls == []
    assert [c.message for c in out] == [c.message for c in hand]


def test_valid_rewrite_is_kept_and_original_recorded():
    case = one_template()
    # keep the digits and people of the original so the checks pass
    rewritten = case.message
    llm = FakeLLM.text(rewritten)
    report = ParaphraseReport()
    out = run([case], llm, report)
    assert out[0].source == "paraphrased"
    assert out[0].original_message == case.message
    assert (report.kept, report.retried, report.reverted) == (1, 0, 0)
    assert report.prompt_tokens == 100 and report.completion_tokens == 20


def test_failed_check_retries_once_then_keeps_original():
    case = one_template("ambiguous_person")
    bad = ScriptedLLM(["Email Alice Chen alice.chen@northwind.io now"])
    report = ParaphraseReport()
    out = run([case], bad, report)
    assert len(bad.calls) == 2
    assert out[0].message == case.message and out[0].source == "template" and out[0].original_message is None
    assert (report.kept, report.retried, report.reverted) == (0, 1, 1)
    assert report.errors == []


def test_second_attempt_can_succeed():
    case = one_template()
    llm = ScriptedLLM(["bad\nmultiline", case.message])
    report = ParaphraseReport()
    out = run([case], llm, report)
    assert len(llm.calls) == 2 and out[0].source == "paraphrased"
    assert (report.kept, report.retried, report.reverted) == (1, 1, 0)


def test_infra_error_retried_once_then_reverted_and_recorded():
    case = one_template()
    llm = ScriptedLLM([RuntimeError("boom")])
    report = ParaphraseReport()
    out = run([case], llm, report)
    assert len(llm.calls) == 2
    assert out[0].message == case.message
    assert (report.kept, report.retried, report.reverted) == (0, 1, 1)
    assert len(report.errors) == 1 and report.errors[0]["case_id"] == case.id
    assert "boom" in report.errors[0]["error"]


def test_infra_error_then_success():
    case = one_template()
    llm = ScriptedLLM([RuntimeError("flaky"), case.message])
    report = ParaphraseReport()
    out = run([case], llm, report)
    assert out[0].source == "paraphrased" and report.errors == [] and report.retried == 1


def test_prompt_states_the_constraints_and_message_only():
    case = one_template("ambiguous_person")
    llm = ScriptedLLM([case.message])
    run([case], llm)
    kw = llm.calls[0]
    text = (kw.get("system") or "") + " ".join(m["content"] for m in kw["messages"])
    assert case.message in text
    assert "only the rewritten message" in text.lower()
    assert "surname" in text.lower()
    assert kw["model"] == MODEL


def test_infra_error_on_first_attempt_logged_when_second_fails_check():
    case = one_template("ambiguous_person")
    llm = ScriptedLLM([RuntimeError("blip"), "Email Alice Chen alice.chen@northwind.io now"])
    report = ParaphraseReport()
    out = run([case], llm, report)
    assert out[0].message == case.message and report.reverted == 1
    assert len(report.errors) == 1 and "blip" in report.errors[0]["error"]
