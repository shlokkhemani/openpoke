"""Oracle and "always do X" baselines. All emit non-legacy calls (``agent_id`` / ``name``).

Each returns a ``RunRecord`` whose ``mode`` is the baseline's name, ``n`` the roster size and
``run_idx`` 0; token, latency and round-trip fields are zero.
"""
from __future__ import annotations

from evals.grading import DISPATCH, USER_MESSAGE, RunRecord, ToolCall
from evals.schema import AgentDef, Case


def _record(case: Case, roster: list[AgentDef], baseline: str, calls: list[ToolCall]) -> RunRecord:
    user_messages = [c.args["message"] for c in calls if c.name == USER_MESSAGE]
    return RunRecord(
        case_id=case.id, mode=baseline, n=len(roster), run_idx=0, calls=calls,
        user_messages=user_messages, final_text="", prompt_tokens=0, completion_tokens=0,
        latency_s=0.0, round_trips=0, error=None,
    )


def _instructions(case: Case) -> str:
    if case.expect_person:
        return f"{case.message}\n\nThe person is {case.expect_person}."
    return case.message


def _create_name(case: Case) -> str:
    return case.message[:60].strip() or "New task"


def _question(case: Case) -> str:
    if case.clarify_should_name:
        return f"Which one do you mean: {' or '.join(case.clarify_should_name)}?"
    return "Could you tell me which one you mean?"


def oracle(case: Case, roster: list[AgentDef]) -> RunRecord:
    """The minimal correct calls for the case's first acceptable outcome.

    For a dispatch outcome: one call per slot (to its target) whose instructions name the slot's
    person, if any, plus the clarifying question if ``ask``.
    """
    o = case.acceptable[0]
    calls: list[ToolCall] = []
    if o.kind == "reuse":
        calls.append(ToolCall(DISPATCH, {"agent_id": o.agent_ids[0], "instructions": _instructions(case)}))
    elif o.kind == "create":
        calls.append(ToolCall(DISPATCH, {"name": _create_name(case), "instructions": _instructions(case)}))
    elif o.kind == "clarify":
        calls.append(ToolCall(USER_MESSAGE, {"message": _question(case)}))
    elif o.kind == "dispatch":  # one dispatch per slot
        for i, slot in enumerate(o.slots, 1):
            text = "Please handle this" + (f" for {' and '.join(slot.persons)}" if slot.persons else "") + "."
            if slot.reuse_id:
                calls.append(ToolCall(DISPATCH, {"agent_id": slot.reuse_id, "instructions": text}))
            else:
                calls.append(ToolCall(DISPATCH, {"name": f"Task {i}", "instructions": text}))
        if o.ask:
            calls.append(ToolCall(USER_MESSAGE, {"message": _question(case)}))
    else:  # answer_set: answer from unique facts; message only agents that have none
        facts = [case.unique_facts[a] for a in o.agent_ids if case.unique_facts.get(a, "").strip()]
        for aid in o.agent_ids:
            if not case.unique_facts.get(aid, "").strip():
                calls.append(ToolCall(DISPATCH, {"agent_id": aid, "instructions": case.message}))
        if facts:
            calls.append(ToolCall(USER_MESSAGE, {"message": "Here's where things stand: " + "; ".join(facts) + "."}))
    return _record(case, roster, "oracle", calls)


def always_create(case: Case, roster: list[AgentDef]) -> RunRecord:
    calls = [ToolCall(DISPATCH, {"name": _create_name(case), "instructions": case.message})]
    return _record(case, roster, "always_create", calls)


def always_ask(case: Case, roster: list[AgentDef]) -> RunRecord:
    calls = [ToolCall(USER_MESSAGE, {"message": "Could you tell me a bit more about which task you mean?"})]
    return _record(case, roster, "always_ask", calls)


def always_reuse_top(case: Case, roster: list[AgentDef], ranked_ids: list[str]) -> RunRecord:
    """Dispatch the case message to the top-ranked agent (``ranked_ids[0]``)."""
    calls = [ToolCall(DISPATCH, {"agent_id": ranked_ids[0], "instructions": case.message})]
    return _record(case, roster, "always_reuse_top", calls)
