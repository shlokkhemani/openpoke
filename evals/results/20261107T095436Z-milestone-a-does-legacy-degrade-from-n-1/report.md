# Routing run: Milestone A: does legacy degrade from N=10 to N=300 (dev, Haiku)

## Setup

- **Purpose:** Milestone A: does legacy degrade from N=10 to N=300 (dev, Haiku)
- **Command:** `python -m evals.run routing --modes legacy --sizes 10,300 --split dev --runs 1 --purpose 'Milestone A: does legacy degrade from N=10 to N=300 (dev, Haiku)' --yes`
- **Date (UTC):** 2026-11-07T09:54:36Z
- **Model:** `anthropic/claude-haiku-5.5`
- **Code:** uncommitted working tree on HEAD c1bc207
- **Case set:** `evals/cases/v1` (v1), MANIFEST sha256 `eb5f510b2a88a0eea0fadce016515fab81f582c0d360da9f00096134d88be8f7`, frozen_on 2026-11-07
- **Split:** dev, 16 cases
- **Grid:** modes legacy × sizes 10, 300 × 1 run(s) = 32 case-runs (0 reused from `legacy`: recency at N ≤ 20)
- **Outcome:** 32 graded, 0 infra errors (not graded), 0 skipped by the max-cost cap ($35), 0 retried
- **Regraded:** 2026-11-07 with the current grader, without LLM calls (before: legacy N=10 38% (6/16), N=300 38% (6/16))

## Cost

- Actual: **$0.0610** (estimate before the run: $0.0376)
- Tokens: 515,052 prompt / 18,930 completion (all attempts)
- Mean latency per case-run: 4.375 s; mean round trips: 2.125

## Pass rate by mode × N

Infra errors are excluded from the denominators; structural failures count as failures.

| mode | N=10 | N=300 |
|---|---|---|
| legacy | 56% (9/16) | 44% (7/16) |

## Pass rate by category

| category | mode | N=10 | N=300 |
|---|---|---|---|
| ambiguous_person | legacy | 50% (1/2) | 50% (1/2) |
| broad_question_person | legacy | 0% (0/2) | 0% (0/2) |
| clear_person | legacy | 50% (1/2) | 50% (1/2) |
| email_followup | legacy | 100% (2/2) | 50% (1/2) |
| multi_intent | legacy | 50% (1/2) | 50% (1/2) |
| multi_person | legacy | 50% (1/2) | 0% (0/2) |
| new_task_lookalike | legacy | 100% (2/2) | 100% (2/2) |
| trigger_management | legacy | 50% (1/2) | 50% (1/2) |

## Flags

| flag | mode | N=10 | N=300 |
|---|---|---|---|
| ambiguous_dispatch | legacy | 1/16 | 1/16 |
| duplicate_create | legacy | 2/16 | 4/16 |
| trigger_duplicate | legacy | 1/16 | 1/16 |
| wrong_reuse | legacy | 2/16 | 0/16 |

## Structural failures

A legacy dispatch by a name that several agents share (e.g. two "Email Alice" agents): the names-only roster cannot express the right target.

| mode | N=10 | N=300 |
|---|---|---|
| legacy | 0 | 0 |

## Infra errors

Retried once; a case-run whose retry also failed is listed in `errors.jsonl` and not graded. Counts are paid case-runs; a reused recency copy of an errored `legacy` case-run is not counted again.

| mode | N=10 | N=300 |
|---|---|---|
| legacy | 0 | 0 |

## Failing case-runs

