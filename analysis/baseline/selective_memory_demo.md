# Selective Memory Demo (Baseline Proof #3)

Captured 2026-10-07 against a live local OpenPoke instance (model `anthropic/claude-sonnet-4` via OpenRouter). No production code was changed and no runtime data was modified.

## Slide summary

One message mixed a durable preference with a throwaway detail: "I prefer meetings after 10 AM. I'm eating a turkey sandwich right now." Then: "When do I prefer meetings?" → OpenPoke answered **"After 10 AM"**.

| Fact | Conversation Log | Working Memory | Final LLM Context | Keep/Ignore Decision |
|---|---|---|---|---|
| Meeting preference | Present | Present | Present | None |
| Turkey sandwich | Present | Present | Present | None |

Line references: conversation log `server/data/conversation/poke_conversation.log` L1–L2 · working memory `server/data/conversation/poke_working_memory.log` L3–L4 · final context `<conversation_history>` (reconstructed, see below).

**Write path:** `log.py:136-138` `record_user_message()` appends the raw text to both files, with no filtering step (`log.py:68-81`, `working_memory_log.py:83`).

**Citation:** Baseline evidence: `analysis/baseline/selective_memory_demo.md`, OpenPoke baseline (2026-10-07).

## User sequence

| Turn | Time (America/Toronto) | User message | OpenPoke reply |
|---|---|---|---|
| 1 | 12:38:52 | I prefer meetings after 10 AM. I'm eating a turkey sandwich right now. | "Got it - noted your preference for meetings after 10 AM. How's that turkey sandwich treating you?" |
| 2 | 12:41:09 | When do I prefer meetings? | "After 10 AM - you mentioned that just a bit ago." |

The reply says "noted your preference", but nothing was noted anywhere: the only trace is the verbatim transcript line. The reply also brings up the sandwich, so the model treated both details alike.

> **Capture note:** the working memory was snapshotted twice: once after turn 1 (12:39) and again after turn 2 (12:41). Lines 1–4 of the post-turn-2 file are byte-identical (`cmp`) to the post-turn-1 snapshot. That proves the "Final LLM context" below was built from the exact state the runtime read for turn 2. The backend log shows turn 2 at 12:41:09, answered via `send_message_to_user` at 12:41:12.

## Conversation log

File: `server/data/conversation/poke_conversation.log` (sha256 `72a51401…7fae3193`, after turn 2)

meetings after 10 AM: **present**
turkey sandwich: **present**

| Line | Entry | "meetings after 10 AM" | "turkey sandwich" |
|---|---|---|---|
| 1 | `<user_message>` I prefer meetings after 10 AM. I'm eating a turkey sandwich right now. | ✔ | ✔ |
| 2 | `<poke_reply>` Got it - noted your preference for meetings after 10 AM. How's that turkey sandwich treating you? | ✔ | ✔ |
| 3 | `<user_message>` When do I prefer meetings? | | |
| 4 | `<poke_reply>` After 10 AM - you mentioned that just a bit ago. | | |

## Working memory

File: `server/data/conversation/poke_working_memory.log` (sha256 `dd16e3fd…2a5145776`, after turn 2; lines 1–4 = pre-turn-2 state, sha256 `928eb69f…9dd36f0f`)

meetings after 10 AM: **present**
turkey sandwich: **present**

| Line | Entry | "meetings after 10 AM" | "turkey sandwich" |
|---|---|---|---|
| 1 | `<summary_info>{"last_index": -1, "updated_at": null}</summary_info>` | | |
| 2 | `<conversation_summary></conversation_summary>` (empty) | | |
| 3 | `<user_message>` (identical to conversation log L1) | ✔ | ✔ |
| 4 | `<poke_reply>` (identical to conversation log L2) | ✔ | ✔ |
| 5 | `<user_message>` (identical to conversation log L3) | | |
| 6 | `<poke_reply>` (identical to conversation log L4) | | |

There is no separate preference or profile store. `server/data/` contains only these two logs, `triggers.db`, `timezone.txt`, and `execution_agents/roster.json` (`[]`).

## Final LLM context

The context for "When do I prefer meetings?" depends only on the working-memory state before that turn, plus the new message:

