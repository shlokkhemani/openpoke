# Runtime experiments — results & reproduction

## Method

The **unmodified** FastAPI app is booted by `analysis/lab/launch_server.py`, which applies process-local patches only.
Nothing on disk in `server/` changes, so this is fully reversible: delete `analysis/` and `.venv-lab/`.

| Seam | Patch | Why |
|---|---|---|
| OpenRouter | `request_chat_completion.__kwdefaults__["base_url"]` → `analysis/lab/mock_openrouter.py` | Captures **every outbound LLM request body verbatim** (`state/llm_captures.jsonl`) and returns scripted tool calls so the real orchestration code runs |
| Composio | `gmail.client._CLIENT = FakeComposio` (`analysis/lab/fake_composio.py`) | Synthetic inbox; logs every Composio call |
| Poll intervals | watcher 3 s, trigger scheduler 1 s | Run in seconds |
| Summary knobs | `LAB_SUMMARY_THRESHOLD/TAIL` env (S5, S6 only) | Defaults (100/10) are used in S3/S4 |

All secrets and PII are synthetic markers, e.g. `LOCKER-7781-SYNTH`, `sk-test-SYNTHETIC-…`, `000-12-3456`, the Visa
test PAN `4111 1111 1111 1111`, `jane.synthetic@example.test`, OTPs `482913`/`771204`, and `42 Synthetic Lane`. The
OpenRouter key is `sk-or-v1-SYNTHETIC-LAB-KEY-0000`.

**Limits of the mock.** The mock LLM is deterministic. These tests therefore prove the *plumbing*: what is stored,
what is sent, what is dropped, and what is re-read. They do not prove what a real model would choose to keep. To bound
that, summarisation was run with two mock policies: **faithful** (keeps every user line) and **lossy** (keeps nothing).
In production, retention falls somewhere between the two, decided entirely by the model.

### Reproduce

```bash
cd OpenPoke
python3.13 -m venv .venv-lab
.venv-lab/bin/pip install 'fastapi>=0.115' 'uvicorn>=0.30' 'pydantic>=2.7' 'httpx>=0.27' python-dateutil beautifulsoup4
cd analysis/lab
../../.venv-lab/bin/python run_experiments.py            # all scenarios, ~2.5 min
../../.venv-lab/bin/python run_experiments.py core       # or one: core race_exec summary_faithful summary_lossy summary_fail race_summary
# results/<scenario>.json  + results/<scenario>.llm_captures.jsonl (every LLM request body)
```

⚠️ The runner wipes `server/data/` before each scenario. Don't run it against a checkout with real data.

## Results

### S1 `core`: persistence, PII, Gmail, triggers, restart, scoping, deletion

| Question | Result | Evidence |
|---|---|---|
| Facts persist across turns? | **Yes.** `locker_code_in_next_turn_history: true`; the API key is too | Turn-3 interaction payload `<conversation_history>` |
| Facts persist across restart? | **Yes.** History length 13 → 13; the locker code is in the first LLM call after restart | `restart.*` |
| Agent roster survives restart? | Yes (`["Synthetic Lab Agent"]`) | `roster_after_restart` |
| Gmail watcher after restart? | **Silently stops.** 0 Gmail fetches in 7 s after restart (the active user id lives only in RAM) | `watcher_gmail_fetches_in_7s_after_restart: 0` |
| Exec agent sees interaction history? | **No.** Only its own per-name log plus the instruction string | `execution_agent_input` |
| Call fan-out for one delegated search | `interaction ×2 → execution → search ×2 → execution → interaction ×2` = **8 LLM calls** | `delegation_call_sequence` |
| Gmail fields → search LLM (B3) | `attachment_count, attachment_filenames, clean_text, has_attachments, id, label_ids, query, recipient, sender, subject, thread_id, timestamp` | `gmail_fields_to_search_subagent_llm` |
| Wire format of search results | **Python `repr()`, not JSON** (`{"repr": "{'status': 'success', … datetime.datetime(…)}"}`) | `search_tool_result_wire_format` |
| Gmail fields → execution LLM (B2) | Same 12 fields, full body | `gmail_fields_to_execution_agent_llm` |
| Email OTP reaches the interaction LLM + conversation log? | **Yes** (`otp_body_reached_interaction_agent: true`) | Locations table |
| Gmail fields → classifier LLM (B4) | Sender, Recipient, Subject, Received, Thread ID, Labels, Has attachments, Attachment filenames, **full cleaned body** (an OTP and address were sent) | `email_classifier_payload` |
| Watcher summary persisted? | **Yes.** The OTP `771204` is in the conversation log and working memory | `watcher_summary_in_conversation_log: true` |
| Trigger persistence | A row holds the payload with `GATE-PIN-5521` and a daily RRULE | `trigger_rows` |
| Per-user scoping (chat) | **None.** An unauthenticated client with a different identity reads the locker code via `GET /chat/history` | `unauthenticated_other_client_sees_locker_code: true` |
| Per-user scoping (Gmail) | **Global switch.** After a `POST /gmail/status {user_id: B}`, the next search runs against B's mailbox for everyone | `composio_user_ids_used_after_user_B_status_call: ["lab-user-B"]` |
| OpenRouter key persisted? | No; it is only sent as an HTTP header | `openrouter_key: []` |
| Markers in server stdout? | None of the markers. Stdout does contain the search instruction text and agent names (`[EMAIL_SEARCH] Starting search for: '…'`) | `state/server_stdout.log` |

