# Routing run: Task 15 dev check: full vs hybrid at N=100/300 (Haiku), search rate and crossover

## Setup

- **Purpose:** Task 15 dev check: full vs hybrid at N=100/300 (Haiku), search rate and crossover
- **Command:** `python -m evals.run routing --modes full,hybrid --sizes 100,300 --split dev --runs 3 --embedder fastembed --max-cost 3 --purpose 'Task 15 dev check: full vs hybrid at N=100/300 (Haiku), search rate and crossover' --yes`
- **Date (UTC):** 2026-11-09T20:06:08Z
- **Model:** `anthropic/claude-haiku-5.5`
- **Code:** uncommitted working tree on HEAD 83e84f2
- **Case set:** `evals/cases/v1` (v1), MANIFEST sha256 `688388e57eb5980fa06046a7e384b5449d9b1c71134c817bbf7d20d166fbcbda`, frozen_on 2026-11-07
- **Split:** dev, 16 cases
- **Descriptions (`full`):** regen, sha256 `5d4d6d7c5b20fa1c53c69d280e122d27804833e7dd04ac623bf1e8e1c93ec232`, covering 310/310 world agents
- **Grid:** modes full, hybrid × sizes 100, 300 × 3 run(s) = 192 case-runs
- **Outcome:** 192 graded, 0 infra errors (not graded), 0 skipped by the max-cost cap ($3), 0 retried

## Cost

- Actual: **$1.1504** (estimate before the run: $1.0972)
- Tokens: 10,820,391 prompt / 136,649 completion (all attempts)
- Mean latency per case-run: 5.525 s; mean round trips: 2.318

## Pass rate by mode × N

Infra errors are excluded from the denominators; structural failures count as failures.

| mode | N=100 | N=300 |
|---|---|---|
| full | 100% (48/48) | 100% (48/48) |
| hybrid | 100% (48/48) | 94% (45/48) |

## Pass rate by category

| category | mode | N=100 | N=300 |
|---|---|---|---|
| ambiguous_person | full | 100% (6/6) | 100% (6/6) |
| ambiguous_person | hybrid | 100% (6/6) | 100% (6/6) |
| broad_question_person | full | 100% (6/6) | 100% (6/6) |
| broad_question_person | hybrid | 100% (6/6) | 100% (6/6) |
| clear_person | full | 100% (6/6) | 100% (6/6) |
| clear_person | hybrid | 100% (6/6) | 100% (6/6) |
| email_followup | full | 100% (6/6) | 100% (6/6) |
| email_followup | hybrid | 100% (6/6) | 100% (6/6) |
| multi_intent | full | 100% (6/6) | 100% (6/6) |
| multi_intent | hybrid | 100% (6/6) | 100% (6/6) |
| multi_person | full | 100% (6/6) | 100% (6/6) |
| multi_person | hybrid | 100% (6/6) | 50% (3/6) |
| new_task_lookalike | full | 100% (6/6) | 100% (6/6) |
| new_task_lookalike | hybrid | 100% (6/6) | 100% (6/6) |
| trigger_management | full | 100% (6/6) | 100% (6/6) |
| trigger_management | hybrid | 100% (6/6) | 100% (6/6) |

## Flags

| flag | mode | N=100 | N=300 |
|---|---|---|---|
| invalid_call | full | 0/48 | 0/48 |
| invalid_call | hybrid | 1/48 | 0/48 |

## Search

Embedder: `fastembed`. The target is the graded case's expected agents (`retrieval_eval.expected_for`); cases without one count in neither target row.

| mode | measure | N=100 | N=300 |
|---|---|---|---|
| hybrid | Search rate (case-runs that searched) | 1/48 | 2/48 |
| hybrid | Search errors (calls) | 0 | 0 |
| hybrid | Target in the initial cards | 42/48 | 39/48 |
| hybrid | Target found only by search | 0/48 | 0/48 |

## Structural failures

A legacy dispatch by a name that several agents share (e.g. two "Email Alice" agents): the names-only roster cannot express the right target.

| mode | N=100 | N=300 |
|---|---|---|
| full | 0 | 0 |
| hybrid | 0 | 0 |

## Infra errors

Retried once; a case-run whose retry also failed is listed in `errors.jsonl` and not graded. Counts are case-runs.

| mode | N=100 | N=300 |
|---|---|---|
| full | 0 | 0 |
| hybrid | 0 | 0 |

## Failing case-runs

