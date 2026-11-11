# Routing run: Experiment 2: legacy scaling curve on dev, 4 sizes x 3 runs (Haiku)

## Setup

- **Purpose:** Experiment 2: legacy scaling curve on dev, 4 sizes x 3 runs (Haiku)
- **Command:** `python -m evals.run routing --modes legacy --sizes 10,30,100,300 --split dev --runs 3 --purpose 'Experiment 2: legacy scaling curve on dev, 4 sizes x 3 runs (Haiku)' --yes`
- **Date (UTC):** 2026-11-07T10:12:32Z
- **Model:** `anthropic/claude-haiku-5.5`
- **Code:** uncommitted working tree on HEAD c1bc207
- **Case set:** `evals/cases/v1` (v1), MANIFEST sha256 `eb5f510b2a88a0eea0fadce016515fab81f582c0d360da9f00096134d88be8f7`, frozen_on 2026-11-07
- **Split:** dev, 16 cases
- **Grid:** modes legacy × sizes 10, 30, 100, 300 × 3 run(s) = 192 case-runs (0 reused from `legacy`: recency at N ≤ 20)
- **Outcome:** 192 graded, 0 infra errors (not graded), 0 skipped by the max-cost cap ($35), 0 retried

## Cost

- Actual: **$0.3498** (estimate before the run: $0.3417)
- Tokens: 2,925,752 prompt / 114,470 completion (all attempts)
- Mean latency per case-run: 4.223 s; mean round trips: 2.177

## Pass rate by mode × N

Infra errors are excluded from the denominators; structural failures count as failures.

| mode | N=10 | N=30 | N=100 | N=300 |
|---|---|---|---|---|
| legacy | 62% (30/48) | 54% (26/48) | 54% (26/48) | 40% (19/48) |

## Pass rate by category

| category | mode | N=10 | N=30 | N=100 | N=300 |
|---|---|---|---|---|---|
| ambiguous_person | legacy | 50% (3/6) | 50% (3/6) | 50% (3/6) | 50% (3/6) |
| broad_question_person | legacy | 0% (0/6) | 0% (0/6) | 0% (0/6) | 0% (0/6) |
| clear_person | legacy | 67% (4/6) | 50% (3/6) | 50% (3/6) | 50% (3/6) |
| email_followup | legacy | 100% (6/6) | 100% (6/6) | 100% (6/6) | 33% (2/6) |
| multi_intent | legacy | 83% (5/6) | 83% (5/6) | 83% (5/6) | 67% (4/6) |
| multi_person | legacy | 50% (3/6) | 0% (0/6) | 0% (0/6) | 0% (0/6) |
| new_task_lookalike | legacy | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |
| trigger_management | legacy | 50% (3/6) | 50% (3/6) | 50% (3/6) | 17% (1/6) |

## Flags

| flag | mode | N=10 | N=30 | N=100 | N=300 |
|---|---|---|---|---|---|
| ambiguous_dispatch | legacy | 3/48 | 3/48 | 3/48 | 3/48 |
| duplicate_create | legacy | 0/48 | 9/48 | 6/48 | 13/48 |
| merged_intents | legacy | 1/48 | 1/48 | 1/48 | 1/48 |
| over_clarify | legacy | 0/48 | 0/48 | 0/48 | 1/48 |
| trigger_duplicate | legacy | 0/48 | 3/48 | 0/48 | 3/48 |
| wrong_reuse | legacy | 8/48 | 3/48 | 3/48 | 0/48 |

## Structural failures

A legacy dispatch by a name that several agents share (e.g. two "Email Alice" agents): the names-only roster cannot express the right target.

| mode | N=10 | N=30 | N=100 | N=300 |
|---|---|---|---|---|
| legacy | 0 | 0 | 0 | 0 |

## Infra errors

Retried once; a case-run whose retry also failed is listed in `errors.jsonl` and not graded. Counts are paid case-runs; a reused recency copy of an errored `legacy` case-run is not counted again.

| mode | N=10 | N=30 | N=100 | N=300 |
|---|---|---|---|---|
| legacy | 0 | 0 | 0 | 0 |

## Failing case-runs

