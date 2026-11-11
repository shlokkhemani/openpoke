# Routing run: Experiment 8: legacy_rules with the names prompt made parallel to the ids prompt, dev, 4 sizes x 3 runs (Haiku)

## Setup

- **Purpose:** Experiment 8: legacy_rules with the names prompt made parallel to the ids prompt, dev, 4 sizes x 3 runs (Haiku)
- **Command:** `python -m evals.run routing --split dev --modes legacy_rules --sizes 10,30,100,300 --runs 3 --max-cost 3 --purpose 'Experiment 8: legacy_rules with the names prompt made parallel to the ids prompt, dev, 4 sizes x 3 runs (Haiku)' --yes`
- **Date (UTC):** 2026-11-08T08:43:17Z
- **Model:** `anthropic/claude-haiku-5.5`
- **Code:** uncommitted working tree on HEAD 878ab60
- **Case set:** `evals/cases/v1` (v1), MANIFEST sha256 `688388e57eb5980fa06046a7e384b5449d9b1c71134c817bbf7d20d166fbcbda`, frozen_on 2026-11-07
- **Split:** dev, 16 cases
- **Grid:** modes legacy_rules × sizes 10, 30, 100, 300 × 3 run(s) = 192 case-runs (0 reused from `legacy`: recency at N ≤ 20)
- **Outcome:** 192 graded, 0 infra errors (not graded), 0 skipped by the max-cost cap ($3), 0 retried

## Cost

- Actual: **$0.4399** (estimate before the run: $0.3753)
- Tokens: 3,654,745 prompt / 148,798 completion (all attempts)
- Mean latency per case-run: 4.863 s; mean round trips: 2.318

## Pass rate by mode × N

Infra errors are excluded from the denominators; structural failures count as failures.

| mode | N=10 | N=30 | N=100 | N=300 |
|---|---|---|---|---|
| legacy_rules | 83% (40/48) | 79% (38/48) | 73% (35/48) | 75% (36/48) |

## Pass rate by category

| category | mode | N=10 | N=30 | N=100 | N=300 |
|---|---|---|---|---|---|
| ambiguous_person | legacy_rules | 50% (3/6) | 50% (3/6) | 50% (3/6) | 50% (3/6) |
| broad_question_person | legacy_rules | 50% (3/6) | 50% (3/6) | 50% (3/6) | 50% (3/6) |
| clear_person | legacy_rules | 67% (4/6) | 50% (3/6) | 50% (3/6) | 50% (3/6) |
| email_followup | legacy_rules | 100% (6/6) | 100% (6/6) | 83% (5/6) | 100% (6/6) |
| multi_intent | legacy_rules | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |
| multi_person | legacy_rules | 100% (6/6) | 83% (5/6) | 50% (3/6) | 50% (3/6) |
| new_task_lookalike | legacy_rules | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |
| trigger_management | legacy_rules | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |

## Flags

