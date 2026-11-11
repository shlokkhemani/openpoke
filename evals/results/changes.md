# Changes

Every change to a grading rule or a retrieval value, with the specific **dev** failure that motivated
it (plan Global Constraints: no weight tuning). Newest first.

## 2026-11-09: recency dropped; production modes full/hybrid

- **What changed.** The `recency` roster mode and the eval reuse mechanism that existed only for it are removed.
  `evals/grading.py`: `ROSTER_MODES = ("legacy", "full", "hybrid")`, `recency` out of `NAME_DISPATCH_MODES`.
  `evals/routing_run.py`, `report_run.py`, `run.py`: `RECENCY_CUTOFF`, `REUSE_SOURCE`, `CaseRun.reuse_source`,
  `Estimate.reused`, `reused_from`, the summary's `reused*` counts and `recency_cutoff`, and the price-table
  entry. Reading `reused_from` from old rows stays tolerant (`run_store`, `inspect_export`). Production modes are
  now `full` and `hybrid` (default `hybrid`); `legacy` and `legacy_rules` are eval-only baselines. The final grid
  becomes `legacy_rules,full,hybrid`.
- **Why.** Siddharth's decision, 2026-11-09. `recency` never ran in any past result folder, so no result changes.
- **Effect on earlier runs.** None; existing run folders are untouched.
- **Test split:** not run.

## 2026-11-09: retrieval simplified to BM25+embeddings RRF, K=20, last exchange

- **What changed.** `server/services/agents/retrieval.py`: ranking is BM25 + embeddings fused by RRF (k=60), top 20.
  The query is the last exchange (2 history items) plus the message. Referenced agent ids from that exchange are
  always appended, uncapped. Removed: contact/recency/trigger boosts, person expansion, all name detection
  (`COMMON_WORDS`, `_people_in_query`), `max_k`, the ablation flags and the `now` / `active_trigger_ids`
  parameters. `RetrievalConfig` keeps `k=20`, `rrf_k=60`, `history_turns=2`; `Settings` keeps the matching three
  `retrieval_*` fields. The Layer-1 eval has one configuration, `KS=(5,10,20)`, headline recall@20 (person cover for
  `both_candidates`), no lowercase group, and a new `unrelated_history` group. The write-up of the removed design
  is `docs/design/retrieval-boosts.md`.
- **Why.** Task 12 dev results: with fastembed at N=300, `rrf` and `rrf_boosts` score the same (0.97 templates,
  0.89 frozen), so the boosts bought no recall; they only shortened the list. They rested on fragile name
  detection, and person expansion never fires for ambiguous first names. K=20 is reasoned, not tuned: one person
  can have 6-7+ agents, it matches the `recency` cutoff of 20, and the IA handled 300 agents in `full` mode.
- **Effect on earlier runs.** The two Layer-1 runs (`20261108T103943Z-...-hashing`, `20261108T104553Z-...-fastembed`)
  used the old configuration (K=5, 4 history items, boosts), so they cannot be compared directly with new runs.
- **Test split:** not run.

## 2026-11-08: retrieval person detection judged per word, not per line

- **What changed.** `server/services/agents/retrieval.py` (`_people_in_query`): capitalisation is judged per
  token, not per line. The first token of each sentence (line start, or after `.`, `?`, `!` plus whitespace)
  is sentence-initial and its case carries no information. A line is all-lowercase if no other token except
  "I" has an uppercase letter. 2-3-token display names match in any case. A 1-gram counts if it is
  capitalised and not sentence-initial; a sentence-initial token or a token on an all-lowercase line counts
  only if it is not in the new fixed `COMMON_WORDS` list (about 100 words, not tuned). Weights unchanged.
- **Why (not a dev failure).** Branch review 1, I1. Under the per-line rule `"Did dana reply?"` found no
  person (false negative) and `"Will you check the budget report?"` boosted Will Varga and dropped the budget
  agent (false positive). Design change approved by Siddharth; supersedes the "Capital rule" bullet of the
  Task 11 design.
