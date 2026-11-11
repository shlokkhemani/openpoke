# Timeline: agent overload experiments

The question throughout: as the number of agents N grows, does the interaction agent (IA) still route each
request to the right agent, create a new one, or ask? All runs are on the dev split (16 cases), with Haiku 5.5 for
the routing runs. Costs are in USD. Run folders are under `evals/results/` and are named by timestamp here. Details
are in each run's `report.md` and in `changes.md`. To keep the repo small, only the final test run and Exp 5 (a test
fixture) keep their per-request transcripts, only the final test-split retrieval runs keep `queries.jsonl`, and hashing-embedder runs are
not kept. Every run's `report.md` and `summary.json` remain.

**Terms**
- **Layer 1** is the offline retrieval eval (free): are the expected agents in the top 20? **Layer 2** is the paid
  routing eval: the real IA loop, with outcomes graded from its tool calls.
- **Modes**
  - `legacy`: the original prompt with a names-only roster.
  - `legacy_rules`: the same roster, with the new routing rules in the prompt.
  - `full`: every agent shown as a card (id, description, contacts, triggers).
  - `hybrid`: the 20 cards retrieval ranks highest, plus a `search_agents` tool.
- **Case sets**
  - v1: 49 cases.
  - v2: the same cases, with realistic agent-backed history.
  - Dense world: a layer-1-only stress roster. Two people each own an agent on the same 48 topics, and the
    queries are paraphrased or name no one.
- **Embedders:** fastembed is production. Hashing is a test stand-in, and its results are informational only.

## 1. Showing the problem (2026-11-07)

**Exp 1–2: `legacy` scaling** (`095436Z`, `101232Z`; 0.41, personal key)
- Pass rate by N (10/30/100/300): 62 / 54 / 54 / 40%.
- The cause is duplicate agents: 0/48 duplicate creates at N=10, 13/48 at N=300.
- Broad questions fail at every N.
- Calibrated the cost estimator; the first estimate was 1.6× low.

## 2. Routing rules on a names-only roster (2026-11-07 to 2026-11-08)

**Exp 3–4: `legacy_rules`** (`193744Z`, `195430Z`; 0.86, personal key)
- 69 / 75 / 65 / 60% in Exp 3, then 79 / 75 / 65 / 67% in Exp 4, after narrowing the broad-question rule
  (it had been firing on specific questions).
- Duplicate creates nearly gone.
- **Still weak:** two Daniels, two Helenas, "transcript" vs "write-up". A names-only roster can't separate them.

**Exp 8: names prompt made parallel to the ids prompt** (`084317Z`; 0.44)
- 83 / 79 / 73 / 75%.
- Isolates the cost of a names-only roster: the remaining failures are the cases names can't disambiguate.

## 3. The `full` ceiling (2026-11-07 to 2026-11-08)

**Exp 5: `full`, first run** (`234451Z`; 1.09, personal key)
- 94 / 94 / 94 / 90% after a grader fix: text-only clarifying replies now count.
- Fixed the names-only failures.
- **Still weak:** the IA wrote one email itself (`amb-person-007`). The final run would cost about 57 against
  about 48 left.

**Exp 6–7: ids-prompt fixes** (`000924Z`, `003748Z`; 2.17, Exp 6 on the personal key)
- Added three prompt rules: never write emails yourself; a pronoun right after an agent's message refers to that
  agent; reply only on existing threads.
- Exp 6: 96 / 98 / 100 / 94%. Exp 7: 100% at every N.
- **Caveat:** these rules were written against dev failures, so the untouched test split is the real check.

## 4. Retrieval, layer 1 (2026-11-08 to 2026-11-09)

**Task 12: first retrieval runs, top 5 with boosts** (`103943Z`, `104553Z`; free)
- recall@5 with fastembed 0.89–0.94. Boosts added nothing.
- Every miss was a first name shared by two people, where the top 5 missed the second candidate.
- **Changed:** retrieval simplified to BM25 + embeddings fused with RRF, top 20, last exchange as history.

**Task 12b/13: simplified retrieval** (`175932Z`, `180051Z`; free)
- recall@20 1.00 / 1.00 / 1.00 / 0.96.
- **Still weak:** history pulls the query toward the old topic (`unrelated_history` at N=300).

**Task 12c: dense stress world** (`190350Z`…`192429Z`; 0.005 for paraphrases)
- Paraphrased requests (`target_para`): recall@20 0.67 / 0.67 / 0.72.
- Requests that follow a report about the other person (`history_pull`): 0.22 / 0.11 / 0.13. After an agent
  reports on person A, a request about person B retrieves A's agents.
- Fixed three eval-set defects along the way.
- **Ruling:** retrieval left unchanged for now, relying on `hybrid`'s search tool.

## 5. `hybrid` end to end (2026-11-09)

**Task 14 smoke** (`194841Z`; 0.20)
- The plumbing works.
- `hybrid` 100% at N=10/30.
- Cut the hybrid cost factor from 1.5 to 1.1.

**Task 15: `full` vs `hybrid` at N=100/300** (`200608Z`; 1.15)
- `full` 100 / 100%. `hybrid` 100 / 94%.
- The one failure: `multi-person-006` at N=300. Sam Okafor's agents fell outside the top 20, so the IA saw one Sam
  and emailed the wrong one.
- `hybrid` uses 0.17× the prompt tokens of `full` at N=300.
- The search tool never rescued a miss: the model only searches when it knows something is missing.
- **Changed:** the case's history ("Is it going to rain in Seattle?") was unrealistic, which led to case set v2.

## 6. Case set v2 and history-robust retrieval (2026-11-09 to 2026-11-10)

