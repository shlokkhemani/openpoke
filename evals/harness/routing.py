"""Run the real Interaction Agent loop on one eval case with stubbed tools (design: routing harness).

The LLM is injected; every tool call the IA makes is recorded and answered with the payload shape
the real tool returns, but nothing is dispatched, logged or written. Exceptions from the loop (LLM
transport errors, malformed responses, the iteration limit) are infrastructure errors: they land in
``RunRecord.error`` with the calls recorded so far, and are never retried here. So do malformed
tool calls (no name, or arguments that are not a JSON object): the runtime drops or rejects them
before the stub sees them, so they are detected by comparing the raw tool calls in the transcript
with the recorded ones.
"""
from __future__ import annotations

import re
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Optional

from evals.grading import RunRecord, ToolCall, created_agent_id
from evals.harness.full_roster import _trigger_records
from evals.harness.load_world import load_into_store
from evals.harness.render import render_legacy_roster, render_transcript
from evals.schema import AgentDef, Case
from evals.world.roster import World, roster_for
from server.agents.interaction_agent import agent as ia_agent
from server.agents.interaction_agent.runtime import InteractionAgentRuntime, LLMCall, _LoopSummary
from server.agents.interaction_agent.roster_view import legacy_tool_schemas
from server.agents.interaction_agent import tools as ia_tools
from server.agents.interaction_agent.tools import ToolResult
from server.agents.interaction_agent.turn_inputs import build_turn_inputs
from server.services.agents.retrieval import RetrievalConfig
from server.services.agents.store import AgentStore

_IA_DIR = Path(ia_agent.__file__).parent
SYSTEM_PROMPT_LEGACY = (_IA_DIR / "system_prompt_legacy.md").read_text(encoding="utf-8").strip()
# The current prompt with the new routing rules, composed for the ``agent_name`` tool
# (``legacy_rules`` mode); byte-identical to system_prompt.md at dbb79c8.
SYSTEM_PROMPT_RULES = ia_agent.build_system_prompt("names")


def build_legacy_messages(
    case: Case, roster: list[AgentDef], system_prompt: str = SYSTEM_PROMPT_LEGACY
) -> tuple[str, list[dict[str, str]]]:
    """System prompt and user message as production builds them, from the case instead of disk.

    Names-only roster and history; ``legacy_rules`` passes the new prompt, everything else is the same.
    """
    transcript = render_transcript(case.ia_history, "legacy")
    sections = [
        ia_agent._render_conversation_history(transcript),
        f"<active_agents>\n{render_legacy_roster(roster)}\n</active_agents>",
        ia_agent._render_current_turn(case.message, "user"),
    ]
    return system_prompt, [{"role": "user", "content": "\n\n".join(sections)}]


class LegacyToolStub:
    """Records every tool call; returns the real tools' result shapes without side effects."""

    def __init__(self, roster: list[AgentDef]) -> None:
        self.calls: list[ToolCall] = []
        self._agent_names = {a.name for a in roster}
        self._tools: dict[str, Callable[..., ToolResult]] = {
            "send_message_to_agent": self._send_message_to_agent,
            "send_message_to_user": self._send_message_to_user,
            "send_draft": self._send_draft,
            "wait": self._wait,
        }

    def __call__(self, name: str, arguments: dict[str, Any]) -> ToolResult:
        self.calls.append(ToolCall(name, dict(arguments)))
        tool = self._tools.get(name)
        if tool is None:
            return ToolResult(success=False, payload={"error": f"Unknown tool: {name}"})
        try:
            return tool(**arguments)
        except TypeError as exc:  # same message as tools.handle_tool_call
            return ToolResult(success=False, payload={"error": f"Missing required arguments: {exc}"})

    def _send_message_to_agent(self, agent_name: str, instructions: str) -> ToolResult:
        is_new = agent_name not in self._agent_names
        self._agent_names.add(agent_name)  # the real tool adds new names to the roster
        return ToolResult(
            success=True,
            payload={"status": "submitted", "agent_name": agent_name, "new_agent_created": is_new},
        )

    def _send_message_to_user(self, message: str) -> ToolResult:
        return ToolResult(
            success=True, payload={"status": "delivered"}, user_message=message, recorded_reply=True
        )

    def _send_draft(self, to: str, subject: str, body: str) -> ToolResult:
        return ToolResult(
            success=True,
            payload={"status": "draft_recorded", "to": to, "subject": subject},
            recorded_reply=True,
        )

    def _wait(self, reason: str) -> ToolResult:
        return ToolResult(
            success=True, payload={"status": "waiting", "reason": reason}, recorded_reply=True
        )


class IdToolStub(LegacyToolStub):
    """``LegacyToolStub`` for the production ``agent_id`` / ``name`` tool, with its exact error texts.

    Known ids are the roster's plus the ones this stub created; the k-th create gets
    ``created_agent_id(k)``, the rule the grader uses to recognise later dispatches to it.
    """

    def __init__(self, roster: list[AgentDef]) -> None:
        super().__init__(roster)
        self._known_ids = {a.id for a in roster}
        self._created = 0

    def _send_message_to_agent(  # type: ignore[override]
        self, instructions: str, agent_id: Optional[str] = None, name: Optional[str] = None
    ) -> ToolResult:
        agent_id, name = ia_tools._given(agent_id), ia_tools._given(name)
        if agent_id and name:
            return ia_tools._error(ia_tools.ERR_BOTH_ID_AND_NAME)
        if not agent_id and not name:
            return ia_tools._error(ia_tools.ERR_NEITHER_ID_NOR_NAME)
        if agent_id and agent_id not in self._known_ids:
            return ia_tools._error(ia_tools.ERR_UNKNOWN_AGENT_ID.format(agent_id=agent_id))
        is_new = not agent_id
        if is_new:
            self._created += 1
            agent_id = created_agent_id(self._created)
            self._known_ids.add(agent_id)
        return ToolResult(
            success=True,
            payload={"status": "submitted", "agent_id": agent_id, "new_agent_created": is_new},
        )


