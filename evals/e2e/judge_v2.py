"""Rubric judge (v2): 16 yes/no questions, half answered from the trace, half by a strong model.

    .venv/bin/python evals/e2e/judge_v2.py evals/e2e/results/<run>          # score every cell lacking judge_v2
    .venv/bin/python evals/e2e/judge_v2.py evals/e2e/results/<run> --force  # rescore all
    .venv/bin/python evals/e2e/judge_v2.py <run> --no-llm                   # harness questions only

Score = 100 * sum(weight * yes) / sum(weight over applicable questions). See RUBRIC.md.
The v1 judge (free-form criteria + 1-5 score) is left untouched in `judge`; this writes `judge_v2`.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parents[1]))

import run_e2e  # noqa: E402
from run_e2e import CASES_PATH, _short, combine_verdict, outcome_judge, resolve_cases  # noqa: E402
from server.config import get_settings  # noqa: E402

_real_llm = run_e2e._real_llm


# ---------------------------------------------------------------------------
# Spend guard: every judge call is metered from the provider's usage block; stop at --budget.
# ---------------------------------------------------------------------------
_PRICES = {  # $ per million tokens (input, output); unknown models fall back to Sonnet pricing
    "anthropic/claude-haiku-4.5": (1.0, 5.0),
    "anthropic/claude-sonnet-4": (3.0, 15.0),
    "deepseek/deepseek-v4-flash": (0.07, 0.14),
}


class BudgetExceeded(Exception):
    pass


class SpendMeter:
    def __init__(self, budget_usd: float) -> None:
        self.budget = budget_usd
        self.spent = 0.0
        self.calls = 0

    def wrap(self, real):
        async def _metered(*, model, **kw):
            if self.spent >= self.budget:
                raise BudgetExceeded(f"judge budget ${self.budget:.2f} reached (spent ${self.spent:.3f})")
            resp = await real(model=model, **kw)
            u = resp.get("usage") or {}
            pi, po = _PRICES.get(model, (3.0, 15.0))
            self.spent += (u.get("prompt_tokens") or 0) / 1e6 * pi + (u.get("completion_tokens") or 0) / 1e6 * po
            self.calls += 1
            return resp
        return _metered

SEND_TOOLS = {"GMAIL_SEND_DRAFT", "GMAIL_REPLY_TO_THREAD", "GMAIL_FORWARD_MESSAGE"}

# id, criterion, question, answered_by, weight
QUESTIONS: List[Tuple[str, str, str, str, int]] = [
    ("q1", "planning", "First action fit the request: answered directly when the answer was already in context, dispatched a worker when work was needed", "judge", 2),
    ("q2", "planning", "Dispatch instructions carried every detail the worker needed (addresses, ids, constraints such as the cc rule); n/a if nothing was dispatched", "judge", 2),
    ("q3", "execution", "Every Gmail call used correct arguments (thread/draft ids, recipients, cc)", "judge", 2),
    ("q4", "execution", "No Gmail call failed on a bad argument", "harness", 1),
    ("q5", "observation", "Acted correctly on results: right email among distractors, returned draft id reused", "judge", 2),
    ("q6", "observation", "Replies to the user matched reality; no 'sent' before the send actually happened", "judge", 2),
    ("q7", "replanning", "After a failure or empty result, the next move was an adjustment rather than a repeat or a give-up; n/a if nothing failed", "judge", 1),
    ("q8", "termination", "No send before the user's confirmation turn", "harness", 2),
    ("q9", "termination", "Did not re-ask once the user had confirmed; n/a if no confirmation was involved", "judge", 1),
    ("q10", "termination", "Stopped when done: no further interaction rounds after the final state was reached", "harness", 1),
    ("q11", "loops", "No duplicate Gmail calls with identical arguments", "harness", 1),
    ("q12", "loops", "At most one wait per turn", "harness", 1),
    ("q13", "loops", "No re-dispatch to a worker that was still running", "harness", 1),
    ("q14", "unnecessary", "Dispatch count within the case's expected maximum", "harness", 1),
    ("q15", "unnecessary", "No searches, drafts, or messages the task did not need", "judge", 1),
    ("q16", "unnecessary", "LLM calls within 2x the case's ideal count", "harness", 1),
    ("q17", "planning", "Dispatched the worker the case expects (the one holding the needed context); n/a when the case names none", "harness", 2),
]
JUDGE_QIDS = [q[0] for q in QUESTIONS if q[3] == "judge"]

# Fallback expectations when a case has no `expected` block.
_DEFAULT_EXPECTED = {"dispatches_max": 2, "ideal_calls": 8}


# ---------------------------------------------------------------------------
# Trace walk: assign a phase to every Gmail call and flag callback rounds
# ---------------------------------------------------------------------------
def _walk(record: Dict[str, Any], llm_calls: List[Dict[str, Any]], world_calls: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Merge into one ordered step list using record['events'] as the ordering oracle."""
    llm = sorted((c for c in llm_calls if c.get("phase") != "seed"), key=lambda c: c.get("t0", 0))
    steps: List[Dict[str, Any]] = []
    li = wi = 0
    phase = llm[0]["phase"] if llm else "turn1"
    for e in record.get("events") or []:
        if e.startswith("[gmail]"):
            if wi < len(world_calls):
                w = world_calls[wi]; wi += 1
                steps.append({"kind": "gmail", "phase": phase, "tool": w["tool"], "ok": w.get("ok", True), "args": w.get("args")})
        elif li < len(llm):
            c = llm[li]; li += 1
            phase = c["phase"]
            first = (c.get("messages") or [{}])[0].get("content")
            steps.append({"kind": "llm", "phase": phase, "component": c["component"], "agent": c.get("agent"),
                          "callback": c["component"] == "interaction_agent" and isinstance(first, str) and "<new_agent_message>" in first,
                          "tools": [t["name"] for t in c.get("tool_calls") or []],
                          "tool_calls": c.get("tool_calls") or [],
                          "text": c.get("assistant_text") or "", "blocked": c.get("gate_blocked"), "error": c.get("error")})
    for c in llm[li:]:
        steps.append({"kind": "llm", "phase": c["phase"], "component": c["component"], "agent": c.get("agent"), "callback": False,
                      "tools": [t["name"] for t in c.get("tool_calls") or []], "tool_calls": c.get("tool_calls") or [],
                      "text": c.get("assistant_text") or "", "blocked": c.get("gate_blocked"), "error": c.get("error")})
    for w in world_calls[wi:]:
        steps.append({"kind": "gmail", "phase": phase, "tool": w["tool"], "ok": w.get("ok", True), "args": w.get("args")})
    return steps


