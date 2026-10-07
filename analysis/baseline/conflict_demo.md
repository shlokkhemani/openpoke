# Conflict Memory Demo

Captured 2026-10-07 against a live local OpenPoke instance (model `anthropic/claude-sonnet-4` via OpenRouter). No production code was changed and no runtime data was modified.

## Slide summary

User said "Python", then "Actually… Rust", then asked which one is their favorite. OpenPoke answered **Rust**.

| Layer | "Python" (old fact) | "Rust" (new fact) | Superseded? | Evidence |
|---|---|---|---|---|
| Conversation log | Present | Present | No | `poke_conversation.log` L1 "…is Python." · L3 "Actually, …is Rust." |
| Working memory | Present | Present | No | `poke_working_memory.log` L3 / L5 (verbatim copy; summary empty, `last_index: -1`) |
| Final LLM context | Present | Present | No | `runtime.py:194-199` loads working memory → `agent.py:37-41` wraps it in `<conversation_history>` containing both lines |

**Takeaway:** The model selected the newer fact, but the memory system did not structurally supersede the old one.

**Citation:** Baseline evidence: `analysis/conflict_demo.md`, OpenPoke baseline, commit `93ea674` (2026-10-07). https://github.com/suneruperera0/openpoke-memory/blob/93ea674/analysis/conflict_demo.md

## User sequence

| Turn | Time (America/Toronto) | User message | OpenPoke reply (abridged) |
|---|---|---|---|
| 1 | 12:03:21 | My favorite programming language is Python. | "Nice choice! Python's pretty sweet…" |
| 2 | 12:03:31 | Actually, my favorite programming language is Rust. | "Ah, switching to the dark side I see! Rust is solid…" |
| 3 | 12:03:41 | What's my favorite programming language? | "…your favorite programming language is **Rust**! You corrected yourself from Python to Rust just a minute ago." |

The answer was correct.

## Conversation log

File: `server/data/conversation/poke_conversation.log` (sha256 `4c447eb8…b52f3f31`)

Python: **present**
Rust: **present**

| Line | Entry | Python | Rust |
|---|---|---|---|
| 1 | `<user_message>` My favorite programming language is Python. | ✔ | |
| 2 | `<poke_reply>` Nice choice! Python's pretty sweet… | ✔ | |
| 3 | `<user_message>` Actually, my favorite programming language is Rust. | | ✔ |
| 4 | `<poke_reply>` …Rust is solid… | | ✔ |
| 5 | `<user_message>` What's my favorite programming language? | | |
| 6 | `<poke_reply>` …is Rust! You corrected yourself from Python to Rust… | ✔ | ✔ |

This file is append-only. Nothing in it marks line 1 as stale.

## Working memory

File: `server/data/conversation/poke_working_memory.log` (sha256 `b2712289…ce658fbfc6`)

Python: **present**
Rust: **present**

| Line | Entry | Python | Rust |
|---|---|---|---|
| 1 | `<summary_info>{"last_index": -1, "updated_at": null}</summary_info>` | | |
| 2 | `<conversation_summary></conversation_summary>` (empty) | | |
| 3 | `<user_message>` …is Python. | ✔ | |
| 4 | `<poke_reply>` …Python's pretty sweet… | ✔ | |
| 5 | `<user_message>` Actually, …is Rust. | | ✔ |
| 6 | `<poke_reply>` …Rust is solid… | | ✔ |
| 7 | `<user_message>` What's my favorite programming language? | | |
| 8 | `<poke_reply>` …Rust! You corrected yourself from Python to Rust… | ✔ | ✔ |

Working memory is a verbatim copy of the conversation log, plus a summary header. The summary is empty (`last_index: -1`). The summarizer only runs once there are at least `conversation_summary_threshold + conversation_summary_tail_size` = 100 + 10 = 110 unsummarized entries (`server/config.py:71-72`, `server/services/conversation/summarization/summarizer.py:84-94`). With only 6 entries, nothing was condensed or rewritten.

Execution agents: `server/data/execution_agents/roster.json` is `[]`. No execution agent ran during this conversation, so there are no execution-agent logs, and Python and Rust appear nowhere else in `server/data/`.

## Final LLM context

The exact OpenRouter request body is not logged by OpenPoke. I rebuilt it deterministically with the production functions, on a copy of the data:

- **Transcript:** `InteractionAgentRuntime.execute` (`server/agents/interaction_agent/runtime.py:69-75`) reads the transcript before it records turn 3. `_load_conversation_transcript` (`runtime.py:194-199`) uses `WorkingMemoryLog.render_transcript()` (`server/services/conversation/summarization/working_memory_log.py:181`) because summarization is enabled.
- **Message assembly:** `prepare_message_with_history` (`server/agents/interaction_agent/agent.py:20-33`) wraps that transcript in `<conversation_history>`, then adds `<active_agents>` and `<new_user_message>`.
- **Input data:** a copy of working memory lines 1–6 (the state just before turn 3), passed through those same functions. The system prompt (`server/agents/interaction_agent/system_prompt.md`) is static and contains neither word.

Python: **present**
Rust: **present**

Exact reconstructed `messages[0].content` sent with the final question:

```xml
<conversation_history>
<user_message timestamp="2026-10-07 12:03:21">My favorite programming language is Python.</user_message>
<poke_reply timestamp="2026-10-07 12:03:23">Nice choice! Python's pretty sweet - clean syntax, tons of libraries, and you can build basically anything with it. What kind of stuff do you like to work on?</poke_reply>
<user_message timestamp="2026-10-07 12:03:31">Actually, my favorite programming language is Rust.</user_message>
<poke_reply timestamp="2026-10-07 12:03:33">Ah, switching to the dark side I see! Rust is solid - memory safety without garbage collection is pretty slick. What drew you to it?</poke_reply>
</conversation_history>

<active_agents>
None
</active_agents>

<new_user_message>
What’s my favorite programming language?
</new_user_message>
```

The model's own reply ("You corrected yourself from Python to Rust") confirms it saw both statements.

## Conclusion

**The model selected the newer fact, but the memory system did not structurally supersede the old one.**

- **No resolution logic:** no component removes, overwrites, or marks the Python statement as outdated. A search of `server/` for supersede/conflict/dedupe/contradict logic finds nothing.
- **What's stored:** both storage layers keep the raw transcript verbatim. The conflicting statements reach the LLM side by side.
- **Why the answer was right:** the LLM resolved the conflict at inference time, using message order and the word "Actually."
- **When this could break:** the correct answer depends on the model's reasoning, not on memory state. It could fail once the summarizer kicks in (at 110 entries) and condenses these turns ambiguously, or when the two statements are far apart in a long context.

## Reproduce

The final-context reconstruction uses `analysis/lab/reconstruct_prompt.py`. It imports the production prompt builders and only reads a copy of working memory; it never writes to `server/data/`.

```bash
cp server/data/conversation/poke_working_memory.log /tmp/wm_copy.log
.venv/bin/python analysis/lab/reconstruct_prompt.py "$PWD" /tmp/wm_copy.log /tmp/wm_before_turn3.log
```
