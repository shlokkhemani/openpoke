# Routing run: Task 14 smoke: legacy/full/hybrid on the real code path, dev, N=10/30 (Haiku)

## Setup

- **Purpose:** Task 14 smoke: legacy/full/hybrid on the real code path, dev, N=10/30 (Haiku)
- **Command:** `python -m evals.run routing --modes legacy,full,hybrid --sizes 10,30 --split dev --runs 1 --embedder fastembed --max-cost 1 --purpose 'Task 14 smoke: legacy/full/hybrid on the real code path, dev, N=10/30 (Haiku)' --yes`
- **Date (UTC):** 2026-11-09T19:48:41Z
- **Model:** `anthropic/claude-haiku-5.5`
- **Code:** uncommitted working tree on HEAD 2e9a0bd
- **Case set:** `evals/cases/v1` (v1), MANIFEST sha256 `688388e57eb5980fa06046a7e384b5449d9b1c71134c817bbf7d20d166fbcbda`, frozen_on 2026-11-07
- **Split:** dev, 16 cases
- **Descriptions (`full`):** regen, sha256 `5d4d6d7c5b20fa1c53c69d280e122d27804833e7dd04ac623bf1e8e1c93ec232`, covering 310/310 world agents
- **Grid:** modes legacy, full, hybrid × sizes 10, 30 × 1 run(s) = 96 case-runs
- **Outcome:** 96 graded, 0 infra errors (not graded), 0 skipped by the max-cost cap ($1), 0 retried

## Cost

- Actual: **$0.2013** (estimate before the run: $0.2313)
- Tokens: 1,702,856 prompt / 61,960 completion (all attempts)
- Mean latency per case-run: 4.691 s; mean round trips: 2.26

## Pass rate by mode × N

Infra errors are excluded from the denominators; structural failures count as failures.

| mode | N=10 | N=30 |
|---|---|---|
| legacy | 50% (8/16) | 62% (10/16) |
| full | 100% (16/16) | 100% (16/16) |
| hybrid | 100% (16/16) | 100% (16/16) |

## Pass rate by category

| category | mode | N=10 | N=30 |
|---|---|---|---|
| ambiguous_person | legacy | 50% (1/2) | 50% (1/2) |
| ambiguous_person | full | 100% (2/2) | 100% (2/2) |
| ambiguous_person | hybrid | 100% (2/2) | 100% (2/2) |
| broad_question_person | legacy | 0% (0/2) | 0% (0/2) |
| broad_question_person | full | 100% (2/2) | 100% (2/2) |
| broad_question_person | hybrid | 100% (2/2) | 100% (2/2) |
| clear_person | legacy | 50% (1/2) | 50% (1/2) |
| clear_person | full | 100% (2/2) | 100% (2/2) |
| clear_person | hybrid | 100% (2/2) | 100% (2/2) |
| email_followup | legacy | 100% (2/2) | 100% (2/2) |
| email_followup | full | 100% (2/2) | 100% (2/2) |
| email_followup | hybrid | 100% (2/2) | 100% (2/2) |
| multi_intent | legacy | 0% (0/2) | 100% (2/2) |
| multi_intent | full | 100% (2/2) | 100% (2/2) |
| multi_intent | hybrid | 100% (2/2) | 100% (2/2) |
| multi_person | legacy | 0% (0/2) | 0% (0/2) |
| multi_person | full | 100% (2/2) | 100% (2/2) |
| multi_person | hybrid | 100% (2/2) | 100% (2/2) |
| new_task_lookalike | legacy | 100% (2/2) | 100% (2/2) |
| new_task_lookalike | full | 100% (2/2) | 100% (2/2) |
| new_task_lookalike | hybrid | 100% (2/2) | 100% (2/2) |
| trigger_management | legacy | 100% (2/2) | 100% (2/2) |
| trigger_management | full | 100% (2/2) | 100% (2/2) |
| trigger_management | hybrid | 100% (2/2) | 100% (2/2) |

## Flags

| flag | mode | N=10 | N=30 |
|---|---|---|---|
| ambiguous_dispatch | legacy | 1/16 | 1/16 |
| ambiguous_dispatch | full | 0/16 | 0/16 |
| ambiguous_dispatch | hybrid | 0/16 | 0/16 |
| duplicate_create | legacy | 2/16 | 2/16 |
| duplicate_create | full | 0/16 | 0/16 |
| duplicate_create | hybrid | 0/16 | 0/16 |
| wrong_reuse | legacy | 3/16 | 1/16 |
| wrong_reuse | full | 0/16 | 0/16 |
| wrong_reuse | hybrid | 0/16 | 0/16 |

## Search

Embedder: `fastembed`. The target is the graded case's expected agents (`retrieval_eval.expected_for`); cases without one count in neither target row.

| mode | measure | N=10 | N=30 |
|---|---|---|---|
| hybrid | Search rate (case-runs that searched) | 0/16 | 1/16 |
| hybrid | Search errors (calls) | 0 | 0 |
| hybrid | Target in the initial cards | 16/16 | 16/16 |
| hybrid | Target found only by search | 0/16 | 0/16 |

## Structural failures

A legacy dispatch by a name that several agents share (e.g. two "Email Alice" agents): the names-only roster cannot express the right target.

| mode | N=10 | N=30 |
|---|---|---|
| legacy | 0 | 0 |
| full | 0 | 0 |
| hybrid | 0 | 0 |

## Infra errors

Retried once; a case-run whose retry also failed is listed in `errors.jsonl` and not graded. Counts are case-runs.