| case | category | mode | N | run | outcome | flags | reason |
|---|---|---|---|---|---|---|---|
| amb-person-006 | ambiguous_person | legacy | 10 | 0 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Find emails from Daniel about conference schedule) |
| amb-person-006 | ambiguous_person | legacy | 300 | 0 | create | – | expected clarify; got create (message_user, dispatch→Check Daniel reply) |
| broad-person-005 | broad_question_person | legacy | 10 | 0 | create | – | expected answer_set([ag_6qcrp7gd, ag_ivh5ynui, ag_msz3aew4, ag_jjm6nfqy, ag_qodxxymf]); got create (message_user, dispatch→Imani latest updates, wait) |
| broad-person-005 | broad_question_person | legacy | 300 | 0 | create | – | expected answer_set([ag_6qcrp7gd, ag_ivh5ynui, ag_msz3aew4, ag_jjm6nfqy, ag_qodxxymf]); got create (message_user, dispatch→Imani latest updates) |
| broad-person-006 | broad_question_person | legacy | 10 | 0 | create | – | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got create (message_user, dispatch→Helena Rossi open items, wait) |
| broad-person-006 | broad_question_person | legacy | 300 | 0 | create | – | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got create (message_user, dispatch→Open items with Helena Rossi) |
| clear-person-005 | clear_person | legacy | 10 | 0 | create | duplicate_create | expected reuse(ag_avdgfagy); got create (message_user, dispatch→Farah Moreau interview write-up search) |
| clear-person-005 | clear_person | legacy | 300 | 0 | create | duplicate_create | expected reuse(ag_avdgfagy); got create (message_user, dispatch→Search Farah Moreau interview write-up) |
| followup-005 | email_followup | legacy | 300 | 0 | create | duplicate_create | expected reuse(ag_4vdh7oh4); got create (message_user, dispatch→Find emails from Amara about party plans) |
| multi-intent-005 | multi_intent | legacy | 10 | 0 | mixed | wrong_reuse | expected dispatch(create[Jamal Kowalski]; create); got mixed (message_user, dispatch→Find emails from Jamal about quarterly report, dispatch→Friday lunch table reminder, wait); slots 1/2 |
| multi-intent-006 | multi_intent | legacy | 300 | 0 | create | duplicate_create, trigger_duplicate | expected dispatch(create[Greta Silva]; reuse(ag_wyehdpnc)); got create (message_user, dispatch→Email Greta bike pump request, dispatch→Bike tune-up reminder reschedule); slots 1/2 |
| multi-person-005 | multi_person | legacy | 300 | 0 | create | duplicate_create | expected dispatch(reuse(ag_3syqqzg7); create[Amara Abara]); got create (message_user, dispatch→Liam Bianchi billing dispute update, dispatch→Email Amara Abara about hairdresser); slots 1/2 |
| multi-person-006 | multi_person | legacy | 10 | 0 | create | ambiguous_dispatch | expected clarify \| dispatch(create[Alice Chen] + ask); got create (message_user, dispatch→Running club invite Sam and Alice Chen); slots 1/1 |
| multi-person-006 | multi_person | legacy | 300 | 0 | create | ambiguous_dispatch | expected clarify \| dispatch(create[Alice Chen] + ask); got create (message_user, dispatch→Running club invite Sam and Alice); slots 1/1 |
| trigger-006 | trigger_management | legacy | 10 | 0 | create | duplicate_create, trigger_duplicate | expected reuse(ag_ohyhhbka); got create (dispatch→Reminder scheduler, message_user, wait) |
| trigger-006 | trigger_management | legacy | 300 | 0 | none | – | expected reuse(ag_ohyhhbka); got none (no tool calls) |

## What we learned

*Regraded on 2026-11-07 with the current grader (`python -m evals.run regrade`; see `evals/results/changes.md`); previous files kept as `*.v1.*`. Before: legacy N=10 38% (6/16), N=300 38% (6/16). After: legacy N=10 56% (9/16), N=300 44% (7/16). Notes below this line were written against the earlier grading.*

*Written by the controller after reading the failures and transcripts.*

- **Headline as graded: no degradation, 38% (6/16) at both N=10 and N=300.** Per the plan, this is reported to Siddharth before going further.
- **4 of the 20 failing case-runs are grader false negatives, not routing mistakes.** In amb-person-007@10, followup-005@10 and followup-006@10/@300 the IA reused the **correct** agent by its exact name, but its instructions named the person by first name only ("Farah", "Amara", "Theo"). The `reuse` + `expect_person` rule (plan Task 3) requires the full name or email in the instructions. For a reuse that's unnecessary: the reused agent already holds the thread and the address. This is the same reasoning as ruling R23 for multi-dispatch slots. Corrected, the scores would be **56% (9/16) at N=10 vs 44% (7/16) at N=300**.
- **Broad questions fail at every N (0/4):** with names only, the IA can't tell which agents involve Imani or Helena, so it creates a new search agent. That's a real `legacy` weakness, but it doesn't depend on roster size.
- **Signs of a scale effect:** duplicate creates go from 2/16 to 4/16. followup-005 reuses the right agent at N=10 but creates a duplicate at N=300. trigger-006 at N=300 asks "which ones?" instead of acting on the reminder from the last exchange.
- **The sample is small:** 16 dev cases, 1 run, Haiku. One case flipping moves a cell by 6 points.
- **The cost estimate is too low:** actual $0.0610 vs estimated $0.0376 (1.6×). Measured per case-run (legacy): **N=10 ≈ 11.9k prompt tokens / 2.3 round trips; N=300 ≈ 20.3k / 1.9**, vs 6.7k / 13.6k estimated. Completions were ~590 tokens vs 320. The char/4 token estimate undercounts, and turns take more than 2 calls. If the same ratio holds, the final Sonnet run would cost ~$45–50, not ~$29. The budget plan needs recalibrating from measured tokens before the final run.
