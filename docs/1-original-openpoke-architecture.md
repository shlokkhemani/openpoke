# OpenPoke Agent Architecture

A two-tier, multi-agent setup: one user-facing **interaction agent** sends work to many named **execution agents**, which can start one nested **email-search** sub-agent. A few background services (the email watcher, the trigger scheduler and the summarizer) feed into the same loop. Every LLM call goes through OpenRouter (`server/openrouter_client`), and each role's model is set in `server/config.py` (default `anthropic/claude-sonnet-4`).

```
 user ──POST /chat (202)──► Interaction Agent ──send_message_to_agent──► Execution Agent(s) ──task_email_search──► Search sub-agent
   ▲                           │      ▲                                    │   (Gmail via Composio,
   └── poll conversation log ◄─┘      └──── batched results ───────────────┘    triggers in SQLite)
                                      ▲
           Important-email watcher ───┤  (every 60s, LLM classifier)
           Trigger scheduler ─────────┘  (every 10s → runs execution agent → results flow back)
```

## Agents

| Agent | Code | Prompt | Tools | Loop |
|---|---|---|---|---|
| **Interaction** ("Poke") | `agents/interaction_agent/` | `system_prompt.md`: persona (witty, terse, adapts to the user's texting style), always delegates, never reveals agents or tools, gets confirmation before sending email | `send_message_to_agent(agent_name, instructions)`, `send_message_to_user(message)`, `send_draft(to, subject, body)`, `wait(reason)` | ≤8 tool iterations per turn |
| **Execution** (many, keyed by name) | `agents/execution_agent/` | `system_prompt.md` template: `{agent_name}`/`{purpose}`. Reports to Poke rather than the user, only drafts emails unless the user confirms, returns drafts verbatim | **Gmail** (Composio): `gmail_create_draft`, `gmail_execute_draft`, `gmail_delete_draft`, `gmail_list_drafts`, `gmail_reply_to_thread`, `gmail_forward_email`, `gmail_get_contacts`, `gmail_get_people`, `gmail_search_people`. **Triggers**: `createTrigger`, `updateTrigger`, `listTriggers`. **Task**: `task_email_search(search_query)` | ≤8 iterations, 90s timeout |
| **Email search** (nested) | `execution_agent/tasks/search_email/` | `system_prompt.py`: Gmail search-operator expert, adds today's date, runs parallel queries, prefers 10 results | `gmail_fetch_emails(query, max_results, …)`, `return_search_results(message_ids)` | ≤8 iterations; returns cleaned emails to the calling execution agent |
| **Importance classifier** | `services/gmail/importance_classifier.py` | Inline prompt: flag an email only if it needs timely attention or contains OTPs | Forced tool `mark_email_importance(important, summary)` | Single call per email |
| **Summarizer** | `services/conversation/summarization/` | `prompt_builder.py`: "chief-of-staff memory curator" rebuilds a briefing with these sections: Timeline, Pending, Routines, Preferences, Context | None | Single call per batch |

## What each agent sees

No agent keeps memory in-process. Every LLM call is rebuilt from scratch out of **append-only, XML-tagged log files** under `server/data/`. Within one turn, the message list grows with each assistant tool call and its tool result, for up to 8 iterations. That list is thrown away when the turn ends. Only what was written to a log carries over to the next turn.

### Interaction agent (Poke)

A turn starts on either a user message (`execute`) or a batched execution result or email-watcher alert (`handle_agent_message`).

| Slot | Content |
|---|---|
| **System prompt** | Static `agents/interaction_agent/system_prompt.md`, identical every turn |
| **User message** (one message) | `<conversation_history>`: the working-memory transcript, which is `<conversation_summary>` (if any) followed by verbatim `user_message` / `agent_message` / `poke_reply` / `wait` entries, all timestamped. Then `<active_agents>`: only the agent **names** from `execution_agents/roster.json`. Then `<new_user_message>` or `<new_agent_message>`: the event that started the turn |
| **In-turn** | Its own tool calls plus the results, e.g. `{"status": "submitted", "agent_name": …}` |
| **Persisted for next turn** | `user_message`/`agent_message` (the triggering event), `poke_reply` (from `send_message_to_user`, from `send_draft` formatted as `To/Subject/body`, or from plain-text fallback), and `wait` |

What it **doesn't** see:
- The `instructions` it sent to execution agents. They are written only to the execution agent's log, never to the conversation log.
- What any execution agent did internally.

All it sees afterwards is the agent's name in `<active_agents>` and, later, the result as `<new_agent_message>`: `[SUCCESS] <name>: <final text>`.

### Execution agent (one per name)

A turn starts on `send_message_to_agent` from Poke or on a trigger firing.

| Slot | Content |
|---|---|
| **System prompt** | `agents/execution_agent/system_prompt.md` with `{agent_name}` filled in and `{agent_purpose}` = `"Handle tasks related to: <name>"`. Then `# Execution History`: the **entire** `execution_agents/<slug>.log`, with no cap |
| **User message** | Poke's `instructions` verbatim. For a trigger, the instruction is `"Trigger fired at …"`, the trigger metadata, and the stored `payload` |
| **In-turn** | Full tool results (e.g. the complete JSON from `task_email_search` or Composio) |
| **Persisted for next turn** | `agent_request` (Poke path only), `agent_action` (`Calling <tool> with: <args[:200]>`), `tool_response` (**truncated to 500 chars**), `agent_response` (final text) |

What it **doesn't** see:
- The user conversation or the summary.
- Other execution agents.
- The user's original wording. It gets only what Poke chose to write.

Some quirks:
- On the Poke path, `agent_request` is logged *before* the run. The current instruction therefore appears twice: at the end of the history in the system prompt, and again as the user message.
- Trigger runs log no `agent_request`, only the final `agent_response`.
- When an agent is reused, it remembers its earlier tool results only as 500-character excerpts. The full email bodies from an earlier search are gone.

### Email search sub-agent (`task_email_search`)

| Slot | Content |
|---|---|
| **System prompt** | `system_prompt.py`: Gmail-operator guide with today's date filled in |
| **User message** | `"Please help me find emails: <search_query>"`. The execution LLM wrote `search_query` |
| **In-turn** | Each `gmail_fetch_emails` result: the cleaned emails (headers plus `clean_text`) |
| **Persisted** | Nothing. It is stateless. Its `record_action` lines go to a separate `task_email_search.log`, which no prompt reads |

It returns JSON built by code (selected IDs → cached `GmailSearchEmail` objects), not text written by an LLM.

### Importance classifier (email watcher)

- **System prompt:** an inline prompt.
- **User message:** a single email's metadata plus its cleaned body.
- **Tool:** the forced `mark_email_importance` tool.
- **Context:** no history. Each email is classified on its own.
- **If the email is important:** its `summary` goes to Poke as `<new_agent_message>` with the text `Important email watcher notification:\n<summary>`.

### Summarizer

- **System prompt:** `prompt_builder.py` ("chief-of-staff memory curator").
- **User message:** `Existing memory summary: <previous summary or None>`, then `New conversation logs to merge:`, then the batch of entries formatted as `[index] user message: …`.

### Context compaction (conversation only)

- **Trigger:** every append to the conversation log calls `schedule_summarization()`. That covers each user message, agent message, reply and `wait`, so a single turn often triggers it 2–3 times. Calls are merged into a single background worker, and it never blocks the turn.
- **Most checks don't call the LLM.** The summarizer counts entries after the last summarized index. It returns early unless there are at least `threshold + tail` = **100 + 10 = 110** of them (`conversation_summary_threshold` / `_tail_size` in `config.py`).
- **When it does run:** it folds the **oldest 100** unsummarized entries, together with the previous summary, into a new `conversation_summary`. It then rewrites `poke_working_memory.log` as the summary plus every entry after the cutoff, at least 10 and usually exactly 10. So compaction happens about once every 100 entries, and the verbatim tail swings between 10 and 109 entries.
- **What Poke reads:** every entry is written to both the raw log and the working-memory file. Poke reads the working-memory transcript whenever it is non-empty, which is effectively always. Until the first fold it is just a copy of the raw log. The raw `poke_conversation.log` is never compacted and is used only by the UI (and as a fallback).
- **Execution agent logs are never compacted.** `conversation_limit` exists but is never set.

### Triggers

Triggers live in `triggers.db` (SQLite) and are owned per agent name. When one fires, the instruction described above goes to that same agent, so it runs with that agent's full execution history.

## Message flow

1. `POST /api/chat` returns `202` right away. The interaction agent runs in the background.
2. Poke calls `send_message_to_user` (to acknowledge) and `send_message_to_agent`. The roster is updated, the request is logged, and the execution agent runs as an async task. The tool returns `submitted` without waiting for the agent to finish.
3. `ExecutionBatchManager` groups every execution agent started in the same turn into one batch. When the last one finishes, it sends a single `[SUCCESS|FAILED] <name>: <response>` message to `InteractionAgentRuntime.handle_agent_message`.
4. Poke handles that `<new_agent_message>`. It summarizes the result for the user, calls `send_draft` followed by `send_message_to_user` if there is a draft, or calls `wait` if the information was already shown. To send a draft, it sends a confirmation back to the **same** agent, which then calls `gmail_execute_draft`.
5. The **email watcher** and the **trigger scheduler** go through the same entry points. The watcher sends `"Important email watcher notification: …"` as an agent message, and the scheduler calls `execute_agent`, whose results flow back through step 3.

## Notable gaps / quirks

- The execution prompt lists only 4 Gmail tools and the 3 trigger tools, although more are registered. It also still contains a placeholder: `[TO BE FILLED IN BY USER]`.
- The interaction prompt mentions a `reacttomessage` tool that doesn't exist.
- Execution history is added to the prompt in full, with no limit (`conversation_limit` is never set). Long-lived agents will keep growing.
- The trigger scheduler creates a new `ExecutionBatchManager` for each trigger, so its batches are separate from the interaction agent's batches.
- Gmail is the only integration (through Composio). Everything runs for a single user, with global file-based state.
