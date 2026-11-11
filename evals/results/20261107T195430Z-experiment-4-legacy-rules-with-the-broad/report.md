# Routing run: Experiment 4: legacy_rules with the broad-question rule limited to no-topic questions, dev, 4 sizes x 3 runs (Haiku)

## Setup

- **Purpose:** Experiment 4: legacy_rules with the broad-question rule limited to no-topic questions, dev, 4 sizes x 3 runs (Haiku)
- **Command:** `python -m evals.run routing --modes legacy_rules --sizes 10,30,100,300 --split dev --runs 3 --purpose 'Experiment 4: legacy_rules with the broad-question rule limited to no-topic questions, dev, 4 sizes x 3 runs (Haiku)' --yes`
- **Date (UTC):** 2026-11-07T19:54:30Z
- **Model:** `anthropic/claude-haiku-5.5`
- **Code:** uncommitted working tree on HEAD c1bc207
- **Case set:** `evals/cases/v1` (v1), MANIFEST sha256 `eb5f510b2a88a0eea0fadce016515fab81f582c0d360da9f00096134d88be8f7`, frozen_on 2026-11-07
- **Split:** dev, 16 cases
- **Grid:** modes legacy_rules × sizes 10, 30, 100, 300 × 3 run(s) = 192 case-runs (0 reused from `legacy`: recency at N ≤ 20)
- **Outcome:** 192 graded, 0 infra errors (not graded), 0 skipped by the max-cost cap ($35), 0 retried

## Cost

- Actual: **$0.4256** (estimate before the run: $0.3753)
- Tokens: 3,520,243 prompt / 147,092 completion (all attempts)
- Mean latency per case-run: 4.936 s; mean round trips: 2.276

## Pass rate by mode × N

Infra errors are excluded from the denominators; structural failures count as failures.

| mode | N=10 | N=30 | N=100 | N=300 |
|---|---|---|---|---|
| legacy_rules | 79% (38/48) | 75% (36/48) | 65% (31/48) | 67% (32/48) |

## Pass rate by category

| category | mode | N=10 | N=30 | N=100 | N=300 |
|---|---|---|---|---|---|
| ambiguous_person | legacy_rules | 33% (2/6) | 50% (3/6) | 50% (3/6) | 50% (3/6) |
| broad_question_person | legacy_rules | 50% (3/6) | 50% (3/6) | 50% (3/6) | 50% (3/6) |
| clear_person | legacy_rules | 100% (6/6) | 67% (4/6) | 50% (3/6) | 50% (3/6) |
| email_followup | legacy_rules | 100% (6/6) | 100% (6/6) | 67% (4/6) | 83% (5/6) |
| multi_intent | legacy_rules | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |
| multi_person | legacy_rules | 100% (6/6) | 83% (5/6) | 50% (3/6) | 50% (3/6) |
| new_task_lookalike | legacy_rules | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |
| trigger_management | legacy_rules | 50% (3/6) | 50% (3/6) | 50% (3/6) | 50% (3/6) |

## Flags

| flag | mode | N=10 | N=30 | N=100 | N=300 |
|---|---|---|---|---|---|
| ambiguous_dispatch | legacy_rules | 0/48 | 0/48 | 3/48 | 0/48 |
| duplicate_create | legacy_rules | 0/48 | 3/48 | 5/48 | 7/48 |
| over_clarify | legacy_rules | 3/48 | 1/48 | 0/48 | 0/48 |
| wrong_reuse | legacy_rules | 6/48 | 6/48 | 6/48 | 6/48 |

## Structural failures

A legacy dispatch by a name that several agents share (e.g. two "Email Alice" agents): the names-only roster cannot express the right target.

| mode | N=10 | N=30 | N=100 | N=300 |
|---|---|---|---|---|
| legacy_rules | 0 | 0 | 0 | 0 |

## Infra errors

Retried once; a case-run whose retry also failed is listed in `errors.jsonl` and not graded. Counts are paid case-runs; a reused recency copy of an errored `legacy` case-run is not counted again.

| mode | N=10 | N=30 | N=100 | N=300 |
|---|---|---|---|---|
| legacy_rules | 0 | 0 | 0 | 0 |

## Failing case-runs