- `InteractionAgentRuntime.execute` reads the transcript before it records the new message (`server/agents/interaction_agent/runtime.py:69-70`).
- `_load_conversation_transcript` uses `WorkingMemoryLog.render_transcript()` (`runtime.py:194-199`).
- `prepare_message_with_history` (`server/agents/interaction_agent/agent.py:20-41`) wraps it in `<conversation_history>`.

I rebuilt it with those production functions, run on the pre-turn-2 working-memory snapshot (lines 1–4), which is byte-identical to what the runtime read.

meetings after 10 AM: **present**
turkey sandwich: **present**

```xml
<conversation_history>
<user_message timestamp="2026-10-07 12:38:52">I prefer meetings after 10 AM. I’m eating a turkey sandwich right now.</user_message>
<poke_reply timestamp="2026-10-07 12:38:54">Got it - noted your preference for meetings after 10 AM. How's that turkey sandwich treating you?</poke_reply>
</conversation_history>

<active_agents>
None
</active_agents>

<new_user_message>
When do I prefer meetings?
</new_user_message>
```

## Is there a STORE / IGNORE code path?

**No, not at write time. And at read time, the one LLM-based curation step never ran in this test.**

| Mechanism | Location | Classifies durable vs. temporary? |
|---|---|---|
| User message write | `server/services/conversation/log.py:136-138` → `_append` (`log.py:68-81`) + `WorkingMemoryLog.append_entry` (`working_memory_log.py:83`) | **No.** The raw text is appended to both files unconditionally. |
| Reply write | `log.py:144-146`, called from `interaction_agent/tools.py:157` | **No.** Same unconditional append. |
| Interaction-agent prompt | `server/agents/interaction_agent/system_prompt.md` | **No.** It has no instructions to save or ignore facts. Line 66 says history "may contain a summary". |
| Email classifier | `server/config.py:58` (`email_classifier_model`), important-email watcher | **No.** It classifies inbound Gmail messages, not conversation memory. |
| Summarizer (only candidate) | `server/services/conversation/summarization/prompt_builder.py:16-58` | **Implicitly, through the prompt only.** It asks the LLM for a "Preferences & Profile" section (L37) and to "Remove items that are complete or obsolete" (L50). It doesn't produce an explicit STORE/IGNORE label or structured record. |
| Summarizer trigger | `summarizer.py:84-94`, `server/config.py:71-72` | Runs only once there are ≥ 110 unsummarized entries (threshold 100 + tail 10). This test had 4, so it **never ran** (`last_index: -1`, empty summary). |

A keyword scan of `server/**/*.py` for durable / long-term / remember / memorize / preference / classify / STORE / IGNORE found no memory-classification logic. The only hits were the email classifier model setting, Gmail search filters, and execution-agent log stores.

## Conclusion

"OpenPoke answered correctly because the model reread the raw conversation context. The memory system did not selectively retain the useful preference while discarding the temporary detail."

- **Same handling:** both facts are written verbatim, in the same entry, to both the conversation log and working memory.
- **Same context:** they reach the model together as raw transcript.
- **No classifier:** no code path labels either one keep or ignore.
- **The only selectivity is latent:** it's an LLM prompt in the summarizer, which only activates after 110 entries and rewrites a free-text summary.

## Integrity

- **No production code changed:** `git status` shows no modifications under `server/` or `web/`. This file is the only change in the evidence commit.
- **Runtime data was read only:** the logs were copied to a scratch directory before analysis. Post-turn-2 sha256 hashes were taken: `poke_conversation.log` `72a51401…7fae3193`, `poke_working_memory.log` `dd16e3fd…2a5145776`. The live files were checked against them again afterwards and were unchanged. The reconstruction ran on a copy, never on `server/data/`.

## Reproduce

```bash
head -4 server/data/conversation/poke_working_memory.log > /tmp/wm_copy.log   # state before turn 2
.venv/bin/python - "$PWD" /tmp/wm_copy.log <<'EOF'
import sys; sys.path.insert(0, sys.argv[1])
from pathlib import Path
from server.services.conversation.summarization.working_memory_log import WorkingMemoryLog
from server.agents.interaction_agent.agent import prepare_message_with_history
print(prepare_message_with_history("When do I prefer meetings?",
      WorkingMemoryLog(Path(sys.argv[2])).render_transcript())[0]["content"])
EOF
grep -n -i "meetings after 10\|turkey sandwich" server/data/conversation/*.log
```
