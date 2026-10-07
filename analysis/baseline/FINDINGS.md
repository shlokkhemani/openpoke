# OpenPoke: current-state findings (memory & privacy)

Baseline commit `5b5f635`. Details: [ARCHITECTURE.md](ARCHITECTURE.md) · Evidence: [TEST_RESULTS.md](TEST_RESULTS.md).
This document describes the system as it is. It deliberately proposes no new architecture.

## The system in one paragraph

OpenPoke is a single-process, **single-tenant** FastAPI app.

- **Memory.** It keeps one global conversation as an append-only, plaintext tag log (`poke_conversation.log`). "Working memory" is a second file: one LLM-written free-text summary plus a verbatim copy of the not-yet-summarised entries.
- **Interaction agent.** Each turn sends the summary, 10–109 raw entries, and the full agent roster to OpenRouter.
- **Summarisation.** It fires at 110 unsummarised entries (≈55 turns) and folds the oldest 100 into a new summary. The raw log is never compacted.
- **Execution agents.** Each keeps a separate, unbounded per-name log that is re-injected whole on every call. They never see the user conversation, only an instruction string.
- **Gmail.** Two paths read Gmail through Composio: an on-demand search sub-agent and a background watcher. The watcher sends the full body of every new inbox email to a classifier LLM. Its summaries (OTPs included, by design) are written into the conversation forever.
- **Isolation and deletion.** Nothing is scoped per user, nothing is redacted, and deletion is a best-effort file unlink that background tasks undo.

## What happens to a fact

| Question | Answer |
|---|---|
| Persists across turns | Yes, as raw text in the history block (S1) |
| Persists across restart | Yes, from files (S1). Gmail watcher state does **not**: the active user lives in RAM |
| What triggers summarisation | ≥ threshold + tail = **110** unsummarised log entries, checked on every append (S3) |
| What survives summarisation | Whatever the summariser LLM writes. There is no deterministic extraction. Faithful policy: everything; lossy policy: nothing (S3/S4) |
| Conflicting facts | No supersession, timestamps, or provenance. Old and new values coexist in the summary and/or tail (S3) |
| Stale facts | Kept forever in the raw log, `/chat/history` and execution logs. Dropped from LLM context only if the summariser drops them |
| Where secrets/PII persist | conv log, working memory, exec-agent logs, Gmail tool journal, triggers.db (+WAL) (S1) |
| Raw values in LLM payloads | Yes, all of them, verbatim, on every subsequent turn until summarised (S1) |
| Deletion removes derived data | **No.** Trigger residue, untouched seen-store/timezone, in-flight resurrection (S2, S6), and external copies |
| Per-user storage | **No.** Unauthenticated global endpoints, and a global Gmail identity switch (S1) |
| Gmail fields sent to models | 12-field objects with full `clean_text` to search + execution LLMs. 8 headers + full body to the classifier for every new email (S1) |

## Weaknesses ranked by severity

Severity reflects impact × likelihood for a deployed, real-mailbox assistant. ✔ = reproduced at runtime; ⓒ = from code.

