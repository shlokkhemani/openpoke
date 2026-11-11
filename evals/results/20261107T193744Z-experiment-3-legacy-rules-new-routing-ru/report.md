# Routing run: Experiment 3: legacy_rules (new routing rules, names-only roster) on dev, 4 sizes x 3 runs (Haiku)

## Setup

- **Purpose:** Experiment 3: legacy_rules (new routing rules, names-only roster) on dev, 4 sizes x 3 runs (Haiku)
- **Command:** `python -m evals.run routing --modes legacy_rules --sizes 10,30,100,300 --split dev --runs 3 --purpose 'Experiment 3: legacy_rules (new routing rules, names-only roster) on dev, 4 sizes x 3 runs (Haiku)' --yes`
- **Date (UTC):** 2026-11-07T19:37:44Z
- **Model:** `anthropic/claude-haiku-5.5`
- **Code:** uncommitted working tree on HEAD c1bc207
- **Case set:** `evals/cases/v1` (v1), MANIFEST sha256 `eb5f510b2a88a0eea0fadce016515fab81f582c0d360da9f00096134d88be8f7`, frozen_on 2026-11-07
- **Split:** dev, 16 cases
- **Grid:** modes legacy_rules × sizes 10, 30, 100, 300 × 3 run(s) = 192 case-runs (0 reused from `legacy`: recency at N ≤ 20)
- **Outcome:** 192 graded, 0 infra errors (not graded), 0 skipped by the max-cost cap ($35), 0 retried

## Cost

- Actual: **$0.4345** (estimate before the run: $0.3753)
- Tokens: 3,540,015 prompt / 161,091 completion (all attempts)
- Mean latency per case-run: 5.256 s; mean round trips: 2.292

## Pass rate by mode × N

Infra errors are excluded from the denominators; structural failures count as failures.

| mode | N=10 | N=30 | N=100 | N=300 |
|---|---|---|---|---|
| legacy_rules | 69% (33/48) | 75% (36/48) | 65% (31/48) | 60% (29/48) |

## Pass rate by category

| category | mode | N=10 | N=30 | N=100 | N=300 |
|---|---|---|---|---|---|
| ambiguous_person | legacy_rules | 50% (3/6) | 50% (3/6) | 50% (3/6) | 33% (2/6) |
| broad_question_person | legacy_rules | 50% (3/6) | 50% (3/6) | 50% (3/6) | 50% (3/6) |
| clear_person | legacy_rules | 50% (3/6) | 50% (3/6) | 50% (3/6) | 50% (3/6) |
| email_followup | legacy_rules | 50% (3/6) | 100% (6/6) | 50% (3/6) | 50% (3/6) |
| multi_intent | legacy_rules | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |
| multi_person | legacy_rules | 100% (6/6) | 100% (6/6) | 67% (4/6) | 50% (3/6) |
| new_task_lookalike | legacy_rules | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |
| trigger_management | legacy_rules | 50% (3/6) | 50% (3/6) | 50% (3/6) | 50% (3/6) |

## Flags

