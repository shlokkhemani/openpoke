# Future work

Improvements we identified but haven't built. Each one names the failure that motivates it and how we would measure
it. Measured history is in `evals/results/changes.md`.

## 1. Retrieval: stop conversation history from swamping the new message

### The problem (measured)
Retrieval builds one query from the last 2 history turns plus the new message (`build_query`), and runs both BM25 and
embeddings on it. When the history is about something else, it pulls the query toward the wrong agents:

- **`multi-person-006` (v2, N=300).** The message is "Ask Sam and Alice Chen if they'd like to join the running club
  on Sundays". The previous exchange was an agent update: "Noor replied that the slot is confirmed", twice. Its words
  ("replied", "slot", "confirmed") appear in many agent descriptions. BM25 matches 130 of 300 agents, and Sam Okafor's
  agents fuse to #23 and #53, outside the top 20 the assistant sees.
- **Dense stress world, `history_pull`.** After an agent reports back about person A, a paraphrased request about
  person B retrieves A's agents. recall@20 is about 0.2, against about 0.7 for the same requests with no history.

Task 16e removed one source of noise: stopwords no longer reach BM25. On v1, that cut BM25 matches from 300 to 9. It
can't fix content words coming from history.

### Option A: weight the message above history (cheap, deterministic)
- **A1.** Run BM25 on the message alone as its own ranking, and keep message plus history for the embedding ranking.
- **A2.** Fuse three rankings with reciprocal rank fusion (RRF): BM25 on the message, BM25 on the full query, and the
  embedding.

Both add no new constants and no model calls, and can be measured offline for $0. The risk is follow-ups like "did
she reply?", where the message alone carries no signal. Referenced agent ids from history and the embedding ranking
cover that case.

#### Measured (2026-11-09, $0)
This was a scratch counterfactual with no code change. The eval's `search_agents` was monkeypatched to fuse different
rankings, with k=20, rrf_k=60, history_turns=2, and referenced ids always taken from the full query. Configurations:
dev split, v2 base world (N=10/30/100/300) and dense world (N=100/200/300), each run with fastembed and hashing. V0
reproduced the official runs `20261109T222346Z`, `222645Z`, `222653Z` and `222656Z` byte for byte. In the variant
names, `msg` is the message alone and `full` is `build_query`'s history plus message.
- **V0:** BM25(full) + emb(full), today's behaviour.
- **A1:** BM25(msg) + emb(full).
- **A2:** BM25(msg) + BM25(full) + emb(full).
- **A3:** BM25(msg) + emb(msg) + BM25(full) + emb(full).
- **A4:** BM25(msg) + emb(msg). History is used only for referenced ids, so this is a bound, not a proposal.

Headline numbers, recall@20, fastembed:

| | V0 | A1 | A2 | A3 | A4 |
|---|---|---|---|---|---|
| `multi-person-006` fused Sam ranks, N=300 | 16/23/53 | 2/4/6 | 3/4/9 | 3/4/11 | 3/4/5 |
| dense `history_pull`, N=100/200/300 | .20/.22/.22 | .52/.52/.52 | .48/.43/.43 | .76/.76/.78 | .80/.83/.80 |
| dense `target_para`, N=100/200/300 | .70/.70/.70 | .70/.70/.70 | **.52/.59/.59** | .72/.72/.78 | .85/.87/.85 |
| v2 template, N=100/300 | .924/.842 | .946/.890 | .949/.890 | .954/.900 | .967/.906 |
| v2 frozen, N=100/300 | .922/.870 | .964/.911 | .964/.932 | .964/.927 | .964/.948 |

- **fastembed (production):** A1, A3 and A4 pass every pre-registered guard: no (group, N) or unreferenced cell drops,
  and dense `target_para` holds. A2 fails, because two BM25 rankings outvote the single embedding ranking on
  paraphrases (−8 of 46 queries at N=100).
- **hashing:** under a strict reading, which applies the guards to hashing too, every variant trips one guard, each by
  one or a few queries:
  - **A1:** unreferenced template/lookalikes at N=100, 0.811 → 0.794. One query, `t103:newtask-006`, loses one of its
    expected agents (fused rank 17 → 15, but the cut-off changed).
  - **A3:** dense `target_para` loses 2 of 46 net at N=200 and 1 at N=300. Agents at ranks 8–20 fall to 21–34.
  - **A4:** dense `target_para` loses 1 per N, and unreferenced template/target at N=100 goes 1.0 → 0.977
    (`t108:trigger-004`, rank 10 → 21).
  - The 0.02 dense threshold is below one query (1/46 = 0.022), so in practice it means "no net loss".
  - The hashing embedder is a token-hash stand-in, and on a short message alone it is noisier than on the longer
    history-plus-message string.
- **`unrelated_history`:** no variant lost an expected agent in either embedder. All of them gained agents, for
  example `newtask-006:unrelated` and `broad-person-005:unrelated`.
- **Ruling (Siddharth, 2026-11-09):** the guards are judged on fastembed only. Production never runs the hashing
  embedder; it is a test and eval stand-in. The hashing results above are kept for information only.
- **Verdict: A3.**
  - A1, A3 and A4 are candidates; A2 is not.
  - Ranked criteria:
    1. `multi-person-006`: all three candidates put all three Sams in the top 20.
    2. Dense `history_pull`: A4 (.80/.83/.80) > A3 (.76/.76/.78) ≫ A1 (.52).
    3. v2 template at N=300: A4 .906 > A3 .900 > A1 .890.
  - A4 leads A3 by about 2 queries on criterion 2 (of 46) and on criterion 3 (of 301). That is not clearly best,
    so the bound is not adopted. A3 wins.
  - A4's margin, mostly on `target_para`, suggests that with referenced ids kept, history adds little to
    retrieval here. But the sets have few follow-ups like "did she reply?" with no id reference, so dropping
    history is under-measured.
  - BM25-only fallback (measured after the verdict, scratch, informational): A3 is level or better in every
    (group, N) mean. v2 N=300 template goes .827 → .881, and dense `history_pull` goes .00 → .17–.26. Five
    individual template-lookalike queries lose agents, against 68 that gain.