| mode | N=10 | N=30 |
|---|---|---|
| legacy | 0 | 0 |
| full | 0 | 0 |
| hybrid | 0 | 0 |

## Failing case-runs

| case | category | mode | N | run | outcome | flags | reason |
|---|---|---|---|---|---|---|---|
| amb-person-006 | ambiguous_person | legacy | 10 | 0 | reuse | wrong_reuse | expected clarify; got reuse (dispatch→Find emails from Daniel about conference schedule, dispatch→Email Daniel about lab results, dispatch→Send Daniel the signed NDA, message_user) |
| amb-person-006 | ambiguous_person | legacy | 30 | 0 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Find emails from Daniel about conference schedule) |
| broad-person-005 | broad_question_person | legacy | 10 | 0 | reuse | – | expected answer_set([ag_6qcrp7gd, ag_ivh5ynui, ag_msz3aew4, ag_jjm6nfqy, ag_qodxxymf]); got reuse (message_user, dispatch→Find emails from Imani about new pricing) |
| broad-person-005 | broad_question_person | legacy | 30 | 0 | reuse | – | expected answer_set([ag_6qcrp7gd, ag_ivh5ynui, ag_msz3aew4, ag_jjm6nfqy, ag_qodxxymf]); got reuse (message_user, dispatch→Find emails from Imani about new pricing) |
| broad-person-006 | broad_question_person | legacy | 10 | 0 | create | – | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got create (message_user, dispatch→Helena Rossi Open Items) |
| broad-person-006 | broad_question_person | legacy | 30 | 0 | create | – | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got create (message_user, dispatch→Open items with Helena Rossi, wait) |
| clear-person-005 | clear_person | legacy | 10 | 0 | create | duplicate_create | expected reuse(ag_avdgfagy); got create (message_user, dispatch→Search Farah interview write-up) |
| clear-person-005 | clear_person | legacy | 30 | 0 | create | duplicate_create | expected reuse(ag_avdgfagy); got create (message_user, dispatch→Search Farah interview write-up) |
| multi-intent-005 | multi_intent | legacy | 10 | 0 | mixed | wrong_reuse | expected dispatch(create[Jamal Kowalski]; create); got mixed (message_user, dispatch→Friday lunch reminder 12:30pm, dispatch→Find emails from Jamal about quarterly report); slots 1/2 |
| multi-intent-006 | multi_intent | legacy | 10 | 0 | reuse | wrong_reuse | expected dispatch(create[Greta Silva]; reuse(ag_wyehdpnc)); got reuse (message_user, dispatch→Email Greta re budget approval, dispatch→Bike service reminder, wait); slots 1/2 |
| multi-person-005 | multi_person | legacy | 10 | 0 | create | duplicate_create | expected dispatch(reuse(ag_3syqqzg7); create[Amara Abara]); got create (message_user, dispatch→Liam Bianchi billing dispute update, dispatch→Draft email to Amara Abara hairdresser); slots 1/2 |
| multi-person-005 | multi_person | legacy | 30 | 0 | create | duplicate_create | expected dispatch(reuse(ag_3syqqzg7); create[Amara Abara]); got create (message_user, dispatch→Liam Bianchi billing dispute update, dispatch→Email Amara Abara about hairdresser); slots 1/2 |
| multi-person-006 | multi_person | legacy | 10 | 0 | create | ambiguous_dispatch | expected clarify \| dispatch(create[Alice Chen] + ask); got create (message_user, dispatch→Running club invite Sam and Alice Chen); slots 1/1 |
| multi-person-006 | multi_person | legacy | 30 | 0 | create | ambiguous_dispatch | expected clarify \| dispatch(create[Alice Chen] + ask); got create (message_user, dispatch→Running club invite to Sam and Alice Chen); slots 1/1 |

## What we learned

- **The plumbing works on a real model.** `hybrid` ran end to end through production `build_turn_inputs` with real
  fastembed retrieval: 96/96 case-runs graded, 0 infra errors, 0 structural failures, 0 search errors.
- **Pass rates.** `full` and `hybrid` are both 100% at N=10 and N=30 (16/16 each). `legacy` is 50% / 62%, failing
  where names alone can't separate agents (wrong_reuse, duplicate_create, broad questions about a person).
- **Search is rarely used at these sizes.** At N=10 every agent is shown, so there is nothing to search (0/16). At
  N=30, 1/16 case-runs searched (newtask-006, query "daily 8am reminder to back up phone photos"; a new task, so
  creating was correct either way). The graded target was in the initial cards 16/16 at both sizes; nothing was
  found only by search. This smoke does not test the history-pull gap from Task 12c. That needs N > 20 with
  paraphrased or history-dependent requests (Task 15).
- **Measured prompt tokens per case-run** (mean over 16, all attempts) against the runner's estimate:

  | mode | N=10 measured / est. | N=30 measured / est. |
  |---|---|---|
  | legacy | 11,869 / 11,900 | 12,669 / 12,479 |
  | full | 16,970 / 18,009 | 24,634 / 24,936 |
  | hybrid | 18,096 / 27,014 | 22,191 / 32,208 |

  The ×1.5 hybrid factor over-estimates by about 1.45× because search was almost never called. Measured hybrid is
  about 1.07× `full` at min(N, 20). For Task 15, use about 1.1 × full@min(N, 20) as hybrid's estimate, and keep the
  `--max-cost` margin.
- **Cost.** Runner $0.2013, billed $0.2013 (estimate $0.2313).