def _arg(tc: Dict[str, Any], key: str) -> Optional[str]:
    a = tc.get("arguments")
    if isinstance(a, str):
        try:
            a = json.loads(a)
        except Exception:
            return None
    return a.get(key) if isinstance(a, dict) else None


# ---------------------------------------------------------------------------
# Harness questions
# ---------------------------------------------------------------------------
def harness_answers(record: Dict[str, Any], case: Dict[str, Any], steps: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    cnt = record.get("counters") or {}
    turns = case.get("turns") or []
    n_turns = len(turns)
    expected = {**_DEFAULT_EXPECTED, **(case.get("expected") or {})}
    ans: Dict[str, Dict[str, Any]] = {}

    # q4 no failed gmail calls
    failed = [s for s in steps if s["kind"] == "gmail" and not s["ok"]]
    ans["q4"] = {"answer": "no" if failed else "yes",
                 "reason": f"{len(failed)} failed Gmail call(s): " + ", ".join(s["tool"] for s in failed[:3]) if failed else "all Gmail calls succeeded"}

    # q8 no send before the confirmation turn (= last turn; if the case forbids sends, any send is a violation)
    sends = [s for s in steps if s["kind"] == "gmail" and s["tool"] in SEND_TOOLS and s["ok"]]
    if (case.get("success") or {}).get("sent_count_max") == 0:
        early = sends
        why = "case allows no sends"
    else:
        confirm_phase = f"turn{n_turns}"
        early = [s for s in sends if s["phase"] != confirm_phase]
        why = f"confirmation turn is turn{n_turns}"
    if not sends:
        ans["q8"] = {"answer": "yes" if (case.get("success") or {}).get("sent_count_max") == 0 else "na", "reason": "nothing was sent"}
    else:
        ans["q8"] = {"answer": "no" if early else "yes",
                     "reason": (f"{len(early)} send(s) in {sorted({s['phase'] for s in early})} ({why})" if early else f"all sends in the confirmation turn ({why})")}

    # q10 stopped when done: IA rounds after the last Gmail call (final turn) that produced nothing user-visible
    last_phase = f"turn{n_turns}"
    final_steps = [s for s in steps if s["phase"] == last_phase]
    gm_idx = [i for i, s in enumerate(final_steps) if s["kind"] == "gmail"]
    after = final_steps[gm_idx[-1] + 1:] if gm_idx else final_steps
    ia_after = [s for s in after if s["kind"] == "llm" and s["component"] == "interaction_agent"]
    silent = [s for s in ia_after if not s["text"] and not any(t in ("send_message_to_user", "send_draft") for t in s["tools"])]
    if gm_idx:
        ans["q10"] = {"answer": "yes" if len(silent) <= 1 else "no",
                      "reason": f"{len(ia_after)} interaction rounds after the last Gmail call, {len(silent)} produced nothing for the user"}
    else:
        ia_total = sum(1 for s in steps if s["kind"] == "llm" and s["component"] == "interaction_agent")
        ans["q10"] = {"answer": "yes" if ia_total <= 2 else "no", "reason": f"no worker activity; {ia_total} interaction rounds"}

    # q11 duplicates
    dups = cnt.get("duplicate_worker_tool_calls", 0)
    ans["q11"] = {"answer": "no" if dups else "yes", "reason": f"{dups} duplicate Gmail call(s)"}

    # q12 at most one wait per turn
    waits: Dict[str, int] = {}
    for s in steps:
        if s["kind"] == "llm" and s["component"] == "interaction_agent":
            waits[s["phase"]] = waits.get(s["phase"], 0) + s["tools"].count("wait")
    over = {p: n for p, n in waits.items() if n > 1}
    ans["q12"] = {"answer": "no" if over else "yes", "reason": (f"wait calls per turn: {over}" if over else f"wait calls per turn: {waits or 'none'}")}

    # q13 re-dispatch to a running worker: same agent dispatched twice in one phase before any callback in that phase
    redispatch: List[str] = []
    for phase in sorted({s["phase"] for s in steps}):
        seen: set = set()
        for s in (x for x in steps if x["phase"] == phase and x["kind"] == "llm" and x["component"] == "interaction_agent"):
            if s["callback"]:
                break
            for tc in s["tool_calls"]:
                if tc["name"] == "send_message_to_agent":
                    name = _arg(tc, "agent_name") or "?"
                    if name in seen:
                        redispatch.append(f"{phase}:{name}")
                    seen.add(name)
    ans["q13"] = {"answer": "no" if redispatch else "yes", "reason": (f"re-dispatched before callback: {redispatch}" if redispatch else "no worker dispatched twice before it returned")}

    # q14 dispatch count
    d = cnt.get("dispatches", 0)
    ans["q14"] = {"answer": "yes" if d <= expected["dispatches_max"] else "no", "reason": f"{d} dispatch(es), expected at most {expected['dispatches_max']}"}

    # q17 expected worker reused (from the mechanical dispatched_agents_include check)
    checks = record.get("checks") or {}
    if "dispatched_agents_include" in checks:
        ans["q17"] = {"answer": "yes" if checks["dispatched_agents_include"] else "no",
                      "reason": next((f for f in record.get("failures", []) if "expected dispatch" in f), "dispatched the expected worker")}
    else:
        ans["q17"] = {"answer": "na", "reason": "case names no expected worker"}

    # q16 LLM calls
    calls = cnt.get("llm_calls", 0)
    ans["q16"] = {"answer": "yes" if calls <= 2 * expected["ideal_calls"] else "no", "reason": f"{calls} LLM calls, ideal {expected['ideal_calls']} (limit {2 * expected['ideal_calls']})"}
    return ans


# ---------------------------------------------------------------------------
# Judge questions
# ---------------------------------------------------------------------------
_TOOL = {
    "type": "function",
    "function": {
        "name": "answer_rubric",
        "description": "Answer each rubric question yes/no/na with a one-sentence reason.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_completed": {"type": "boolean", "description": "Your own view of whether the user's request was fulfilled."},
                **{qid: {"$ref": "#/$defs/ans"} for qid in JUDGE_QIDS},
            },
            "required": ["task_completed", *JUDGE_QIDS],
            "additionalProperties": False,
            "$defs": {"ans": {"type": "object", "properties": {"answer": {"type": "string", "enum": ["yes", "no", "na"]}, "reason": {"type": "string"}},
                              "required": ["answer", "reason"], "additionalProperties": False}},
        },
    },
}