**Task 16: v2 baseline** (layer 1 `214830Z`/`215151Z`; layer 2 `214557Z`, 1.54)
- `full` 100% at every N.
- `legacy_rules` 83 / 85 / 81 / 77%: the same names-only failures as on v1.
- `multi-person-006` is still outside the top 20 at N=300.

**Task 16e: BM25 drops stopwords** (`222346Z`…`222656Z`; free)
- Headline unchanged.
- `multi-person-006` not fixed: Sams at 16/23/53. v2's history words ("Noor replied that the slot is confirmed")
  match many agents and outvote the message.

**Exp 16f: five fusion variants** (scratch; free)
- Compared five ways of weighting the message above history.
- Variant A3 adds BM25 and embedding rankings on the message alone:
  - Sams at 3/4/11;
  - dense `history_pull` .20 → .77;
  - no fastembed guard tripped.
- **Ruling:** guards judged on fastembed only. A3 adopted.

**Task 16f: A3 in production** (`235838Z`, `000139Z`, `000150Z`, `000155Z`; free)
- Reproduces the scratch runs byte for byte.
- v2 headline 1.00 at every N. Template N=300 .842 → .900.
- Dense `history_pull` .76 / .76 / .78, `target_para` .72 / .72 / .78.
- With BM25 only (the fallback when fastembed is unavailable, scratch): A3 is level or better in every group.

**Task 16f: `hybrid` on v2** (`000801Z`; 0.47)
- 100% at every N, including `multi-person-006`.
- Target in the initial 20 cards in 180/192 case-runs. The misses still passed.
- Cost per case-run is flat in N: about a fifth of `full` at N=300.

**Task 16g: surname-only clarifying questions accepted** (grader; free)
- `clarify_named_ok` now counts "Kaplan or Walsh?" as naming both candidates (Siddharth's ruling). Pass rates
  are unaffected.

**Clarify-answer probe** (scratch; free)
- One-word replies to "Which Sam/Daniel?" at N=300. Surnames put the chosen agent at #1.
- "The second one" drops the candidates to #5–9, still in the top 20.

## 7. Test split (2026-11-10, frozen at `39a1439`)

`39a1439` and the other commit hashes recorded in run reports are from the local development history, which was
squashed before publishing. The server code, eval code, tests and cases in this commit are identical to `39a1439`,
so the test-split runs below used exactly this code.

**Layer 1 on test** (`062643Z`, `063013Z`, `063023Z`, `063028Z`; free)
- v2 fastembed headline: 1.00 / 1.00 / 0.95 / 0.90 (dev was 1.00 at every N).
- Two real misses at N=300:
  - `amb-person-005`: "Email her…", where the only mention of Alice is outside the 2-item history window.
  - `trigger-001`: "evening email recap" vs "Nightly digest", a paraphrase.
- Dense test scores are higher than dev: `target_para` and `history_pull` .85. Names-free questions are still
  weak: `topic_noname` .44 at N=300.

**Final routing run on test** (`193519Z`; 4.12, Haiku)
- Pass rate (N=10/30/100/300):
  - `legacy_rules` 80 / 76 / 74 / 63%;
  - `full` 94 / 93 / 93 / 93%;
  - `hybrid` 96 / 98 / 96 / 97%.
- Most of `full`'s failures are two cases, `amb-person-003` and `amb-person-005`. There `full` resolves "Alice"/"her"
  from two exchanges back, while the cases require asking. Without those two cases, `full` passes 98.0% and
  `hybrid` 98.5%.
- `hybrid`'s edge on `amb-person-005` is partly a retrieval artifact: at large N it can't see the Alice cards, so it
  asks.
- `hybrid`'s one retrieval failure: `trigger-001` at N=300. "Evening recap" vs "Nightly digest" isn't in the 20
  cards. It asked which recap rather than acting, a safe failure.

## Where things stand

- **Production:** `hybrid` by default, with A3 retrieval. k=20, rrf_k=60, history_turns=2.
- **Routing on the test split** (Haiku, N=10/30/100/300):
  - `hybrid` 96 / 98 / 96 / 97%;
  - `full` 94 / 93 / 93 / 93%;
  - `legacy_rules` 80 / 76 / 74 / 63%.
  - Without the two "last exchange only" Alice cases, `hybrid` and `full` are level at about 98%.
  - `hybrid` costs about a fifth of `full` at N=300.
- **Weakest retrieval** (dense, fastembed, N=300): questions that name no person, 0.24 on dev and 0.44 on test.

## Open threads

- **`full` vs `hybrid` stress test:** v2 dev saturates at 100% for both, so it can't separate them. The plan is a
  set of multi-turn sessions at N=100/300 (FUTURE_WORK §2).
- **Search tool:** it has never found a target the initial cards missed.
- **"Last exchange only" rule:** `amb-person-003` and `amb-person-005` expect a clarifying question when the person
  was named two exchanges back. `full` resolves the person instead. Decide whether the rule or the IA is right.
- **Clarify follow-ups:** no case tests the turn after a clarifying question. An agent report arriving between
  the question and the answer could push the request out of the 2-item history window.
- **Option B (query rewriting):** not measured (FUTURE_WORK §1).
- **Test split and final report:**
  - The test split has never been run.
  - The final-run estimate (about 41, 2026-11-08) predates dropping `recency` and needs redoing.
  - `evals/report.py` (Task 15) and the smoke test (Task 17) are not built.

## Spend (company key, SPEND.md)

8 paid runs, 9.00 billed of 50; 41.00 left. A further 4.17 on a personal key covers Exp 1–6 and setup.