| case | category | mode | N | run | outcome | flags | reason |
|---|---|---|---|---|---|---|---|
| multi-person-006 | multi_person | hybrid | 300 | 0 | create | – | expected clarify \| dispatch(create[Alice Chen] + ask); got create (message_user, dispatch→Email Sam Rivera about joining running club, dispatch→Email Alice Chen about joining running club); slots 1/1 |
| multi-person-006 | multi_person | hybrid | 300 | 1 | create | – | expected clarify \| dispatch(create[Alice Chen] + ask); got create (message_user, dispatch→Email Sam Rivera about Sunday running club, dispatch→Email Alice Chen about Sunday running club); slots 1/1 |
| multi-person-006 | multi_person | hybrid | 300 | 2 | create | – | expected clarify \| dispatch(create[Alice Chen] + ask); got create (message_user, dispatch→Email Sam Rivera about Sunday running club, dispatch→Email Alice Chen about Sunday running club); slots 1/1 |

## What we learned

- **Pass rates.** `full` is 100% at N=100 and N=300 (48/48 each), the same as Experiment 7's `full` at those sizes
  (48/48 each), so run-to-run noise on `full` is nil here. `hybrid` is 100% (48/48) at N=100 and 94% (45/48) at
  N=300. All three N=300 failures are one case, `multi-person-006`, failing in every run (below).
- **Crossover.** With the Task 14 smoke (N=10 and N=30: both 100%), `hybrid` is no worse than `full` at N=10, 30
  and 100. It costs the same at N=10 (every agent fits in 20), 0.90× at N=30 (22,191 vs 24,634 prompt tokens per
  case-run) and 0.43× at N=100 (22,216 vs 51,445). At N=300 it costs 0.17× (21,496 vs 130,268) but loses one dev
  case in 3/3 runs. So on dev the measured crossover is: `hybrid` is better from N≈30 to at least N=100, and at
  N=300 it trades 6 points of pass rate for an 83% cut in prompt tokens. Sixteen dev cases are too few to say
  whether that 6 points is one unlucky case or a rate.
- **The N=300 failure is the dense-world gap, and search did not close it.** `multi-person-006` says "Ask Sam and
  Alice Chen if they'd like to join the running club on Sundays." Two people are called Sam (Sam Rivera, Sam
  Okafor), so the right move is to ask which Sam. At N=300 the initial 20 held Sam Rivera's agent but neither of
  Sam Okafor's two. The model saw one Sam, had no reason to doubt it, never searched, and emailed Sam Rivera.
  At N=100 all three Sam agents were in the initial 20, and in every run it started Alice Chen's email and asked
  which Sam (the second acceptable outcome). This is the failure `search_agents` cannot
  fix on its own: the model only searches when it knows something is missing.
- **Search behaviour.** The search rate was 1/48 at N=100 and 2/48 at N=300, with 0 search errors. All three
  searches were `newtask-006` ("daily 8am reminder to back up phone photos"), a new task where creating is right
  either way; the search returned 20 ids and surfaced one of the lookalike agents each time, and the model still
  (correctly) created. The graded target was in the initial 20 in 42/48 case-runs at N=100 and 39/48 at N=300;
  nothing was found only by search (0/48 at both). The target was missing both ways (not in the initial 20, and
  no search or a search that missed part of it) in 6/48 at N=100 (`multi-intent-005` and `newtask-006`, 3 runs
  each) and 9/48 at N=300 (those two plus `multi-person-006`). For `multi-intent-005` and `newtask-006` the
  target is a set of lookalike agents that should *not* be reused, so missing them is harmless and they passed.
  The only harmful miss is `multi-person-006`, which never searched.
- **Cost.** Measured prompt tokens per case-run against the estimate:

  | mode | N=100 measured / est. | N=300 measured / est. |
  |---|---|---|
  | full | 51,445 / 51,878 | 130,268 / 117,473 |
  | hybrid | 22,216 / 23,619 | 21,496 / 23,619 |

  `hybrid` is 1.03× and 1.00× `full`@20 (21,472), so the new ×1.1 factor over-estimates by 6% and 9%. That is
  inside 10%, so the factor stays at 1.1 and needs no recalibration. `full` at N=300 came in 11% above its
  estimate (Experiment 7's own figure). The first-call prompt is identical (52,831 tokens minimum in both runs),
  so the difference is round trips: 2.44 per case-run here against 2.21 in Experiment 7. This is noise in how
  often Haiku takes a third turn, not a change in the prompt. Total: estimate $1.0972, runner $1.1504; the
  overrun is almost all `full`@300.
- **Next decision.** v1 dev mostly does not reach the dense-world gap: at N=300 the target was in the initial 20
  for 39/48 case-runs, and the misses that matter came from one case. That one case shows the gap is real and
  that the model does not search its way out of it, because it cannot see what is missing. Whether a
  dense-request routing run (many same-name people, paraphrased or history-dependent requests, at N=300) is worth
  building before the final test run is the open question for Siddharth. The cheaper alternative is to accept
  the one-case loss and report it.