- **Status: adopted as A3 (Task 16f, 2026-11-09).** The four official layer-1 runs reproduce the scratch A3
  `queries.jsonl` byte for byte (`evals/results/changes.md`). Option B stays open.

### Option B: query rewriting with a small model
Before retrieval, a cheap model gets the last k turns plus the new message. It returns one standalone search query,
keeping person names verbatim. This is conversational query reformulation. It is the principled fix, because it is
the only option that tells "did *she* reply?" (history needed) apart from a topic switch (history irrelevant).

**For:**
- It resolves pronouns and topic switches the way a person would.
- Its output is short and keyword-dense, which suits BM25 and embeddings.
- It needs no tuned constants.

**Against:**
- **Latency:** an extra model call before every turn that has history, typically a few hundred ms.
- **Cost:** it is paid on every turn, small per turn but recurring.
- **Confident errors:** a dropped name, a wrong "she" or an invented topic sends retrieval the wrong way, and only the
  `search_agents` tool can recover from that.
- **Nondeterminism:** outputs drift across model and prompt versions, so evals need cached rewrites.
- **No roster knowledge:** it can't tell which "Sam" is meant. Disambiguation stays with the interaction agent.
- **Overlap with `hybrid`:** in `hybrid` the interaction agent already writes its own `search_agents` queries. The
  rewriter's extra value is mainly a better injected top-20, so the agent searches less often.

**De-risking:**
- Add the rewrite as another RRF ranking next to the raw message instead of replacing it. A bad rewrite then only
  dilutes the ranking.
- Fall back to the current query on timeout or error.
- Skip the call when there is no history.

### How we'd decide
1. ~~Measure A1 and A2 offline ($0) on case set v2 and the dense world.~~ Done (Experiment 16f, A1–A4); A3 adopted in Task 16f. B is to be compared against A3.
2. Measure B on the same queries with cached rewrites, once per query regardless of roster size, so well under $1.
3. Score all of them on the same points:
   - `multi-person-006` ranks;
   - dense `history_pull` and `target_para` (recall@20 and MRR);
   - `unrelated_history`, the group most likely to regress.
4. Adopt B only if it clearly beats the best of A, because it adds a recurring cost and a latency and failure path
   that A doesn't.

## 2. Stress test: multi-turn sessions, `full` vs `hybrid`

### Why
- On v2 dev, `full` and `hybrid` both pass 100% at every N up to 300, so the dev set can't separate them.
- Every case is a single turn with at most two history items. Neither mode has been tested across a long
  conversation.

### What could break
- **`full`: attention across a long prompt.** Each turn, production rebuilds one user message:
  `<conversation_history>` (the transcript as text), then `<active_agents>` (every card), then the new message.
  At N=300 that is about 50k tokens of near-identical cards between the history and the message.
  - The cards don't pile up across turns, but the transcript grows until the summarizer cuts it. That happens at
    `conversation_summary_threshold = 100` entries, keeping the last 10 verbatim.
  - The risk is that a follow-up ("did she reply?") has to be linked to the right card across that gap.
- **`hybrid`: retrieval misses.** Retrieval sees only the last 2 history items (`history_turns`). Known weak spots
  (dense world, fastembed, N=300):
  - paraphrased topics: `target_para` .78;
  - no person named: `topic_noname` .24;
  - short answers to a clarifying question ("the second one").
  - The search tool has never recovered a missing target.

### Design
- **Sessions:** scripted conversations of 10–20 turns, each turn graded on its own:
  - a mix of reuse, create and clarify;
  - follow-ups that depend on earlier turns;
  - answers to clarifying questions: one word, a surname, "the second one";
  - agent reports arriving between a question and its answer;
  - dense-world turns with paraphrased topics or no person named.
  - At least one session should be long enough to trigger the summarizer, or use a lower threshold for the test.
- **Build:**
  - The harness runs single turns today. A session runner must carry the transcript and the store's state from
    turn to turn.
  - This needs a separate frozen set; v2 stays untouched.
- **Grid:** `full` and `hybrid` at N=100 and 300, Haiku, 1 run first.
- **Report:** pass rate by mode × N × turn index. Rot shows up as accuracy falling with turn number.

### Cost (Haiku, rough)
- One 15-turn session at N=300: about 0.18 USD for `full`, about 0.04 USD for `hybrid`.
- First pass, 10 sessions × 2 modes × N=100/300: about 3–4 USD.
- N=300 keeps every call under OpenRouter's 100k-token threshold, above which Haiku costs 5× more. So no
  pricing change is needed.

### Later, if `full` holds at N=300
- **N=1000** finds where it breaks. It needs:
  - a prefix-preserving world extension, so N≤300 results stay valid;
  - tiered pricing in `evals/pricing.py`, without which the estimate and `--max-cost` read about 5× low;
  - about 2.9 USD per `full` session.
- **Prompt caching** for `full`: the cards come after the history, which changes every turn. Across turns, only
  the system prompt is cacheable. Caching the cards would need the order system prompt, cards, history, message,
  which is a production prompt change to measure on its own. Within a turn, the 2nd and 3rd round trips already
  share a prefix.