| flag | mode | N=10 | N=30 | N=100 | N=300 |
|---|---|---|---|---|---|
| ambiguous_dispatch | legacy_rules | 0/48 | 0/48 | 3/48 | 1/48 |
| duplicate_create | legacy_rules | 1/48 | 3/48 | 4/48 | 5/48 |
| invalid_call | legacy_rules | 1/48 | 0/48 | 0/48 | 0/48 |
| wrong_reuse | legacy_rules | 7/48 | 7/48 | 6/48 | 6/48 |

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
| amb-person-006 | ambiguous_person | legacy_rules | 10 | 0 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Email Daniel about lab results, dispatch→Find emails from Daniel about conference schedule, dispatch→Send Daniel the signed NDA) |
| amb-person-006 | ambiguous_person | legacy_rules | 10 | 1 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Email Daniel about lab results, dispatch→Find emails from Daniel about conference schedule, dispatch→Send Daniel the signed NDA, wait) |
| amb-person-006 | ambiguous_person | legacy_rules | 10 | 2 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Email Daniel about lab results, dispatch→Find emails from Daniel about conference schedule, dispatch→Send Daniel the signed NDA) |
| amb-person-006 | ambiguous_person | legacy_rules | 30 | 0 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Email Daniel about lab results, dispatch→Send Daniel the signed NDA, dispatch→Find emails from Daniel about conference schedule, wait) |
| amb-person-006 | ambiguous_person | legacy_rules | 30 | 1 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Email Daniel about lab results, dispatch→Send Daniel the signed NDA, dispatch→Find emails from Daniel about conference schedule) |
| amb-person-006 | ambiguous_person | legacy_rules | 30 | 2 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Email Daniel about lab results, dispatch→Send Daniel the signed NDA, dispatch→Find emails from Daniel about conference schedule, wait) |
| amb-person-006 | ambiguous_person | legacy_rules | 100 | 0 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Find emails from Daniel about conference schedule, dispatch→Send Daniel the signed NDA, dispatch→Email Daniel about lab results, wait) |
| amb-person-006 | ambiguous_person | legacy_rules | 100 | 1 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Find emails from Daniel about conference schedule, dispatch→Send Daniel the signed NDA, dispatch→Email Daniel about lab results, wait) |
| amb-person-006 | ambiguous_person | legacy_rules | 100 | 2 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Find emails from Daniel about conference schedule, dispatch→Send Daniel the signed NDA, dispatch→Email Daniel about lab results) |
| amb-person-006 | ambiguous_person | legacy_rules | 300 | 0 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Send Daniel the signed NDA, dispatch→Email Daniel about lab results, dispatch→Find emails from Daniel about conference schedule, wait) |
| amb-person-006 | ambiguous_person | legacy_rules | 300 | 1 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Send Daniel the signed NDA, dispatch→Find emails from Daniel about conference schedule, dispatch→Email Daniel about lab results) |
| amb-person-006 | ambiguous_person | legacy_rules | 300 | 2 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Send Daniel the signed NDA, dispatch→Find emails from Daniel about conference schedule, dispatch→Email Daniel about lab results, wait) |
| broad-person-006 | broad_question_person | legacy_rules | 10 | 0 | reuse | invalid_call, wrong_reuse | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got reuse (message_user, dispatch→?, dispatch→?, dispatch→?, dispatch→?, dispatch→?, dispatch→?, dispatch→Find emails from Helena about interv... |
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
| clear-person-005 | clear_person | legacy_rules | 10 | 0 | create | duplicate_create | expected reuse(ag_avdgfagy); got create (message_user, dispatch→Find Farah Moreau emails about interview write-up, wait) |
| clear-person-005 | clear_person | legacy_rules | 10 | 2 | reuse | wrong_reuse | expected reuse(ag_avdgfagy); got reuse (message_user, dispatch→Email Farah the transcript, dispatch→Email Farah the reading list, dispatch→Email Farah re offer letter) |
| clear-person-005 | clear_person | legacy_rules | 30 | 0 | reuse | wrong_reuse | expected reuse(ag_avdgfagy); got reuse (message_user, dispatch→Email Farah the transcript, dispatch→Email Farah re offer letter, dispatch→Email Farah the reading list) |
| clear-person-005 | clear_person | legacy_rules | 30 | 1 | create | duplicate_create | expected reuse(ag_avdgfagy); got create (message_user, dispatch→Find emails from Farah Moreau about interview write-up) |
| clear-person-005 | clear_person | legacy_rules | 30 | 2 | create | duplicate_create | expected reuse(ag_avdgfagy); got create (message_user, dispatch→Find emails from Farah Moreau about interview write-up) |
| clear-person-005 | clear_person | legacy_rules | 100 | 0 | create | duplicate_create | expected reuse(ag_avdgfagy); got create (message_user, dispatch→Find emails from Farah Moreau about interview write-up) |
| clear-person-005 | clear_person | legacy_rules | 100 | 1 | create | duplicate_create | expected reuse(ag_avdgfagy); got create (message_user, dispatch→Find emails from Farah Moreau about interview write-up) |
| clear-person-005 | clear_person | legacy_rules | 100 | 2 | create | duplicate_create | expected reuse(ag_avdgfagy); got create (message_user, dispatch→Find emails from Farah Moreau about interview write-up) |
| clear-person-005 | clear_person | legacy_rules | 300 | 0 | create | duplicate_create | expected reuse(ag_avdgfagy); got create (message_user, dispatch→Find emails from Farah Moreau about interview write-up) |
| clear-person-005 | clear_person | legacy_rules | 300 | 1 | create | duplicate_create | expected reuse(ag_avdgfagy); got create (message_user, dispatch→Find emails from Farah Moreau about interview write-up) |
| clear-person-005 | clear_person | legacy_rules | 300 | 2 | create | duplicate_create | expected reuse(ag_avdgfagy); got create (message_user, dispatch→Find emails from Farah Moreau about interview write-up) |
| followup-005 | email_followup | legacy_rules | 100 | 0 | create | duplicate_create | expected reuse(ag_4vdh7oh4); got create (message_user, dispatch→Find emails from Amara about party plans, wait) |
| multi-person-005 | multi_person | legacy_rules | 30 | 2 | create | duplicate_create | expected dispatch(reuse(ag_3syqqzg7); create[Amara Abara]); got create (message_user, dispatch→Check billing dispute update with Liam Bianchi, dispatch→Email Amara Abara about hairdresser); slots 1/2 |
| multi-person-005 | multi_person | legacy_rules | 300 | 1 | create | duplicate_create | expected dispatch(reuse(ag_3syqqzg7); create[Amara Abara]); got create (message_user, dispatch→Check Liam Bianchi billing dispute update, dispatch→Email Amara Abara about hairdresser); slots 1/2 |
| multi-person-005 | multi_person | legacy_rules | 300 | 2 | create | duplicate_create | expected dispatch(reuse(ag_3syqqzg7); create[Amara Abara]); got create (message_user, dispatch→Check Liam Bianchi billing dispute update, dispatch→Email Amara Abara about hairdresser); slots 1/2 |
| multi-person-006 | multi_person | legacy_rules | 100 | 0 | create | ambiguous_dispatch | expected clarify \| dispatch(create[Alice Chen] + ask); got create (message_user, dispatch→Invite Sam to Sunday running club, dispatch→Invite Alice Chen to Sunday running club, message_user, dispatch→Invite Sam to Sund... |
| multi-person-006 | multi_person | legacy_rules | 100 | 1 | create | ambiguous_dispatch | expected clarify \| dispatch(create[Alice Chen] + ask); got create (message_user, dispatch→Email Alice Chen re running club, dispatch→Email Sam re running club, dispatch→Email Sam re running club, message_user); slots 1/1 |
| multi-person-006 | multi_person | legacy_rules | 100 | 2 | create | ambiguous_dispatch | expected clarify \| dispatch(create[Alice Chen] + ask); got create (message_user, dispatch→Email Sam re running club, dispatch→Email Alice Chen re running club, wait); slots 1/1 |
| multi-person-006 | multi_person | legacy_rules | 300 | 2 | create | ambiguous_dispatch | expected clarify \| dispatch(create[Alice Chen] + ask); got create (message_user, dispatch→Invite Alice Chen to Sunday running club, dispatch→Invite Sam to Sunday running club, dispatch→Invite Sam to Sunday running clu... |

## What we learned

- **What changed since experiment 4:** the names prompt now carries the same rules as the ids prompt
  (`changes.md`, 2026-11-08: names prompt made parallel to the ids prompt). The only differences left are the
  tool wording, the ids-only "`agent_id` or `name`, never both" rule and the agent-cards sentence. A test
  enforces this. Also since experiment 4: the F2 grader fix and the `trigger-006` rewording ("these" → "this").
  Experiment 4 can't be regraded on the current case set, so the per-cell diff against it mixes all three.
- **Result: 83 / 79 / 73 / 75%** at N = 10 / 30 / 100 / 300 (149/192), against 79 / 75 / 65 / 67% in experiment 4.
  `trigger-006` is now 12/12, was 0/12; that is the pronoun rule plus the rewording, not separable here.
- **The fair comparison is experiment 7** (`full`, same cases, same grader, now the same rules): 100% at every N.
  The remaining legacy_rules failures are the ones a names-only roster can't avoid:
  - `amb-person-006` 0/12: "Has Daniel gotten back to you?" with agents for two different Daniels, whose names
    carry no surname. It messages all three Daniel agents instead of asking which Daniel (wrong_reuse).
  - `broad-person-006` 0/12: "anything still open with Helena Rossi?" with six "Helena" agents; it can't tell which
    are Helena Rossi's (wrong_reuse).
  - `clear-person-005` 1/12: "Did Farah Moreau mention the interview write-up?" with three "Farah" agents; it
    mostly starts a new search agent (duplicate_create), sometimes messages every Farah agent.
  - `multi-person-005` 3 fails (duplicate_create), `multi-person-006` 4 fails (ambiguous_dispatch), and
    `followup-005` 1 fail, mostly at N ≥ 100.
  - Flags: wrong_reuse 26, duplicate_create 13, ambiguous_dispatch 4, invalid_call 1. 0 infra errors.
- **Caveats:** 16 dev cases × 3 runs; Haiku, not the final model. Dev results are not the headline; the test split is.
- **Cost:** $0.4399 on the company key (see `evals/results/SPEND.md`). Billed by OpenRouter: $0.439874
  (estimate $0.3753).
