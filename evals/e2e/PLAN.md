# Budgeted-strategy work plan (2026-09-11)

## Rules
- Legacy path stays byte-for-byte as on `main`. Every change is gated on `OPENPOKE_CONTEXT_STRATEGY=budgeted`.
- Prompts are versioned, never edited in place: `system_prompt.md` is legacy; a budgeted variant lives in
  `system_prompt.budgeted.md` (or an addendum constant) and is selected by strategy.
- A tool whose shape changes gets a NEW versioned tool (e.g. `gmail_create_draft_v2`) registered only in the budgeted
  list; the legacy tool is never modified. Each agent's tool list is gated per strategy in its registry.
- Budgeted-only code lives under each agent's `context/` and `tools/budgeted.py`; shared context primitives live
  in `server/context/`. The legacy and budgeted paths can both be selected by the eval harness.
- Before each eval: check remaining credit (`/api/v1/auth/key`), estimate the cost, run only the cells that
  the change under test could flip.

## Goals (in order)
1. No request exceeds the window on any scenario.
2. Outcome judge passes every scenario.
3. Fewer billed tokens.
4. Fewer LLM and tool calls.

## Gaps, prioritised by scenarios blocked
| # | gap | where | scenarios | fix |
|---|-----|-------|-----------|-----|
| 1 | worker log pasted whole into the worker system prompt | execution_agent/agent.py | 02 03 04 05 | token-budgeted worker history: recent verbatim, older indexed; per-entry bound |
| 2 | tool results (search bodies) unbounded inside a run; overflow surfaces as a generic error and every layer retries | tasks/search_email, execution_agent/runtime.py | 09 12 (and 10) | bound each tool result before it enters messages; typed "result too large" error that is terminal (no retry) |
| 3 | merged batch callback in the current-turn slot unbounded | interaction agent prepare_message / batch_manager payload | 12 | preview oversized callback payloads; full text stays in the log and is recallable |
| 4 | recall tool cap: verify it pages instead of returning 80k | interaction_agent/context/history.py | 14 | already capped at 6k; verify behaviour, fix prompt guidance if the agent loops |
| 5 | wait as a tool round; re-dispatch to a running worker | interaction runtime | all (cost) | budgeted: `wait` ends the turn; dispatch dedupe per turn |

## Status (2026-09-12)
- Baseline legacy: 0/10, all overflow (`results/20260911-223236`).
- Budgeted before gaps 1-5: 4/10 (`results/20260911-231751`): 01, 11, 13, 14 pass; 02-05 overflow on the worker log; 09, 12 storm on tool results.
- Gap 1 (worker history budget + recall_worker_history): 02, 03, 04, 05 pass, max prompt ~22k (`results/20260911-233326`).
- Gap 2 (bounded tool results, read_email, digest_email map-reduce, terminal overflow errors): 09 and 12 pass
  (`results/20260912-000123`). Digest recall needed reasoning ON at 8k chunks (measured 3/3 vs 1/3 without); empty-output
  fallback retries without reasoning. Search sub-agent capped at 3 rounds in budgeted mode with a versioned addendum.
- Gap 3 (turn-slot preview) and gap 5 (wait ends turn, dispatch dedupe, stop after ack+dispatch) implemented; full suite rerun pending.
- Harness: per-cell runtime cap 180s; judges see complete replies (were cut at 400 chars); digest calls traced as component "digest".

## Final (2026-09-12)
- Three full budgeted passes on the final code: 10/10 (`results/20260912-003253`), 9/10 (`results/20260912-105840`, E2E-09 timed out on slow
  reasoning digest calls, fixed), 10/10 (`results/20260912-112211`). Legacy 0/10 (`results/20260911-223236`).
- Max prompt 26.9k against a 64k window. Agent cost ≈ $0.09-0.10 per full pass on DeepSeek flash.
- Later gap 6 (search cache per run + page cap + run tool-result budget): E2E-12 63 -> 51 calls, Gmail fetches 53 -> 10.
- Later gap 7 (digest latency): reasoning off + 8-way parallel + 45s per-call timeout; avg chunk read 5s (was 12-94s).

## Future work (noted 2026-09-12)
- **Recall search is in-memory keyword matching.** `recall_entries` / `recall_worker_entries` load every log entry into memory
  and score by term hits. Fine for one user's log; does not scale and misses paraphrases. Next: persist log entries in a DB
  (SQLite FTS to start), then embeddings + vector search for semantic recall, so the whole log is never loaded per call.
- **Constraint store.** Standing rules extracted at compaction time into a small structured list kept inline; the summary
  kept the cc rule in E2E-07 but dropped the draft id in E2E-08 (recall covered it). Makes rule recall independent of the
  agent suspecting a rule exists.
- Needle-in-summary cases E2E-06/07/08 re-enabled: 9/9 across three passes on budgeted with no code change.

## Refactor verification (2026-09-13)

- Deterministic context/tool boundary tests: 6/6 (`python -m unittest discover -s tests -v`), with no LLM calls.
- Full process-parallel run after module reorganization: budgeted 20/20; legacy 5/20 with the same 15 expected
  context-window overflows as the preceding legacy full run (`results/20260913-2140-refactor-fixed-full`).
- No budgeted request overflowed; maximum budgeted prompt was 25,670 tokens against the 64k simulated window.
