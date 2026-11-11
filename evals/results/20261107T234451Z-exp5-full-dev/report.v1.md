# Routing run: exp5-full-dev

## Setup

- **Purpose:** exp5-full-dev
- **Command:** `python -m evals.run routing --split dev --modes full --sizes 10,30,100,300 --runs 3 --max-cost 3 --purpose exp5-full-dev --yes`
- **Date (UTC):** 2026-11-07T23:44:51Z
- **Model:** `anthropic/claude-haiku-5.5`
- **Code:** uncommitted working tree on HEAD 4d629cc
- **Case set:** `evals/cases/v1` (v1), MANIFEST sha256 `688388e57eb5980fa06046a7e384b5449d9b1c71134c817bbf7d20d166fbcbda`, frozen_on 2026-11-07
- **Split:** dev, 16 cases
- **Descriptions (`full`):** regen, sha256 `5d4d6d7c5b20fa1c53c69d280e122d27804833e7dd04ac623bf1e8e1c93ec232`, covering 310/310 world agents
- **Grid:** modes full × sizes 10, 30, 100, 300 × 3 run(s) = 192 case-runs (0 reused from `legacy`: recency at N ≤ 20)
- **Outcome:** 192 graded, 0 infra errors (not graded), 0 skipped by the max-cost cap ($3), 0 retried

## Cost

- Actual: **$1.0913** (estimate before the run: $0.7096)
- Tokens: 10,190,218 prompt / 144,562 completion (all attempts)
- Mean latency per case-run: 5.034 s; mean round trips: 2.318

## Pass rate by mode × N

Infra errors are excluded from the denominators; structural failures count as failures.

| mode | N=10 | N=30 | N=100 | N=300 |
|---|---|---|---|---|
| full | 88% (42/48) | 88% (42/48) | 88% (42/48) | 81% (39/48) |

## Pass rate by category

| category | mode | N=10 | N=30 | N=100 | N=300 |
|---|---|---|---|---|---|
| ambiguous_person | full | 0% (0/6) | 17% (1/6) | 0% (0/6) | 0% (0/6) |
| broad_question_person | full | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |
| clear_person | full | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |
| email_followup | full | 100% (6/6) | 83% (5/6) | 100% (6/6) | 100% (6/6) |
| multi_intent | full | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |
| multi_person | full | 100% (6/6) | 100% (6/6) | 100% (6/6) | 83% (5/6) |
| new_task_lookalike | full | 100% (6/6) | 100% (6/6) | 100% (6/6) | 100% (6/6) |
| trigger_management | full | 100% (6/6) | 100% (6/6) | 100% (6/6) | 67% (4/6) |

## Flags

| flag | mode | N=10 | N=30 | N=100 | N=300 |
|---|---|---|---|---|---|
| dropped_intent | full | 0/48 | 0/48 | 0/48 | 1/48 |
| over_clarify | full | 3/48 | 2/48 | 3/48 | 3/48 |

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

