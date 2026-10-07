# OpenPoke LTM: Implementation Handoff

**Audience:** the implementation agent.
**Goal:** build exactly what the frozen spec describes, until the acceptance gates in §6 pass, and emit
`openpoke.ltm.demo_trace.v1` files for the four presentation proofs in both modes.
**Do not build the visual UI.**

---

## 1. The frozen spec

| Document | Role | sha256 at freeze |
|---|---|---|
| [LTM_SYSTEM_DESIGN.md](LTM_SYSTEM_DESIGN.md) | Architecture, gates (§19.1), proofs table (§24), data contract (§25), file list (§26) | `e60c47262464a4048d8968adabeb9ca6c3e5f241bca0d773e8e98e136d2a76c7` |
| [LTM_DECISIONS.md](LTM_DECISIONS.md) | Decisions D1–D28 | `ae5d955da2e5aeb70a26f9e8a79497ee9b349939821de3f6259a55321c2e8655` |
| [LTM_ENGINEERING_DEEP_DIVE.md](LTM_ENGINEERING_DEEP_DIVE.md) | Algorithms, constants, DDL, pseudocode, harness (§29) | `134698b7578a656685123a30790394918c2d2697c0a0dafff5b28b3be4b003cc` |

Verify before starting:

```bash
cd analysis/design && shasum -a 256 LTM_SYSTEM_DESIGN.md LTM_DECISIONS.md LTM_ENGINEERING_DEEP_DIVE.md
```

**Precedence when documents disagree:**
1. This handoff's §4 *binding clarifications*.
2. Design §19.1 / §24 / §25 (gates and contract).
3. The deep-dive constants and pseudocode.
4. Everything else in the design.

Constants (thresholds, weights, TTLs, k, token budget) are taken **verbatim** from the deep dive. Do not tune them to make a test pass.
If a gate can't pass with the spec constants, that's a blocker (§2).

Background evidence, not spec: [ARCHITECTURE.md](../baseline/ARCHITECTURE.md), [FINDINGS.md](../baseline/FINDINGS.md), [TEST_RESULTS.md](../baseline/TEST_RESULTS.md),
[conflict_demo.md](../baseline/conflict_demo.md).

---

## 2. Ground rules and blocker protocol

**Ground rules**

1. **Scope is frozen.** Build only what is listed in §3. Section 9 lists what not to build.
2. **No new dependencies.** Use the standard library only (`sqlite3`, `re`, `json`, `hmac`, `hashlib`, `asyncio`, `unittest`), plus
   packages already in `server/requirements.txt` (FastAPI, httpx, pydantic).
3. **Python 3.10 compatible.** The README requires 3.10+. That means no `enum.StrEnum` (use `class X(str, Enum)`), no `typing.Self`,
   and no `datetime.UTC` (use `timezone.utc`). Develop and run the gate on 3.13 (`/opt/homebrew/bin/python3.13`, as the lab used), but
   don't use 3.11+ APIs.
4. **Flags default off. With them off, behaviour must be byte-identical to the baseline:**
   - no `server/data/memory/` directory;
   - no new prompt sections;
   - the same system prompt (sha256);
   - the same files written.
5. **Don't touch `web/`.** Summariser, Gmail, trigger and `openrouter_client/` modules are used as-is.
6. **Never write a real or synthetic secret into any committed file, log line, event, trace or test fixture output.** Test inputs may
   contain the synthetic markers. Test *outputs* must not.
7. **Don't commit or push** unless the user explicitly asks. Leave the working tree for review.
8. **Don't edit the three frozen documents.**

