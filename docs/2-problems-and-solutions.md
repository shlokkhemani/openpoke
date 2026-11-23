# OpenPoke: Problems and Proposed Solutions

Companion to [1-original-openpoke-architecture.md](1-original-openpoke-architecture.md).

> **Implementation status (branch `fork-architecture`):**
> - **Implemented:** §1 `delegate` and `read_conversation` (default mode: results still return to Poke), §2 the granularity prompt, parallel tool calls and execution-log compaction, and all of §3 (roster records with `report_status`, `find_agents` that Poke calls before every delegation, and the lifecycle sweep, archive and revive).
> - **Not implemented:** skills, tool search and the optional direct-reply mode.
> - **One addition beyond this doc:** the server-built handoff includes `<current_time>`. Verbatim forwarding would otherwise lose the date context that Poke's paraphrase used to carry.
> - **Added after testing:** `delegate` takes an optional `task`. When one message holds several tasks, or Poke acts on an agent's result, the handoff marks that agent's part as `<task>` and the user's message as background, and the agent may only change reminders that belong to its task.

---

## 1. Handoff cost: Poke rewrites everything both ways

### Problem

Each delegated task costs two full generations by Poke, the interaction agent, and both carry the whole conversation history:

```
user ─► Poke (ack + write instructions) ─► Exec loop ─► Exec final text ─► Poke (rewrite result) ─► user
```

- **Outbound.** Poke paraphrases the user's request into `instructions` (`interaction_agent/tools.py:28`).
- **Inbound.** The result starts a new Poke turn (`batch_manager.py` → `handle_agent_message`), which restates text the execution agent already wrote.
- **Costs.** Latency from two serial Poke calls, wasted tokens, and context loss: the execution agent sees only Poke's paraphrase, never the user's words.

### Proposal

```
default:  user ─► Poke (route: delegate(name)) ─► Exec loop ─► Exec final text ─► Poke (relay) ─► user
optional: user ─► Poke (route: delegate(name)) ─► Exec loop ─► Exec send_message_to_user ─► user
```

**Outbound: forward, don't rewrite.** Replace `send_message_to_agent` with `delegate(agent_name, note?)`. The server builds the execution agent's input. No LLM writes it:

```
<previous_poke_reply>…</previous_poke_reply>   <!-- covers "work" / "send it" style replies -->
<user_message>…verbatim…</user_message>
<note>…optional, a few tokens…</note>
```

**Context on demand.** Execution agents get a read-only tool:

```jsonc
read_conversation(last_n?: int = 10, query?: string, include_summary?: bool = false)
```

- **What it returns:** entries from the working-memory transcript: `user_message`, `poke_reply` and `agent_reply`. It never returns other agents' logs.
- **When agents call it:** when the message refers to something missing from their own history, such as "him", "the other one" or "same as before". Agents should also call it with `query=<entity>` before irreversible actions like sending email or creating triggers.
- **Cost:** nothing for self-contained requests. Follow-ups pay one extra loop iteration.
- **Gap:** an agent can't ask for context it doesn't know is missing, for example that the user said three turns ago they'd be in Berlin. Poke covers this with a short `note`.

**Inbound (default): results still go back to Poke.** Agents stay hidden from the user, and Poke keeps one consistent voice, as its prompt requires today. The outbound change alone already removes the paraphrase and the context loss. The inbound Poke turn remains, but it's a relay: Poke turns the result into a user-facing message, or calls `send_draft`.

**Inbound (optional): the execution agent replies to the user directly.** This is behind a config flag, for setups that are fine with exposing agents:
- Execution agents get `send_message_to_user` and `send_draft`.
- These write a new `agent_reply` log tag. It maps to its own role in `to_chat_messages`, so the UI can render it separately, and Poke still sees it in history.
- Poke gets a new turn only when an agent **fails or times out**. That saves the inbound generation.
- Agents need Poke's tone rules, moved into a prompt snippet both prompts share.

**Poke still decides whether to delegate.** Greetings and anything answerable from the conversation get a direct reply.

**Acknowledgements.** Poke's prompt requires an "on it" message before every delegation, which is extra output on every task. Make it optional, used only for slow tasks, or replace it with a UI "working" indicator.

**Touch points:**
- `interaction_agent/tools.py`: `delegate`.
- `execution_agent/tools/registry.py`: `read_conversation`, plus user-facing tools behind the flag.
- *Optional mode only:*
  - `conversation/log.py`: `agent_reply` tag and role mapping.
  - `batch_manager.py`: dispatch to Poke only on failure.
  - `web/components/chat/ChatMessages.tsx`: bubble style.

---

## 2. Tasks are split too finely

### Problem