| case | category | mode | N | run | outcome | flags | reason |
|---|---|---|---|---|---|---|---|
| amb-person-006 | ambiguous_person | legacy | 10 | 0 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Find emails from Daniel about conference schedule) |
| amb-person-006 | ambiguous_person | legacy | 10 | 1 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Find emails from Daniel about conference schedule) |
| amb-person-006 | ambiguous_person | legacy | 10 | 2 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Email Daniel about lab results, wait) |
| amb-person-006 | ambiguous_person | legacy | 30 | 0 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Find emails from Daniel about conference schedule) |
| amb-person-006 | ambiguous_person | legacy | 30 | 1 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Find emails from Daniel about conference schedule) |
| amb-person-006 | ambiguous_person | legacy | 30 | 2 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Find emails from Daniel about conference schedule, wait) |
| amb-person-006 | ambiguous_person | legacy | 100 | 0 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Find emails from Daniel about conference schedule) |
| amb-person-006 | ambiguous_person | legacy | 100 | 1 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Find emails from Daniel about conference schedule, wait) |
| amb-person-006 | ambiguous_person | legacy | 100 | 2 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Find emails from Daniel about conference schedule) |
| amb-person-006 | ambiguous_person | legacy | 300 | 0 | create | – | expected clarify; got create (message_user, dispatch→Check Daniel reply) |
| amb-person-006 | ambiguous_person | legacy | 300 | 1 | create | – | expected clarify; got create (message_user, dispatch→Check for reply from Daniel) |
| amb-person-006 | ambiguous_person | legacy | 300 | 2 | create | – | expected clarify; got create (message_user, dispatch→Check Daniel replies) |
| broad-person-005 | broad_question_person | legacy | 10 | 0 | reuse | – | expected answer_set([ag_6qcrp7gd, ag_ivh5ynui, ag_msz3aew4, ag_jjm6nfqy, ag_qodxxymf]); got reuse (message_user, dispatch→Find emails from Imani about new pricing) |
| broad-person-005 | broad_question_person | legacy | 10 | 1 | reuse | – | expected answer_set([ag_6qcrp7gd, ag_ivh5ynui, ag_msz3aew4, ag_jjm6nfqy, ag_qodxxymf]); got reuse (message_user, dispatch→Find emails from Imani about new pricing) |
| broad-person-005 | broad_question_person | legacy | 10 | 2 | reuse | – | expected answer_set([ag_6qcrp7gd, ag_ivh5ynui, ag_msz3aew4, ag_jjm6nfqy, ag_qodxxymf]); got reuse (message_user, dispatch→Find emails from Imani about new pricing, dispatch→Email Imani about Q4 roadmap, wait) |
| broad-person-005 | broad_question_person | legacy | 30 | 0 | create | – | expected answer_set([ag_6qcrp7gd, ag_ivh5ynui, ag_msz3aew4, ag_jjm6nfqy, ag_qodxxymf]); got create (message_user, dispatch→Imani latest updates) |
| broad-person-005 | broad_question_person | legacy | 30 | 1 | create | – | expected answer_set([ag_6qcrp7gd, ag_ivh5ynui, ag_msz3aew4, ag_jjm6nfqy, ag_qodxxymf]); got create (message_user, dispatch→Imani latest updates) |
| broad-person-005 | broad_question_person | legacy | 30 | 2 | create | – | expected answer_set([ag_6qcrp7gd, ag_ivh5ynui, ag_msz3aew4, ag_jjm6nfqy, ag_qodxxymf]); got create (message_user, dispatch→Imani latest updates) |
| broad-person-005 | broad_question_person | legacy | 100 | 0 | create | – | expected answer_set([ag_6qcrp7gd, ag_ivh5ynui, ag_msz3aew4, ag_jjm6nfqy, ag_qodxxymf]); got create (message_user, dispatch→Imani latest updates) |
| broad-person-005 | broad_question_person | legacy | 100 | 1 | create | – | expected answer_set([ag_6qcrp7gd, ag_ivh5ynui, ag_msz3aew4, ag_jjm6nfqy, ag_qodxxymf]); got create (message_user, dispatch→Recent emails from Imani, wait) |
| broad-person-005 | broad_question_person | legacy | 100 | 2 | create | – | expected answer_set([ag_6qcrp7gd, ag_ivh5ynui, ag_msz3aew4, ag_jjm6nfqy, ag_qodxxymf]); got create (message_user, dispatch→Check Imani updates) |
| broad-person-005 | broad_question_person | legacy | 300 | 0 | reuse | – | expected answer_set([ag_6qcrp7gd, ag_ivh5ynui, ag_msz3aew4, ag_jjm6nfqy, ag_qodxxymf]); got reuse (message_user, dispatch→Find emails from Imani about new pricing) |
| broad-person-005 | broad_question_person | legacy | 300 | 1 | create | – | expected answer_set([ag_6qcrp7gd, ag_ivh5ynui, ag_msz3aew4, ag_jjm6nfqy, ag_qodxxymf]); got create (message_user, dispatch→Imani recent updates, wait) |
| broad-person-005 | broad_question_person | legacy | 300 | 2 | create | – | expected answer_set([ag_6qcrp7gd, ag_ivh5ynui, ag_msz3aew4, ag_jjm6nfqy, ag_qodxxymf]); got create (message_user, dispatch→Imani latest updates) |
| broad-person-006 | broad_question_person | legacy | 10 | 0 | create | – | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got create (message_user, dispatch→Helena Rossi Open Items) |
| broad-person-006 | broad_question_person | legacy | 10 | 1 | create | – | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got create (message_user, dispatch→Helena Rossi Open Items) |
| broad-person-006 | broad_question_person | legacy | 10 | 2 | create | – | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got create (dispatch→Helena Rossi open items, message_user) |
| broad-person-006 | broad_question_person | legacy | 30 | 0 | create | – | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got create (message_user, dispatch→Helena Rossi open items) |
| broad-person-006 | broad_question_person | legacy | 30 | 1 | create | – | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got create (message_user, dispatch→Helena Rossi open items check) |
| broad-person-006 | broad_question_person | legacy | 30 | 2 | create | – | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got create (message_user, dispatch→Helena Rossi open items) |
| broad-person-006 | broad_question_person | legacy | 100 | 0 | create | – | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got create (message_user, dispatch→Helena Rossi open items) |
| broad-person-006 | broad_question_person | legacy | 100 | 1 | create | – | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got create (message_user, dispatch→Helena Rossi open items) |
| broad-person-006 | broad_question_person | legacy | 100 | 2 | create | – | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got create (message_user, dispatch→Helena Rossi open items, wait) |
| broad-person-006 | broad_question_person | legacy | 300 | 0 | create | – | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got create (message_user, dispatch→Helena Rossi open items check) |
| broad-person-006 | broad_question_person | legacy | 300 | 1 | create | – | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got create (dispatch→Helena Rossi open items, message_user) |
| broad-person-006 | broad_question_person | legacy | 300 | 2 | create | – | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got create (message_user, dispatch→Helena Rossi open items check) |
| clear-person-005 | clear_person | legacy | 10 | 0 | reuse | wrong_reuse | expected reuse(ag_avdgfagy); got reuse (message_user, dispatch→Email Farah re offer letter) |
| clear-person-005 | clear_person | legacy | 10 | 2 | reuse | wrong_reuse | expected reuse(ag_avdgfagy); got reuse (message_user, dispatch→Email Farah re offer letter) |
| clear-person-005 | clear_person | legacy | 30 | 0 | create | duplicate_create | expected reuse(ag_avdgfagy); got create (message_user, dispatch→Search Farah Moreau interview write-up) |
| clear-person-005 | clear_person | legacy | 30 | 1 | create | duplicate_create | expected reuse(ag_avdgfagy); got create (message_user, dispatch→Search Farah Moreau interview write-up) |
| clear-person-005 | clear_person | legacy | 30 | 2 | create | duplicate_create | expected reuse(ag_avdgfagy); got create (message_user, dispatch→Search Farah Moreau interview write-up) |
| clear-person-005 | clear_person | legacy | 100 | 0 | create | duplicate_create | expected reuse(ag_avdgfagy); got create (message_user, dispatch→Find emails from Farah Moreau about interview write-up) |
| clear-person-005 | clear_person | legacy | 100 | 1 | create | duplicate_create | expected reuse(ag_avdgfagy); got create (message_user, dispatch→Find emails from Farah about interview write-up) |
| clear-person-005 | clear_person | legacy | 100 | 2 | create | duplicate_create | expected reuse(ag_avdgfagy); got create (message_user, dispatch→Find emails from Farah Moreau about interview write-up) |
| clear-person-005 | clear_person | legacy | 300 | 0 | create | duplicate_create | expected reuse(ag_avdgfagy); got create (message_user, dispatch→Farah Moreau interview write-up search) |
| clear-person-005 | clear_person | legacy | 300 | 1 | create | duplicate_create | expected reuse(ag_avdgfagy); got create (message_user, dispatch→Find emails from Farah about interview write-up) |
| clear-person-005 | clear_person | legacy | 300 | 2 | create | duplicate_create | expected reuse(ag_avdgfagy); got create (message_user, dispatch→Find emails from Farah Moreau about interview write-up, wait) |
| followup-005 | email_followup | legacy | 300 | 0 | create | duplicate_create | expected reuse(ag_4vdh7oh4); got create (message_user, dispatch→Find emails from Amara about party plans) |
| followup-005 | email_followup | legacy | 300 | 1 | create | duplicate_create | expected reuse(ag_4vdh7oh4); got create (message_user, dispatch→Find new emails from Amara about party plans) |
| followup-005 | email_followup | legacy | 300 | 2 | create | duplicate_create | expected reuse(ag_4vdh7oh4); got create (message_user, dispatch→Find new emails from Amara about party plans) |
| followup-006 | email_followup | legacy | 300 | 2 | create | duplicate_create | expected reuse(ag_m7zywmxw); got create (message_user, dispatch→Theo deadline extension reply check) |
| multi-intent-005 | multi_intent | legacy | 10 | 1 | create | merged_intents | expected dispatch(create[Jamal Kowalski]; create); got create (message_user, dispatch→Jamal lunch note and reminder); slots 1/2 |
| multi-intent-005 | multi_intent | legacy | 30 | 1 | create | merged_intents | expected dispatch(create[Jamal Kowalski]; create); got create (message_user, dispatch→Email Jamal lunch time change); slots 1/2 |
| multi-intent-005 | multi_intent | legacy | 100 | 2 | create | merged_intents | expected dispatch(create[Jamal Kowalski]; create); got create (message_user, dispatch→Jamal team lunch update, wait); slots 1/2 |
| multi-intent-005 | multi_intent | legacy | 300 | 1 | create | merged_intents | expected dispatch(create[Jamal Kowalski]; create); got create (message_user, dispatch→Jamal team lunch update, wait); slots 1/2 |
| multi-intent-006 | multi_intent | legacy | 300 | 1 | create | duplicate_create, trigger_duplicate | expected dispatch(create[Greta Silva]; reuse(ag_wyehdpnc)); got create (message_user, dispatch→Email Greta Silva bike pump, dispatch→Bike tune-up reminder to 8pm); slots 1/2 |
| multi-person-005 | multi_person | legacy | 30 | 0 | create | duplicate_create | expected dispatch(reuse(ag_3syqqzg7); create[Amara Abara]); got create (message_user, dispatch→Liam Bianchi billing dispute update, dispatch→Email Amara Abara hairdresser); slots 1/2 |
| multi-person-005 | multi_person | legacy | 30 | 1 | create | duplicate_create | expected dispatch(reuse(ag_3syqqzg7); create[Amara Abara]); got create (message_user, dispatch→Liam Bianchi billing dispute update, dispatch→Draft email to Amara Abara hairdresser); slots 1/2 |
| multi-person-005 | multi_person | legacy | 30 | 2 | create | duplicate_create | expected dispatch(reuse(ag_3syqqzg7); create[Amara Abara]); got create (message_user, dispatch→Liam Bianchi billing dispute update, dispatch→Email Amara Abara hairdresser question); slots 1/2 |
| multi-person-005 | multi_person | legacy | 100 | 0 | create | duplicate_create | expected dispatch(reuse(ag_3syqqzg7); create[Amara Abara]); got create (message_user, dispatch→Liam Bianchi billing dispute update, dispatch→Draft email to Amara Abara hairdresser); slots 1/2 |
| multi-person-005 | multi_person | legacy | 100 | 1 | create | duplicate_create | expected dispatch(reuse(ag_3syqqzg7); create[Amara Abara]); got create (message_user, dispatch→Liam Bianchi billing dispute update, dispatch→Draft email to Amara Abara hairdresser); slots 1/2 |
| multi-person-005 | multi_person | legacy | 100 | 2 | create | duplicate_create | expected dispatch(reuse(ag_3syqqzg7); create[Amara Abara]); got create (dispatch→Liam Bianchi billing dispute update, dispatch→Email Amara Abara about hairdresser, message_user); slots 1/2 |
| multi-person-005 | multi_person | legacy | 300 | 0 | create | duplicate_create | expected dispatch(reuse(ag_3syqqzg7); create[Amara Abara]); got create (message_user, dispatch→Liam Bianchi billing dispute update, dispatch→Email Amara Abara hairdresser question); slots 1/2 |
| multi-person-005 | multi_person | legacy | 300 | 1 | create | duplicate_create | expected dispatch(reuse(ag_3syqqzg7); create[Amara Abara]); got create (message_user, dispatch→Liam Bianchi billing dispute update, dispatch→Email Amara Abara hairdresser); slots 1/2 |
| multi-person-005 | multi_person | legacy | 300 | 2 | create | duplicate_create | expected dispatch(reuse(ag_3syqqzg7); create[Amara Abara]); got create (message_user, dispatch→Liam Bianchi billing dispute update, dispatch→Email Amara Abara about hairdresser, wait); slots 1/2 |
| multi-person-006 | multi_person | legacy | 10 | 0 | create | ambiguous_dispatch | expected clarify \| dispatch(create[Alice Chen] + ask); got create (message_user, dispatch→Draft Running Club Invite Sam and Alice Chen); slots 1/1 |
| multi-person-006 | multi_person | legacy | 10 | 1 | create | ambiguous_dispatch | expected clarify \| dispatch(create[Alice Chen] + ask); got create (message_user, dispatch→Email Sam and Alice Chen re running club); slots 1/1 |
| multi-person-006 | multi_person | legacy | 10 | 2 | create | ambiguous_dispatch | expected clarify \| dispatch(create[Alice Chen] + ask); got create (message_user, dispatch→Email Sam and Alice Chen about Sunday running club); slots 1/1 |
| multi-person-006 | multi_person | legacy | 30 | 0 | create | ambiguous_dispatch | expected clarify \| dispatch(create[Alice Chen] + ask); got create (message_user, dispatch→Running club invite to Sam and Alice Chen); slots 1/1 |
| multi-person-006 | multi_person | legacy | 30 | 1 | create | ambiguous_dispatch | expected clarify \| dispatch(create[Alice Chen] + ask); got create (message_user, dispatch→Draft running club invite to Sam, dispatch→Draft running club invite to Alice Chen); slots 1/1 |
| multi-person-006 | multi_person | legacy | 30 | 2 | create | ambiguous_dispatch | expected clarify \| dispatch(create[Alice Chen] + ask); got create (message_user, dispatch→Running club invite drafts); slots 1/1 |
| multi-person-006 | multi_person | legacy | 100 | 0 | create | ambiguous_dispatch | expected clarify \| dispatch(create[Alice Chen] + ask); got create (message_user, dispatch→Running club invite Sam and Alice Chen); slots 1/1 |
| multi-person-006 | multi_person | legacy | 100 | 1 | create | ambiguous_dispatch | expected clarify \| dispatch(create[Alice Chen] + ask); got create (message_user, dispatch→Running club invite to Sam and Alice Chen); slots 1/1 |
| multi-person-006 | multi_person | legacy | 100 | 2 | create | ambiguous_dispatch | expected clarify \| dispatch(create[Alice Chen] + ask); got create (message_user, dispatch→Running club invite draft); slots 1/1 |
| multi-person-006 | multi_person | legacy | 300 | 0 | create | ambiguous_dispatch | expected clarify \| dispatch(create[Alice Chen] + ask); got create (message_user, dispatch→Running club invite to Sam and Alice Chen); slots 1/1 |
| multi-person-006 | multi_person | legacy | 300 | 1 | create | ambiguous_dispatch | expected clarify \| dispatch(create[Alice Chen] + ask); got create (message_user, dispatch→Running club invite drafts); slots 1/1 |
| multi-person-006 | multi_person | legacy | 300 | 2 | create | ambiguous_dispatch | expected clarify \| dispatch(create[Alice Chen] + ask); got create (message_user, dispatch→Running club invite drafts); slots 1/1 |
| trigger-005 | trigger_management | legacy | 300 | 1 | create | duplicate_create, trigger_duplicate | expected reuse(ag_x37e3tdn); got create (message_user, dispatch→Reschedule weekday trip bookings digest) |
| trigger-005 | trigger_management | legacy | 300 | 2 | create | duplicate_create, trigger_duplicate | expected reuse(ag_x37e3tdn); got create (dispatch→Reschedule weekday trip bookings digest, message_user) |
| trigger-006 | trigger_management | legacy | 10 | 0 | reuse | wrong_reuse | expected reuse(ag_ohyhhbka); got reuse (message_user, dispatch→Subscription audit reminder, dispatch→Passport reminder, dispatch→Update roadmap reminder, dispatch→Inbox zero reminder, dispatch→Weekday expense summary,... |
| trigger-006 | trigger_management | legacy | 10 | 1 | reuse | wrong_reuse | expected reuse(ag_ohyhhbka); got reuse (message_user, dispatch→Subscription audit reminder, dispatch→Update roadmap reminder, dispatch→Passport reminder, dispatch→Inbox zero reminder, dispatch→Weekday expense summary,... |
| trigger-006 | trigger_management | legacy | 10 | 2 | reuse | wrong_reuse | expected reuse(ag_ohyhhbka); got reuse (message_user, dispatch→Update roadmap reminder, dispatch→Passport reminder, dispatch→Subscription audit reminder, dispatch→Inbox zero reminder) |
| trigger-006 | trigger_management | legacy | 30 | 0 | create | duplicate_create, trigger_duplicate | expected reuse(ag_ohyhhbka); got create (dispatch→Reminder rescheduler, message_user) |
| trigger-006 | trigger_management | legacy | 30 | 1 | create | duplicate_create, trigger_duplicate | expected reuse(ag_ohyhhbka); got create (message_user, dispatch→Reminder rescheduler) |
| trigger-006 | trigger_management | legacy | 30 | 2 | create | duplicate_create, trigger_duplicate | expected reuse(ag_ohyhhbka); got create (message_user, dispatch→Reminder schedule shift, wait) |
| trigger-006 | trigger_management | legacy | 100 | 0 | none | – | expected reuse(ag_ohyhhbka); got none (no tool calls) |
| trigger-006 | trigger_management | legacy | 100 | 1 | none | – | expected reuse(ag_ohyhhbka); got none (no tool calls) |
| trigger-006 | trigger_management | legacy | 100 | 2 | none | – | expected reuse(ag_ohyhhbka); got none (no tool calls) |
| trigger-006 | trigger_management | legacy | 300 | 0 | clarify | over_clarify | expected reuse(ag_ohyhhbka); got clarify (message_user) |
| trigger-006 | trigger_management | legacy | 300 | 1 | none | – | expected reuse(ag_ohyhhbka); got none (no tool calls) |
| trigger-006 | trigger_management | legacy | 300 | 2 | none | – | expected reuse(ag_ohyhhbka); got none (no tool calls) |

## What we learned

*Written by the controller after reading the failures.*

- **`legacy` gets worse as the roster grows: 62% → 54% → 54% → 40%** (N=10 / 30 / 100 / 300; 16 dev cases × 3 runs). The drop from 10 to 300 is 22 points, larger than the run-to-run noise at this size (one case is ~2 points per cell here).
- **The mechanism is duplicate creation:** duplicate creates rise from 0/48 at N=10 to 13/48 at N=300. With 300 names, the IA misses the existing agent and makes a new one:
  - email follow-ups go 100% → 33% at N=300 (followup-005/006 create "Find new emails from Amara…" instead of reusing the Amara thread);
  - trigger management goes 50% → 17% (trigger-005 creates a second "trip bookings digest" rescheduler — a duplicate reminder, high severity).
- **Some failures don't depend on N:**
  - broad questions are 0% at every size (names alone can't say who an agent involves);
  - ambiguous_person is a flat 50%;
  - multi-person-006 ("Sam and Alice Chen") messages the ambiguous "Sam" at every N (`ambiguous_dispatch`) — today's prompt has no ambiguity rule;
  - new tasks with a lookalike pass 100% everywhere (creating is the default).
- **multi_person drops 50% → 0% from N=10 to N=30:** multi-person-005 reuses Liam's "Email Liam re invoice dispute" thread at N=10 but creates "Liam Bianchi billing dispute update" from N=30 up. The name says "invoice", the user says "billing", and with more names to scan the IA stops connecting them — a names-only weakness that richer candidate cards (`full`) should fix.
- **trigger-006 ("can u push these back an hour?") behaves erratically:** at N=10 it reschedules five reminders at once; at N=100/300 it does nothing or asks. "These" refers to the reminder in the last exchange.
- **Cost estimate is now calibrated:** actual $0.3498 vs estimated $0.3417. Mean 2.18 round trips and 4.2 s per case-run.
