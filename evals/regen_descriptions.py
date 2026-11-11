"""Regenerate the world's agent descriptions with the production DescriptionUpdater.

Reads the frozen world (never writes it) and writes ``descriptions.regen.json`` next to it. The
instructions are each agent's first ``agent_request``, the final response its last
``agent_response``, the previous description is empty, and the facts are the world agent's contacts.
"""
from __future__ import annotations

import asyncio
import json
import tempfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from evals.pricing import estimate_cost
from evals.world.generate import WORLD_PATH
from evals.world.roster import World, load_world
from server.services.agents.descriptions import SYSTEM_PROMPT, DescriptionUpdater, RunFacts
from server.services.agents.store import AgentRecord, AgentStore, ContactRecord

OUT_PATH = WORLD_PATH.parent / "descriptions.regen.json"
DEFAULT_MAX_COST = 1.0
COMPLETION_TOKENS = 80  # a 1-3 sentence description
_EPOCH = datetime(2026, 11, 1, 12, 0, tzinfo=timezone.utc)  # EVAL_NOW


def default_llm() -> Callable[..., Awaitable[dict]]:
    """The real chat-completion call with the configured key (imported lazily)."""
    from server.config import get_settings
    from server.openrouter_client import request_chat_completion

    api_key = get_settings().openrouter_api_key

    async def call(**kwargs: Any) -> dict:
        return await request_chat_completion(api_key=api_key, **kwargs)

    return call


def default_model() -> str:
    from server.config import get_settings
    return get_settings().description_model


def _inputs(world: World, agent_id: str) -> tuple[str, str]:
    log = world.logs.get(agent_id, [])
    instructions = next((t for k, t in log if k == "agent_request"), "")
    responses = [t for k, t in log if k == "agent_response"]
    return instructions, (responses[-1] if responses else "")


def _agent_prompt_tokens(world: World, agent_id: str) -> int:
    instructions, response = _inputs(world, agent_id)
    chars = len(SYSTEM_PROMPT) + len(instructions) + len(response) + 120
    chars += sum(len(c.email) + len(c.display_name) + 6 for c in world.agents[agent_id].contacts)
    return chars // 4 + 1


def estimate(world: World, model: str) -> tuple[int, int, int, float]:
    """(agents, prompt tokens, completion tokens, USD), at ~4 characters per token."""
    prompt = sum(_agent_prompt_tokens(world, a) for a in world.agents)
    completion = COMPLETION_TOKENS * len(world.agents)
    return len(world.agents), prompt, completion, estimate_cost(model, prompt, completion)


@dataclass
class RegenResult:
    descriptions: dict[str, str] = field(default_factory=dict)  # only agents the LLM wrote
    succeeded: int = 0
    fell_back: int = 0
    skipped: int = 0
    spent: float = 0.0

    @property
    def complete(self) -> bool:
        return self.fell_back == 0 and self.skipped == 0


async def regenerate(world: World, llm: Callable[..., Awaitable[dict]], model: str, max_cost: float) -> RegenResult:
    """Sequential, so the cap is exact: an agent is skipped, with no call, when its estimated cost
    would take the spend past ``max_cost``. A call without a usage block is counted at its estimate."""
    result = RegenResult()
    with tempfile.TemporaryDirectory() as tmp:
        store = AgentStore(Path(tmp) / "regen.db")
        for agent_id, agent in world.agents.items():
            store.insert_agent(AgentRecord(agent_id, agent.name, "", _EPOCH, None, None))
            store.add_contacts(agent_id, [ContactRecord(c.email, c.display_name, c.role) for c in agent.contacts])
        updater = DescriptionUpdater(store, llm, model)
        for agent_id in world.agents:
            prompt_tokens = _agent_prompt_tokens(world, agent_id)
            est = estimate_cost(model, prompt_tokens, COMPLETION_TOKENS)
            if result.spent + est > max_cost:
                result.skipped += 1
                continue
            usage: dict[str, Any] = {}

            async def metered(**kwargs: Any) -> dict:
                response = await llm(**kwargs)
                usage.update(response.get("usage") or {})
                return response

            updater.llm = metered
            instructions, response = _inputs(world, agent_id)
            facts = RunFacts(store.contacts_for(agent_id), [])
            text, fell_back = await updater.update_checked(agent_id, instructions, response, facts)
            if usage:
                result.spent += estimate_cost(model, usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0))
            else:  # no usage block (or the call failed): count the estimate rather than nothing
                result.spent += est
            if fell_back:
                result.fell_back += 1
            else:
                result.succeeded += 1
                result.descriptions[agent_id] = text
    return result


def run(world_path: Path = WORLD_PATH, out_path: Path = OUT_PATH, yes: bool = False,
        max_cost: Optional[float] = None) -> int:
    world = load_world(world_path)
    model = default_model()
    n, prompt, completion, usd = estimate(world, model)
    cap = DEFAULT_MAX_COST if max_cost is None else max_cost
    print(f"Estimated cost: ${usd:.4f} for {n} descriptions with {model} "
          f"(~{prompt:,} prompt + ~{completion:,} completion tokens).")
    if not yes:
        print("Refusing to run without --yes.")
        return 2
    if usd > cap:
        print(f"Estimate exceeds --max-cost ${cap:g}; refusing.")
        return 1
    result = asyncio.run(regenerate(world, default_llm(), model, cap))
    print(f"{result.succeeded} succeeded, {result.fell_back} fell back, {result.skipped} skipped; "
          f"spend ${result.spent:.4f}")
    if not result.complete:
        print(f"Not writing {out_path}: every agent needs a regenerated description.")
        return 1
    descriptions = result.descriptions
    out_path.write_text(json.dumps({
        "model": model,
        "generated_on": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
        "descriptions": descriptions,
    }, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(descriptions)} descriptions to {out_path}")
    return 0