- **Effect on earlier runs.** None: no paid run used retrieval yet; layer 1 (Task 12) has not run.
- **Test split:** not run.

## 2026-11-08: names prompt made parallel to the ids prompt

- **What changed.** `server/agents/interaction_agent/prompt_tools_names.md`: the names block now carries the
  same rules as the ids block (reuse rule reworded in the same shape, "never write an email yourself",
  pronoun rule), differing only in tool wording (`agent_name`), minus the `agent_id`-or-`name` rule and the
  agent-cards sentence. A test enforces the parity (names block == mechanical transform of the ids block).
- **Why (not a dev failure).** Fairness of the `legacy_rules` vs `full` comparison (Siddharth, 2026-11-08):
  since experiments 6-7 the ids prompt had two rules the names prompt lacked, so a gap between the modes
  would partly measure prompt rules, not the roster.
- **Effect on earlier runs.** `legacy_rules` experiments 3-4 used the old names prompt and are not comparable
  to later runs; the ids and legacy prompts are unchanged. Checked by experiment 8: legacy_rules 83 / 79 / 73 / 75% on dev (149/192), 0 infra errors.
- **Test split:** not run.

## 2026-11-08: ids prompt - pronoun after an agent's message; reply rule limited to existing threads

- **What changed.** `server/agents/interaction_agent/prompt_tools_ids.md`: the 4th bullet now says to reply
  to or follow up on an email an agent already handled by sending the instructions to that agent's
  `agent_id`, and that a new email on a new topic needs a new agent even when an existing agent already
  emails the same person. A 5th bullet says that a message right after an agent's message that refers to it
  with "this", "that" or "it" means that agent: send the request to its `agent_id` without asking which one.
