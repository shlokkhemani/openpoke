# Routing run: Experiment 7: full with ids-prompt pronoun rule and reply rule limited to existing threads, dev, 4 sizes x 3 runs (Haiku)

## Setup

- **Purpose:** Experiment 7: full with ids-prompt pronoun rule and reply rule limited to existing threads, dev, 4 sizes x 3 runs (Haiku)
- **Command:** `python -m evals.run routing --split dev --modes full --sizes 10,30,100,300 --runs 3 --max-cost 3 --purpose 'Experiment 7: full with ids-prompt pronoun rule and reply rule limited to existing threads, dev, 4 sizes x 3 runs (Haiku)' --yes`
- **Date (UTC):** 2026-11-08T00:37:48Z
- **Model:** `anthropic/claude-haiku-5.5`
- **Code:** uncommitted working tree on HEAD 4d629cc
- **Case set:** `evals/cases/v1` (v1), MANIFEST sha256 `688388e57eb5980fa06046a7e384b5449d9b1c71134c817bbf7d20d166fbcbda`, frozen_on 2026-11-07
- **Split:** dev, 16 cases
- **Descriptions (`full`):** regen, sha256 `5d4d6d7c5b20fa1c53c69d280e122d27804833e7dd04ac623bf1e8e1c93ec232`, covering 310/310 world agents
- **Grid:** modes full × sizes 10, 30, 100, 300 × 3 run(s) = 192 case-runs (0 reused from `legacy`: recency at N ≤ 20)
- **Outcome:** 192 graded, 0 infra errors (not graded), 0 skipped by the max-cost cap ($3), 0 retried

## Cost

- Actual: **$1.0805** (estimate before the run: $1.0766)
- Tokens: 10,126,140 prompt / 135,798 completion (all attempts)
- Mean latency per case-run: 4.741 s; mean round trips: 2.271

## Pass rate by mode × N

Infra errors are excluded from the denominators; structural failures count as failures.

| mode | N=10 | N=30 | N=100 | N=300 |
|---|---|---|---|---|
| full | 100% (48/48) | 100% (48/48) | 100% (48/48) | 100% (48/48) |

## Pass rate by category

| category | mode | N=10 | N=30 | N=100 | N=300 |
|---|---|---|---|---|---|
| ambiguous_person | full | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |
| broad_question_person | full | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |
| clear_person | full | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |
| email_followup | full | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |
| multi_intent | full | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |
| multi_person | full | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |
| new_task_lookalike | full | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |
| trigger_management | full | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |

## Flags

No flags raised.

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

None.

## What we learned

- **What changed since experiment 6:** two ids-prompt edits, logged in `changes.md`.
  - A pronoun rule: "this/that/it" right after an agent's message means that agent; act without asking.
  - The reply rule now covers only emails an agent already handled. A new topic for the same person needs a new agent.
- **Result: 100% at every N (192/192)**, against 96 / 98 / 100 / 94% in experiment 6. No flags, 0 infra errors.
  - `trigger-006` 12/12, was 7/12: it pushes the subscription audit reminder back instead of asking which one.
  - `multi-person-006` 12/12, was 11/12: no more reuse of Alice's Q3-budget agent for the running-club email.
  - `amb-person-007` stays 12/12. duplicate_create stays 0, so "new topic needs a new agent" did not cause extra creates.
- **Caveats:**
  - 16 dev cases × 3 runs is a small set, and these edits were written against these very failures. Some of
    this is fitting to dev, and the test split is where it gets checked.
  - The pronoun rule is untested on a case where "this" right after an agent's message means something else.
- **Cost:** $1.0805 on the company key (see `evals/results/SPEND.md`). Billed by OpenRouter: $1.080513 (estimate $1.0766).