| case | category | mode | N | run | outcome | flags | reason |
|---|---|---|---|---|---|---|---|
| amb-person-006 | ambiguous_person | legacy_rules | 10 | 0 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Email Daniel about lab results, dispatch→Find emails from Daniel about conference schedule, dispatch→Send Daniel the signed NDA, wait) |
| amb-person-006 | ambiguous_person | legacy_rules | 10 | 1 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Email Daniel about lab results, dispatch→Find emails from Daniel about conference schedule, dispatch→Send Daniel the signed NDA, wait) |
| amb-person-006 | ambiguous_person | legacy_rules | 10 | 2 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Email Daniel about lab results, dispatch→Find emails from Daniel about conference schedule, dispatch→Send Daniel the signed NDA) |
| amb-person-006 | ambiguous_person | legacy_rules | 30 | 0 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Email Daniel about lab results, dispatch→Send Daniel the signed NDA, dispatch→Find emails from Daniel about conference schedule) |
| amb-person-006 | ambiguous_person | legacy_rules | 30 | 1 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Email Daniel about lab results, dispatch→Send Daniel the signed NDA, dispatch→Find emails from Daniel about conference schedule, wait) |
| amb-person-006 | ambiguous_person | legacy_rules | 30 | 2 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Email Daniel about lab results, dispatch→Send Daniel the signed NDA, dispatch→Find emails from Daniel about conference schedule, wait) |
| amb-person-006 | ambiguous_person | legacy_rules | 100 | 0 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Find emails from Daniel about conference schedule, dispatch→Send Daniel the signed NDA, dispatch→Email Daniel about lab results, wait) |
| amb-person-006 | ambiguous_person | legacy_rules | 100 | 1 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Find emails from Daniel about conference schedule, dispatch→Send Daniel the signed NDA, dispatch→Email Daniel about lab results, wait) |
| amb-person-006 | ambiguous_person | legacy_rules | 100 | 2 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Find emails from Daniel about conference schedule, dispatch→Send Daniel the signed NDA, dispatch→Email Daniel about lab results, wait) |
| amb-person-006 | ambiguous_person | legacy_rules | 300 | 0 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Send Daniel the signed NDA, dispatch→Find emails from Daniel about conference schedule, dispatch→Email Daniel about lab results, wait) |
| amb-person-006 | ambiguous_person | legacy_rules | 300 | 1 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Send Daniel the signed NDA, dispatch→Find emails from Daniel about conference schedule, dispatch→Email Daniel about lab results) |
| amb-person-006 | ambiguous_person | legacy_rules | 300 | 2 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Send Daniel the signed NDA, dispatch→Find emails from Daniel about conference schedule, dispatch→Email Daniel about lab results, wait) |
| amb-person-007 | ambiguous_person | legacy_rules | 10 | 2 | clarify | over_clarify | expected reuse(ag_dcl3r2h4); got clarify (send_draft, message_user) |
| broad-person-006 | broad_question_person | legacy_rules | 10 | 0 | reuse | wrong_reuse | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got reuse (message_user, dispatch→Find emails from Helena about interview loop, dispatch→Follow up with Helena on contract renewal, dispatch→E... |
| broad-person-006 | broad_question_person | legacy_rules | 10 | 1 | reuse | wrong_reuse | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got reuse (message_user, dispatch→Find emails from Helena about interview loop, dispatch→Follow up with Helena on contract renewal, dispatch→E... |
| broad-person-006 | broad_question_person | legacy_rules | 10 | 2 | reuse | wrong_reuse | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got reuse (message_user, dispatch→Find emails from Helena about interview loop, dispatch→Follow up with Helena on contract renewal, dispatch→E... |
| broad-person-006 | broad_question_person | legacy_rules | 30 | 0 | reuse | wrong_reuse | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got reuse (message_user, dispatch→Email Helena re podcast interview, dispatch→Find emails from Helena about interview loop, dispatch→Follow up... |
| broad-person-006 | broad_question_person | legacy_rules | 30 | 1 | reuse | wrong_reuse | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got reuse (message_user, dispatch→Email Helena re podcast interview, dispatch→Find emails from Helena about interview loop, dispatch→Follow up... |
| broad-person-006 | broad_question_person | legacy_rules | 30 | 2 | reuse | wrong_reuse | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got reuse (message_user, dispatch→Email Helena re podcast interview, dispatch→Find emails from Helena about interview loop, dispatch→Follow up... |
| broad-person-006 | broad_question_person | legacy_rules | 100 | 0 | reuse | wrong_reuse | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got reuse (message_user, dispatch→Find emails from Helena about interview loop, dispatch→Email Helena re podcast interview, dispatch→Follow up... |
| broad-person-006 | broad_question_person | legacy_rules | 100 | 1 | reuse | wrong_reuse | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got reuse (message_user, dispatch→Find emails from Helena about interview loop, dispatch→Email Helena re podcast interview, dispatch→Follow up... |
| broad-person-006 | broad_question_person | legacy_rules | 100 | 2 | reuse | wrong_reuse | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got reuse (message_user, dispatch→Find emails from Helena about interview loop, dispatch→Email Helena re podcast interview, dispatch→Follow up... |
| broad-person-006 | broad_question_person | legacy_rules | 300 | 0 | reuse | wrong_reuse | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got reuse (message_user, dispatch→Email Helena re podcast interview, dispatch→Find emails from Helena about interview loop, dispatch→Email Hel... |
| broad-person-006 | broad_question_person | legacy_rules | 300 | 1 | reuse | wrong_reuse | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got reuse (message_user, dispatch→Email Helena re podcast interview, dispatch→Find emails from Helena about interview loop, dispatch→Email Hel... |
| broad-person-006 | broad_question_person | legacy_rules | 300 | 2 | reuse | wrong_reuse | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got reuse (message_user, dispatch→Email Helena re podcast interview, dispatch→Find emails from Helena about interview loop, dispatch→Email Hel... |
| clear-person-005 | clear_person | legacy_rules | 30 | 1 | create | duplicate_create | expected reuse(ag_avdgfagy); got create (message_user, dispatch→Search Farah Moreau re interview write-up) |
| clear-person-005 | clear_person | legacy_rules | 30 | 2 | create | duplicate_create | expected reuse(ag_avdgfagy); got create (message_user, dispatch→Search Farah Moreau emails re interview write-up) |
| clear-person-005 | clear_person | legacy_rules | 100 | 0 | create | duplicate_create | expected reuse(ag_avdgfagy); got create (message_user, dispatch→Find emails from Farah Moreau about interview write-up) |
| clear-person-005 | clear_person | legacy_rules | 100 | 1 | create | duplicate_create | expected reuse(ag_avdgfagy); got create (message_user, dispatch→Find emails from Farah Moreau about interview write-up) |
| clear-person-005 | clear_person | legacy_rules | 100 | 2 | create | duplicate_create | expected reuse(ag_avdgfagy); got create (message_user, dispatch→Find emails from Farah Moreau about interview write-up) |
| clear-person-005 | clear_person | legacy_rules | 300 | 0 | create | duplicate_create | expected reuse(ag_avdgfagy); got create (message_user, dispatch→Find emails from Farah Moreau about interview write-up) |
| clear-person-005 | clear_person | legacy_rules | 300 | 1 | create | duplicate_create | expected reuse(ag_avdgfagy); got create (message_user, dispatch→Search Farah Moreau re interview write-up) |
| clear-person-005 | clear_person | legacy_rules | 300 | 2 | create | duplicate_create | expected reuse(ag_avdgfagy); got create (message_user, dispatch→Find Farah Moreau emails about interview write-up) |
| followup-005 | email_followup | legacy_rules | 100 | 0 | create | duplicate_create | expected reuse(ag_4vdh7oh4); got create (message_user, dispatch→Find emails from Amara about party plans) |
| followup-005 | email_followup | legacy_rules | 100 | 1 | create | duplicate_create | expected reuse(ag_4vdh7oh4); got create (message_user, dispatch→Find emails from Amara about party plans) |
| followup-005 | email_followup | legacy_rules | 300 | 1 | create | duplicate_create | expected reuse(ag_4vdh7oh4); got create (message_user, dispatch→Find emails from Amara about party plans) |
| multi-person-005 | multi_person | legacy_rules | 30 | 1 | create | duplicate_create | expected dispatch(reuse(ag_3syqqzg7); create[Amara Abara]); got create (message_user, dispatch→Billing dispute update from Liam Bianchi, dispatch→Email Amara Abara about hairdresser); slots 1/2 |
| multi-person-005 | multi_person | legacy_rules | 300 | 0 | create | duplicate_create | expected dispatch(reuse(ag_3syqqzg7); create[Amara Abara]); got create (message_user, dispatch→Billing dispute update with Liam Bianchi, dispatch→Email Amara Abara about her hairdresser); slots 1/2 |
| multi-person-005 | multi_person | legacy_rules | 300 | 1 | create | duplicate_create | expected dispatch(reuse(ag_3syqqzg7); create[Amara Abara]); got create (message_user, dispatch→Check Liam Bianchi billing dispute update, dispatch→Email Amara Abara about hairdresser); slots 1/2 |
| multi-person-005 | multi_person | legacy_rules | 300 | 2 | create | duplicate_create | expected dispatch(reuse(ag_3syqqzg7); create[Amara Abara]); got create (message_user, dispatch→Check Liam Bianchi billing dispute update, dispatch→Email Amara Abara about hairdresser); slots 1/2 |
| multi-person-006 | multi_person | legacy_rules | 100 | 0 | create | ambiguous_dispatch | expected clarify \| dispatch(create[Alice Chen] + ask); got create (message_user, dispatch→Draft running club invite to Sam, dispatch→Draft running club invite to Alice Chen, message_user, dispatch→Draft running club i... |
| multi-person-006 | multi_person | legacy_rules | 100 | 1 | create | ambiguous_dispatch | expected clarify \| dispatch(create[Alice Chen] + ask); got create (message_user, dispatch→Email Alice Chen about Sunday running club, dispatch→Email Sam about Sunday running club); slots 1/1 |
| multi-person-006 | multi_person | legacy_rules | 100 | 2 | create | ambiguous_dispatch | expected clarify \| dispatch(create[Alice Chen] + ask); got create (message_user, dispatch→Email Alice Chen about Sunday running club, dispatch→Email Sam about Sunday running club, dispatch→Email Sam about Sunday runni... |
| trigger-006 | trigger_management | legacy_rules | 10 | 0 | none | – | expected reuse(ag_ohyhhbka); got none (no tool calls) |
| trigger-006 | trigger_management | legacy_rules | 10 | 1 | clarify | over_clarify | expected reuse(ag_ohyhhbka); got clarify (message_user) |
| trigger-006 | trigger_management | legacy_rules | 10 | 2 | clarify | over_clarify | expected reuse(ag_ohyhhbka); got clarify (message_user) |
| trigger-006 | trigger_management | legacy_rules | 30 | 0 | none | – | expected reuse(ag_ohyhhbka); got none (no tool calls) |
| trigger-006 | trigger_management | legacy_rules | 30 | 1 | none | – | expected reuse(ag_ohyhhbka); got none (no tool calls) |
| trigger-006 | trigger_management | legacy_rules | 30 | 2 | clarify | over_clarify | expected reuse(ag_ohyhhbka); got clarify (message_user) |
| trigger-006 | trigger_management | legacy_rules | 100 | 0 | none | – | expected reuse(ag_ohyhhbka); got none (no tool calls) |
| trigger-006 | trigger_management | legacy_rules | 100 | 1 | none | – | expected reuse(ag_ohyhhbka); got none (no tool calls) |
| trigger-006 | trigger_management | legacy_rules | 100 | 2 | none | – | expected reuse(ag_ohyhhbka); got none (no tool calls) |
| trigger-006 | trigger_management | legacy_rules | 300 | 0 | none | – | expected reuse(ag_ohyhhbka); got none (no tool calls) |
| trigger-006 | trigger_management | legacy_rules | 300 | 1 | none | – | expected reuse(ag_ohyhhbka); got none (no tool calls) |
| trigger-006 | trigger_management | legacy_rules | 300 | 2 | none | – | expected reuse(ag_ohyhhbka); got none (no tool calls) |

## What we learned

- **The narrower broad-question rule works:** legacy_rules goes from 69 / 75 / 65 / 60% (experiment 3)
  to **79 / 75 / 65 / 67%** at N = 10 / 30 / 100 / 300. Legacy (experiment 2) was 62 / 54 / 54 / 40%.
- **Fan-out on specific questions is gone:** wrong_reuse 12 / 9 / 10 / 13 → 6 / 6 / 6 / 6 of 48, and the
  6 left are the two cases names can't solve (`amb-person-006`, and `broad-person-006` with its two
  Helenas). `followup-006` 6/12 → 12/12.
- **`clear-person-005` is now a names-only limit, not a prompt bug:** it passes at N=10 (3/3) but at
  N ≥ 100 creates "Find emails from Farah Moreau about interview write-up" instead of reusing "Email Farah
  the transcript". Nothing in that name links "transcript" to "interview write-up"; the agent's
  description in `full` mode does. Most of the duplicate creates (0 / 3 / 5 / 7 of 48) are this case.
- `multi-person-005` at N=300 (0/3 here, 1/3 in experiment 3) and `multi-person-006` at N=100 move
  between runs: with 3 runs a case's score at one N is noisy, so read trends across N, not single cells.
- Still failing at every N: `amb-person-006`, `broad-person-006`, `trigger-006` (no tool call, or asks).
- Cost $0.4256.