_CARD_ID = re.compile(r'<agent id="([^"]+)"')


class HybridToolStub(IdToolStub):
    """``IdToolStub`` plus ``search_agents`` served by the production search core over the run's store.

    One real search per stub (= per case-run turn); a blank query does not spend it, as in production.
    Every search is kept in ``searches`` as ``{query, ids, error}``.
    """

    def __init__(self, roster: list[AgentDef], store: AgentStore, embedder: Any,
                 cfg: RetrievalConfig, triggers_for: Callable[[str], list]) -> None:
        super().__init__(roster)
        self._search_ctx = (store, embedder, cfg, triggers_for)
        self._searched = False
        self.searches: list[dict[str, Any]] = []
        self._tools["search_agents"] = self._search_agents

    def _search_agents(self, query: Any = None) -> ToolResult:
        if ia_tools._given(query) is not None and self._searched:
            result = ia_tools._error(ia_tools.ERR_ALREADY_SEARCHED)
        else:
            result = ia_tools.search_agents_result(query, *self._search_ctx)
            self._searched = self._searched or result.success
        ok = result.success
        self.searches.append({
            "query": query,
            "ids": _CARD_ID.findall(result.payload["agents"]) if ok else [],
            "error": None if ok else result.payload["error"],
        })
        return result


def _malformed_tool_calls(messages: list[dict[str, Any]], recorded: int) -> Optional[str]:
    """An error string if the model emitted tool calls that never reached the stub."""
    raw = [
        tc
        for m in messages
        if m.get("role") == "assistant"
        for tc in (m.get("tool_calls") or [])
    ]
    if len(raw) == recorded:
        return None
    return (
        f"MalformedToolCall: {len(raw) - recorded} of {len(raw)} tool calls had no name "
        f"or invalid arguments"
    )


async def run_case(
    case: Case, world: World, mode: str, n: int, llm: LLMCall, run_idx: int = 0,
    descriptions: Optional[dict[str, str]] = None, embedder: Any = None,
) -> RunRecord:
    """Run the real IA loop once on ``case`` with a roster of size ``n`` and grade-ready output.

    ``full`` and ``hybrid`` load the roster into a temporary store and take prompt, roster block and
    tool schemas from production ``build_turn_inputs``; ``descriptions`` (agent id -> text, ``{}`` for
    the world's own) is required there and ignored by the name modes. ``hybrid`` also needs
    ``embedder`` and serves ``search_agents`` by real retrieval over the same store.
    """
    roster = roster_for(case, world, n)
    stub: LegacyToolStub
    initial_ids: list[str] = []
    store_dir = None
    if mode in ("legacy", "legacy_rules"):
        prompt = SYSTEM_PROMPT_LEGACY if mode == "legacy" else SYSTEM_PROMPT_RULES
        system_prompt, messages = build_legacy_messages(case, roster, prompt)
        stub = LegacyToolStub(roster)
        schemas = legacy_tool_schemas()
    elif mode in ("full", "hybrid"):
        if mode == "hybrid" and embedder is None:
            raise ValueError("mode 'hybrid' needs an embedder")
        if descriptions is None and mode == "full":
            raise ValueError("mode 'full' needs descriptions: the regenerated map, or {} for the world's own")
        cfg = RetrievalConfig()
        by_id = {a.id: a for a in roster}
        triggers_for = lambda agent_id: _trigger_records(by_id[agent_id]) if agent_id in by_id else []  # noqa: E731
        history = [(t.role, t.text, t.agent_id) for t in case.ia_history]
        store_dir = tempfile.TemporaryDirectory()
        store = AgentStore(Path(store_dir.name) / "agents.db")
        load_into_store(roster, world, store, embedder, descriptions, keep_order=True)
        inputs = build_turn_inputs(mode, store, embedder, case.message, history,
                                   triggers_for=triggers_for, cfg=cfg)
        if mode == "hybrid":
            stub = HybridToolStub(roster, store, embedder, cfg, triggers_for)
            initial_ids = _CARD_ID.findall(inputs.roster_block)
        else:
            stub = IdToolStub(roster)
        system_prompt, schemas = inputs.system_prompt, inputs.tool_schemas
        messages = ia_agent.prepare_message_with_history(
            case.message, render_transcript(case.ia_history, mode), "user",
            roster_block=inputs.roster_block)
    else:
        raise ValueError(f"unknown roster mode {mode!r}")

    runtime = InteractionAgentRuntime(
        llm=llm, tool_handler=stub, tool_schemas=schemas, require_api_key=False
    )
    summary = _LoopSummary()
    error = None
    start = time.perf_counter()
    try:
        await runtime.run_loop(system_prompt, messages, summary)
    except Exception as exc:  # infrastructure error: recorded, never graded as an answer
        error = f"{type(exc).__name__}: {exc}"
    finally:
        if store_dir is not None:
            store_dir.cleanup()
    latency = time.perf_counter() - start
    if error is None:
        error = _malformed_tool_calls(messages, len(stub.calls))

    return RunRecord(
        case_id=case.id,
        mode=mode,
        n=n,
        run_idx=run_idx,
        calls=list(stub.calls),
        user_messages=list(summary.user_messages),
        final_text=summary.last_assistant_text,
        prompt_tokens=summary.prompt_tokens,
        completion_tokens=summary.completion_tokens,
        latency_s=latency,
        round_trips=summary.round_trips,
        error=error,
        searches=list(getattr(stub, "searches", [])),
        initial_ids=initial_ids,
    )
