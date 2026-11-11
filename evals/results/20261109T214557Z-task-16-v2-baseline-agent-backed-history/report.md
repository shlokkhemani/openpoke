# Routing run: Task 16: v2 baseline (agent-backed history), dev, legacy_rules+full x 4 sizes x 3 runs (Haiku)

## Setup

- **Purpose:** Task 16: v2 baseline (agent-backed history), dev, legacy_rules+full x 4 sizes x 3 runs (Haiku)
- **Command:** `python -m evals.run routing --modes legacy_rules,full --sizes 10,30,100,300 --split dev --runs 3 --max-cost 5 --cases-dir evals/cases/v2 --purpose 'Task 16: v2 baseline (agent-backed history), dev, legacy_rules+full x 4 sizes x 3 runs (Haiku)' --yes`
- **Date (UTC):** 2026-11-09T21:45:57Z
- **Model:** `anthropic/claude-haiku-5.5`
- **Code:** uncommitted working tree on HEAD 6c9e97c
- **Case set:** `evals/cases/v2` (v2), MANIFEST sha256 `d0c9a4ca5b94e38c5c16bc428609f90cd25ba1b03d8adf80e733689c4649cc3c`, frozen_on 2026-11-09
- **Split:** dev, 16 cases
- **Descriptions (`full`):** regen, sha256 `5d4d6d7c5b20fa1c53c69d280e122d27804833e7dd04ac623bf1e8e1c93ec232`, covering 310/310 world agents
- **Grid:** modes legacy_rules, full × sizes 10, 30, 100, 300 × 3 run(s) = 384 case-runs
- **Outcome:** 384 graded, 0 infra errors (not graded), 0 skipped by the max-cost cap ($5), 0 retried

## Cost

- Actual: **$1.5420** (estimate before the run: $1.4519)
- Tokens: 14,013,922 prompt / 281,148 completion (all attempts)
- Mean latency per case-run: 5.24 s; mean round trips: 2.284

## Pass rate by mode × N

Infra errors are excluded from the denominators; structural failures count as failures.

| mode | N=10 | N=30 | N=100 | N=300 |
|---|---|---|---|---|
| legacy_rules | 83% (40/48) | 85% (41/48) | 81% (39/48) | 77% (37/48) |
| full | 100% (48/48) | 100% (48/48) | 100% (48/48) | 100% (48/48) |

## Pass rate by category

| category | mode | N=10 | N=30 | N=100 | N=300 |
|---|---|---|---|---|---|
| ambiguous_person | legacy_rules | 50% (3/6) | 50% (3/6) | 50% (3/6) | 50% (3/6) |
| ambiguous_person | full | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |
| broad_question_person | legacy_rules | 50% (3/6) | 50% (3/6) | 50% (3/6) | 50% (3/6) |
| broad_question_person | full | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |
| clear_person | legacy_rules | 83% (5/6) | 83% (5/6) | 50% (3/6) | 50% (3/6) |
| clear_person | full | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |
| email_followup | legacy_rules | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |
| email_followup | full | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |
| multi_intent | legacy_rules | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |
| multi_intent | full | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |
| multi_person | legacy_rules | 83% (5/6) | 100% (6/6) | 100% (6/6) | 67% (4/6) |
| multi_person | full | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |
| new_task_lookalike | legacy_rules | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |
| new_task_lookalike | full | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |
| trigger_management | legacy_rules | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |
| trigger_management | full | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |

## Flags

| flag | mode | N=10 | N=30 | N=100 | N=300 |
|---|---|---|---|---|---|
| duplicate_create | legacy_rules | 1/48 | 1/48 | 3/48 | 5/48 |
| duplicate_create | full | 0/48 | 0/48 | 0/48 | 0/48 |
| wrong_reuse | legacy_rules | 7/48 | 6/48 | 6/48 | 6/48 |
| wrong_reuse | full | 0/48 | 0/48 | 0/48 | 0/48 |

## Structural failures

A legacy dispatch by a name that several agents share (e.g. two "Email Alice" agents): the names-only roster cannot express the right target.

| mode | N=10 | N=30 | N=100 | N=300 |
|---|---|---|---|---|
| legacy_rules | 0 | 0 | 0 | 0 |
| full | 0 | 0 | 0 | 0 |

## Infra errors

Retried once; a case-run whose retry also failed is listed in `errors.jsonl` and not graded. Counts are case-runs.

| mode | N=10 | N=30 | N=100 | N=300 |
|---|---|---|---|---|
| legacy_rules | 0 | 0 | 0 | 0 |
| full | 0 | 0 | 0 | 0 |

## Failing case-runs

