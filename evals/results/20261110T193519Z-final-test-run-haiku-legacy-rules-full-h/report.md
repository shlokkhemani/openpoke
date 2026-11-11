# Routing run: Final test run: Haiku, legacy_rules+full+hybrid x N=10,30,100,300 x 3 runs, frozen 39a1439

## Setup

- **Purpose:** Final test run: Haiku, legacy_rules+full+hybrid x N=10,30,100,300 x 3 runs, frozen 39a1439
- **Command:** `python -m evals.run routing --modes legacy_rules,full,hybrid --sizes 10,30,100,300 --split test --runs 3 --embedder fastembed --max-cost 6 --purpose 'Final test run: Haiku, legacy_rules+full+hybrid x N=10,30,100,300 x 3 runs, frozen 39a1439' --yes`
- **Date (UTC):** 2026-11-10T19:35:19Z
- **Model:** `anthropic/claude-haiku-5.5`
- **Code:** uncommitted working tree on HEAD 39a1439
- **Case set:** `evals/cases/v2` (v2), MANIFEST sha256 `d0c9a4ca5b94e38c5c16bc428609f90cd25ba1b03d8adf80e733689c4649cc3c`, frozen_on 2026-11-09
- **Split:** test, 33 cases
- **Descriptions (`full`):** regen, sha256 `5d4d6d7c5b20fa1c53c69d280e122d27804833e7dd04ac623bf1e8e1c93ec232`, covering 310/310 world agents
- **Grid:** modes legacy_rules, full, hybrid × sizes 10, 30, 100, 300 × 3 run(s) = 1188 case-runs
- **Outcome:** 1188 graded, 0 infra errors (not graded), 0 skipped by the max-cost cap ($6), 0 retried

## Cost

- Actual: **$4.1160** (estimate before the run: $4.0110)
- Tokens: 36,883,566 prompt / 855,263 completion (all attempts)
- Mean latency per case-run: 5.115 s; mean round trips: 2.244

## Pass rate by mode × N

Infra errors are excluded from the denominators; structural failures count as failures.

| mode | N=10 | N=30 | N=100 | N=300 |
|---|---|---|---|---|
| legacy_rules | 80% (79/99) | 76% (75/99) | 74% (73/99) | 63% (62/99) |
| full | 94% (93/99) | 93% (92/99) | 93% (92/99) | 93% (92/99) |
| hybrid | 96% (95/99) | 98% (97/99) | 96% (95/99) | 97% (96/99) |

## Pass rate by category

| category | mode | N=10 | N=30 | N=100 | N=300 |
|---|---|---|---|---|---|
| ambiguous_person | legacy_rules | 67% (10/15) | 67% (10/15) | 60% (9/15) | 40% (6/15) |
| ambiguous_person | full | 67% (10/15) | 67% (10/15) | 73% (11/15) | 67% (10/15) |
| ambiguous_person | hybrid | 73% (11/15) | 87% (13/15) | 93% (14/15) | 100% (15/15) |
| broad_question_person | legacy_rules | 50% (6/12) | 50% (6/12) | 50% (6/12) | 50% (6/12) |
| broad_question_person | full | 100% (12/12) | 100% (12/12) | 100% (12/12) | 100% (12/12) |
| broad_question_person | hybrid | 100% (12/12) | 100% (12/12) | 100% (12/12) | 100% (12/12) |
| clear_person | legacy_rules | 100% (12/12) | 100% (12/12) | 100% (12/12) | 100% (12/12) |
| clear_person | full | 100% (12/12) | 92% (11/12) | 83% (10/12) | 100% (12/12) |
| clear_person | hybrid | 100% (12/12) | 100% (12/12) | 83% (10/12) | 100% (12/12) |
| email_followup | legacy_rules | 100% (12/12) | 100% (12/12) | 100% (12/12) | 100% (12/12) |
| email_followup | full | 100% (12/12) | 92% (11/12) | 92% (11/12) | 92% (11/12) |
| email_followup | hybrid | 100% (12/12) | 100% (12/12) | 100% (12/12) | 100% (12/12) |
| multi_intent | legacy_rules | 92% (11/12) | 83% (10/12) | 75% (9/12) | 75% (9/12) |
| multi_intent | full | 100% (12/12) | 100% (12/12) | 100% (12/12) | 100% (12/12) |
| multi_intent | hybrid | 100% (12/12) | 100% (12/12) | 100% (12/12) | 100% (12/12) |
| multi_person | legacy_rules | 83% (10/12) | 83% (10/12) | 75% (9/12) | 33% (4/12) |
| multi_person | full | 92% (11/12) | 100% (12/12) | 100% (12/12) | 100% (12/12) |
| multi_person | hybrid | 100% (12/12) | 100% (12/12) | 92% (11/12) | 100% (12/12) |
| new_task_lookalike | legacy_rules | 75% (9/12) | 75% (9/12) | 75% (9/12) | 75% (9/12) |
| new_task_lookalike | full | 100% (12/12) | 100% (12/12) | 100% (12/12) | 100% (12/12) |
| new_task_lookalike | hybrid | 100% (12/12) | 100% (12/12) | 100% (12/12) | 100% (12/12) |
| trigger_management | legacy_rules | 75% (9/12) | 50% (6/12) | 58% (7/12) | 33% (4/12) |
| trigger_management | full | 100% (12/12) | 100% (12/12) | 100% (12/12) | 92% (11/12) |
| trigger_management | hybrid | 100% (12/12) | 100% (12/12) | 100% (12/12) | 75% (9/12) |

## Flags

