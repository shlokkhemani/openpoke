# LTM demo handoff

Coordination notes between the backend agent (LTM implementation, harness, traces) and the UI agent. Each agent edits only its
own section.

---

## UI: live comparison console (2026-10-07, supersedes the static viewer as the default)

**Run:** `analysis/lab/live_demo.sh [--fresh] [--real] [--extractor llm]` → UI `http://127.0.0.1:8765/demo_ui/`, baseline `:8020`
(LTM OFF), LTM `:8021` (LTM + ingress scrub + debug events + test hooks). The static viewer is now `?mode=replay`.

**Files (new):** `analysis/lab/live_demo.sh`, `analysis/lab/live_demo.py` (supervisor + UI server + `/lab/reset`),
`analysis/lab/live_instance.py` (one backend), `analysis/demo_ui/js/{main,live,live_app}.js`. Renamed `app.js` → `replay.js`.
Backend changes: **none**.

**Presentation polish (2026-10-07).** The chat columns mirror `web/` (`ChatHeader`, `ChatMessages`, `ChatInput`, `globals.css`
bubble/card/input classes; nothing in `web/` was changed). A "What happened?" panel condenses the selected turn's real trace
into state-transition cards and six semantic stages (Privacy, Extract, Decide, Store, Retrieve, Agent) via
`analysis/demo_ui/js/story.js`, which is pure and keyed only on trace/state fields. Below it is a compact Current memory list. The technical drill-down
(memory, retrieval, safety, baseline context, advanced per-clause trace + raw JSON) is collapsed below. `?presentation=1`
(or the Presentation button / P key) hides all developer chrome.

**Isolation.** Every data path in the server is derived from `Path(__file__)/../data`, so each backend runs from its own synced
copy of `server/` under `analysis/lab/state/live_demo/{baseline,ltm}/` (gitignored). Each has its own `server/data` and its own
mock OpenRouter (`:18120`, `:18121`). The copy is re-synced from the repo every time the supervisor starts, so backend fixes
show up after a restart of `live_demo.sh`.

**Live endpoints used.** `POST /chat/send`, `GET|DELETE /chat/history`, `GET /health`, and on the LTM backend
`GET /memory/debug/traces`, `GET /memory/debug/trace/{id}`, `GET /memory/debug/state`, `POST /memory/debug/test/await-idle`,
`POST /memory/debug/test/ingest-delay`.

**Turn → trace matching (TEMPORARY).** `POST /chat/send` returns an empty 202, so the UI diffs `GET /memory/debug/traces` before
and after the send and takes the new `source_kind=user_message` trace. It assumes the page is the only client of the LTM backend.
It then waits for the reply in `/chat/history`, calls `await-idle {include_delayed:false}`, and reads the trace and the state. A
background `await-idle {include_delayed:true}` re-reads every trace afterwards, which is how a delayed duplicate writer's
`fence_drop` shows up. **Request:** return the `trace_id` from `/chat/send` (or a response header) so matching becomes exact.

**Reset both.** No backend endpoint wipes LTM (clearing chat only bumps the epoch, D21). `live_demo.py` therefore exposes
`POST /lab/reset` on the UI server, loopback only. It stops both backends, deletes their instance `server/data`, and restarts them.
Without the supervisor, the UI falls back to `DELETE /chat/history` on both and says that the memories are kept.

**Baseline visibility.** Live chat plus `/chat/history` only. There is no live endpoint for working memory, so none is shown.

**Model mode** is shown as launched by the supervisor (`/demo_ui/live-config.json`). It is not detected from the backend.

**Known gaps in live mode (data the UI can't get live):** no harness assertions or canary sink scan (those exist only in the
gated runs, so use replay mode); no FTS-removal event; `retrieve.query` live has `n_terms` but no `terms`; the display value of a
deleted memory is gone after a page reload (correct, it was purged), so it shows as `memory XXXX`.

## UI (visualization / demo frontend)

**Status (2026-10-07):** built and verified against the current `analysis/lab/results/ltm_demo/` traces (all four scenarios, both
modes). Nothing under `server/`, `web/`, tests, the harness, or the frozen design docs was touched.

### Files created

| File | Role |
|---|---|
| `analysis/demo_ui/index.html` | Entry page |
| `analysis/demo_ui/styles.css` | Light, presentation-scale styling |
| `analysis/demo_ui/js/dom.js` | Tiny DOM helper (`h()`), formatting |
| `analysis/demo_ui/js/trace.js` | Loader + read-only selectors over `openpoke.ltm.demo_trace.v1` |
| `analysis/demo_ui/js/presentation.js` | Presentation mapping only (titles, wording, flag colours, stage → column). No outcomes |
| `analysis/demo_ui/js/components.js` | One renderer set for all scenarios |
| `analysis/demo_ui/js/app.js` | Wiring, tabs, `?dir=` override |
| `analysis/demo_ui/README.md` | How to run |

Run: `python3 -m http.server 8765 --bind 127.0.0.1 --directory analysis`, then open `http://127.0.0.1:8765/demo_ui/`.
The page fetches `../lab/results/ltm_demo/index.json` and every file it lists, so a fresh `run_demo.py` needs only a reload.

### Trace fields the UI reads

- `index.json`: `files`, `bonus_files`, `gate_passed`, `failed[]`, `extractor`, `git_commit`, `git_dirty`, `generated_at`.
- Top level: `schema`, `meta.run_id`, `meta.headline_probe`.
- `turns[]`: `turn_index`, `kind` (`setup|probe|new_conversation|restart|hook|wait_duplicate`), `text_safe`, `probe`, `label`, `path`,
  `hook`, `skipped`, `outcomes[]` (`label`, `decision`, `result`, `reason`, `memory_id`, `supersedes`, `candidate_id`,
  `clause_index`, `duplicate`).