| case | category | mode | N | run | outcome | flags | reason |
|---|---|---|---|---|---|---|---|
| amb-person-006 | ambiguous_person | legacy_rules | 10 | 0 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Email Daniel about lab results, dispatch→Find emails from Daniel about conference schedule, dispatch→Send Daniel the signed NDA, wait) |
| amb-person-006 | ambiguous_person | legacy_rules | 10 | 1 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Email Daniel about lab results, dispatch→Find emails from Daniel about conference schedule, dispatch→Send Daniel the signed NDA) |
| amb-person-006 | ambiguous_person | legacy_rules | 10 | 2 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Email Daniel about lab results, dispatch→Find emails from Daniel about conference schedule, dispatch→Send Daniel the signed NDA, wait) |
| amb-person-006 | ambiguous_person | legacy_rules | 30 | 0 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Email Daniel about lab results, dispatch→Send Daniel the signed NDA, dispatch→Find emails from Daniel about conference schedule, wait) |
| amb-person-006 | ambiguous_person | legacy_rules | 30 | 1 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Email Daniel about lab results, dispatch→Send Daniel the signed NDA, dispatch→Find emails from Daniel about conference schedule, wait) |
| amb-person-006 | ambiguous_person | legacy_rules | 30 | 2 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Email Daniel about lab results, dispatch→Send Daniel the signed NDA, dispatch→Find emails from Daniel about conference schedule, wait) |
| amb-person-006 | ambiguous_person | legacy_rules | 100 | 0 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Find emails from Daniel about conference schedule, dispatch→Send Daniel the signed NDA, dispatch→Email Daniel about lab results) |
| amb-person-006 | ambiguous_person | legacy_rules | 100 | 1 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Find emails from Daniel about conference schedule, dispatch→Send Daniel the signed NDA, dispatch→Email Daniel about lab results, wait) |
| amb-person-006 | ambiguous_person | legacy_rules | 100 | 2 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Find emails from Daniel about conference schedule, dispatch→Send Daniel the signed NDA, dispatch→Email Daniel about lab results) |
| amb-person-006 | ambiguous_person | legacy_rules | 300 | 0 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Send Daniel the signed NDA, dispatch→Find emails from Daniel about conference schedule, dispatch→Email Daniel about lab results) |
| amb-person-006 | ambiguous_person | legacy_rules | 300 | 1 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Send Daniel the signed NDA, dispatch→Find emails from Daniel about conference schedule, dispatch→Email Daniel about lab results) |
| amb-person-006 | ambiguous_person | legacy_rules | 300 | 2 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Send Daniel the signed NDA, dispatch→Email Daniel about lab results, dispatch→Find emails from Daniel about conference schedule) |
| broad-person-006 | broad_question_person | legacy_rules | 10 | 0 | reuse | wrong_reuse | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got reuse (message_user, dispatch→Find emails from Helena about interview loop, dispatch→Follow up with Helena on contract renewal, dispatch→E... |
| broad-person-006 | broad_question_person | legacy_rules | 10 | 1 | reuse | wrong_reuse | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got reuse (message_user, dispatch→Find emails from Helena about interview loop, dispatch→Follow up with Helena on contract renewal, dispatch→E... |
| broad-person-006 | broad_question_person | legacy_rules | 10 | 2 | reuse | wrong_reuse | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got reuse (message_user, dispatch→Find emails from Helena about interview loop, dispatch→Follow up with Helena on contract renewal, dispatch→E... |
| broad-person-006 | broad_question_person | legacy_rules | 30 | 0 | reuse | wrong_reuse | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got reuse (message_user, dispatch→Email Helena re podcast interview, dispatch→Follow up with Helena on catering order, dispatch→Find emails fr... |
| broad-person-006 | broad_question_person | legacy_rules | 30 | 1 | reuse | wrong_reuse | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got reuse (message_user, dispatch→Email Helena re podcast interview, dispatch→Find emails from Helena about interview loop, dispatch→Follow up... |
| broad-person-006 | broad_question_person | legacy_rules | 30 | 2 | reuse | wrong_reuse | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got reuse (message_user, dispatch→Email Helena re podcast interview, dispatch→Follow up with Helena on catering order, dispatch→Find emails fr... |
| broad-person-006 | broad_question_person | legacy_rules | 100 | 0 | reuse | wrong_reuse | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got reuse (message_user, dispatch→Find emails from Helena about interview loop, dispatch→Email Helena re podcast interview, dispatch→Follow up... |
| broad-person-006 | broad_question_person | legacy_rules | 100 | 1 | reuse | wrong_reuse | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got reuse (message_user, dispatch→Find emails from Helena about interview loop, dispatch→Email Helena re podcast interview, dispatch→Follow up... |
| broad-person-006 | broad_question_person | legacy_rules | 100 | 2 | reuse | wrong_reuse | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got reuse (message_user, dispatch→Find emails from Helena about interview loop, dispatch→Email Helena re podcast interview, dispatch→Email Hel... |
| broad-person-006 | broad_question_person | legacy_rules | 300 | 0 | reuse | wrong_reuse | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got reuse (message_user, dispatch→Email Helena re podcast interview, dispatch→Find emails from Helena about interview loop, dispatch→Email Hel... |
| broad-person-006 | broad_question_person | legacy_rules | 300 | 1 | reuse | wrong_reuse | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got reuse (message_user, dispatch→Email Helena re podcast interview, dispatch→Find emails from Helena about interview loop, dispatch→Email Hel... |
| broad-person-006 | broad_question_person | legacy_rules | 300 | 2 | reuse | wrong_reuse | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got reuse (message_user, dispatch→Email Helena re podcast interview, dispatch→Find emails from Helena about interview loop, dispatch→Email Hel... |
| clear-person-005 | clear_person | legacy_rules | 10 | 2 | reuse | wrong_reuse | expected reuse(ag_avdgfagy); got reuse (message_user, dispatch→Email Farah the transcript, dispatch→Email Farah the reading list, dispatch→Email Farah re offer letter) |
| clear-person-005 | clear_person | legacy_rules | 30 | 2 | create | duplicate_create | expected reuse(ag_avdgfagy); got create (message_user, dispatch→Find emails from Farah Moreau about interview write-up) |
| clear-person-005 | clear_person | legacy_rules | 100 | 0 | create | duplicate_create | expected reuse(ag_avdgfagy); got create (message_user, dispatch→Find emails from Farah Moreau about interview write-up) |
| clear-person-005 | clear_person | legacy_rules | 100 | 1 | create | duplicate_create | expected reuse(ag_avdgfagy); got create (message_user, dispatch→Find emails from Farah Moreau about interview write-up) |
| clear-person-005 | clear_person | legacy_rules | 100 | 2 | create | duplicate_create | expected reuse(ag_avdgfagy); got create (message_user, dispatch→Find emails from Farah Moreau about interview write-up) |
| clear-person-005 | clear_person | legacy_rules | 300 | 0 | create | duplicate_create | expected reuse(ag_avdgfagy); got create (message_user, dispatch→Find emails from Farah Moreau about interview write-up) |
| clear-person-005 | clear_person | legacy_rules | 300 | 1 | create | duplicate_create | expected reuse(ag_avdgfagy); got create (message_user, dispatch→Find emails from Farah Moreau about interview write-up) |
| clear-person-005 | clear_person | legacy_rules | 300 | 2 | create | duplicate_create | expected reuse(ag_avdgfagy); got create (message_user, dispatch→Find emails from Farah Moreau about interview write-up) |
| multi-person-005 | multi_person | legacy_rules | 10 | 2 | create | duplicate_create | expected dispatch(reuse(ag_3syqqzg7); create[Amara Abara]); got create (message_user, dispatch→Check billing dispute status with Liam Bianchi, dispatch→Email Amara Abara about hairdresser); slots 1/2 |
| multi-person-005 | multi_person | legacy_rules | 300 | 1 | create | duplicate_create | expected dispatch(reuse(ag_3syqqzg7); create[Amara Abara]); got create (message_user, dispatch→Check Liam Bianchi billing dispute update, dispatch→Email Amara Abara about hairdresser, wait); slots 1/2 |
| multi-person-005 | multi_person | legacy_rules | 300 | 2 | create | duplicate_create | expected dispatch(reuse(ag_3syqqzg7); create[Amara Abara]); got create (message_user, dispatch→Check billing dispute with Liam Bianchi, dispatch→Email Amara Abara about hairdresser); slots 1/2 |

## What we learned

- **First run on case set v2** (`evals/cases/v2`, frozen 2026-11-09): same 49 cases and labels as v1, but the 38
  cases whose history was off-product chat (weather, flights, unit conversion, calendar) now carry agent-backed
  Gmail/trigger exchanges with a real filler agent in the roster (`context_agents`).
- **`full` is unaffected: 100% at every N** (48/48 × 4), as on v1 (Task 14 smoke N=10/30, Task 15 N=100/300). An
  unrelated agent in the last exchange does not pull `full` off the right target.
- **`legacy_rules`: 83 / 85 / 81 / 77%** at N = 10 / 30 / 100 / 300, against 83 / 79 / 73 / 75% in Experiment 8 (v1,
  older harness code before Task 14, so not a pure history effect). The failing cases are the same ones:
  `amb-person-006` (12/12, reuses a Daniel agent instead of asking which Daniel) and `broad-person-006` (12/12, reuses
  one Helena agent instead of answering over all four) fail in every run on both sets — prompt-rule failures, not
  history; `clear-person-005` 8/12 (11/12 on v1), `multi-person-005` 3/12 (3/12). `multi-person-006` (4/12 on v1) and
  `followup-005` (1/12) no longer fail.
- **Cost:** $1.5420 against a $1.4519 estimate (+6%: mostly `legacy_rules`, whose prompt tokens per case-run ran
  9–21% over its estimate at every N, likely the longer v2 histories; `full` was within −3% to +4%). Billed matches the runner (SPEND.md row 6).
- **Not run:** `hybrid` on v2 (left out at Siddharth's request). The free layer-1 retrieval eval on v2
  (`20261109T214830Z`, `20261109T215151Z`) shows `multi-person-006`'s Sam Okafor agents still outside the top 20 at
  N=300, so the Task 15 `hybrid` miss is probably not fixed by the history change alone.