**Blocker protocol** (when implementation reveals the spec can't be built as written):

1. Stop the affected step. Don't work around it silently.
2. Append an entry to `analysis/design/LTM_BLOCKERS.md`: id, step, observed problem (with file:line or test output), the minimal deviation
   proposed, the gates affected, and why no smaller change works.
3. Apply only that minimal deviation, keeping it behind the same flags, and continue.
4. List every blocker in the final report (§10).

Pre-approved fallbacks (use them without a blocker entry, but record them in the final report):
- **FTS5 `secure-delete` unavailable** (SQLite < 3.42): after each delete, run `INSERT INTO memories_fts(memories_fts) VALUES('optimize')`.
  The byte canary gate is the arbiter. Verified available on this machine: Python 3.13/3.14 → SQLite 3.53.4, and system 3.9 → 3.51.0.
- **`PRAGMA secure_delete` silently unsupported:** additionally run `VACUUM` after a delete in test mode only. Record this.

---

## 3. Deliverables

### 3.1 New files

```
server/services/memory/
  __init__.py        get_memory_service(), resolve_memory_scope()
  models.py          enums (str, Enum), MemoryScope, TurnRef, Finding, ScrubbedText, Candidate, Decision, records
  detectors.py       deep dive §2-§3 (incl. digit-gated code/pin rule, trailing-punctuation strip)
  privacy.py         ingress_scrub (§4.1), scrub/P0 (§4), classify/P1 (§9), egress/P2 (§18)
  vocab.py           predicate vocabulary + intent lexicon + alias table (deep dive §0.3, §16)
  extractor.py       Extractor protocol, RuleExtractor (default), LLMExtractor (§5), clause reporting
  policy.py          decide() (§10), importance (§7), confidence (§8), poisoning_check (§20), ttl (§13)
  consolidate.py     consolidate/merge/supersede/contest/DROP_STALE (§11-§12)
  store.py           DDL (§0.1), pragmas, MemoryScope-only API, commit_candidate with fence (§22), sweep (§13)
  retrieval.py       build_query, candidates, rank, select (§16-§17), retrieve.filter debug view (§24.1)
  render.py          render_block incl. replaces_earlier_value (§19), notices
  forget.py          detect/apply/delete_slot/forget_all incl. empty-slot tombstone (§21)
  events.py          sink: memory_events table (+ optional JSONL), emit()
  trace.py           assemble_turn_trace, memory_state_snapshot, leak guard (§24.1)
  service.py         MemoryService.prepare_turn / schedule_ingest / await_idle / test hooks (§1)
  prompt_addendum.md LTM paragraph for the system prompt (loaded only when the flag is on)
server/routes/memory_debug.py   /memory/debug/{traces,trace/{id},state} + /memory/debug/test/{ingest-delay,await-idle}
server/tests/__init__.py
server/tests/memory/__init__.py
server/tests/memory/test_*.py   unittest suites (§6.1)
analysis/lab/ltm_demo/
  __init__.py
  scenarios.py       the 4 proofs (+ poisoning bonus): steps, values, canaries, assertion functions
  contract.py        validate_trace(doc): stdlib structural validator for openpoke.ltm.demo_trace.v1
  run_demo.py        harness (deep dive §29.1): both modes → results/ltm_demo/{scenario}.{mode}.json + index.json; exit 1 on any failed gate
analysis/design/LTM_BLOCKERS.md        (only if a blocker occurs)
```

### 3.2 Existing files to edit (all behind flags; design §26)

| File | Edit |
|---|---|
| `server/config.py` | Env-backed settings: `ltm_enabled` (`OPENPOKE_LTM_ENABLED`), `ingress_scrub_enabled` (`OPENPOKE_INGRESS_SCRUB`, default = `ltm_enabled`), `ltm_debug` (`OPENPOKE_LTM_DEBUG`), `ltm_debug_events` (`OPENPOKE_LTM_DEBUG_EVENTS`), `ltm_test_hooks` (`OPENPOKE_LTM_TEST_HOOKS`), `ltm_extractor` (`OPENPOKE_LTM_EXTRACTOR`, `rules`\|`llm`, default `rules`), `memory_extractor_model` (default = `summarizer_model`), `ltm_user` (`OPENPOKE_LTM_USER`, default `local-user`) |
| `server/agents/interaction_agent/runtime.py` | `execute` (`:65`) and `handle_agent_message` (`:100`): ingress scrub as the first statement. No reference to the raw string afterwards. Then `prepare_turn`, pass the block and notices, and `schedule_ingest` after `record_user_message` (deep dive §1) |
| `server/agents/interaction_agent/agent.py` | `prepare_message_with_history(..., long_term_memory=None, memory_notices=None)` (deep dive §19). `build_system_prompt()` appends `prompt_addendum.md` only when `ltm_enabled` |
| `server/services/conversation/log.py` | `record_*` (`:136-151`): one `ingress_scrub` when enabled; pass the same string to `_append` and `append_entry` |
| `server/routes/chat.py` | `clear_history` (`:25`): if `ltm_enabled`, `get_memory_service().bump_epoch(scope)` |
| `server/routes/__init__.py` | `if settings.ltm_debug: api_router.include_router(memory_debug_router)` |
| `server/app.py` | Startup: if `ltm_enabled`, open the store and run `sweep()` once |
| `analysis/lab/mock_openrouter.py` | (lab, not production) add a `memory_extractor` category, classified by a unique phrase in the extractor system prompt, returning `{"candidates": [], "ignored": []}` by default. Its captures are needed for the "zero secret in extractor captures" gate when `OPENPOKE_LTM_EXTRACTOR=llm` |

Optional stretch, only after every gate passes: the same scrub in `server/services/execution/log_store.py:_append`.

---

## 4. Binding clarifications

These resolve gaps found while preparing this handoff. They are not scope changes.

| # | Topic | Resolution |
|---|---|---|
| C1 | **Finding a turn's `trace_id`** | `POST /chat/send` returns an empty 202 (`chat_handler.py:47-49`), so the harness can't get the id from the response. Add `GET /api/v1/memory/debug/traces?limit=N` → `[{trace_id, ts, source_kind, kind: setup\|probe\|forget, turn_id}]`, newest first. Same gating as the other debug routes |
| C2 | **Trace lifetime** | A trace id is created in `prepare_turn`, and the async ingest job for that turn emits into the **same** `trace_id`. `await-idle` must return only when every job (including delayed duplicates) has committed or fence-dropped, with a 10 s timeout and HTTP 504 on timeout |
| C3 | **Default extractor for the gate** | `RuleExtractor` (`OPENPOKE_LTM_EXTRACTOR=rules`). Run the `llm` extractor only in its own unit tests (fake transport) plus one harness run of the `privacy` scenario, to prove the extractor capture holds no secret. Gates never depend on mock-LLM extraction quality |
| C4 | **RuleExtractor grammar (minimum)** | Must handle the exact proof strings: "My favorite programming language is X." / "Actually, my favorite programming language is X." → `pref.favorite_programming_language`. "I prefer meetings after/before/between …" → `pref.meeting_time`. "I prefer concise/short/brief/detailed emails" → `pref.email_style` (alias brief/short→concise). "My email is …" → `profile.email`. "My (test )?API key is …" → `profile.api_key`. Present-progressive transient clauses → `NO_CANDIDATE TRANSIENT_STATE`. Questions → `NO_CANDIDATE QUESTION`. Plus the forget grammar (deep dive §21). `profile.email` and `profile.api_key` exist only so policy has something to REJECT. They are not in the stored vocabulary |
| C5 | **Clause splitting** | Split on `(?<=[.!?])\s+`, then on `,\s*(?:and\s+)?` **only** when both sides contain a verb. The proof-2 mixed message must yield exactly three clauses (email, key, preference). Test this explicitly |
| C6 | **Placeholders in clause text** | `extract.clause.safe_text` is the P0 output (email → `[EMAIL_1]`, key → `[SECRET:API_KEY]`). No contact or secret value ever appears in events, traces or debug state |
| C7 | **System prompt flag-off identity** | Never edit `system_prompt.md`. The addendum lives in `server/services/memory/prompt_addendum.md` and is appended at runtime only when the flag is on. The gate compares the sha256 of the flag-off system prompt with `system_prompt.md` |
| C8 | **Event loop / locks** | `batch_manager.py:190` can call `handle_agent_message` under a **different** event loop (`asyncio.run`). Agent-message turns never ingest (D6), but `prepare_turn` runs there: keep it synchronous and lock-free. Per-user ingest locks must be created lazily per running loop (or use a `threading.Lock` around the commit). Never share an `asyncio.Lock` across loops |
| C9 | **DB connections** | Follow `TriggerStore` (`triggers/store.py:31-34`): a short-lived connection per operation, `isolation_level=None`, explicit `BEGIN IMMEDIATE` for writes, and `PRAGMA secure_delete=ON` / `foreign_keys=ON` **per connection** (they are connection-scoped). `journal_mode=WAL` is set once at schema creation |
| C10 | **Time** | `observed_at` = `datetime.now(timezone.utc)` captured at the first line of `execute()`, ISO-8601 with milliseconds. Don't reuse `now_in_user_timezone` (it has no offset; F-13) |
| C11 | **HMAC key** | `OPENPOKE_LTM_HMAC_KEY` env, else `server/data/memory/.hmac_key` (32 random bytes, created with mode 0600 on first use). Never logged |
| C12 | **`new_conversation` probe** | The harness calls `await-idle`, then `DELETE /api/v1/chat/history`. This bumps the epoch (LTM mode) and must not delete memories (D21). In baseline mode it is the plain existing endpoint |
| C13 | **Restart** | The harness stops and starts only the server process (`run_experiments.stop("server")` / `start_server(env)`), keeping `server/data/` and the mock running. LTM must reopen `ltm.db` and serve the `after_restart` probe |
| C14 | **Stale-writer hook** | `POST /memory/debug/test/ingest-delay {"duplicate_next_job_with_delay_ms": 4000}` enqueues the next ingest job twice. The second copy has an identical `TurnRef` and sleeps *before* taking the per-user lock. It must go through the real `commit_candidate` fence. No test-only branch may decide the outcome |
| C15 | **Demo canary for the email** | The contact canary is `test.user@example.com`. In LTM mode, gate it only on LTM sinks (`ltm.db*`, FTS, events, LTM blocks, extractor captures, trace file). It is **expected** in the conversation log, working memory and interaction payloads (D24). Assert that expectation explicitly as `privacy.email_in_short_term_history_by_design`, so the caveat appears in the data |
| C16 | **Harness reuse** | Import the stack helpers from `analysis/lab/run_experiments.py` (`fresh_stack`, `start_server`, `stop`, `captures`, `send`, `wait_idle`, `section`; `main()` is guarded by `__name__`). Note that `fresh_stack` wipes `server/data/` and `analysis/lab/state/`, so never point it at a checkout with real data |
| C17 | **Python for the harness** | Same as the existing lab: `python3.13 -m venv .venv-lab && .venv-lab/bin/pip install 'fastapi>=0.115' 'uvicorn>=0.30' 'pydantic>=2.7' 'httpx>=0.27' python-dateutil beautifulsoup4` (TEST_RESULTS.md "Reproduce") |

---

## 5. Build order (each step ends green; no step edits existing files before step 9)

| Step | Build | Exit criteria (tests in `server/tests/memory/`) |
|---|---|---|
| 1 | `models.py`, `store.py` (DDL verbatim from deep dive §0.1), `MemoryScope` API | `test_store`: schema creates; direct second active insert in a single slot raises `IntegrityError`; deleted-with-content violates the CHECK; FTS row written in the same txn; two-scope isolation (read, delete, epoch) |
| 2 | `detectors.py`, `privacy.py` (`ingress_scrub`, P0, P1, P2) | `test_privacy`: all lab markers + `sk-test-SYNTHETIC-12345` + `test.user@example.com` detected with the correct class; `ingress_scrub` leaves contacts, replaces secrets/IDs, is idempotent and has no reverse map; false-positive set passes untouched ("the code is in main.py", "order 482913 shipped", "meet at 10:30", "$1,234.56", "2026-10-07"); trailing punctuation preserved |
| 3 | `events.py`, `trace.py` skeleton + leak guard | `test_events`: emit/read by trace id; REJECT events carry no value/length/offset; the leak guard raises on an injected secret |
| 4 | `vocab.py`, `extractor.py` (RuleExtractor + clause reporting + grounding) | `test_extractor`: C4 grammar; C5 three-clause split; turkey → `NO_CANDIDATE TRANSIENT_STATE`; ungrounded candidate dropped |
| 5 | `policy.py` | `test_policy`: one table row per design §7.2 example (decision + reason codes + importance values from deep dive §7) |
| 6 | `consolidate.py` + fenced `commit_candidate` | `test_consolidate`: INSERT/MERGE/SUPERSEDE/CONTEST/DROP_STALE; out-of-order commit (turn 2 committed before turn 1) leaves Rust active; supersede emits the edge |
| 7 | `retrieval.py`, `render.py` | `test_retrieval`: proof-3 probe selects only the meeting preference with the deep-dive score; "What's 2+2?" → empty string; superseded never a candidate but appears in `retrieve.filter` when debug events are on; `replaces_earlier_value` present on the superseding item |
| 8 | `forget.py`, `service.py` (`prepare_turn`, `schedule_ingest`, `await_idle`, hooks) | `test_forget`: slot chain purged (content NULL, FTS gone, events scrubbed), slot + value tombstones; **stale duplicate writer → `fence_drop TOMBSTONED`**; **forget-before-write → `fence_drop TOMBSTONED`**; "don't forget to email Bob" is not a forget; ambiguous forget deletes nothing; byte canary on `ltm.db`/`-wal`/`-shm` after checkpoint |
| 9 | Integration edits (§3.2), `memory_debug.py`, `prompt_addendum.md` | `test_integration` (in-process; OpenRouter patched like the lab): flag off → no `server/data/memory`, prompt sha256 unchanged, raw values in conversation files; flag on → placeholder in conversation files and payload, LTM block on the next relevant turn; debug routes 404 when disabled and 403 from non-loopback |
| 10 | `analysis/lab/ltm_demo/` (`scenarios.py`, `contract.py`, `run_demo.py`) + mock extractor category | `run_demo.py` produces 8 files + `index.json`; every file passes `validate_trace`; all assertions pass (§6.2) |
| 11 | `LLMExtractor` | `test_llm_extractor`: fake transport; the request body contains only LLM_SAFE text and the existing slot keys; malformed JSON → zero candidates; one harness `privacy` run with `OPENPOKE_LTM_EXTRACTOR=llm` → 0 secret hits in extractor captures |

---

## 6. Acceptance gates (definition of done)

Implementation is complete only when **both** commands exit 0 and `index.json` has `"gate_passed": true`:

```bash
cd /path/to/openpoke-memory
.venv-lab/bin/python -m unittest discover -s server/tests -t . -v
cd analysis/lab && ../../.venv-lab/bin/python ltm_demo/run_demo.py      # all scenarios, both modes
```

### 6.1 Unit/integration gate (`unittest`)

Every exit criterion in §5. In addition, these four named tests must exist, so the user can point at them:

| Test | Proves |
|---|---|
| `test_consolidate.TestConflict.test_exactly_one_active_per_single_slot` | DB invariant + Python→Rust supersession |
| `test_privacy.TestIngress.test_secret_never_persisted_or_sent` | Ingress + P0 + P1 on the proof-2 strings (in-process, all sinks) |
| `test_extractor.TestSelective.test_turkey_sandwich_ignored_preference_stored` | Selective memory |
| `test_forget.TestRace.test_stale_writer_fence_dropped` (+ `test_forget_before_write_fence_dropped`) | Deletion race, both variants |

### 6.2 End-to-end gate (`run_demo.py`): required assertion ids

Each id is an entry in `assertions[]` of the named file with `"passed": true`. Missing ids count as failures. Ids and semantics come
from deep dive §29.2 and design §19.1.

| File | Required ids |
|---|---|
| `conflict.ltm.json` | `conflict.one_active_per_slot`, `conflict.python_superseded_by_rust`, `conflict.old_fact_not_retrieved`, `conflict.ltm_block_has_new_value`, `conflict.old_value_absent_new_conversation`, `conflict.same_session_history_unchanged_by_design`, `persistence.after_restart_retrieves_rust`, `ui.replaces_earlier_value_flag` |
| `conflict.baseline.json` | `baseline.both_values_in_conversation_log`, `baseline.both_values_in_working_memory`, `baseline.both_values_in_model_context`, `baseline.no_ltm_db` |
| `privacy.ltm.json` | `privacy.secret_zero_hits_all_sinks`, `privacy.ingress_no_verbatim_secret_in_new_log_lines`, `privacy.no_secret_in_any_interaction_payload`, `privacy.email_classified_contact`, `privacy.email_not_in_ltm`, `privacy.email_in_short_term_history_by_design`, `privacy.useful_fact_stored`, `privacy.useful_fact_retrieved`, `privacy.trace_file_leak_free` |
| `privacy.baseline.json` | `baseline.secret_in_conversation_log`, `baseline.secret_in_working_memory`, `baseline.secret_replayed_next_turn`, `baseline.email_in_context`, `baseline.no_ltm_db` |
| `selective.ltm.json` | `selective.preference_active`, `selective.sandwich_no_memory_row`, `selective.sandwich_ignore_event`, `selective.probe_block_only_preference`, `selective.offtopic_no_block` |
| `selective.baseline.json` | `baseline.both_clauses_in_conversation_log`, `baseline.both_clauses_in_model_context`, `baseline.no_ltm_db` |
| `forget.ltm.json` | `forget.row_deleted_content_null`, `forget.fts_row_removed`, `forget.tombstone_written`, `forget.stale_writer_fence_dropped`, `forget.slot_row_count_unchanged_after_drop`, `forget.retrieval_empty_all_probes`, `forget.bytes_absent_ltm_db` |
| `forget.baseline.json` | `baseline.preference_still_in_context_after_forget_request`, `baseline.no_ltm_db` |
| every file | `contract.valid` (from `validate_trace`), `contract.leak_free` (no prohibited-class pattern in the file) |
| every `*.baseline.json` | `flag_off.system_prompt_identical`, `flag_off.no_ltm_sections_in_payloads` |

`privacy.secret_zero_hits_all_sinks` must cover every sink in deep dive §29.4, and each sink is reported individually in
`canary_scan.sinks`.

The poisoning scenario is a bonus. If built, it's reported but not gated.

---

## 7. Demo trace emission requirements

The UI is built later and consumes **only** these files, so the contract is part of the deliverable, not decoration.

- **Location:** `analysis/lab/results/ltm_demo/{conflict,privacy,selective,forget}.{baseline,ltm}.json` and `index.json`
  (`{"schema": "openpoke.ltm.demo_trace.index.v1", "run_id", "generated_at", "git_commit", "files": [...], "gate_passed": bool,
  "failed": [{"file", "assertion_id"}]}`).
- **Schema:** design §25, verbatim key names. Required top-level keys in every file: `schema`, `scenario`, `mode`, `meta`,
  `flow_graph`, `turns`, `pipeline`, `memory_state`, `retrieval`, `retrieved`, `model_context`, `probes`, `baseline_observations`,
  `canary_scan`, `assertions`. Empty is allowed where the design says so (e.g. `memory_state: []` in baseline).
- **`flow_graph` node ids are fixed:**
  - baseline: `conversation, raw_persistence, working_memory, broad_context, agent`;
  - ltm: `conversation, ingress_scrub, privacy, extract, policy, consolidate, store, ignore, reject, supersede, delete, fence_drop,
    retrieve, agent`.

  Every `turns[].path` and `pipeline[].node` value must be one of these.
- **Visual beats the files must make drawable** (from your review). Each one must be derivable without UI-side inference:

| Beat | Where in the file |
|---|---|
| Conflict: `Python STORE→ACTIVE —superseded_by→ Rust STORE→ACTIVE` | `memory_state[].memories[].status_history` + `edges[kind=superseded_by]` + `turns[].outcomes` |
| Selective: `Meeting preference → STORE`, `Turkey sandwich → IGNORE` | `turns[0].outcomes` (one per clause, with `reason`) + `pipeline[stage=extract.clause]` |
| Privacy: `Email → PII → REJECT`, `API key → SECRET → REJECT`, `preference → STORE` | `pipeline[stage=ingress.scrub \| privacy.classify \| policy]` + `turns[].outcomes` |
| Delete: `ACTIVE → DELETE/PURGE → TOMBSTONE`, `stale write → FENCE_DROP` | `memory_state` before/after + `tombstones[]` + `pipeline[stage=fence_drop]` with `refs.job_observed_at`/`tombstone_at` |
| Retrieval: candidates, hard filters, score breakdown, selected, final block | `retrieval[]` (`hard_filters`, `excluded_by_filters`, `candidates[]` with `rel/imp/conf/rec/total`, `selected`, `ltm_block`) |
| Baseline lane per message | `turns[].path` + `baseline_observations[]` presence matrix |

- **Determinism:** with the mock LLM + RuleExtractor, two runs must produce identical files except `meta.run_id`, `meta.generated_at`,
  ids derived from ULIDs, and timestamps. Write keys sorted and use `indent=2`.
- **Never** include raw secret or contact values. `canary_scan.canaries` are labels (`SECRET:API_KEY`, `CONTACT:EMAIL`,
  `OLD_VALUE:python`), never values.

---

## 8. Verified pitfalls in the existing code

| Where | Pitfall | Consequence if ignored |
|---|---|---|
| `runtime.py:69-70` | `transcript_before` is read **before** `record_user_message` | Fine as is; keep the order. Ingress scrub must happen before both lines |
| `runtime.py:196-199` | If working memory renders empty, the **entire raw conversation log** is loaded | `new_conversation` must clear both files (`DELETE /chat/history` does). Don't simulate it by clearing working memory only |
| `log.py:136-151` | `_append` and `append_entry` are called with the same `content`; there is no single chokepoint | Scrub once in each `record_*`, then pass the same string to both |
| `tools.py:154-178` | `send_message_to_user` / `send_draft` call `record_reply` directly | Covered by I2 |
| `batch_manager.py:190` | `asyncio.run(...handle_agent_message...)` can start a new loop | C8 |
| `chat_handler.py:47-49` | Returns an empty 202; work runs in a background task | C1 + harness waits (`send` + `await-idle`) |
| `summarizer.py:81` | The summariser reads the conversation log | It needs no change; it inherits the scrub |
| `triggers/store.py:57` | WAL is set per DB; connection-level pragmas are not persistent | C9 |
| `mock_openrouter.py:classify` | Unknown callers get `"unknown caller"` text | Add the `memory_extractor` category (§3.2) before any `llm` extractor run |
| `mock_openrouter.py:interaction_agent` | Always replies `send_message_to_user("Noted.")` | Gates assert on payloads and state, not replies (D28) |
| `.gitignore:34` | `server/data/` is ignored | Results under `analysis/lab/results/ltm_demo/` are *not* ignored. They must be leak-free (gate `contract.leak_free`) |
| `web/app/page.tsx:33,55` | The UI replaces its message list from `/chat/history` | With ingress on, the user's bubble shows `[SECRET:API_KEY]` after the next poll. Expected (design §8.9). Don't "fix" it in `web/` |

---

## 9. Out of scope (do not build)

- The visual/side-by-side UI and the inspector UI.
- Embeddings, the token vault, encryption/KMS, Gmail/tool-sourced memories, the LLM conflict adjudicator.
- `commitment`/`episodic` types.
- Auth/multi-tenant plumbing, summariser changes, contact-PII scrubbing of the short-term log, retroactive scrubbing, forget
  propagation into the conversation log.
- A durable job queue, the quarantine review flow, `web/` changes, tuning spec constants.

---

## 10. Final report the implementation agent must return

1. Gate status: both commands' exit codes, `index.json.gate_passed`, and the per-file assertion table (id → pass/fail).
2. Files created/edited, with one line each. Confirm `web/` and the three frozen docs are unchanged (re-run the §1 sha256).
3. Blockers (`LTM_BLOCKERS.md` ids) and pre-approved fallbacks used.
4. The §24.1 caveats as they appear in the generated data (e.g. `conflict.same_session_history_unchanged_by_design` passed, meaning
   the old value is still in short-term history).
5. How to re-run: exact commands, Python version, SQLite version.
6. Anything built beyond §3 (should be nothing; justify if not).