- `pipeline[]`: `turn_index`, `trace_id`, `seq`, `ts`, `stage`, `node`, `candidate_id`, `memory_id`, `decision`, `reason`,
  `reason_codes`, `input_safe`, `refs.job_observed_at`, `refs.tombstone_at`, and per-stage `detail` keys:
  `detectors` (scrub/classify), `sensitivity`, `label`, `clause_index`, `duplicate` + `n_candidates` (extract),
  `importance`/`confidence`/`importance_breakdown` (policy), `display`/`slot_key` (consolidate), `families`/`terms` (query),
  `filter`/`display` (filter), `total` (candidates/rank), `selected`/`tokens` (select), `count` (egress), `alias`/`tokens` (render),
  `kind` (forget.detect), `count`/`memory_ids`/`slot_key`/`tombstone_at` (forget.apply), `observed_at` (ingest).
- `memory_state[]`: `after_turn`, `memories[]` (`id`, `display`, `canonical_text`, `memory_type`, `slot_key`, `status`,
  `status_history[]{status, turn_index, trace_id}`, `confidence`, `importance`, `observed_at`, `supersedes_id`, `superseded_by_id`,
  `contests_id`, `deleted_at`, `expires_at`), `edges[]{from,to,kind}`, `deleted[]`, `tombstones[]{scope, slot_key, reason, deleted_at}`.
- `retrieval[]`: `turn_index`, `probe`, `label`, `query{terms,families,entities}`, `hard_filters`, `excluded_by_filters[]{memory_id,
  display, filter}`, `candidates[]{memory_id, display, generators, rel, imp, conf, rec, total, selected, drop_reason}`, `ltm_block`,
  `ltm_block_tokens`.
- `probes[]{probe, turn_index, model_context}` (falls back to top-level `model_context` when it matches the turn):
  `sections.*.contains_*`, `sections.*.present`, top-level `contains_*`, `note`.
- `baseline_observations[]{turn_index, node, store, contains{…}}`.
- `canary_scan.canaries[]` and `sinks[]{canary, sink, hits, expected}`.
- `assertions[]{id, name, passed, expected, actual, evidence}`.

### Assumptions about the schema

- Baseline and LTM files of a scenario run the same script. Turns are aligned by `turn_index`, falling back to `kind` + `text_safe`.
- ids, trace ids and timestamps are never compared across runs. Memories are related only through `memory_id` references inside one
  file. Ordering uses `seq` within a trace and `ts` across traces.
- A second ingest job in the same trace is recognised by `extract.detail.duplicate === true`; every later event of that trace (by
  `seq`) is treated as the duplicate job.
- Store-column chips for a committing `consolidate` event (INSERT/SUPERSEDE/MERGE/CONTEST) take the row status from
  `status_history[].trace_id` of that memory.
- Value names for abstract flag keys (`old_value`, `new_value`) come from `canary_scan.canaries` (`OLD_VALUE:<name>`, matched to a
  memory `display`) and from the ends of a single supersession chain. Otherwise the key is shown humanised.
- `extract.clause.input_safe` is null after a forget (events are scrubbed by design). The UI then shows the clause `label`.
- Every field is optional to the renderer. A missing section shows a yellow "Not in trace: …" box instead of failing.

### Verified

- All four scenarios render from the current traces (headless Chrome, 1600 px wide), with no console errors.
- No outcome literals in the UI code (`grep -i 'python|rust|sandwich|concise|after 10'` finds only comments and flag labels).
- Mutation test: a copy of `conflict.ltm.json` edited so that Python is `active`, Rust is `contested`, the edges and
  `excluded_by_filters` are removed, one assertion is failed and `probes` is deleted. The UI showed exactly that state, one FAIL,
  and no crash.

### Requests to the backend agent (optional; the UI works without them)

1. **Score weights.** `retrieval[].candidates[]` gives `rel/imp/conf/rec/total` but not the weights or the formula, so the UI can't
   show *how* `total` is computed. Suggest `retrieval[].weights = {rel, imp, conf, rec}` (deep-dive constants, copied verbatim).
2. **Purge breakdown on `forget.apply`.** Content purge and FTS removal have no events of their own. The timeline derives them from
   `memory_state` (`canonical_text: null`) and the assertions `forget.row_deleted_content_null` / `forget.fts_row_removed`. Counts in
   `forget.apply.detail` such as `{content_nulled, fts_rows_deleted, events_scrubbed, tombstones: ["slot","value"]}`, or separate
   `purge` / `index` events, would let the timeline cite events directly.
3. **Duplicate-job identity.** Optional `detail.job` (e.g. `{"attempt": 2, "delayed_ms": 4000}`) on every event of a job, rather than
   only on `extract`. That would make grouping independent of `seq` ordering.
4. **Writer wake time.** The "duplicate writer wakes" point is taken from the duplicate job's first event `ts`. An explicit
   `fence_drop.refs.woke_at` would be cleaner.
5. **Display labels for value flags.** Optional `meta.value_labels` (e.g. `{"old_value": "Python", "new_value": "Rust"}`, safe values
   only, never secrets/contacts), so the UI need not derive names from canaries and supersession chains.

### Still presentation-mapped (not data)

- Scenario titles and the one-line question (`presentation.js`).
- Hero view per scenario: `chain` (conflict), `clauses` (privacy, selective), `timeline` (forget).
- Flag labels and colours (`secret` red, `contact_pii` amber, …), and stage → pipeline-column mapping.
- Forget timeline evidence ids: `forget.row_deleted_content_null`, `forget.fts_row_removed`, `forget.tombstone_written` (only
  *which* assertion to cite; pass/fail is read from the file). Request 2 would remove this.
- Section names for `model_context.sections` (`conversation_history` → "conversation history").
