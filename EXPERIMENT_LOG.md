# Active Agents Prompt Bloat — Experiment Log

## Problem Statement
The `<active_agents>` XML block is injected into every interaction-agent LLM prompt unconditionally. 
The roster is append-only (no `remove_agent()`), so dead/finished agents accumulate forever.
As N grows, every LLM call carries O(N) stale XML tags — wasted input tokens, diluted context.

## Architecture Summary
- `roster.py` — append-only `AgentRoster` backed by `roster.json`
- `agent.py` — `_render_active_agents()` serializes full roster into `<active_agents>` block
- `tools.py:120` — `add_agent()` called on spawn, never reversed
- `batch_manager.py` — knows when agents finish (SUCCESS/FAILED) but doesn't notify roster
- `clear_history()` in `chat.py` — only way to shrink roster (nuclear option)

## Current State (Baseline)
Roster: `["Lambda MicroVMs Research", "Phone Shutdown Reminder", "Gold Price Email", "Browser Automation"]`
4 agents — all completed long ago, still in every prompt.

---

## Experiment 1: Agent Lifecycle Tracking

### Hypothesis
Adding status tracking (active/completed) to the roster and only rendering active agents
will reduce prompt bloat without breaking any existing functionality.

### Changes
1. Extend `AgentRoster` with status per agent (`active` / `completed`)
2. Add `complete_agent(name)` method
3. Call `complete_agent()` from `batch_manager._complete_execution()` when agent finishes
4. Modify `_render_active_agents()` to only show `active` agents
5. Keep backward compat: plain list in roster.json → treat all as `active` on load

### Status: ✅ PASSED

### Results
- **Unit tests**: 6/6 passed (add, complete, reload, backward compat, re-activation, get_agents)
- **Integration test**: Server responds 202, processes messages correctly
- **Lifecycle test**: Agent spawned as `active`, automatically marked `completed` when batch_manager finishes
- **Reuse test**: Completed agents re-activate when `send_message_to_agent` targets them
- **Prompt savings**: 97% reduction (152→4 chars) with 4 completed agents, 0 active
- **Backward compat**: Old `roster.json` (plain list) auto-migrated to new format on first load
- **No regressions**: Chat still works end-to-end (simple queries + agent-spawning queries)

### Token Impact
| Scenario | Old (all agents) | New (active only) | Savings |
|---|---|---|---|
| 4 completed, 0 active | 152 chars / ~38 tokens | 4 chars / ~1 token | 97% |
| 50 completed, 1 active | ~1900 chars / ~475 tokens | ~50 chars / ~12 tokens | 97% |

---

## Experiment 2: Edge Case & Regression Testing

### Hypothesis
The lifecycle changes handle all edge cases: concurrent agents, timeout/failure, clear_history, and the system prompt still makes sense.

### Test Cases
1. Multiple agents spawned simultaneously (batch) — both complete independently
2. Agent that times out — still marked completed
3. Agent that throws an exception — still marked completed
4. `clear_history()` still works (clears new format)
5. System prompt mentions of agents still coherent

### Status: ✅ PASSED

### Results
- ✓ Concurrent agents complete independently (A, B, C in any order)
- ✓ `complete_agent` on unknown agent is a safe no-op
- ✓ `clear()` works with new dict format
- ✓ 100 agents stress test: all transition correctly
- ✓ Roster with 100 completed agents: 3202 bytes (manageable)
- ✓ Live integration: server processes messages, agents spawn/complete correctly

---

## Experiment 3: Roster Pruning (Bounded Growth)

### Hypothesis
Even though completed agents no longer bloat the prompt, the roster.json file still
grows unboundedly. Adding a max-completed cap (e.g., keep last 20 completed agents)
prevents filesystem bloat while preserving recent context for agent reuse decisions.

### Changes
1. Add `MAX_COMPLETED` constant (20)
2. In `complete_agent()`, prune oldest completed entries when over the cap
3. Verify the system prompt interaction agent still knows about reusable agents

### Status: ✅ PASSED

### Results
- ✓ Pruning caps completed agents at 20 (oldest evicted first)
- ✓ Compact rendering: 10 most recent completed agents on a single line
- ✓ With 1 active + 20 completed (post-pruning): 173 chars vs 549 old = **68% savings**
- ✓ With 0 active + 4 completed (realistic): compact single line vs 4 individual tags
- ✓ Active agents unaffected by pruning
- ✓ `clear()` still works

---

## Final Summary

### Changes Made (4 files)
1. **`server/services/execution/roster.py`** — Rewritten to dict-based status tracking
   - `add_agent()` → sets `"active"` status
   - New `complete_agent()` → transitions to `"completed"` + prunes oldest
   - New `get_active_agents()`, `get_completed_agents()`, `get_agent_status()`
   - `_prune_completed()` caps at 20 completed agents
   - Backward compat: plain list auto-migrated to dict format

2. **`server/agents/interaction_agent/agent.py`** — `_render_active_agents()` updated
   - Active agents: full XML tags with `status="active"`
   - Completed agents: single compact `<completed_agents names="..." />` tag (last 10)
   - Empty roster: renders `"None"`

3. **`server/agents/execution_agent/batch_manager.py`** — Lifecycle hook added
   - Calls `roster.complete_agent()` after execution finishes (success or failure)
   - Wrapped in try/except to avoid disrupting execution flow

4. **`server/agents/interaction_agent/tools.py`** — Agent reuse support
   - When `send_message_to_agent` targets a completed agent, re-activates it

### Token Impact (with 50 agents ever spawned)
| Metric | Before | After | Savings |
|---|---|---|---|
| Prompt chars (0 active) | ~1900 | ~170 | **91%** |
| Prompt chars (1 active) | ~1950 | ~220 | **89%** |
| Roster file growth | Unbounded | Capped at 20 completed + active | **Bounded** |

### Verified Scenarios
- [x] Simple queries (no agents spawned)
- [x] Agent-spawning queries (new agent lifecycle)
- [x] Agent reuse (completed → active)
- [x] Multiple concurrent agents
- [x] Agent timeout/failure (still marks completed)
- [x] Backward compatibility with old roster.json format
- [x] clear_history() endpoint
- [x] 100-agent stress test
- [x] Live E2E through localhost:3000 UI