| flag | mode | N=10 | N=30 | N=100 | N=300 |
|---|---|---|---|---|---|
| ambiguous_dispatch | legacy_rules | 1/99 | 0/99 | 1/99 | 3/99 |
| ambiguous_dispatch | full | 0/99 | 0/99 | 0/99 | 0/99 |
| ambiguous_dispatch | hybrid | 0/99 | 0/99 | 0/99 | 0/99 |
| duplicate_create | legacy_rules | 2/99 | 5/99 | 7/99 | 9/99 |
| duplicate_create | full | 0/99 | 0/99 | 0/99 | 0/99 |
| duplicate_create | hybrid | 0/99 | 0/99 | 1/99 | 0/99 |
| invalid_call | legacy_rules | 1/99 | 0/99 | 0/99 | 0/99 |
| invalid_call | full | 1/99 | 0/99 | 0/99 | 0/99 |
| invalid_call | hybrid | 2/99 | 0/99 | 0/99 | 0/99 |
| over_clarify | legacy_rules | 0/99 | 3/99 | 1/99 | 5/99 |
| over_clarify | full | 0/99 | 2/99 | 3/99 | 2/99 |
| over_clarify | hybrid | 0/99 | 0/99 | 0/99 | 3/99 |
| trigger_duplicate | legacy_rules | 0/99 | 1/99 | 2/99 | 1/99 |
| trigger_duplicate | full | 0/99 | 0/99 | 0/99 | 0/99 |
| trigger_duplicate | hybrid | 0/99 | 0/99 | 0/99 | 0/99 |
| wrong_reuse | legacy_rules | 3/99 | 3/99 | 3/99 | 3/99 |
| wrong_reuse | full | 1/99 | 0/99 | 0/99 | 0/99 |
| wrong_reuse | hybrid | 1/99 | 0/99 | 2/99 | 0/99 |

## Search

Embedder: `fastembed`. The target is the graded case's expected agents (`retrieval_eval.expected_for`); cases without one count in neither target row.

| mode | measure | N=10 | N=30 | N=100 | N=300 |
|---|---|---|---|---|---|
| hybrid | Search rate (case-runs that searched) | 0/99 | 7/99 | 7/99 | 7/99 |
| hybrid | Search errors (calls) | 0 | 0 | 0 | 0 |
| hybrid | Target in the initial cards | 99/99 | 99/99 | 96/99 | 87/99 |
| hybrid | Target found only by search | 0/99 | 0/99 | 0/99 | 0/99 |

## Structural failures

A legacy dispatch by a name that several agents share (e.g. two "Email Alice" agents): the names-only roster cannot express the right target.

| mode | N=10 | N=30 | N=100 | N=300 |
|---|---|---|---|---|
| legacy_rules | 3 | 2 | 2 | 2 |
| full | 0 | 0 | 0 | 0 |
| hybrid | 0 | 0 | 0 | 0 |

## Infra errors

Retried once; a case-run whose retry also failed is listed in `errors.jsonl` and not graded. Counts are case-runs.

| mode | N=10 | N=30 | N=100 | N=300 |
|---|---|---|---|---|
| legacy_rules | 0 | 0 | 0 | 0 |
| full | 0 | 0 | 0 | 0 |
| hybrid | 0 | 0 | 0 | 0 |

## Failing case-runs