| case | category | mode | N | run | outcome | flags | reason |
|---|---|---|---|---|---|---|---|
| amb-person-006 | ambiguous_person | full | 10 | 0 | none | – | expected clarify; got none (no tool calls) |
| amb-person-006 | ambiguous_person | full | 10 | 1 | none | – | expected clarify; got none (no tool calls) |
| amb-person-006 | ambiguous_person | full | 10 | 2 | none | – | expected clarify; got none (no tool calls) |
| amb-person-006 | ambiguous_person | full | 30 | 0 | none | – | expected clarify; got none (no tool calls) |
| amb-person-006 | ambiguous_person | full | 30 | 1 | none | – | expected clarify; got none (no tool calls) |
| amb-person-006 | ambiguous_person | full | 30 | 2 | none | – | expected clarify; got none (no tool calls) |
| amb-person-006 | ambiguous_person | full | 100 | 0 | none | – | expected clarify; got none (no tool calls) |
| amb-person-006 | ambiguous_person | full | 100 | 1 | none | – | expected clarify; got none (no tool calls) |
| amb-person-006 | ambiguous_person | full | 100 | 2 | none | – | expected clarify; got none (no tool calls) |
| amb-person-006 | ambiguous_person | full | 300 | 0 | none | – | expected clarify; got none (no tool calls) |
| amb-person-006 | ambiguous_person | full | 300 | 1 | none | – | expected clarify; got none (no tool calls) |
| amb-person-006 | ambiguous_person | full | 300 | 2 | none | – | expected clarify; got none (no tool calls) |
| amb-person-007 | ambiguous_person | full | 10 | 0 | clarify | over_clarify | expected reuse(ag_dcl3r2h4); got clarify (send_draft, message_user) |
| amb-person-007 | ambiguous_person | full | 10 | 1 | clarify | over_clarify | expected reuse(ag_dcl3r2h4); got clarify (send_draft, message_user) |
| amb-person-007 | ambiguous_person | full | 10 | 2 | clarify | over_clarify | expected reuse(ag_dcl3r2h4); got clarify (send_draft, message_user) |
| amb-person-007 | ambiguous_person | full | 30 | 0 | clarify | over_clarify | expected reuse(ag_dcl3r2h4); got clarify (send_draft, message_user) |
| amb-person-007 | ambiguous_person | full | 30 | 1 | clarify | over_clarify | expected reuse(ag_dcl3r2h4); got clarify (send_draft, message_user) |
| amb-person-007 | ambiguous_person | full | 100 | 0 | clarify | over_clarify | expected reuse(ag_dcl3r2h4); got clarify (send_draft, message_user) |
| amb-person-007 | ambiguous_person | full | 100 | 1 | clarify | over_clarify | expected reuse(ag_dcl3r2h4); got clarify (send_draft, message_user) |
| amb-person-007 | ambiguous_person | full | 100 | 2 | clarify | over_clarify | expected reuse(ag_dcl3r2h4); got clarify (send_draft, message_user) |
| amb-person-007 | ambiguous_person | full | 300 | 0 | clarify | over_clarify | expected reuse(ag_dcl3r2h4); got clarify (send_draft, message_user) |
| amb-person-007 | ambiguous_person | full | 300 | 1 | clarify | over_clarify | expected reuse(ag_dcl3r2h4); got clarify (send_draft, message_user) |
| amb-person-007 | ambiguous_person | full | 300 | 2 | clarify | over_clarify | expected reuse(ag_dcl3r2h4); got clarify (send_draft, message_user) |
| followup-006 | email_followup | full | 30 | 0 | none | – | expected reuse(ag_m7zywmxw); got none (no tool calls) |
| multi-person-006 | multi_person | full | 300 | 2 | none | dropped_intent | expected clarify \| dispatch(create[Alice Chen] + ask); got none (no tool calls); slots 0/1 |
| trigger-006 | trigger_management | full | 300 | 0 | none | – | expected reuse(ag_ohyhhbka); got none (no tool calls) |
| trigger-006 | trigger_management | full | 300 | 1 | none | – | expected reuse(ag_ohyhhbka); got none (no tool calls) |

## What we learned

- **Purpose:** Experiment 5, plan Task 13a. `full` mode: every roster agent rendered as a card (id, regenerated
  description, contacts, active triggers) through the production ids prompt, message builder and
  `TOOL_SCHEMAS`. Same grid as experiment 4 (dev, N = 10/30/100/300, 3 runs, Haiku). `full` is the ceiling
  `hybrid` must approach. Descriptions: `descriptions.regen.json` (310/310 agents, regen cost $0.0208). The
  ids prompt no longer has the "answer broad status questions from descriptions first" line.
- **full vs legacy_rules (experiment 4):** **88 / 88 / 88 / 81%** vs 79 / 75 / 65 / 67% at N = 10 / 30 / 100 / 300.
  It degrades far less with N: −7 points from 10 to 300, against −12 for legacy_rules and −22 for legacy
  (experiment 2). Caveat: `trigger-006` was reworded after experiment 4 (see `changes.md`). The two runs
  differ by that one case.
