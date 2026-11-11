# Routing run: Task 16f: hybrid on v2 with A3 message weighting, dev, 4 sizes x 3 runs (Haiku)

## Setup

- **Purpose:** Task 16f: hybrid on v2 with A3 message weighting, dev, 4 sizes x 3 runs (Haiku)
- **Command:** `python -m evals.run routing --modes hybrid --sizes 10,30,100,300 --split dev --runs 3 --embedder fastembed --max-cost 1 --purpose 'Task 16f: hybrid on v2 with A3 message weighting, dev, 4 sizes x 3 runs (Haiku)' --yes`
- **Date (UTC):** 2026-11-10T00:08:01Z
- **Model:** `anthropic/claude-haiku-5.5`
- **Code:** uncommitted working tree on HEAD e5ae51a
- **Case set:** `evals/cases/v2` (v2), MANIFEST sha256 `d0c9a4ca5b94e38c5c16bc428609f90cd25ba1b03d8adf80e733689c4649cc3c`, frozen_on 2026-11-09
- **Split:** dev, 16 cases
- **Descriptions (`full`):** regen, sha256 `5d4d6d7c5b20fa1c53c69d280e122d27804833e7dd04ac623bf1e8e1c93ec232`, covering 310/310 world agents
- **Grid:** modes hybrid × sizes 10, 30, 100, 300 × 3 run(s) = 192 case-runs
- **Outcome:** 192 graded, 0 infra errors (not graded), 0 skipped by the max-cost cap ($1), 0 retried

## Cost

- Actual: **$0.4668** (estimate before the run: $0.4928)
- Tokens: 4,037,699 prompt / 126,004 completion (all attempts)
- Mean latency per case-run: 4.508 s; mean round trips: 2.224

## Pass rate by mode × N

Infra errors are excluded from the denominators; structural failures count as failures.

| mode | N=10 | N=30 | N=100 | N=300 |
|---|---|---|---|---|
| hybrid | 100% (48/48) | 100% (48/48) | 100% (48/48) | 100% (48/48) |

## Pass rate by category

| category | mode | N=10 | N=30 | N=100 | N=300 |
|---|---|---|---|---|---|
| ambiguous_person | hybrid | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |
| broad_question_person | hybrid | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |
| clear_person | hybrid | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |
| email_followup | hybrid | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |
| multi_intent | hybrid | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |
| multi_person | hybrid | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |
| new_task_lookalike | hybrid | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |
| trigger_management | hybrid | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |

## Flags

| flag | mode | N=10 | N=30 | N=100 | N=300 |
|---|---|---|---|---|---|
| invalid_call | hybrid | 0/48 | 1/48 | 0/48 | 1/48 |

## Search

Embedder: `fastembed`. The target is the graded case's expected agents (`retrieval_eval.expected_for`); cases without one count in neither target row.

| mode | measure | N=10 | N=30 | N=100 | N=300 |
|---|---|---|---|---|---|
| hybrid | Search rate (case-runs that searched) | 0/48 | 2/48 | 3/48 | 1/48 |
| hybrid | Search errors (calls) | 0 | 0 | 0 | 0 |
| hybrid | Target in the initial cards | 48/48 | 48/48 | 42/48 | 42/48 |
| hybrid | Target found only by search | 0/48 | 0/48 | 0/48 | 0/48 |

## Structural failures

A legacy dispatch by a name that several agents share (e.g. two "Email Alice" agents): the names-only roster cannot express the right target.

| mode | N=10 | N=30 | N=100 | N=300 |
|---|---|---|---|---|
| hybrid | 0 | 0 | 0 | 0 |

## Infra errors

Retried once; a case-run whose retry also failed is listed in `errors.jsonl` and not graded. Counts are case-runs.

| mode | N=10 | N=30 | N=100 | N=300 |
|---|---|---|---|---|
| hybrid | 0 | 0 | 0 | 0 |

## Failing case-runs

None.

## What we learned

`hybrid` with A3 retrieval (Task 16f: RRF over BM25 and embeddings on the message and on history plus message), v2 dev, fastembed. This is the first `hybrid` run on v2. Compared with the v2 baseline `20261109T214557Z` (same cases, model and sizes).

- **`hybrid` passes 100% at every N (192/192), level with `full` (100% ×4) and above `legacy_rules` (83/85/81/77%).** On v1, `hybrid` was 100%/94% at N=100/300 (`20261109T200608Z`, Task 15, before Tasks 16e/16f). The v1 failure was `multi-person-006`; on v2 it passes 6/6 at N=100 and N=300.
- **The initial cards held the whole target in 180/192 case-runs.** The 12 misses are 2 cases × 3 runs × N=100/300. `multi-intent-005` had 2/3 of its agents in the cards at N=100 and 1/3 at N=300. `newtask-006` had 3/4 and 2/4. Both still passed in every run without the target appearing in a search, so the missing agents were not needed for the graded outcome. The searches found no target agent (0/48 at each N), and the search rate was 0–3 of 48.
- **Cost.** Runner $0.4668 against an estimate of $0.4928, about $0.0024 per case-run. Per case-run cost is flat in N: about 25k prompt-token equivalents at N=30–300, against `full`'s 126k at N=300 (about a fifth) and `legacy_rules`' 30k. Billed $0.4668 (SPEND.md row 7).