_SYSTEM = """You grade the trajectory of a two-tier email assistant by answering fixed yes/no questions.

System under test: an interaction agent talks to the user and can only send_message_to_user, send_message_to_agent (dispatch a named background worker), send_draft (show a draft card; creates nothing), wait, and in some configurations recall_history (fetch older entries; a normal step). Workers do the real work with Gmail tools against a fake in-memory mailbox; lines starting [gmail] are the ground-truth calls it received. Workers may only create a draft when asked to email someone; sending needs the user's confirmation in a later turn and a second dispatch. Worker results return to the interaction agent as a callback round, which then replies to the user.

You get the task, an ideal-trajectory reference, the merged event log, the replies the user saw, the final mailbox state, and the harness outcome. Answer each question with yes, no, or na (only when the question's own n/a condition holds), plus one sentence naming the step that decided it. Answer the question as asked; do not let the overall outcome pull an answer. Call answer_rubric exactly once."""


def _prompt(record: Dict[str, Any], case: Dict[str, Any]) -> str:
    world = record.get("world") or {}
    state = [f"sent: {len(world.get('sent', []))}"]
    for s in world.get("sent", []):
        state.append(f"  - to={s.get('to')} cc={s.get('cc')} thread={s.get('thread_id')} via={s.get('via')} subject={_short(s.get('subject', ''), 80)} body={_short(s.get('body', ''), 200)}")
    state.append(f"drafts remaining: {len(world.get('drafts', []))}, drafts created during run: {world.get('drafts_created')}")
    for d in world.get("drafts", []):
        state.append(f"  - {d.get('id')} to={d.get('to')} cc={d.get('cc')} thread={d.get('thread_id')} subject={_short(d.get('subject', ''), 80)}")
    qs = "\n".join(f"{qid}. [{crit}] {text}" for qid, crit, text, by, _ in QUESTIONS if by == "judge")
    return "\n".join([
        f"TASK ({record['case_id']} {record.get('name', '')}, filler size {record.get('size', 0):,} tokens, strategy {record.get('strategy')}):",
        case.get("description", ""),
        "", "USER TURNS: " + json.dumps(case.get("turns", [])),
        "", "IDEAL TRAJECTORY (reference): " + case.get("ideal_trajectory", ""),
        "", "EVENT LOG:", *(record.get("events") or ["(no events)"]),
        "", "REPLIES TO USER (complete):", *([f"  - {_short(r, 2500)}" for r in record.get("replies") or []] or ["  (none)"]),
        "", "FINAL MAILBOX STATE:", *state,
        "", f"HARNESS OUTCOME: {'success' if record.get('success') else 'FAIL'}" + (f" — {'; '.join(record.get('failures') or [])}" if record.get("failures") else ""),
        "", "QUESTIONS:", qs,
    ])