**Where each synthetic value physically lived before deletion** (`locations_before_restart`):

| Marker | conv log | working mem | exec agent log | triggers db/WAL | LLM calls that received it |
|---|---|---|---|---|---|
| locker code, PII email, API key, SSN-like, card | ✔ | ✔ | – | – | interaction |
| search-email OTP `482913` | ✔ | ✔ | ✔ | – | search, execution, interaction |
| watched-email OTP `771204` | ✔ | ✔ | – | – | classifier, interaction |
| street address (email body) | ✔ | ✔ | ✔ | – | search, execution, interaction, classifier |
| trigger PIN | ✔ | ✔ | ✔ | ✔ (WAL) | interaction, execution |

**After `DELETE /chat/history`** (`locations_after_delete`):

- Conversation log, execution logs, and roster are removed. Working memory is re-initialised.
- `GATE-PIN-5521` **is still in `triggers.db` and `triggers.db-wal`.** `DELETE FROM` frees pages without overwriting them; no `VACUUM` or `secure_delete`.
- `gmail_seen.json` and `timezone.txt` are untouched.
- Every value already sent to OpenRouter (and Composio) cannot be deleted from this side.

### S2 `race_exec`: deletion while an execution agent is in flight

The execution agent was delayed 4 s, then `DELETE /chat/history` ran 2 s after the request.

| Moment | `RACE-MARKER-9090` on disk |
|---|---|
| Before delete | conv log, WM, exec log |
| Right after delete | none |
| After the in-flight agent finished | **conv log, WM, exec log again**. `/chat/history` shows `"Update: [SUCCESS] Synthetic Lab Agent: Done: note RACE-MARKER-9090"` |

**Deleted data is resurrected.** `clear_history` does not cancel or fence background tasks.

### S3 `summary_faithful` / S4 `summary_lossy`: what triggers summarisation, and what survives (defaults 100/10)

Script: turn 0 "dentist is Dr. Alpha", turn 1 "LOCKER-OLD-1111", turns 2–47 filler, turn 48 "Correction: dentist is
now Dr. Beta", turn 49 "LOCKER-NEW-2222", fillers up to turn 55, then a probe question.

| | faithful | lossy |
|---|---|---|
| First summariser call | turn 54 = **110 entries** | same |
| Batch sent | entries **0–99** (100), tags `user message` + `poke reply` | same |
| WM after | `last_index: 99`, summary + 10–12 raw entries | same |
| Raw conversation log | 114 lines, **nothing removed** | same |
| Old facts visible to the LLM on the probe | Alpha ✔, Beta ✔, OLD ✔, NEW ✔ (**both conflicting values together**, no ordering or supersession marker) | **all four ✘** |
| Facts still on disk and in `/chat/history` | all ✔ | **all ✔** (user can see them; assistant can't recall them) |

Takeaways:

- Retention after summarisation depends entirely on one free-text LLM output.
- Conflicts are never resolved structurally. In the faithful case, the stale and current values both reach the model.
- Every successful summary makes another LLM copy of the 100 raw entries.

### S5 `summary_fail`: summariser outage (threshold 10 / tail 2 for speed)

- **26 summariser requests in 7 turns.** Every log append re-schedules a pass, and every pass makes 2 attempts. Each one resends the same ~2.9 KB batch. There is no backoff and no circuit breaker.
- WM keeps `last_index: -1`, so the raw tail grows without bound. That raw tail goes to the interaction LLM every turn (24 raw entries at the probe).

### S6 `race_summary`: deletion while the summariser is in flight

The summariser was delayed 4 s, and the marker `SUMMARY-RACE-SECRET-3141` was in turn 0.

| Check | Result |
|---|---|
| Summariser in flight at delete | true |
| Marker in WM after the summariser finished | **true** (the summary was re-written *after* the delete) |
| `summary_info` after delete | `last_index: 9` (stale index into a log that now has 2 lines) |
| Marker sent to the LLM on the next turn ("Hello again after deleting everything.") | **true** |

The deleted conversation comes back into the model's context. The stale `last_index` also means the next ≥10 entries
of the new conversation are invisible to the summariser.

### Code-only observations (not executed)

- Concurrent `/chat/send` calls each snapshot the transcript before the other writes. One global batch manager merges results from unrelated delegations into a single `agent_message`.
- Execution-agent memory is unbounded (`conversation_limit=None`) and keyed by an LLM-chosen name. `_slugify` makes "Email Bob" and "email-bob" share one file.
- `prompt_builder.py:80`: `dedent()` is defeated by interpolated multi-line text, so the summariser input keeps 8-space indentation on the header lines and the first entry. This is cosmetic, but it broke a naive parser in the first run of this harness.