| case | category | mode | N | run | outcome | flags | reason |
|---|---|---|---|---|---|---|---|
| amb-person-001 | ambiguous_person | legacy_rules | 100 | 0 | create | – | expected clarify; got create (message_user, dispatch→Email Alice re offsite planning call) |
| amb-person-001 | ambiguous_person | legacy_rules | 100 | 1 | create | – | expected clarify; got create (message_user, dispatch→Email Alice re offsite planning call) |
| amb-person-001 | ambiguous_person | legacy_rules | 100 | 2 | create | – | expected clarify; got create (message_user, dispatch→Email Alice re offsite planning call) |
| amb-person-001 | ambiguous_person | legacy_rules | 300 | 0 | create | – | expected clarify; got create (message_user, dispatch→Email Alice re offsite planning call) |
| amb-person-001 | ambiguous_person | legacy_rules | 300 | 1 | create | – | expected clarify; got create (message_user, dispatch→Email Alice about offsite planning call) |
| amb-person-001 | ambiguous_person | legacy_rules | 300 | 2 | create | – | expected clarify; got create (message_user, dispatch→Email Alice about offsite planning call) |
| amb-person-003 | ambiguous_person | legacy_rules | 10 | 0 | create | – | expected clarify; got create (message_user, dispatch→Email Alice Chen re Thursday offsite call) |
| amb-person-003 | ambiguous_person | legacy_rules | 10 | 2 | create | – | expected clarify; got create (message_user, dispatch→Email Alice Chen re offsite planning call) |
| amb-person-003 | ambiguous_person | legacy_rules | 30 | 0 | create | – | expected clarify; got create (message_user, dispatch→Email Alice Chen re offsite planning call) |
| amb-person-003 | ambiguous_person | legacy_rules | 30 | 2 | create | – | expected clarify; got create (message_user, dispatch→Email Alice Chen re offsite planning call) |
| amb-person-003 | ambiguous_person | legacy_rules | 100 | 0 | create | – | expected clarify; got create (message_user, dispatch→Email Alice Chen re offsite planning call) |
| amb-person-003 | ambiguous_person | legacy_rules | 300 | 0 | create | – | expected clarify; got create (message_user, dispatch→Email Alice Chen re offsite planning call) |
| amb-person-003 | ambiguous_person | legacy_rules | 300 | 1 | create | – | expected clarify; got create (message_user, dispatch→Email Alice Chen re offsite planning call) |
| amb-person-003 | ambiguous_person | legacy_rules | 300 | 2 | create | – | expected clarify; got create (message_user, dispatch→Email Alice Chen re offsite planning call) |
| amb-person-003 | ambiguous_person | full | 10 | 1 | create | – | expected clarify; got create (message_user, dispatch→Email Alice Chen re offsite planning call) |
| amb-person-003 | ambiguous_person | full | 10 | 2 | create | – | expected clarify; got create (message_user, dispatch→Email Alice Chen re offsite planning call) |
| amb-person-003 | ambiguous_person | full | 30 | 0 | create | – | expected clarify; got create (message_user, dispatch→Email Alice Chen re Thursday offsite planning call, wait) |
| amb-person-003 | ambiguous_person | full | 30 | 2 | create | – | expected clarify; got create (message_user, dispatch→Email Alice Chen re Thursday offsite planning call) |
| amb-person-003 | ambiguous_person | full | 100 | 2 | create | – | expected clarify; got create (message_user, dispatch→Email Alice Chen re offsite planning call) |
| amb-person-003 | ambiguous_person | full | 300 | 0 | create | – | expected clarify; got create (message_user, dispatch→Email Alice Chen re offsite planning call, wait) |
| amb-person-003 | ambiguous_person | full | 300 | 1 | create | – | expected clarify; got create (message_user, dispatch→Email Alice Chen about offsite planning call) |
| amb-person-003 | ambiguous_person | hybrid | 10 | 2 | create | – | expected clarify; got create (message_user, dispatch→Email Alice Chen re Thursday offsite planning call) |
| amb-person-005 | ambiguous_person | legacy_rules | 10 | 0 | create | – | expected clarify; got create (message_user, dispatch→Email Alice Chen re offsite planning call) |
| amb-person-005 | ambiguous_person | legacy_rules | 10 | 1 | create | – | expected clarify; got create (message_user, dispatch→Email Alice Chen re offsite planning call) |
| amb-person-005 | ambiguous_person | legacy_rules | 10 | 2 | create | – | expected clarify; got create (message_user, dispatch→Email Alice Chen re offsite planning call) |
| amb-person-005 | ambiguous_person | legacy_rules | 30 | 0 | create | – | expected clarify; got create (message_user, dispatch→Email Alice Chen re offsite planning call) |
| amb-person-005 | ambiguous_person | legacy_rules | 30 | 1 | create | – | expected clarify; got create (message_user, dispatch→Email Alice Chen re offsite planning call) |
| amb-person-005 | ambiguous_person | legacy_rules | 30 | 2 | create | – | expected clarify; got create (message_user, dispatch→Email Alice Chen re offsite planning call) |
| amb-person-005 | ambiguous_person | legacy_rules | 100 | 0 | create | – | expected clarify; got create (message_user, dispatch→Email Alice Chen re offsite planning call) |
| amb-person-005 | ambiguous_person | legacy_rules | 100 | 2 | create | – | expected clarify; got create (message_user, dispatch→Email Alice Chen re offsite planning call) |
| amb-person-005 | ambiguous_person | legacy_rules | 300 | 0 | create | – | expected clarify; got create (message_user, dispatch→Email Alice Chen re offsite planning call) |
| amb-person-005 | ambiguous_person | legacy_rules | 300 | 1 | create | – | expected clarify; got create (message_user, dispatch→Email Alice Chen re offsite planning call) |
| amb-person-005 | ambiguous_person | legacy_rules | 300 | 2 | create | – | expected clarify; got create (message_user, dispatch→Email Alice Chen re offsite planning call) |
| amb-person-005 | ambiguous_person | full | 10 | 0 | create | – | expected clarify; got create (message_user, dispatch→Email Alice Chen about Thursday offsite planning call) |
| amb-person-005 | ambiguous_person | full | 10 | 1 | create | – | expected clarify; got create (message_user, dispatch→Email Alice Chen re offsite planning call Thursday) |
| amb-person-005 | ambiguous_person | full | 10 | 2 | create | – | expected clarify; got create (message_user, dispatch→Email Alice Chen about Thursday offsite planning call) |
| amb-person-005 | ambiguous_person | full | 30 | 0 | create | – | expected clarify; got create (message_user, dispatch→Email Alice Chen re offsite planning call, wait) |
| amb-person-005 | ambiguous_person | full | 30 | 1 | create | – | expected clarify; got create (message_user, dispatch→Email Alice Chen re offsite planning call, wait) |
| amb-person-005 | ambiguous_person | full | 30 | 2 | create | – | expected clarify; got create (message_user, dispatch→Email Alice Chen re offsite planning call Thursday) |
| amb-person-005 | ambiguous_person | full | 100 | 0 | create | – | expected clarify; got create (message_user, dispatch→Email Alice Chen about offsite planning call) |
| amb-person-005 | ambiguous_person | full | 100 | 1 | create | – | expected clarify; got create (message_user, dispatch→Email Alice Chen about offsite planning call, wait) |
| amb-person-005 | ambiguous_person | full | 100 | 2 | create | – | expected clarify; got create (message_user, dispatch→Email Alice Chen about offsite planning call Thursday, wait) |
| amb-person-005 | ambiguous_person | full | 300 | 0 | create | – | expected clarify; got create (message_user, dispatch→Email Alice Chen re offsite planning call) |
| amb-person-005 | ambiguous_person | full | 300 | 1 | create | – | expected clarify; got create (message_user, dispatch→Email Alice Chen about Thursday offsite planning call) |
| amb-person-005 | ambiguous_person | full | 300 | 2 | create | – | expected clarify; got create (message_user, dispatch→Draft email to Alice Chen re offsite planning call Thursday) |
| amb-person-005 | ambiguous_person | hybrid | 10 | 0 | create | – | expected clarify; got create (message_user, dispatch→Email Alice Chen about Thursday offsite planning call) |
| amb-person-005 | ambiguous_person | hybrid | 10 | 1 | reuse | wrong_reuse | expected clarify; got reuse (dispatch→ag_chen_budget, message_user) |
| amb-person-005 | ambiguous_person | hybrid | 10 | 2 | create | – | expected clarify; got create (message_user, dispatch→Email Alice Chen about Thursday offsite planning call) |
| amb-person-005 | ambiguous_person | hybrid | 30 | 1 | create | – | expected clarify; got create (message_user, dispatch→Email Alice Chen about Thursday offsite planning call) |
| amb-person-005 | ambiguous_person | hybrid | 30 | 2 | create | – | expected clarify; got create (message_user, dispatch→Email Alice Chen about offsite planning call) |
| amb-person-005 | ambiguous_person | hybrid | 100 | 1 | create | – | expected clarify; got create (message_user, dispatch→Draft email to Alice Chen re offsite planning call Thursday) |
| broad-person-001 | broad_question_person | legacy_rules | 10 | 0 | reuse | – | expected answer_set([ag_dana_repair, ag_dana_lease, ag_dana_parking]); got reuse (message_user, dispatch→Email Dana about lease renewal, dispatch→Ask Dana about a parking spot) |
| broad-person-001 | broad_question_person | legacy_rules | 10 | 1 | reuse | – | expected answer_set([ag_dana_repair, ag_dana_lease, ag_dana_parking]); got reuse (message_user, dispatch→Email Dana about lease renewal, dispatch→Ask Dana about a parking spot) |
| broad-person-001 | broad_question_person | legacy_rules | 10 | 2 | reuse | – | expected answer_set([ag_dana_repair, ag_dana_lease, ag_dana_parking]); got reuse (message_user, dispatch→Email Dana about lease renewal, dispatch→Ask Dana about a parking spot) |
| broad-person-001 | broad_question_person | legacy_rules | 30 | 0 | reuse | – | expected answer_set([ag_dana_repair, ag_dana_lease, ag_dana_parking]); got reuse (message_user, dispatch→Ask Dana about a parking spot, dispatch→Email Dana about lease renewal) |
| broad-person-001 | broad_question_person | legacy_rules | 30 | 1 | reuse | – | expected answer_set([ag_dana_repair, ag_dana_lease, ag_dana_parking]); got reuse (message_user, dispatch→Ask Dana about a parking spot, dispatch→Email Dana about lease renewal, wait) |
| broad-person-001 | broad_question_person | legacy_rules | 30 | 2 | reuse | – | expected answer_set([ag_dana_repair, ag_dana_lease, ag_dana_parking]); got reuse (message_user, dispatch→Ask Dana about a parking spot, dispatch→Email Dana about lease renewal) |
| broad-person-001 | broad_question_person | legacy_rules | 100 | 0 | reuse | – | expected answer_set([ag_dana_repair, ag_dana_lease, ag_dana_parking]); got reuse (message_user, dispatch→Ask Dana about a parking spot, dispatch→Email Dana about lease renewal) |
| broad-person-001 | broad_question_person | legacy_rules | 100 | 1 | reuse | – | expected answer_set([ag_dana_repair, ag_dana_lease, ag_dana_parking]); got reuse (message_user, dispatch→Ask Dana about a parking spot, dispatch→Email Dana about lease renewal) |
| broad-person-001 | broad_question_person | legacy_rules | 100 | 2 | reuse | – | expected answer_set([ag_dana_repair, ag_dana_lease, ag_dana_parking]); got reuse (message_user, dispatch→Ask Dana about a parking spot, dispatch→Email Dana about lease renewal, wait) |
| broad-person-001 | broad_question_person | legacy_rules | 300 | 0 | reuse | – | expected answer_set([ag_dana_repair, ag_dana_lease, ag_dana_parking]); got reuse (message_user, dispatch→Ask Dana about a parking spot, dispatch→Email Dana about lease renewal, wait) |
| broad-person-001 | broad_question_person | legacy_rules | 300 | 1 | reuse | – | expected answer_set([ag_dana_repair, ag_dana_lease, ag_dana_parking]); got reuse (message_user, dispatch→Ask Dana about a parking spot, dispatch→Email Dana about lease renewal, wait) |
| broad-person-001 | broad_question_person | legacy_rules | 300 | 2 | reuse | – | expected answer_set([ag_dana_repair, ag_dana_lease, ag_dana_parking]); got reuse (message_user, dispatch→Ask Dana about a parking spot, dispatch→Email Dana about lease renewal) |
| broad-person-004 | broad_question_person | legacy_rules | 10 | 0 | reuse | invalid_call, wrong_reuse | expected answer_set([ag_ydks7yml, ag_ubyfxd34, ag_w4lalqsk]); got reuse (message_user, dispatch→?, dispatch→?, dispatch→?, dispatch→?, dispatch→?, dispatch→Find emails from Isaac about school form, dispatch→Email Isaa... |
| broad-person-004 | broad_question_person | legacy_rules | 10 | 1 | reuse | wrong_reuse | expected answer_set([ag_ydks7yml, ag_ubyfxd34, ag_w4lalqsk]); got reuse (message_user, dispatch→Find emails from Isaac about school form, dispatch→Email Isaac re catering order, dispatch→Follow up with Isaac on deposi... |
| broad-person-004 | broad_question_person | legacy_rules | 10 | 2 | reuse | wrong_reuse | expected answer_set([ag_ydks7yml, ag_ubyfxd34, ag_w4lalqsk]); got reuse (message_user, dispatch→Find emails from Isaac about school form, dispatch→Email Isaac re catering order, dispatch→Follow up with Isaac on deposi... |
| broad-person-004 | broad_question_person | legacy_rules | 30 | 0 | reuse | wrong_reuse | expected answer_set([ag_ydks7yml, ag_ubyfxd34, ag_w4lalqsk]); got reuse (message_user, dispatch→Follow up with Isaac on deposit refund, dispatch→Find emails from Isaac about school form, dispatch→Follow up with Isaac ... |
| broad-person-004 | broad_question_person | legacy_rules | 30 | 1 | reuse | wrong_reuse | expected answer_set([ag_ydks7yml, ag_ubyfxd34, ag_w4lalqsk]); got reuse (message_user, dispatch→Follow up with Isaac on deposit refund, dispatch→Find emails from Isaac about school form, dispatch→Follow up with Isaac ... |
| broad-person-004 | broad_question_person | legacy_rules | 30 | 2 | reuse | wrong_reuse | expected answer_set([ag_ydks7yml, ag_ubyfxd34, ag_w4lalqsk]); got reuse (message_user, dispatch→Follow up with Isaac on deposit refund, dispatch→Find emails from Isaac about school form, dispatch→Follow up with Isaac ... |
| broad-person-004 | broad_question_person | legacy_rules | 100 | 0 | reuse | wrong_reuse | expected answer_set([ag_ydks7yml, ag_ubyfxd34, ag_w4lalqsk]); got reuse (message_user, dispatch→Follow up with Isaac on Q4 roadmap, dispatch→Find emails from Isaac about flight confirmation, dispatch→Follow up with Is... |
| broad-person-004 | broad_question_person | legacy_rules | 100 | 1 | reuse | wrong_reuse | expected answer_set([ag_ydks7yml, ag_ubyfxd34, ag_w4lalqsk]); got reuse (message_user, dispatch→Follow up with Isaac on Q4 roadmap, dispatch→Find emails from Isaac about flight confirmation, dispatch→Follow up with Is... |
| broad-person-004 | broad_question_person | legacy_rules | 100 | 2 | reuse | wrong_reuse | expected answer_set([ag_ydks7yml, ag_ubyfxd34, ag_w4lalqsk]); got reuse (message_user, dispatch→Follow up with Isaac on Q4 roadmap, dispatch→Find emails from Isaac about flight confirmation, dispatch→Follow up with Is... |
| broad-person-004 | broad_question_person | legacy_rules | 300 | 0 | reuse | wrong_reuse | expected answer_set([ag_ydks7yml, ag_ubyfxd34, ag_w4lalqsk]); got reuse (message_user, dispatch→Follow up with Isaac on deposit refund, dispatch→Find emails from Isaac about flight confirmation, dispatch→Follow up wit... |
| broad-person-004 | broad_question_person | legacy_rules | 300 | 1 | reuse | wrong_reuse | expected answer_set([ag_ydks7yml, ag_ubyfxd34, ag_w4lalqsk]); got reuse (message_user, dispatch→Follow up with Isaac on deposit refund, dispatch→Follow up with Isaac on Q4 roadmap, dispatch→Find emails from Isaac abou... |
| broad-person-004 | broad_question_person | legacy_rules | 300 | 2 | reuse | wrong_reuse | expected answer_set([ag_ydks7yml, ag_ubyfxd34, ag_w4lalqsk]); got reuse (message_user, dispatch→Find emails from Isaac about flight confirmation, dispatch→Email Isaac re catering order, dispatch→Follow up with Isaac o... |
| clear-person-003 | clear_person | hybrid | 100 | 1 | reuse | wrong_reuse | expected create; got reuse (message_user, dispatch→ag_mehguqob, wait) |
| clear-person-003 | clear_person | hybrid | 100 | 2 | reuse | wrong_reuse | expected create; got reuse (message_user, dispatch→ag_mehguqob) |
| clear-person-004 | clear_person | full | 30 | 2 | clarify | over_clarify | expected create; got clarify (no tool calls) |
| clear-person-004 | clear_person | full | 100 | 0 | clarify | over_clarify | expected create; got clarify (no tool calls) |
| clear-person-004 | clear_person | full | 100 | 1 | clarify | over_clarify | expected create; got clarify (no tool calls) |
| followup-003 | email_followup | full | 30 | 1 | clarify | over_clarify | expected reuse(ag_k6vvos7t); got clarify (no tool calls) |
| followup-003 | email_followup | full | 100 | 2 | clarify | over_clarify | expected reuse(ag_k6vvos7t); got clarify (no tool calls) |
| followup-003 | email_followup | full | 300 | 0 | clarify | over_clarify | expected reuse(ag_k6vvos7t); got clarify (no tool calls) |
| multi-intent-002 | multi_intent | legacy_rules | 10 | 1 | mixed | duplicate_create | expected dispatch(reuse(ag_c6obzuoh); create); got mixed (message_user, dispatch→Email Omar Underwood re Saturday monitor delivery, dispatch→Reminder clear desk Saturday 9:30am, dispatch→Email Omar Underwood re Saturd... |
| multi-intent-002 | multi_intent | legacy_rules | 30 | 0 | create | duplicate_create | expected dispatch(reuse(ag_c6obzuoh); create); got create (message_user, dispatch→Email Omar Underwood re Saturday monitor delivery, dispatch→Reminder clear desk Saturday 9:30am); slots 1/2 |
| multi-intent-002 | multi_intent | legacy_rules | 30 | 1 | create | duplicate_create | expected dispatch(reuse(ag_c6obzuoh); create); got create (message_user, dispatch→Email Omar Underwood re Saturday monitor delivery, dispatch→Reminder clear desk Saturday 9:30am); slots 1/2 |
| multi-intent-002 | multi_intent | legacy_rules | 100 | 0 | create | duplicate_create | expected dispatch(reuse(ag_c6obzuoh); create); got create (message_user, dispatch→Email Omar Underwood about Saturday delivery, dispatch→Desk clearing reminder Saturday 9:30am, wait); slots 1/2 |
| multi-intent-002 | multi_intent | legacy_rules | 100 | 1 | create | duplicate_create | expected dispatch(reuse(ag_c6obzuoh); create); got create (message_user, dispatch→Email Omar Underwood about monitor delivery, dispatch→Saturday 9:30am desk clearing reminder); slots 1/2 |
| multi-intent-002 | multi_intent | legacy_rules | 100 | 2 | create | duplicate_create | expected dispatch(reuse(ag_c6obzuoh); create); got create (message_user, dispatch→Email Omar Underwood about monitor delivery, dispatch→Reminder clear desk Saturday 9:30am, wait); slots 1/2 |
| multi-intent-002 | multi_intent | legacy_rules | 300 | 0 | create | duplicate_create | expected dispatch(reuse(ag_c6obzuoh); create); got create (message_user, dispatch→Email Omar Underwood about monitor delivery, dispatch→Saturday 9:30am desk clearing reminder); slots 1/2 |
| multi-intent-002 | multi_intent | legacy_rules | 300 | 1 | create | duplicate_create | expected dispatch(reuse(ag_c6obzuoh); create); got create (message_user, dispatch→Email Omar Underwood about Saturday delivery, dispatch→Reminder Clear desk Saturday 9:30am, wait); slots 1/2 |
| multi-intent-002 | multi_intent | legacy_rules | 300 | 2 | create | duplicate_create | expected dispatch(reuse(ag_c6obzuoh); create); got create (message_user, dispatch→Email Omar Underwood about Saturday delivery, dispatch→Clear desk reminder Saturday 9:30am, wait); slots 1/2 |
| multi-person-001 | multi_person | legacy_rules | 10 | 0 | create | duplicate_create | expected dispatch(reuse(ag_3w3vngdn); create[Theo Brennan]); got create (message_user, dispatch→Check Aaron Castillo pitch doc read status, dispatch→Ask Theo Brennan about plumber); slots 1/2 |
| multi-person-001 | multi_person | legacy_rules | 30 | 1 | create | duplicate_create | expected dispatch(reuse(ag_3w3vngdn); create[Theo Brennan]); got create (message_user, dispatch→Check if Aaron Castillo read pitch doc, dispatch→Ask Theo Brennan about plumber, wait); slots 1/2 |
| multi-person-001 | multi_person | legacy_rules | 30 | 2 | create | duplicate_create | expected dispatch(reuse(ag_3w3vngdn); create[Theo Brennan]); got create (message_user, dispatch→Check Aaron Castillo pitch doc read status, dispatch→Ask Theo Brennan for plumber recommendation); slots 1/2 |
| multi-person-001 | multi_person | legacy_rules | 100 | 1 | create | duplicate_create | expected dispatch(reuse(ag_3w3vngdn); create[Theo Brennan]); got create (message_user, dispatch→Check Aaron Castillo pitch doc read status, dispatch→Email Theo Brennan for plumber recommendation); slots 1/2 |
| multi-person-001 | multi_person | legacy_rules | 100 | 2 | create | duplicate_create | expected dispatch(reuse(ag_3w3vngdn); create[Theo Brennan]); got create (message_user, dispatch→Check Aaron Castillo pitch doc read status, dispatch→Email Theo Brennan about plumber recommendation, wait); slots 1/2 |
| multi-person-001 | multi_person | legacy_rules | 300 | 0 | create | duplicate_create | expected dispatch(reuse(ag_3w3vngdn); create[Theo Brennan]); got create (message_user, dispatch→Check Aaron Castillo pitch doc status, dispatch→Email Theo Brennan asking for plumber); slots 1/2 |
| multi-person-001 | multi_person | legacy_rules | 300 | 1 | create | duplicate_create | expected dispatch(reuse(ag_3w3vngdn); create[Theo Brennan]); got create (message_user, dispatch→Check Aaron Castillo pitch doc status, dispatch→Email Theo Brennan about plumber recommendation); slots 1/2 |
| multi-person-001 | multi_person | legacy_rules | 300 | 2 | create | duplicate_create | expected dispatch(reuse(ag_3w3vngdn); create[Theo Brennan]); got create (message_user, dispatch→Check Aaron Castillo pitch doc read status, dispatch→Ask Theo Brennan for plumber recommendation); slots 1/2 |
| multi-person-001 | multi_person | hybrid | 100 | 0 | create | duplicate_create | expected dispatch(reuse(ag_3w3vngdn); create[Theo Brennan]); got create (message_user, dispatch→Check if Aaron Castillo read pitch doc, dispatch→Ask Theo Brennan for plumber recommendation); slots 1/2 |
| multi-person-003 | multi_person | legacy_rules | 10 | 2 | create | ambiguous_dispatch | expected clarify \| dispatch(create[Sam Rivera] + ask); got create (message_user, dispatch→Coffee availability Alice next week, dispatch→Coffee availability Sam Rivera next week, dispatch→Coffee availability Alice next... |
| multi-person-003 | multi_person | legacy_rules | 100 | 0 | create | ambiguous_dispatch | expected clarify \| dispatch(create[Sam Rivera] + ask); got create (message_user, dispatch→Check Alice coffee availability next week, dispatch→Check Sam Rivera coffee availability next week, dispatch→Check Alice coffee... |
| multi-person-003 | multi_person | legacy_rules | 300 | 0 | create | ambiguous_dispatch | expected clarify \| dispatch(create[Sam Rivera] + ask); got create (message_user, dispatch→Check Alice availability coffee next week, dispatch→Check Sam Rivera availability coffee next week, wait); slots 1/1 |
| multi-person-003 | multi_person | legacy_rules | 300 | 1 | create | ambiguous_dispatch | expected clarify \| dispatch(create[Sam Rivera] + ask); got create (message_user, dispatch→Check Alice availability for coffee next week, dispatch→Check Sam Rivera availability for coffee next week, wait); slots 1/1 |
| multi-person-003 | multi_person | legacy_rules | 300 | 2 | create | ambiguous_dispatch | expected clarify \| dispatch(create[Sam Rivera] + ask); got create (message_user, dispatch→Coffee availability Alice next week, dispatch→Coffee availability Sam Rivera next week); slots 1/1 |
| multi-person-003 | multi_person | full | 10 | 1 | reuse | wrong_reuse | expected clarify \| dispatch(create[Sam Rivera] + ask); got reuse (message_user, dispatch→ag_m7s4pnzj, wait); slots 0/1 |
| multi-person-004 | multi_person | legacy_rules | 300 | 1 | mixed | duplicate_create | expected dispatch(reuse(ag_g2fqxn3g); reuse(ag_zwldc5g3)); got mixed (message_user, dispatch→Email Paloma Zielinski about new hire setup, dispatch→Email Mateo the resume); slots 1/2 |
| multi-person-004 | multi_person | legacy_rules | 300 | 2 | create | duplicate_create | expected dispatch(reuse(ag_g2fqxn3g); reuse(ag_zwldc5g3)); got create (message_user, dispatch→Ping Paloma Zielinski re new hire setup, dispatch→Check Mateo Petrov reply on revised CV); slots 0/2 |
| newtask-001 | new_task_lookalike | legacy_rules | 10 | 0 | create | – | expected create; got create (message_user, dispatch→Email landlord re bedroom painting); wrong person in instructions |
| newtask-001 | new_task_lookalike | legacy_rules | 10 | 1 | create | – | expected create; got create (message_user, dispatch→Email landlord re bedroom painting, wait); wrong person in instructions |
| newtask-001 | new_task_lookalike | legacy_rules | 10 | 2 | create | – | expected create; got create (message_user, dispatch→Email landlord re bedroom painting, wait); wrong person in instructions |
| newtask-001 | new_task_lookalike | legacy_rules | 30 | 0 | create | – | expected create; got create (message_user, dispatch→Email landlord re bedroom paint, message_user); wrong person in instructions |
| newtask-001 | new_task_lookalike | legacy_rules | 30 | 1 | create | – | expected create; got create (message_user, dispatch→Email landlord re bedroom painting); wrong person in instructions |
| newtask-001 | new_task_lookalike | legacy_rules | 30 | 2 | create | – | expected create; got create (message_user, dispatch→Email landlord re bedroom painting, wait); wrong person in instructions |
| newtask-001 | new_task_lookalike | legacy_rules | 100 | 0 | create | – | expected create; got create (message_user, dispatch→Email landlord re bedroom painting); wrong person in instructions |
| newtask-001 | new_task_lookalike | legacy_rules | 100 | 1 | create | – | expected create; got create (message_user, dispatch→Email landlord re bedroom painting); wrong person in instructions |
| newtask-001 | new_task_lookalike | legacy_rules | 100 | 2 | create | – | expected create; got create (message_user, dispatch→Email landlord re painting bedroom); wrong person in instructions |
| newtask-001 | new_task_lookalike | legacy_rules | 300 | 0 | create | – | expected create; got create (message_user, dispatch→Email landlord re bedroom painting); wrong person in instructions |
| newtask-001 | new_task_lookalike | legacy_rules | 300 | 1 | create | – | expected create; got create (message_user, dispatch→Email landlord re bedroom painting); wrong person in instructions |
| newtask-001 | new_task_lookalike | legacy_rules | 300 | 2 | create | – | expected create; got create (message_user, dispatch→Email landlord re bedroom painting); wrong person in instructions |
| trigger-001 | trigger_management | legacy_rules | 30 | 0 | clarify | over_clarify | expected reuse(ag_nightly_digest); got clarify (message_user) |
| trigger-001 | trigger_management | legacy_rules | 30 | 1 | clarify | over_clarify | expected reuse(ag_nightly_digest); got clarify (message_user) |
| trigger-001 | trigger_management | legacy_rules | 30 | 2 | clarify | over_clarify | expected reuse(ag_nightly_digest); got clarify (no tool calls) |
| trigger-001 | trigger_management | legacy_rules | 100 | 1 | create | duplicate_create, trigger_duplicate | expected reuse(ag_nightly_digest); got create (message_user, dispatch→Reschedule evening email recap to 8pm) |
| trigger-001 | trigger_management | legacy_rules | 300 | 0 | clarify | over_clarify | expected reuse(ag_nightly_digest); got clarify (no tool calls) |
| trigger-001 | trigger_management | legacy_rules | 300 | 1 | clarify | over_clarify | expected reuse(ag_nightly_digest); got clarify (no tool calls) |
| trigger-001 | trigger_management | legacy_rules | 300 | 2 | clarify | over_clarify | expected reuse(ag_nightly_digest); got clarify (no tool calls) |
| trigger-001 | trigger_management | hybrid | 300 | 0 | clarify | over_clarify | expected reuse(ag_nightly_digest); got clarify (message_user, search_agents) |
| trigger-001 | trigger_management | hybrid | 300 | 1 | clarify | over_clarify | expected reuse(ag_nightly_digest); got clarify (message_user) |
| trigger-001 | trigger_management | hybrid | 300 | 2 | clarify | over_clarify | expected reuse(ag_nightly_digest); got clarify (no tool calls) |
| trigger-002 | trigger_management | legacy_rules | 100 | 1 | clarify | over_clarify | expected reuse(ag_nightly_digest); got clarify (message_user) |
| trigger-002 | trigger_management | legacy_rules | 300 | 1 | clarify | over_clarify | expected reuse(ag_nightly_digest); got clarify (message_user) |
| trigger-002 | trigger_management | legacy_rules | 300 | 2 | clarify | over_clarify | expected reuse(ag_nightly_digest); got clarify (message_user) |
| trigger-002 | trigger_management | full | 300 | 0 | clarify | over_clarify | expected reuse(ag_nightly_digest); got clarify (no tool calls) |
| trigger-004 | trigger_management | legacy_rules | 10 | 0 | invalid | – | expected reuse(ag_jjrnptml); got invalid (message_user, dispatch→Inbox zero reminder); structural: a dispatched name matches several agents |
| trigger-004 | trigger_management | legacy_rules | 10 | 1 | invalid | – | expected reuse(ag_jjrnptml); got invalid (message_user, dispatch→Inbox zero reminder, wait); structural: a dispatched name matches several agents |
| trigger-004 | trigger_management | legacy_rules | 10 | 2 | invalid | – | expected reuse(ag_jjrnptml); got invalid (message_user, dispatch→Inbox zero reminder); structural: a dispatched name matches several agents |
| trigger-004 | trigger_management | legacy_rules | 30 | 0 | create | duplicate_create, trigger_duplicate | expected reuse(ag_jjrnptml); got create (message_user, dispatch→Re-enable weekday 5pm inbox cleanup reminder) |
| trigger-004 | trigger_management | legacy_rules | 30 | 1 | invalid | – | expected reuse(ag_jjrnptml); got invalid (message_user, dispatch→Inbox zero reminder, wait); structural: a dispatched name matches several agents |
| trigger-004 | trigger_management | legacy_rules | 30 | 2 | invalid | – | expected reuse(ag_jjrnptml); got invalid (message_user, dispatch→Inbox zero reminder, wait); structural: a dispatched name matches several agents |
| trigger-004 | trigger_management | legacy_rules | 100 | 0 | create | duplicate_create, trigger_duplicate | expected reuse(ag_jjrnptml); got create (message_user, dispatch→Re-enable weekday 5pm inbox cleanup reminder) |
| trigger-004 | trigger_management | legacy_rules | 100 | 1 | invalid | – | expected reuse(ag_jjrnptml); got invalid (message_user, dispatch→Inbox zero reminder); structural: a dispatched name matches several agents |
| trigger-004 | trigger_management | legacy_rules | 100 | 2 | invalid | – | expected reuse(ag_jjrnptml); got invalid (message_user, dispatch→Inbox zero reminder, wait); structural: a dispatched name matches several agents |
| trigger-004 | trigger_management | legacy_rules | 300 | 0 | create | duplicate_create, trigger_duplicate | expected reuse(ag_jjrnptml); got create (message_user, dispatch→Re-enable weekday 5pm inbox reminder) |
| trigger-004 | trigger_management | legacy_rules | 300 | 1 | invalid | – | expected reuse(ag_jjrnptml); got invalid (message_user, dispatch→Inbox zero reminder, wait); structural: a dispatched name matches several agents |
| trigger-004 | trigger_management | legacy_rules | 300 | 2 | invalid | – | expected reuse(ag_jjrnptml); got invalid (message_user, dispatch→Inbox zero reminder); structural: a dispatched name matches several agents |

## What we learned

## What we learned

This is the final test-split run: 33 unseen cases, on the config frozen at `39a1439`. Haiku 5.5 ran the IA, the model used for every dev run. Production defaults to Sonnet 5.5; Siddharth chose Haiku to keep the company key's spend down. The grid matches the dev runs. Compared with dev: `20261109T214557Z` for `legacy_rules`/`full`, `20261110T000801Z` for `hybrid`.

- **Pass rate** (N=10/30/100/300; failures: `legacy_rules` 107, `full` 27, `hybrid` 13 of 396):

  | mode | test | dev |
  |---|---|---|
  | `legacy_rules` | 80 / 76 / 74 / 63% | 83 / 85 / 81 / 77% |
  | `full` | 94 / 93 / 93 / 93% | 100% at every N |
  | `hybrid` | 96 / 98 / 96 / 97% | 100% at every N |

- **Two cases are most of the `full`/`hybrid` gap.** In `amb-person-003` ("email Alice…") and `amb-person-005` ("email her…"), Alice Chen was discussed two exchanges back. The cases' rule is that a name or pronoun resolves only from the last exchange, so the IA must ask. `full` resolved to Alice Chen in 19/24 case-runs. Leaving out those two cases, `full` passes 98.0% and `hybrid` 98.5%: level.
  - **`hybrid`'s edge here is partly an artifact of retrieval.** In `amb-person-005` at N=300, retrieval drops both Alice cards (layer 1, `20261110T062643Z`). With no Alice to see, `hybrid` asks and passes. At N=10, where every card is shown, it fails like `full` (3/3).
  - Whether "last exchange only" is the right rule for this history is a labeling question, not a retrieval or prompt bug.
- **`hybrid`'s one retrieval failure is `trigger-001` at N=300 (0/3), as layer 1 predicted.** "Evening email recap" vs "Nightly digest" puts the target at rank 33, outside the 20 cards. In every run the IA asked which recap was meant instead of acting on a wrong agent. One run searched first, but the search did not surface the digest either. That is a safe failure (`over_clarify`).
  - Target in the initial cards: 99 / 99 / 96 / 87 of 99. Found only by search: 0 at every N.
- **Other `full` failures** were over-clarifying in `clear-person-004` and `followup-003` (6 case-runs), one wrong reuse and one over-clarify. **Other `hybrid` failures:** `clear-person-003` reused a near-miss agent at N=100 (2/3), and one duplicate create.
- **`legacy_rules` still degrades with N:** 80% → 63%, with duplicate creates rising from 2 to 9 of 99. It fails 4 cases in all 12 case-runs: broad questions and a trigger case. The cards fix these in `full` and `hybrid`.
- **Dev → test:** `full` and `hybrid` drop by 2–7 points, mostly on the two Alice cases. Without them, both stay at about 98%, so the dev fixes mostly generalize.
- **Cost:** runner 4.1160 USD against an estimate of 4.0110 (+2.6%). Billed 4.1160 (SPEND.md row 8).
