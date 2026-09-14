# Trajectory rubric v2

Replace the judge's opaque 1–5 score with 16 yes/no questions. "Harness" questions are answered
from the trace with no LLM; "judge" questions are answered by the strong model with a one-line reason.
Each question has a weight and may be n/a.

Score = 100 × Σ(weight × yes) ÷ Σ(weight of applicable questions).
The judge also answers `task_completed` separately as a cross-check against the harness verdict; it is not part of the score.

| # | criterion | question | by | weight |
|---|---|---|---|---|
| 1 | planning | First action fit the request: answered directly when the answer was already in context, dispatched a worker when work was needed | judge | 2 |
| 2 | planning | Dispatch instructions carried every detail the worker needed (addresses, ids, constraints such as the cc rule) | judge, n/a if no dispatch | 2 |
| 3 | execution | Every Gmail call used correct arguments (thread/draft ids, recipients, cc) | judge | 2 |
| 4 | execution | No Gmail call failed on a bad argument | harness: failed fake-Gmail calls | 1 |
| 5 | observation | Acted correctly on results: right email among distractors, returned draft id reused | judge | 2 |
| 6 | observation | Replies to the user matched reality; no "sent" before the send happened | judge | 2 |
| 7 | replanning | After a failure or empty result, the next move was an adjustment, not a repeat or a give-up | judge, n/a if nothing failed | 1 |
| 8 | termination | No send before the user's confirmation turn | harness: phase of send call vs confirmation turn | 2 |
| 9 | termination | Did not re-ask once the user had confirmed | judge | 1 |
| 10 | termination | Stopped when done: no further interaction rounds after the final state was reached | harness | 1 |
| 11 | loops | No duplicate Gmail calls with identical arguments | harness | 1 |
| 12 | loops | At most one `wait` per turn | harness | 1 |
| 13 | loops | No re-dispatch to a worker that was still running | harness: same worker twice in one phase before its callback | 1 |
| 14 | unnecessary | Dispatch count within the case's `expected.dispatches_max` | harness (new case field) | 1 |
| 15 | unnecessary | No searches, drafts, or messages the task did not need | judge | 1 |
| 16 | unnecessary | LLM calls within 2 × the case's `expected.ideal_calls` | harness (new case field) | 1 |
| 17 | planning | Dispatched the worker the case expects (`success.dispatched_agents_include`); n/a when none named | harness | 2 |

Why: reproducible score, per-question pass rates across a run become a diagnosis ("legacy failed #13 in 7/25 cells"),
and 8 of 16 questions cost no judge tokens.

Implemented in `judge_v2.py` (standalone rescoring of a results dir, also called by `run_e2e.py` per cell). Stored as `judge_v2` on each record; the v1 judge stays in `judge`. Harness answers for q8/q10/q13 use the event order to assign a turn to each Gmail call; q14/q16 read the case's `expected` block (defaults: 2 dispatches, 8 calls).

Cells whose only request was blocked at the context window, or that were aborted (call cap / deadline), are not scored: every harness question would answer yes for lack of activity. They show as n/a.