- **Why (dev failure).** Experiment 6: `trigger-006` ("Could you push this back by an hour?" right after the
  Subscription audit reminder agent's message) asked "which one?" in 5/12 runs although it named the right
  reminder. `multi-person-006` N=10 reused Alice's Q3-budget agent (`ag_chen_budget`) for a new
  running-club email (1/12).
- **Effect on earlier runs.** Ids prompt only; the names and legacy prompts are unchanged. Verified by
  experiment 7 (controller).
- **Test split:** not run.

## 2026-11-07: grader counts a text-only final reply as a user message

- **What changed.** In `evals/grading.py`, `_user_texts` now includes `record.final_text` when the turn
  sent no user message (`user_messages` empty, no `send_message_to_user` call) and the text is non-blank,
  the same condition production uses to deliver the last assistant text. With any user message,
  `final_text` is not added. Applies to every mode. `asked`, `clarify_named_ok`, the clarify / answer_set
  outcome kinds and failure reasons all read it.
- **Why (dev failure).** Experiment 5, `amb-person-006` ("Has Daniel gotten back to you yet?"): failed 12/12
  although every run asked "Do you mean Daniel Walsh ... or Daniel Kaplan ...?", in plain text, so the
  grader saw no user message and graded "none".
- **Effect on earlier runs.** Experiment 5 is regraded (controller does it). Experiments 1-4 cannot be
  regraded against the live case set (the manifest changed with the trigger-006 rewording); in them every
  text-only reply was a trigger-006 question whose label is reuse, so their verdicts would not change.
- **Test split:** not run.

## 2026-11-07: ids prompt - never write emails yourself

- **What changed.** `server/agents/interaction_agent/prompt_tools_ids.md` has a 4th bullet: never write an
  email yourself; `send_draft` only shows a draft an agent wrote; reply to or follow up on an email by
  sending instructions to the `agent_id` of the agent that handled the thread; addresses on the cards are
  for picking the agent, not for emailing directly.
- **Why (dev failure).** Experiment 5, `amb-person-007` ("Let her know I appreciate it ...", expected
  `reuse(ag_dcl3r2h4)`): failed 11/12. The card shows Farah's address, so the IA wrote the email itself
  with `send_draft` and "want me to send it?" instead of dispatching to the thread's agent.
- **Effect on earlier runs.** Ids prompt only (full / production ids mode); the names and legacy prompts
  and the shared `system_prompt.md` are unchanged. Verified by experiment 6 (controller).
- **Test split:** not run.

## 2026-11-07: `full` cost table set to measured values

- **What changed.** In `evals/routing_run.py`, `PROMPT_TOKENS_PER_CASE_RUN["full"]` is now the measured
  `{10: 18009, 30: 24936, 100: 51878, 300: 117473}` (was the rough table x 1.6: 12320 / 16480 / 31840 /
  75200). `adaptive` (the dearer of full and hybrid per N) follows it.
- **Why.** Experiment 5's actual cost was $1.0913 against an estimate of $0.7096 (1.54x low); measured over
  rough per-turn tokens was 1.46 / 1.51 / 1.63 / 1.56 at N=10 / 30 / 100 / 300.
- **Effect.** Cost estimates and the spend cap only; no grading rule or retrieval value changed.
  `recency` and `hybrid` are still the rough table x 1.6.

## 2026-11-07: case `trigger-006` reworded, "these" → "this"

- **What changed.** In the frozen set `evals/cases/v1/`, `trigger-006`'s message is now "Could you push
  this back by an hour?" (was "these"); `original_message` likewise; the generator template in
  `evals/expand.py` too. Label unchanged: `reuse(ag_ohyhhbka)`. Its sha256 is updated in `MANIFEST.json`,
  which records the change under `amendments`. The paraphrase checks pass on the new wording.
- **Why (dev failure).** Experiments 2–4: the conversation shows one reminder, but the plural "these"
  made the IA either reschedule every reminder and summary (legacy, up to six agents) or ask "just the
  subscription audit reminder, or all of them?" (legacy_rules). The question is reasonable for a plural
  pronoun, so the reuse-only label graded a fair answer as wrong. Decided by Siddharth.
- **Effect on earlier runs.** The MANIFEST sha256 is now
  `688388e57eb5980fa06046a7e384b5449d9b1c71134c817bbf7d20d166fbcbda` (was `eb5f510b…`), so experiments 1–4
  can no longer be regraded against the live set (regrade refuses, by design: they ran the old wording).
  Their results stand as recorded; trigger-006 is compared only from experiment 5 on.
- **Test split:** not run.

## 2026-11-07: broad-question rule limited to questions with no topic

- **What changed.** In `system_prompt.md`, "Broad questions": a question is broad only if it names a
  person but no specific topic; a question that names a topic goes only to that topic's agent.
- **Why (dev failures).** Experiment 3 (`20261107T193744Z-experiment-3-legacy-rules-new-routing-ru`,
  legacy_rules): the fan-out rule fired on specific questions. `clear-person-005` ("Did Farah Moreau
  mention anything about the interview write-up?") messaged all three Farah agents in 12/12 runs, and
  `followup-006` ("Did Theo ever reply about the deadline extension?") messaged all three Theo agents,
  flagged wrong_reuse in 6/12. Not rerun yet.
- **Test split:** not run.

## 2026-11-07: routing rules added to `system_prompt.md`; new eval mode `legacy_rules`

- **What changed.** `server/agents/interaction_agent/system_prompt.md` (production) gets the design §4.2
  rules ahead of Task 9: the reuse rule rewritten ("same task, or same person and thread"; the old
  "Don't worry if the agent name is unrelated" line removed), one dispatch per atomic operation, the
  same-first-name ask rule with the last-exchange exception and no assume-and-proceed, partial
  ambiguity, broad questions, and the general clarify rule. `system_prompt_legacy.md` keeps the
  original byte for byte (a test pins its sha256). New eval-only mode `legacy_rules`: exactly
  `legacy` (names-only roster, `agent_name` tool) except for the system prompt, so legacy → legacy_rules
  measures the rules alone and legacy_rules → full measures ids and agent cards.
- **Not from the design text, written for a names-only roster:**
  - "check the active agents for one that already handles this person and task before creating".
    Dev failure: duplicate creates in experiment 2 (0/48 at N=10, 13/48 at N=300), e.g.
    `followup-005` at N=300.
  - Broad questions say "message every existing agent that involves that person" instead of the
    design's "answer from the candidates' descriptions first", because names-only mode has no
    descriptions. Dev failure: `broad-person-005` ("Anything new with Imani?") reused one agent or
    created "Imani latest updates" in all 12 runs of experiment 2 while all five Imani agents were
    named in the roster. Task 9 restores the descriptions-first wording for `full`/`hybrid`.
- **Grader.** Unchanged rules. `classify` now grades every names-dispatch mode (`legacy`, `recency`,
  `legacy_rules`) by `agent_name`; before, only `legacy` was (recency had not run yet).
- **Test split:** not run.

## 2026-11-07: `reuse(id)` no longer checks `expect_person`

- **What changed.** In `evals/grading.py`, a `reuse(id)` outcome passes on the dispatch structure
  alone (dispatched to `id`, created nothing, no other existing id). `expect_person` no longer
  affects pass/fail on a reuse; `person_ok` is still computed and reported for information, and
  failure reasons cite it only when a `create` outcome is acceptable. An `@person` on a reuse slot of
  a `dispatch` outcome is likewise ignored, so a one-slot dispatch still grades exactly like
  `reuse(id)`. `create` + `expect_person` is unchanged: there a wrong person is a real risk. Plan
  text amended in Task 3, "Grading rules". Same reasoning as ruling R23 for multi-dispatch slots.
- **Why (dev failures).** Run `evals/results/20261107T095436Z-milestone-a-does-legacy-degrade-from-n-1/`
  (legacy, Haiku, 16 dev cases, N=10 and 300). In 4 of its 20 failing case-runs the IA reused the
  **correct** agent by its exact name, but its instructions used only the first name, so the
  full-name-or-email rule failed them:
  - `amb-person-007` N=10 ("Farah", expected Farah Moreau)
  - `followup-005` N=10 ("Amara", expected Amara Abara)
  - `followup-006` N=10 and N=300 ("Theo", expected Theo Brennan)

  The reused agent already holds the thread and the address, so these are grader false negatives,
  not routing mistakes.
- **Effect on experiment 1 (dev, from `python -m evals.run regrade`, no LLM calls).** Before:
  legacy N=10 38% (6/16), N=300 38% (6/16). After: legacy N=10 **56% (9/16)**, N=300 **44% (7/16)**.
  `followup-005` at N=300 stays a failure (it created a duplicate agent).
- **Baselines** (frozen v1 set, all 49 cases, N = 10 / 30 / 100 / 300): oracle 49/49 at every N;
  always_create 10/49 and always_ask 4/49, unchanged. always_reuse_top by recency goes from 0/49 to
  1/49 at N=10 and N=30 (unchanged 0/49 at N=100 and 300): at those sizes the most recent agent
  happens to be the right one for `followup-006`, whose message says only "Theo".
- **Test split:** not run. Only dev results have been looked at.

## 2026-11-09: dense-person stress roster + name-overlap baseline (eval set addition; no retrieval value changed)

- **What.** A second retrieval world with two heavy contacts (48 agents each, same 48 topics) built on top of the
  frozen base world (`evals/world/dense.py`), topic paraphrases from `stress-paraphrase` (leak-checked), a
  name-overlap baseline (`base@20`) in every retrieval report, and `python -m evals.run retrieval --world dense`.
- **Why.** Base-world recall@20 of 1.00/1.00/1.00/0.96 does not test a heavy user: a person's whole cluster fits in
  the top 20. The dense roster makes the right agent win inside its own cluster.
- **Unchanged.** `RetrievalConfig`, `retrieval.py`, `world.json`, `cases/v1`, all earlier result folders. Existing
  cell values are identical (a test pins them); cells only gain a `baseline` key.

## 2026-11-09: dense stress fixes — topic-free history_pull history, template article fix, tokenizer keeps one-character tokens (eval set fix; no retrieval value changed)

- **Why.** The first dense runs showed three artifacts: history_pull (0.83) scored above target_para (0.73) because
  the last exchange repeated the topic's own words ("replied that the menu is locked in"), which let BM25 match both
  people's same-topic agents; templates wrote "the {topic}" so paraphrases that start with an article produced
  "regarding the the ..."; and the tokenizer dropped one-character tokens, so "that W-9 thing" passed the leak
  check against `w-9 form`. The history is now "{Name} got back to you." (same agent id, no topic words), templates take
  a bare topic (target_exact fills "the <short>"), and `evals.textwords` keeps one-character tokens unless they are
  stopwords. `RetrievalConfig`, `retrieval.py`, `world.json`, `cases/v1` and `dense_paraphrases.json` untouched.

## 2026-11-09: harness runs full/hybrid through build_turn_inputs; search core extracted (no behaviour change)

- **What.** The routing harness builds a temp `AgentStore` per case-run and calls production `build_turn_inputs` for
  `full` and `hybrid`. `search_agents` in `hybrid` is served by `search_agents_result`, a pure core extracted from
  the production tool (same output; the production tool keeps its once-per-turn budget). New flag
  `routing --embedder fastembed|hashing` (default fastembed, recorded in `summary.json`); hybrid estimate is the
  `full` estimate at min(N, 20) × 1.5. Reports gain search rate, search errors and target-in-initial-20.
- **Why.** Retrieval stays fixed (Siddharth, option 3 after the dense eval); `hybrid` relies on `search_agents` for
  the misses, so the eval has to run the real tool to measure it.
- **Unchanged.** `full` prompt, message and tool schemas are byte-identical to the old `render_full_roster` path for
  every v1 case at N = 10, 30, 100, 300 (a test pins it), so Experiment 7 stays comparable. `RetrievalConfig`,
  `retrieval.py`, `world.json`, `cases/v1` and earlier result folders untouched.

## 2026-11-09: hybrid estimate factor 1.5 → 1.1 (measured)

- **What.** `HYBRID_SEARCH_FACTOR` in `evals/routing_run.py` is 1.1 (was 1.5). The `hybrid` estimate per case-run is
  the `full` estimate at min(N, 20) × 1.1.
- **Why.** The Task 14 smoke (`20261109T194841Z-task-14-smoke-legacy-full-hybrid-on-the`) measured `hybrid` at
  18,096 / 22,191 prompt tokens per case-run at N = 10 / 30, against `full`@min(N, 20) of 18,009 / 21,472
  (×1.00–1.03; it searched in 1 of 32 case-runs). ×1.5 over-estimated by about 45%, which inflated printed
  estimates and `--max-cost` reservations. ×1.1 leaves headroom for more searching at N ≥ 100. PROVISIONAL until
  recalibrated from the Task 15 dev check (N = 100 / 300).
- **Unchanged.** Every other estimate, the prompts, the harness, `world.json`, `cases/v1` and earlier result
  folders.

## 2026-11-09: case set v2: in-product agent-backed history

- **What.** New frozen case set `evals/cases/v2` (49 cases, built by `python -m evals.run build-cases-v2` from frozen
  v1, $0, no API calls). The 38 cases whose `ia_history` contained an off-product pair (7 user lines: weather, rain,
  flight, unit conversion, and three calendar questions) get one agent-backed exchange per pair, in the same position:
  an email thread ("Any news from {Name} on {topic}?" → agent update → assistant summary) or a trigger report led by a
  user line that names no one ("Did any of my reminders go off?" → reminder/summary → assistant relays it).
  `ambiguous_person` gets trigger reports only, `trigger_management` email threads only. The agent is a world filler
  that shares no name, email or topic word with the case; it is listed in the new `Case.context_agents`, always in the
  roster, never in the labels. The two generic pairs ("Thanks, that's all for now.", "What day is the first of next
  month?") are kept. Messages, paraphrases, labels and the `trigger-006` amendment are unchanged. The default case set
  (`evals.caseset.CASES_DIR`) is now v2; `build-cases` still writes v1, and `regrade` uses each run's recorded set.
  The retrieval eval's template queries get the same rewrite.
- **Why.** The assistant has Gmail and triggers only, so weather/calendar chat was unrealistic, and Task 15 traced
  part of `hybrid`'s `multi-person-006` miss to "Is it going to rain in Seattle tomorrow?" as the last exchange.
- **Unchanged.** `evals/cases/v1` (kept for regrading old runs), `world.json`, retrieval values, prompts, and earlier
  result folders. v1 rosters and case files round-trip byte-identically (tests pin it).
- **Effect.** Layer-1 retrieval (fastembed) recall@20 at N=300: frozen 0.87 → 0.87, template 0.87 → 0.84;
  `unrelated_history` shrinks from 14 to 4 queries. Routing (Haiku, dev): `full` 100% at every N;
  `legacy_rules` 83/85/81/77% (`20261109T214557Z-task-16-v2-baseline-agent-backed-history`).


## 2026-11-09: BM25 query drops stopwords (retrieval value change, Task 16e)

- **What.** `_fts_query` (`server/services/agents/store.py`) keeps the same tokenizer and drops tokens whose lowercase
  form is in `STOPWORDS`. That list now lives in `server/services/agents/stopwords.py`; `evals/textwords.py`
  re-exports it, with the same set as before. A query made only of stopwords gives an empty BM25 match, and ranking
  then falls back to embeddings plus referenced ids. It applies to the injected top-20 and to the `search_agents`
  tool.
- **Why.** Dev failure `multi-person-006` (`hybrid`, N=300, Task 15): every token was ORed, stopwords included, so
  BM25 matched all 300 agents. A rare exact name ("Sam") was worth about as much in RRF as a vague embedding match.
  In the v1 counterfactual, dropping stopwords cut BM25 matches 300→9 and put the Sams at BM25 #3–5 (now pinned in
  `tests/evals/test_bm25_stopwords.py`).
- **Unchanged.** k=20, rrf_k=60, history_turns=2, `build_query`, the embedding query, the referenced-id regex,
  prompts, cases and `world.json`.
- **Effect (layer 1, $0).**
  - v2 fastembed (`20261109T222346Z` vs `20261109T214830Z`):
    - headline recall@20 is unchanged at 1.00/1.00/1.00/0.96;
    - template N=100 is 0.91→0.92;
    - frozen is identical.
  - v2 hashing (`20261109T222645Z` vs `20261109T215151Z`):
    - frozen N=100 is 0.93→0.95;
    - original N=300 is 0.86→0.88;
    - template N=100/300 is 0.86→0.89 and 0.72→0.74.
  - unrelated_history (4 queries) dips by one agent in a few cells.
  - Dense stress (`20261109T222653Z`/`222656Z` vs `192304Z`/`192308Z`):
    - fastembed target_para@20 is 0.67/0.67/0.72→0.70/0.70/0.70, but @5/@10 and MRR drop (MRR 0.18–0.21→0.14–0.15);
    - history_pull@20 is 0.22/0.11/0.13→0.20/0.22/0.22;
    - hashing target_para@20 is 0.39/0.41/0.41→0.35/0.37/0.37.
- **Not fixed: `multi-person-006` on v2.** At N=300, Sam Okafor's agents are fused #23 and #53 (they were #26 and
  #56), and Sam Rivera's is #16 (was #18). v2's agent-backed history ("Noor replied that the slot is confirmed", twice)
  carries content words that are common in descriptions. BM25 still matches 130/300 agents, and the Sams stay at BM25
  #20–22. Any further fix (weighting the message above history, document-frequency pruning) is a new design and needs
  Siddharth's approval.

## 2026-11-09: retrieval also ranks on the message (A3, retrieval change, Task 16f)

- **What.** `search_agents` (`server/services/agents/retrieval.py`) takes `message=`. When it is given and differs from
  the query, RRF fuses four rankings instead of two: BM25(message), emb(message), BM25(history+message),
  emb(history+message). Each reason is added once per agent, and referenced ids still come from the full query.
  `build_turn_inputs` (`hybrid`) passes the message through `retrieve_cards`, including the BM25-only retry when
  embedding fails. The IA's `search_agents` tool passes no message, so it is unchanged. `evals/retrieval_eval.py`
  passes `q.message`, so layer 1 measures production.
- **Why.** `multi-person-006` on v2 was still outside the top 20 after Task 16e: history content words ("Noor replied
  that the slot is confirmed") outvoted the message. Experiment 16f (scratch, $0, FUTURE_WORK §1) compared five
  variants. Siddharth ruled that the guards are judged on fastembed only, and A3 won.
- **Unchanged.** k=20, rrf_k=60, history_turns=2, `build_query`, `_fts_query`, prompts, cases and `world.json`. With
  no message, or a message equal to the query (no history), results are byte-identical to before.
- **Reproduction.** All four official runs' `queries.jsonl` are byte-identical to the scratch A3 runs.
- **Effect (layer 1, $0, vs the Task 16e runs).**
  - v2 fastembed (`20261109T235838Z` vs `20261109T222346Z`):
    - headline recall@20 is 1.00/1.00/1.00/0.96 → 1.00/1.00/1.00/1.00;
    - template N=100/300 is 0.924/0.842 → 0.954/0.900;
    - frozen N=300 is 0.870 → 0.927;
    - no group × N cell drops;
    - `multi-person-006` Sams at N=300 move from 16/23/53 to 3/4/11 (fixed).
  - v2 hashing (`20261110T000139Z` vs `20261109T222645Z`): headline at N=300 is 0.98 → 1.00, template N=300 is
    0.740 → 0.892, and no cell drops.
  - Dense fastembed (`20261110T000150Z` vs `20261109T222653Z`):
    - history_pull@20 is 0.20/0.22/0.22 → 0.76/0.76/0.78;
    - target_para@20 is 0.70/0.70/0.70 → 0.72/0.72/0.78;
    - target_para @5/@10/MRR recover what Task 16e lost (MRR 0.14–0.15 → 0.17–0.18).
  - Dense hashing (`20261110T000155Z` vs `20261109T222656Z`, informational): history_pull is 0.00 → 0.28, but
    target_para N=200/300 loses 2 and 1 of 46 queries, and topic_noname at N=100 is 0.28 → 0.24.
- **BM25-only fallback (scratch, informational).** This is what production runs when fastembed is unavailable. The
  check used V0 vs A3 with `embedder=None` at search time.
  - v2 N=300: frozen 0.828 → 0.932, original 0.827 → 0.940, template 0.827 → 0.881. No group × N mean drops. Five
    individual template-lookalike queries lose agents, against 68 that gain.
  - Dense: history_pull 0.00 → 0.17–0.26, and the other kinds are unchanged.
- **Layer 2 (paid, Siddharth's go-ahead).** `hybrid` on v2 dev, N=10/30/100/300 × 3 runs, Haiku
  (`20261110T000801Z`): 100% at every N (192/192), level with `full` and above `legacy_rules` (83/85/81/77%).
  `multi-person-006` passes at N=100/300. Billed $0.4668 (SPEND.md row 7).

## 2026-11-10: `clarify_named_ok` accepts a surname (grader, Task 16g)

- **What.** A name in `clarify_should_name` now counts as named if a user-facing text has the full name, or its
  surname as a whole word, case-insensitive. "Which Daniel, Kaplan or Walsh?" names both Daniels. "Parking" does
  not count as "Park".
- **Why.** Siddharth ruled that a surname-only clarifying question is valid. Since Experiment 3, passing runs had
  been marked `clarify_named_ok = False` for exactly this.
- **Unchanged.** `passed`, outcome kinds, flags and the ask rule. `clarify_named_ok` never affected the pass rate.
  Past run folders are not regraded.
