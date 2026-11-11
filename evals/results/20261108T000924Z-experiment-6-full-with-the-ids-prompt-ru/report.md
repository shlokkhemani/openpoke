# Routing run: Experiment 6: full with the ids-prompt rule 'never write an email yourself' and the text-reply grader fix, dev, 4 sizes x 3 runs (Haiku)

## Setup

- **Purpose:** Experiment 6: full with the ids-prompt rule 'never write an email yourself' and the text-reply grader fix, dev, 4 sizes x 3 runs (Haiku)
- **Command:** `python -m evals.run routing --split dev --modes full --sizes 10,30,100,300 --runs 3 --max-cost 3 --purpose 'Experiment 6: full with the ids-prompt rule '"'"'never write an email yourself'"'"' and the text-reply grader fix, dev, 4 sizes x 3 runs (Haiku)' --yes`
- **Date (UTC):** 2026-11-08T00:09:24Z
- **Model:** `anthropic/claude-haiku-5.5`
- **Code:** uncommitted working tree on HEAD 4d629cc
- **Case set:** `evals/cases/v1` (v1), MANIFEST sha256 `688388e57eb5980fa06046a7e384b5449d9b1c71134c817bbf7d20d166fbcbda`, frozen_on 2026-11-07
- **Split:** dev, 16 cases
- **Descriptions (`full`):** regen, sha256 `5d4d6d7c5b20fa1c53c69d280e122d27804833e7dd04ac623bf1e8e1c93ec232`, covering 310/310 world agents
- **Grid:** modes full × sizes 10, 30, 100, 300 × 3 run(s) = 192 case-runs (0 reused from `legacy`: recency at N ≤ 20)
- **Outcome:** 192 graded, 0 infra errors (not graded), 0 skipped by the max-cost cap ($3), 0 retried

## Cost

- Actual: **$1.0869** (estimate before the run: $1.0766)
- Tokens: 10,167,415 prompt / 140,260 completion (all attempts)
- Mean latency per case-run: 4.835 s; mean round trips: 2.26

## Pass rate by mode × N

Infra errors are excluded from the denominators; structural failures count as failures.

| mode | N=10 | N=30 | N=100 | N=300 |
|---|---|---|---|---|
| full | 96% (46/48) | 98% (47/48) | 100% (48/48) | 94% (45/48) |

## Pass rate by category

| category | mode | N=10 | N=30 | N=100 | N=300 |
|---|---|---|---|---|---|
| ambiguous_person | full | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |
| broad_question_person | full | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |
| clear_person | full | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |
| email_followup | full | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |
| multi_intent | full | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |
| multi_person | full | 83% (5/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |
| new_task_lookalike | full | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |
| trigger_management | full | 83% (5/6) | 83% (5/6) | 100% (6/6) | 50% (3/6) |

## Flags

| flag | mode | N=10 | N=30 | N=100 | N=300 |
|---|---|---|---|---|---|
| over_clarify | full | 1/48 | 1/48 | 0/48 | 3/48 |
| wrong_reuse | full | 1/48 | 0/48 | 0/48 | 0/48 |

## Structural failures

A legacy dispatch by a name that several agents share (e.g. two "Email Alice" agents): the names-only roster cannot express the right target.

| mode | N=10 | N=30 | N=100 | N=300 |
|---|---|---|---|---|
| full | 0 | 0 | 0 | 0 |

## Infra errors

Retried once; a case-run whose retry also failed is listed in `errors.jsonl` and not graded. Counts are paid case-runs; a reused recency copy of an errored `legacy` case-run is not counted again.

| mode | N=10 | N=30 | N=100 | N=300 |
|---|---|---|---|---|
| full | 0 | 0 | 0 | 0 |

## Failing case-runs

| case | category | mode | N | run | outcome | flags | reason |
|---|---|---|---|---|---|---|---|
| multi-person-006 | multi_person | full | 10 | 0 | reuse | wrong_reuse | expected clarify \| dispatch(create[Alice Chen] + ask); got reuse (dispatch→ag_chen_budget, message_user); slots 0/1 |
| trigger-006 | trigger_management | full | 10 | 1 | clarify | over_clarify | expected reuse(ag_ohyhhbka); got clarify (no tool calls) |
| trigger-006 | trigger_management | full | 30 | 2 | clarify | over_clarify | expected reuse(ag_ohyhhbka); got clarify (no tool calls) |
| trigger-006 | trigger_management | full | 300 | 0 | clarify | over_clarify | expected reuse(ag_ohyhhbka); got clarify (no tool calls) |
| trigger-006 | trigger_management | full | 300 | 1 | clarify | over_clarify | expected reuse(ag_ohyhhbka); got clarify (no tool calls) |
| trigger-006 | trigger_management | full | 300 | 2 | clarify | over_clarify | expected reuse(ag_ohyhhbka); got clarify (no tool calls) |

## What we learned

- **What changed since experiment 5:** two changes, logged in `changes.md`.
  - The grader counts a text-only final reply as a user message, as production does (`runtime.py:104`).
  - The ids prompt says "Never write an email yourself… send the instructions to the `agent_id` of the
    agent that handled that thread". Everything else is identical: the same grid, case set and regen descriptions.
- **Result:** **96 / 98 / 100 / 94%**, against 94 / 94 / 94 / 90% for experiment 5 regraded and 79 / 75 / 65 / 67% for
  legacy_rules (experiment 4).
- **Separating the two effects:**
  - The grader fix alone took experiment 5 from 88 / 88 / 88 / 81% to 94 / 94 / 94 / 90% (regrade, no new calls).
    That is `amb-person-006` (two Daniels) going from 0/12 to 12/12, plus one `multi-person-006` run.
  - The prompt rule took `amb-person-007` from 1/12 to **12/12**. The IA now dispatches the thank-you to
    the Farah offer-letter agent instead of writing it with `send_draft`. ambiguous_person is 100% at every N.
- **No new failure from the prompt rule:** duplicate_create stays 0, and no case that passed in experiment 5 now fails
  because of it. No dev case expects `send_draft` after an agent's draft, so the rule's cost on that path is untested.
- **Left (6 of 192 runs):**
  - `trigger-006` (5): the IA asks "which reminder?" instead of moving the one just shown. That is 3/3 at N=300, so with
    many trigger agents on the roster it hesitates more.
  - `multi-person-006` N=10 (1): it sent the running-club invite for Alice Chen to `ag_chen_budget`, Alice's budget
    agent (wrong_reuse).
- **Cost:** $1.0869 against an estimate of $1.0766 (1.01×). The measured `full` token table is now accurate. Prompt tokens
  are unchanged from experiment 5 (10.17M vs 10.19M), so the final-run projection (≈ $57 against ≈ $46.5 left)
  still holds.