- **The names-only failures are fixed:**
  - **Two Helenas (`broad-person-006`):** 12/12, was 0/12. With contacts on the cards, the IA picks only the
    Helena Rossi agents.
  - **Transcript vs write-up (`clear-person-005`):** 12/12, was 4/12 (3/3 at N=10, 1/9 at N ≥ 30). The
    description links "transcript" to the interview.
  - **`clear_person`:** 100% at every N.
  - **`multi_person`:** 100 / 100 / 100 / 83%.
  - **Flags:** duplicate_create 0 at every N (was 0 / 3 / 5 / 7 of 48); wrong_reuse 0 (was 6 per N).
- **Two Daniels (`amb-person-006`):** 0/12. This is a grader gap, not a model failure. Every run asks the right
  question ("Do you mean Daniel Walsh (lab results and the NDA) or Daniel Kaplan (the conference schedule)?"),
  but as plain assistant text with no `send_message_to_user` call. Production sends that text to the user
  (`runtime.py:104`, `record_reply` when there are no user messages). The grader's clarify check reads only
  `send_message_to_user` and `user_messages`, never `final_text`, so it grades the reply as "none".
  - Counting a text-only final reply as a user message would pass all 12 runs. Full would then score
    **94 / 94 / 94 / 88%**.
  - It changes no legacy or legacy_rules verdict: every text-only reply in experiments 1–4 is a
    `trigger-006` question, where a reuse is expected.
  - Not applied. It is a grading change, so it waits for Siddharth.
- **New failure, `amb-person-007` (1/12, was 11/12):** the cards show Farah Kowalski's email, so the IA
  writes the reply itself (`send_draft` + "want me to send it?") instead of handing it to the agent that owns
  the offer-letter thread. It is graded over_clarify. Seeing contact addresses tempts the IA to skip the
  thread's agent. A prompt or card question for Task 13: the reply should go in the existing thread.
- **Other failures (1–2 runs each):**
  - `followup-006` N=30: answered "did Theo reply?" from the description instead of asking the agent to
    look, although the user said "Can you look?".
  - `trigger-006` N=300 (2/3): asks which reminder.
  - `multi-person-006` N=300 (1/3): asks "which Alice", although the user said Alice Chen.
- **Regen artefact:** descriptions of agents with only a trigger (e.g. "Nightly receipt summary") say "there
  is no previous description, no contacts…". That is updater-prompt wording leaking into the description:
  harmless here, but worth a line in the updater prompt.
- **Tokens (what full really costs):**

  | N | prompt tokens per case-run (measured) | rough table (×1.6) | ratio |
  |---|---|---|---|
  | 10 | 18,009 | 12,320 | 1.46 |
  | 30 | 24,936 | 16,480 | 1.51 |
  | 100 | 51,878 | 31,840 | 1.63 |
  | 300 | 117,473 | 75,200 | 1.56 |

  - Completion: 753 per case-run.
  - The pre-run estimate was $0.71; the actual was $1.09 (1.54×), all from the rough `full` table.
  - The table is now updated to these measured values (`changes.md`).
- **Final-run budget projection (Sonnet 5.5 at $2 / $10 per MTok; test split 33 cases × 2 runs; modes
  legacy, recency, full, hybrid × N = 10/30/100/300):**
  - Assumptions: legacy measured (experiment 2); `recency` reuses legacy at N=10 and is ~11.6k elsewhere;
    `hybrid` is ~18k per case-run (≈ full at N=10: k ≤ 10 cards plus a search round trip); both are unmeasured.
  - Per case per run: ≈ $0.76 prompt + $0.11 completion ≈ **$0.87**, so ≈ **$57** for the run, against
    ≈ $47.6 left (spent so far ≈ $2.40).
  - `full` alone is ≈ $29 of it, and `full` N=300 alone is ≈ $16.
  - **The planned final run does not fit the budget.** The scope's $29 assumed 47k tokens at N=300; measured
    is 117k.
- Cost $1.0913 (estimate $0.7096). 0 infra errors.