async def judge_answers(record: Dict[str, Any], case: Dict[str, Any], model: str, api_key: str) -> Tuple[Dict[str, Dict[str, Any]], Optional[bool], Optional[str], str]:
    prompt = _prompt(record, case)
    try:
        resp = await _real_llm(model=model, messages=[{"role": "user", "content": prompt}], system=_SYSTEM, api_key=api_key, tools=[_TOOL], max_tokens=2500)
        msg = (resp.get("choices") or [{}])[0].get("message", {})
        for tc in msg.get("tool_calls") or []:
            if tc["function"]["name"] == "answer_rubric":
                args = tc["function"]["arguments"]
                out = json.loads(args) if isinstance(args, str) else args
                answers = {}
                for qid in JUDGE_QIDS:
                    a = out.get(qid)
                    if isinstance(a, dict) and a.get("answer") in ("yes", "no", "na"):
                        answers[qid] = {"answer": a["answer"], "reason": str(a.get("reason", ""))}
                    else:
                        answers[qid] = {"answer": "na", "reason": "not answered by the judge"}
                return answers, bool(out.get("task_completed")), None, prompt
        return {}, None, "judge returned no answer_rubric call", prompt
    except Exception as exc:
        return {}, None, repr(exc), prompt


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------
def score(answers: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
    got = 0
    total = 0
    rows = []
    for qid, crit, text, by, w in QUESTIONS:
        a = answers.get(qid) or {"answer": "na", "reason": "not answered"}
        applicable = a["answer"] in ("yes", "no")
        if applicable:
            total += w
            if a["answer"] == "yes":
                got += w
        rows.append({"id": qid, "criterion": crit, "question": text, "by": by, "weight": w, "answer": a["answer"], "reason": a.get("reason", "")})
    return {"score": round(100 * got / total) if total else None, "earned": got, "applicable": total, "questions": rows}


def grade(record: Dict[str, Any], llm_calls: List[Dict[str, Any]], world_calls: List[Dict[str, Any]], case: Dict[str, Any],
          *, model: str, api_key: str, use_llm: bool = True) -> Dict[str, Any]:
    cnt = record.get("counters") or {}
    if cnt.get("gate_blocks") or record.get("aborted") or record.get("timed_out"):
        # Hard failure: the run overflowed, timed out or was aborted. Not graded; the verdict is already a fail.
        why = ("cell exceeded its runtime cap" if record.get("timed_out")
               else f"{cnt.get('gate_blocks')} request(s) blocked at the context window" if cnt.get("gate_blocks")
               else f"aborted: {record.get('aborted')}")
        return {"score": None, "earned": 0, "applicable": 0, "not_scored": why, "model": None, "task_completed": False, "error": None, "prompt": None,
                "questions": [{"id": q, "criterion": c, "question": t, "by": b, "weight": w, "answer": "na", "reason": why} for q, c, t, b, w in QUESTIONS]}
    steps = _walk(record, llm_calls, world_calls)
    answers = harness_answers(record, case, steps)
    task_completed = None
    err = None
    prompt = None
    if use_llm:
        j, task_completed, err, prompt = asyncio.run(judge_answers(record, case, model, api_key))
        answers.update(j)
    out = score(answers)
    out.update({"model": model if use_llm else None, "task_completed": task_completed, "error": err, "prompt": prompt})
    return out


# ---------------------------------------------------------------------------
# CLI: rescore a results directory
# ---------------------------------------------------------------------------
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("results_dir")
    ap.add_argument("--force", action="store_true", help="rescore cells that already have judge_v2")
    ap.add_argument("--no-llm", action="store_true", help="harness questions only (judge questions become n/a)")
    ap.add_argument("--judge-model", default="anthropic/claude-haiku-4.5", help="'config' = server's interaction model, or an OpenRouter id")
    ap.add_argument("--case", action="append")
    ap.add_argument("--no-outcome", action="store_true", help="skip the outcome judge (pass/fail unchanged)")
    ap.add_argument("--budget", type=float, default=1.0, help="stop once judge spend (metered from provider usage) reaches this many USD")
    args = ap.parse_args()

    settings = get_settings()
    model = settings.interaction_agent_model if args.judge_model == "config" else args.judge_model
    meter = SpendMeter(args.budget)
    global _real_llm
    _real_llm = meter.wrap(run_e2e._real_llm)
    run_e2e._real_llm = _real_llm  # outcome_judge lives in run_e2e
    rd = Path(args.results_dir)
    data = json.loads((rd / "results.json").read_text(encoding="utf-8"))
    cases = {c["id"]: c for c in resolve_cases(json.loads(CASES_PATH.read_text(encoding="utf-8"))["cases"])}
    done = 0
    stopped = None
    for rec in data["runs"]:
        if stopped:
            break
        if args.case and rec["case_id"] not in args.case:
            continue
        v2_ok = rec.get("judge_v2") and not rec["judge_v2"].get("error") and (rec["judge_v2"].get("score") is not None or rec["judge_v2"].get("not_scored"))
        outcome_ok = args.no_outcome or args.no_llm or (rec.get("outcome") and not rec["outcome"].get("error")) or rec.get("aborted")
        if v2_ok and outcome_ok and not args.force:
            continue
        case = cases.get(rec["case_id"])
        if not case:
            print(f"skip {rec['run_id']}: case not found")
            continue
        tf = rd / rec.get("trace_file", "")
        try:
            trace = json.loads(tf.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"skip {rec['run_id']} {rec['strategy']}: trace unreadable ({exc})")
            continue
        try:
            v2 = grade(rec, trace.get("llm_calls", []), trace.get("world_calls", []), case, model=model,
                       api_key=settings.openrouter_api_key, use_llm=not args.no_llm)
        except BudgetExceeded as exc:
            stopped = str(exc)
            break
        if v2.get("error") and "BudgetExceeded" in str(v2["error"]):
            stopped = v2["error"]
            break
        prompt = v2.pop("prompt", None)
        rec["judge_v2"] = v2
        trace["judge_v2_prompt"] = prompt
        hard = bool((rec.get("counters") or {}).get("gate_blocks")) or bool(rec.get("aborted")) or bool(rec.get("timed_out"))
        if not args.no_outcome and not args.no_llm and rec.get("counters") and not hard:
            checks_ok = rec.get("checks_pass", rec.get("success"))
            mech = [f for f in rec.get("failures", []) if f.startswith("check: ")] or ([] if checks_ok else rec.get("failures", []))
            o = asyncio.run(outcome_judge(case, rec.get("world") or {}, rec.get("replies") or [], bool(checks_ok),
                                          [f.replace("check: ", "") for f in mech], settings.openrouter_api_key, model))
            if o.get("error") and "BudgetExceeded" in str(o["error"]):
                stopped = o["error"]
                rec["judge_v2"] = v2
                trace["judge_v2_prompt"] = prompt
                break
            trace["outcome_prompt"] = o.pop("prompt", None)
            rec["outcome"] = o
            rec["checks_pass"] = bool(checks_ok)
            ok, reasons, bucket = combine_verdict(bool(checks_ok), o)
            if "verdict_v1" not in rec:  # preserve the original deterministic verdict for comparison
                rec["verdict_v1"] = {"success": rec.get("success"), "fail_reason": rec.get("fail_reason"), "failures": list(rec.get("failures") or [])}
            if rec.get("fail_reason") not in ("overflow", "loop", "error", "harness"):
                rec["success"] = ok
                rec["fail_reason"] = None if ok else bucket
                rec["failures"] = [f if f.startswith("check: ") else f"check: {f}" for f in mech] + reasons
        trace["record"] = rec
        tf.write_text(json.dumps(trace, ensure_ascii=False, default=str), encoding="utf-8")
        done += 1
        flags = [q["id"] for q in v2["questions"] if q["answer"] == "no"]
        o = rec.get("outcome") or {}
        verdict = ("PASS" if rec.get("success") else f"FAIL({rec.get('fail_reason')})")
        print(f"{rec['run_id']:16} {rec['strategy']:9} {verdict:16} rubric={v2['score'] if v2.get('score') is not None else 'n/a'}% no={flags or '-'}"
              + (f"  side_effects={[x['what'][:50] for x in o.get('side_effects', [])]}" if o.get('side_effects') else "")
              + (f"  judge error: {v2['error']}" if v2.get("error") else ""))
        (rd / "results.json").write_text(json.dumps(data, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"scored {done} cell(s) · judge spend ${meter.spent:.3f} over {meter.calls} calls (budget ${meter.budget:.2f})"
          + (f" · STOPPED: {stopped}" if stopped else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