| # | Sev | Weakness | Evidence |
|---|---|---|---|
| F-1 | **Critical** | **No identity, auth or tenancy.** Every endpoint is unauthenticated. The server binds `0.0.0.0` with `CORS *`, so anyone who can reach the port can read the full history, wipe it, change the timezone, or point the global Gmail binding at another `user_id`. All stores are process singletons | ✔ S1 scoping; ⓒ `config.py:66`, `services/gmail/client.py:24` |
| F-2 | **High** | **Deletion is incomplete and non-atomic.** (a) In-flight execution agents and the summariser re-write logs/summary after `DELETE` (✔ S2, S6). (b) Trigger payloads remain in `triggers.db`/WAL (✔ S1). (c) `gmail_seen.json`, `timezone.txt`, the in-memory profile cache, and the Composio connection are untouched. (d) OpenRouter/provider/Composio copies can't be addressed. (e) The stale `last_index` corrupts the post-delete summariser state (✔ S6) | `routes/chat.py:26-43`, `triggers/store.py:122` |
| F-3 | **High** | **Secrets, OTPs and PII are stored and replayed verbatim.** No detection, redaction, encryption at rest, or TTL. Each value lands in 2–4 files and is resent to the LLM on every turn (up to ~55 turns, longer on summariser failure). Summariser rule 5 ("include all … identifiers") pushes secrets into the long-lived summary | ✔ S1 locations; ⓒ `prompt_builder.py:53` |
| F-4 | **High** | **Gmail over-collection to third-party models.** The watcher sends the **full body of every new inbox email** to an LLM with no user request. The classifier is told OTPs are "important", so OTP summaries are permanently written into the conversation and re-sent. Search results ship all 12 fields to two models and 500 chars into exec logs | ✔ S1 classifier/search; ⓒ `importance_classifier.py:30,50`, `importance_watcher.py:225` |
| F-5 | **Med-High** | **Memory is one free-text blob.** No structured facts, provenance, confidence, timestamps-of-assertion, or conflict resolution. Summarisation can silently drop facts (✔ S4), and keeps contradictory values side by side (✔ S3). The user still sees dropped facts in `/history` while the assistant can't recall them | `summarizer.py`, `prompt_builder.py` |
| F-6 | **Medium** | **Summariser failure → request storm + unbounded context.** 2 attempts per append, no backoff (26 calls/7 turns ✔ S5). The raw tail then grows without limit into every interaction call | `scheduler.py`, `summarizer.py:30-70` |
| F-7 | **Medium** | **Execution-agent memory is unbounded and mis-keyed.** The full per-name log goes into the system prompt each call. Names are LLM-chosen and reused across topics, and `_slugify` collisions merge logs. The roster is never pruned and is sent on every turn | ⓒ `execution_agent/agent.py:73`, `log_store.py:_slugify` |
| F-8 | **Medium** | **Raw log never compacted.** Stale facts are retained indefinitely, and pre-summary working memory is a full duplicate | ✔ S3 (114 lines after summarising) |
| F-9 | **Medium** | **Gmail binding is volatile and global.** It's lost on restart (watcher idles silently, ✔ S1) and the last `/gmail/status` caller wins for all background work. The default `user_id` is `web-<pid>` | `gmail/client.py:215` |
| F-10 | **Low-Med** | **Search results reach the LLM as Python `repr`.** `json.dumps` fails on `datetime` and falls back to `{"repr": …}`, so the sub-agent parses a non-JSON blob | ✔ S1; `search_email/tool.py:418-420` |
| F-11 | **Low-Med** | **Concurrency.** Overlapping turns snapshot stale transcripts. The global batch manager merges unrelated agent results into one message | ⓒ `interaction_agent/runtime.py:69`, `batch_manager.py:101` |
| F-12 | **Low** | **Log hygiene.** Stdout logs Gmail search instructions/queries, agent names and draft recipients. Unhandled-exception paths log full tracebacks. Structured `extra={}` fields are dropped by the formatter, so most PII in `extra` doesn't print | ⓒ `search_email/tool.py:95`, `interaction_agent/tools.py` |
| F-13 | **Low** | **Small correctness issues.** The summariser `dedent` bug; HTML-escaped payloads (`&amp;`) inside context; timestamps without UTC offset in the user's *current* timezone (changing timezone re-labels history inconsistently); summarisation knobs not configurable via env | `prompt_builder.py:80`, `log.py:69`, `config.py:71` |

## Things that are fine today

- The OpenRouter key is never persisted or logged (✔ S1).
- `extra={}` log fields are not rendered.
- Working-memory rewrites are atomic (tmp + rename).
- The Gmail seen-store holds IDs only.
- Execution logs truncate tool args and results (200/500 chars). The Gmail journal (`gmail-execution-agent.log`) does not.