Poke's prompt says: *"split it into as much concurrent calls to `send_message_to_agent` as possible."* So "ask Alice and Bob if they're free for lunch tomorrow" becomes two agents. That doubles cost, splits the follow-up context ("Alice yes, Bob no" lives in two places), and leaves Poke to merge the results.

### Proposal: one goal, one execution agent

- **Delegate per user goal, not per action.** Name agents after the goal ("Lunch tomorrow – Alice & Bob"). Split only for unrelated goals that happen to arrive in one message.
- **Big tasks stay in one agent too.** One agent has the full picture: when a reply changes the plan, the agent that wrote the draft revises it. Splitting adds a coordination layer that brings back section 1's handoff cost.
- **Parallelism happens inside the agent.** `ExecutionAgentRuntime.execute` awaits tool calls one at a time. Switch it to `asyncio.gather`. Also revisit `MAX_TOOL_ITERATIONS = 8` and the 90s timeout for bigger tasks.

### Manage context instead of splitting

A single agent's context grows, so manage it in place:

- **Skills.** Keep the base prompt small. Load detailed instructions (search operators, draft etiquette, recurrence rules) on demand.
- **Tool search.** Send a core set of tool schemas plus `search_tools(query)`. Today every schema is sent on every iteration.
- **Compaction of execution logs.** Execution logs are never compacted, and `conversation_limit` is never set. Past a threshold, fold old entries into a task summary (goal, decisions, open items, key IDs) and keep the recent tail verbatim, the same pattern Poke's working memory uses.
### Future: sub-agents under the execution agent

If a task really needs sub-tasks, the execution agent can own sub-agents. It keeps the goal and merges results itself, and Poke stays out of it. Add this only when there's a concrete need.

---

## 3. Agent sprawl overloads Poke's context

### Problem

`roster.json` is a flat list of names. Nothing is ever removed, and every Poke turn lists all of them in `<active_agents>`. Over time this wastes tokens, dilutes attention, and turns picking the right agent to reuse into guessing from names alone.

### Proposal

**3a. Summaries, not names.** Make roster entries records:

```jsonc
{ "name": "Lunch tomorrow – Alice & Bob",
  "summary": "Emailed both re Tue 12:30. Alice yes, Bob pending.",
  "status": "active | waiting_on_user | waiting_on_external | done",
  "entities": ["alice@…", "bob@…", "thread:18c…"],
  "has_triggers": false,
  "last_active": "2026-11-22T10:15:00" }
```

The execution agent fills these in with `report_status(status, summary)` at the end of its run, so there's no extra LLM call.

**3b. One search function instead of the full list.**

```jsonc
find_agents(query?: string, status?: "active" | "closed" | "all" = "all", limit?: int = 3)
```

- **Matching:** BM25 or keyword search over `name + summary + entities`, with exact entity matches (emails, thread IDs) ranked first. Active agents get a ranking boost but are not capped separately.
- **Poke searches first, as a tool call.** Poke's prompt has no agent list. Before every `delegate`, Poke calls `find_agents` with a query it writes from the whole conversation, such as "mom call" or "meds 2pm". The latest message alone often lacks the words needed to find the right agent. It costs one extra Poke call per delegated turn.
- **Top 3 by default.** `status="active"` answers "what are you working on?", `status="closed"` covers an old task, and paging past `limit` reaches more results. No agent is unreachable.
- **Empty query:** `find_agents(status="active")` with no query lists active agents by `last_active`.

**3c. Lifecycle.**
- **Real-time close:** the agent marks itself `done` through `report_status`. It already knows whether the task is finished, so no separate decision model is needed.
- **Nightly sweep:** archive agents that are `done` or idle for more than N days. **Skip agents with active triggers**, since triggers are keyed by `agent_name`.
- **Archive, don't delete:**
  - Move the log to `execution_agents/archive/` and keep the record searchable.
  - A follow-up like "did Bob ever reply?" revives the agent with its history intact.
- **Merging:** postpone it. Retrieval plus revival covers most of the value with less risk.

---

## Rollout

| # | Change | Why this order |
|---|---|---|
| 1 | Granularity prompt fix, `asyncio.gather` (§2) | Smallest change, immediate savings |
| 2 | Roster records and `report_status` (§3a) | Prerequisite for §3 |
| 3 | `delegate` and `read_conversation` (§1) | Removes the outbound generation and the context loss |
| 3b | *Optional:* direct `agent_reply` and UI role (§1) | Removes the inbound generation, but exposes agents |
| 4 | Execution-log compaction, skills, tool search (§2) | Keeps single-goal agents within budget |
| 5 | `find_agents` (Poke searches before delegating) and lifecycle (§3b, §3c) | Matters once the roster grows |