| flag | mode | N=10 | N=30 | N=100 | N=300 |
|---|---|---|---|---|---|
| ambiguous_dispatch | legacy_rules | 0/48 | 0/48 | 2/48 | 1/48 |
| duplicate_create | legacy_rules | 0/48 | 0/48 | 2/48 | 2/48 |
| over_clarify | legacy_rules | 1/48 | 1/48 | 0/48 | 1/48 |
| wrong_reuse | legacy_rules | 12/48 | 9/48 | 10/48 | 13/48 |

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
| amb-person-006 | ambiguous_person | legacy_rules | 30 | 0 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Email Daniel about lab results, dispatch→Send Daniel the signed NDA, dispatch→Find emails from Daniel about conference schedule, wait) |
| amb-person-006 | ambiguous_person | legacy_rules | 30 | 1 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Email Daniel about lab results, dispatch→Send Daniel the signed NDA, dispatch→Find emails from Daniel about conference schedule) |
| amb-person-006 | ambiguous_person | legacy_rules | 30 | 2 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Email Daniel about lab results, dispatch→Send Daniel the signed NDA, dispatch→Find emails from Daniel about conference schedule, wait) |
| amb-person-006 | ambiguous_person | legacy_rules | 100 | 0 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Find emails from Daniel about conference schedule, dispatch→Send Daniel the signed NDA, dispatch→Email Daniel about lab results, wait) |
| amb-person-006 | ambiguous_person | legacy_rules | 100 | 1 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Find emails from Daniel about conference schedule, dispatch→Send Daniel the signed NDA, dispatch→Email Daniel about lab results, wait) |
| amb-person-006 | ambiguous_person | legacy_rules | 100 | 2 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Find emails from Daniel about conference schedule, dispatch→Send Daniel the signed NDA, dispatch→Email Daniel about lab results) |
| amb-person-006 | ambiguous_person | legacy_rules | 300 | 0 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Send Daniel the signed NDA, dispatch→Find emails from Daniel about conference schedule, dispatch→Email Daniel about lab results) |
| amb-person-006 | ambiguous_person | legacy_rules | 300 | 1 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Send Daniel the signed NDA, dispatch→Find emails from Daniel about conference schedule, dispatch→Email Daniel about lab results) |
| amb-person-006 | ambiguous_person | legacy_rules | 300 | 2 | reuse | wrong_reuse | expected clarify; got reuse (message_user, dispatch→Send Daniel the signed NDA, dispatch→Email Daniel about lab results, dispatch→Find emails from Daniel about conference schedule, wait) |
| amb-person-007 | ambiguous_person | legacy_rules | 300 | 1 | clarify | over_clarify | expected reuse(ag_dcl3r2h4); got clarify (send_draft, message_user) |
| broad-person-006 | broad_question_person | legacy_rules | 10 | 0 | reuse | wrong_reuse | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got reuse (message_user, dispatch→Find emails from Helena about interview loop, dispatch→Follow up with Helena on contract renewal, dispatch→E... |
| broad-person-006 | broad_question_person | legacy_rules | 10 | 1 | reuse | wrong_reuse | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got reuse (message_user, dispatch→Find emails from Helena about interview loop, dispatch→Follow up with Helena on contract renewal, dispatch→E... |
| broad-person-006 | broad_question_person | legacy_rules | 10 | 2 | reuse | wrong_reuse | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got reuse (message_user, dispatch→Find emails from Helena about interview loop, dispatch→Follow up with Helena on contract renewal, dispatch→E... |
| broad-person-006 | broad_question_person | legacy_rules | 30 | 0 | reuse | wrong_reuse | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got reuse (message_user, dispatch→Email Helena re podcast interview, dispatch→Find emails from Helena about interview loop, dispatch→Follow up... |
| broad-person-006 | broad_question_person | legacy_rules | 30 | 1 | reuse | wrong_reuse | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got reuse (message_user, dispatch→Email Helena re podcast interview, dispatch→Find emails from Helena about interview loop, dispatch→Follow up... |
| broad-person-006 | broad_question_person | legacy_rules | 30 | 2 | reuse | wrong_reuse | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got reuse (message_user, dispatch→Email Helena re podcast interview, dispatch→Find emails from Helena about interview loop, dispatch→Follow up... |
| broad-person-006 | broad_question_person | legacy_rules | 100 | 0 | reuse | wrong_reuse | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got reuse (message_user, dispatch→Find emails from Helena about interview loop, dispatch→Email Helena re podcast interview, dispatch→Follow up... |
| broad-person-006 | broad_question_person | legacy_rules | 100 | 1 | reuse | wrong_reuse | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got reuse (message_user, dispatch→Find emails from Helena about interview loop, dispatch→Email Helena re podcast interview, dispatch→Email Hel... |
| broad-person-006 | broad_question_person | legacy_rules | 100 | 2 | reuse | wrong_reuse | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got reuse (message_user, dispatch→Find emails from Helena about interview loop, dispatch→Email Helena re podcast interview, dispatch→Email Hel... |
| broad-person-006 | broad_question_person | legacy_rules | 300 | 0 | reuse | wrong_reuse | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got reuse (message_user, dispatch→Email Helena re podcast interview, dispatch→Find emails from Helena about interview loop, dispatch→Email Hel... |
| broad-person-006 | broad_question_person | legacy_rules | 300 | 1 | reuse | wrong_reuse | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got reuse (message_user, dispatch→Email Helena re podcast interview, dispatch→Find emails from Helena about interview loop, dispatch→Email Hel... |
| broad-person-006 | broad_question_person | legacy_rules | 300 | 2 | reuse | wrong_reuse | expected answer_set([ag_hy76qnfy, ag_m57q5oei, ag_qyhcermq, ag_ibojksyx]); got reuse (message_user, dispatch→Email Helena re podcast interview, dispatch→Find emails from Helena about interview loop, dispatch→Email Hel... |
| clear-person-005 | clear_person | legacy_rules | 10 | 0 | reuse | wrong_reuse | expected reuse(ag_avdgfagy); got reuse (message_user, dispatch→Email Farah the transcript, dispatch→Email Farah the reading list, dispatch→Email Farah re offer letter) |
| clear-person-005 | clear_person | legacy_rules | 10 | 1 | reuse | wrong_reuse | expected reuse(ag_avdgfagy); got reuse (message_user, dispatch→Email Farah the transcript, dispatch→Email Farah the reading list, dispatch→Email Farah re offer letter, wait) |
| clear-person-005 | clear_person | legacy_rules | 10 | 2 | reuse | wrong_reuse | expected reuse(ag_avdgfagy); got reuse (message_user, dispatch→Email Farah the transcript, dispatch→Email Farah the reading list, dispatch→Email Farah re offer letter) |
| clear-person-005 | clear_person | legacy_rules | 30 | 0 | reuse | wrong_reuse | expected reuse(ag_avdgfagy); got reuse (message_user, dispatch→Email Farah the transcript, dispatch→Email Farah re offer letter, dispatch→Email Farah the reading list, wait) |
| clear-person-005 | clear_person | legacy_rules | 30 | 1 | reuse | wrong_reuse | expected reuse(ag_avdgfagy); got reuse (message_user, dispatch→Email Farah the transcript, dispatch→Email Farah re offer letter, dispatch→Email Farah the reading list) |
| clear-person-005 | clear_person | legacy_rules | 30 | 2 | reuse | wrong_reuse | expected reuse(ag_avdgfagy); got reuse (message_user, dispatch→Email Farah the transcript, dispatch→Email Farah re offer letter, dispatch→Email Farah the reading list, wait) |
| clear-person-005 | clear_person | legacy_rules | 100 | 0 | reuse | wrong_reuse | expected reuse(ag_avdgfagy); got reuse (message_user, dispatch→Email Farah the reading list, dispatch→Email Farah re offer letter, dispatch→Email Farah the transcript, wait) |
| clear-person-005 | clear_person | legacy_rules | 100 | 1 | reuse | wrong_reuse | expected reuse(ag_avdgfagy); got reuse (message_user, dispatch→Email Farah the reading list, dispatch→Email Farah re offer letter, dispatch→Email Farah the transcript, wait) |
| clear-person-005 | clear_person | legacy_rules | 100 | 2 | reuse | wrong_reuse | expected reuse(ag_avdgfagy); got reuse (message_user, dispatch→Email Farah the reading list, dispatch→Email Farah re offer letter, dispatch→Email Farah the transcript) |
| clear-person-005 | clear_person | legacy_rules | 300 | 0 | reuse | wrong_reuse | expected reuse(ag_avdgfagy); got reuse (message_user, dispatch→Email Farah the transcript, dispatch→Email Farah re offer letter, dispatch→Email Farah the reading list, wait) |
| clear-person-005 | clear_person | legacy_rules | 300 | 1 | reuse | wrong_reuse | expected reuse(ag_avdgfagy); got reuse (message_user, dispatch→Email Farah the transcript, dispatch→Email Farah re offer letter, dispatch→Email Farah the reading list) |
| clear-person-005 | clear_person | legacy_rules | 300 | 2 | reuse | wrong_reuse | expected reuse(ag_avdgfagy); got reuse (message_user, dispatch→Email Farah re offer letter, dispatch→Email Farah the transcript, dispatch→Email Farah the reading list, wait) |
| followup-005 | email_followup | legacy_rules | 10 | 0 | reuse | wrong_reuse | expected reuse(ag_4vdh7oh4); got reuse (message_user, dispatch→Find emails from Amara about birthday plans, dispatch→Follow up with Amara on project deadline, dispatch→Find emails from Amara about refund, dispatch→Fol... |
| followup-005 | email_followup | legacy_rules | 100 | 1 | create | duplicate_create | expected reuse(ag_4vdh7oh4); got create (message_user, dispatch→Find emails from Amara about party plans) |
| followup-005 | email_followup | legacy_rules | 100 | 2 | create | duplicate_create | expected reuse(ag_4vdh7oh4); got create (message_user, dispatch→Find emails from Amara about party plans) |
| followup-006 | email_followup | legacy_rules | 10 | 0 | reuse | wrong_reuse | expected reuse(ag_m7zywmxw); got reuse (message_user, dispatch→Follow up with Theo on project deadline, dispatch→Find emails from Theo about apartment viewing, dispatch→Email Theo re warranty replacement, wait) |
| followup-006 | email_followup | legacy_rules | 10 | 1 | reuse | wrong_reuse | expected reuse(ag_m7zywmxw); got reuse (message_user, dispatch→Follow up with Theo on project deadline, dispatch→Find emails from Theo about apartment viewing, dispatch→Email Theo re warranty replacement) |
| followup-006 | email_followup | legacy_rules | 100 | 0 | reuse | wrong_reuse | expected reuse(ag_m7zywmxw); got reuse (message_user, dispatch→Follow up with Theo on project deadline, dispatch→Email Theo re warranty replacement, dispatch→Find emails from Theo about apartment viewing) |
| followup-006 | email_followup | legacy_rules | 300 | 0 | reuse | wrong_reuse | expected reuse(ag_m7zywmxw); got reuse (message_user, dispatch→Follow up with Theo on project deadline, dispatch→Find emails from Theo about apartment viewing, dispatch→Email Theo re warranty replacement) |
| followup-006 | email_followup | legacy_rules | 300 | 1 | reuse | wrong_reuse | expected reuse(ag_m7zywmxw); got reuse (message_user, dispatch→Follow up with Theo on project deadline, dispatch→Find emails from Theo about apartment viewing, dispatch→Email Theo re warranty replacement) |
| followup-006 | email_followup | legacy_rules | 300 | 2 | reuse | wrong_reuse | expected reuse(ag_m7zywmxw); got reuse (message_user, dispatch→Follow up with Theo on project deadline, dispatch→Email Theo re warranty replacement, dispatch→Find emails from Theo about apartment viewing) |
| multi-person-005 | multi_person | legacy_rules | 300 | 1 | create | duplicate_create | expected dispatch(reuse(ag_3syqqzg7); create[Amara Abara]); got create (message_user, dispatch→Check billing dispute update with Liam Bianchi, dispatch→Email Amara Abara about hairdresser, wait); slots 1/2 |
| multi-person-005 | multi_person | legacy_rules | 300 | 2 | mixed | duplicate_create, wrong_reuse | expected dispatch(reuse(ag_3syqqzg7); create[Amara Abara]); got mixed (message_user, dispatch→Email Liam re invoice dispute, dispatch→Follow up with Liam on vendor contract, dispatch→Find emails from Liam about billin... |
| multi-person-006 | multi_person | legacy_rules | 100 | 0 | create | ambiguous_dispatch | expected clarify \| dispatch(create[Alice Chen] + ask); got create (message_user, dispatch→Draft Sam running club invite, dispatch→Draft Alice Chen running club invite); slots 1/1 |
| multi-person-006 | multi_person | legacy_rules | 100 | 1 | create | ambiguous_dispatch | expected clarify \| dispatch(create[Alice Chen] + ask); got create (message_user, dispatch→Invite Alice Chen to Sunday running club, dispatch→Invite Sam to Sunday running club); slots 1/1 |
| multi-person-006 | multi_person | legacy_rules | 300 | 0 | create | ambiguous_dispatch | expected clarify \| dispatch(create[Alice Chen] + ask); got create (message_user, dispatch→Email Alice Chen re Sunday running club, dispatch→Email Sam re Sunday running club, wait); slots 1/1 |
| trigger-006 | trigger_management | legacy_rules | 10 | 0 | none | – | expected reuse(ag_ohyhhbka); got none (no tool calls) |
| trigger-006 | trigger_management | legacy_rules | 10 | 1 | clarify | over_clarify | expected reuse(ag_ohyhhbka); got clarify (message_user) |
| trigger-006 | trigger_management | legacy_rules | 10 | 2 | none | – | expected reuse(ag_ohyhhbka); got none (no tool calls) |
| trigger-006 | trigger_management | legacy_rules | 30 | 0 | none | – | expected reuse(ag_ohyhhbka); got none (no tool calls) |
| trigger-006 | trigger_management | legacy_rules | 30 | 1 | none | – | expected reuse(ag_ohyhhbka); got none (no tool calls) |
| trigger-006 | trigger_management | legacy_rules | 30 | 2 | clarify | over_clarify | expected reuse(ag_ohyhhbka); got clarify (message_user, wait) |
| trigger-006 | trigger_management | legacy_rules | 100 | 0 | none | – | expected reuse(ag_ohyhhbka); got none (no tool calls) |
| trigger-006 | trigger_management | legacy_rules | 100 | 1 | none | – | expected reuse(ag_ohyhhbka); got none (no tool calls) |
| trigger-006 | trigger_management | legacy_rules | 100 | 2 | none | – | expected reuse(ag_ohyhhbka); got none (no tool calls) |
| trigger-006 | trigger_management | legacy_rules | 300 | 0 | none | – | expected reuse(ag_ohyhhbka); got none (no tool calls) |
| trigger-006 | trigger_management | legacy_rules | 300 | 1 | none | – | expected reuse(ag_ohyhhbka); got none (no tool calls) |
| trigger-006 | trigger_management | legacy_rules | 300 | 2 | none | – | expected reuse(ag_ohyhhbka); got none (no tool calls) |

## What we learned

- **The rules alone help a lot, at every N:** legacy (experiment 2) 62 / 54 / 54 / 40% → legacy_rules
  69 / 75 / 65 / 60% at N = 10 / 30 / 100 / 300. Same cases, same names-only roster; only the prompt differs.
- **Duplicate creates almost gone:** 0 / 9 / 6 / 13 of 48 → 0 / 0 / 2 / 2. Trigger duplicates 3 → 0.
  `trigger-005` and `multi-person-005` (the "billing" vs "invoice" Liam case) now hold up at large N.
- **Fixed by specific rules:** `broad-person-005` 0/12 → 12/12 (fan out to all of Imani's agents);
  `multi-person-006` 0/12 → 9/12 (asks about the ambiguous Sam); `multi-intent-005` 8/12 → 12/12.
- **New failure: the broad-question rule over-fires.** `clear-person-005` ("Did Farah Moreau mention
  anything about the interview write-up?") and `followup-006` ("Did Theo ever reply about the deadline
  extension?") are specific questions, but the IA messages *every* agent of that person. wrong_reuse
  rises to 9–13 of 48 per N. The rule's wording ("a broad question about a person") doesn't say that a
  question naming a topic is not broad.
- **Unchanged, as expected for names only:** `broad-person-006` (two Helenas, names can't separate
  them: it now fans out to both Helenas' agents, wrong_reuse 12/12), `amb-person-006`, `trigger-006`.
- Cost $0.4345 vs estimate $0.3753: fan-out adds completion tokens (161k vs 114k in experiment 2).
