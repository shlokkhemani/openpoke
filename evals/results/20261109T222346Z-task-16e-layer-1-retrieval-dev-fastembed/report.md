# Retrieval eval: Task 16e layer-1 retrieval dev fastembed v2, BM25 stopwords dropped

- command: `python -m evals.run retrieval --embedder fastembed --purpose 'Task 16e layer-1 retrieval dev fastembed v2, BM25 stopwords dropped'`
- split: dev; embedder: fastembed; descriptions: regen
- counts: {'frozen': 16, 'original': 14, 'unrelated_history': 4, 'template': 301, 'frozen_cases_in_split': 16, 'skipped_empty_expected': 0, 'referenced': 252, 'skipped_n_below_required': 0}
- dev recall@20 (rrf) at N=10/30/100/300: 1.00/1.00/1.00/0.96

Cells marked `*` have N <= K and are trivially 1.0. all_found, person_cover, mean_len and extra_referenced are at K=20; mrr is on the full fused ranking. Referenced ids from the last exchange are always appended.

## frozen

| kind | N | count | recall@5 | recall@10 | recall@20 | base@20 | all_found@20 | person_cover@20 | mean_len@20 | mrr | extra_referenced@20 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| both_candidates | 10 | 2 | 0.83 | 1.00* | 1.00* | 1.00 | 1.00 | 1.00 | 10.00 | 0.38 | – |
| both_candidates | 30 | 2 | 0.67 | 0.83 | 1.00 | 1.00 | 1.00 | 1.00 | 20.00 | 0.35 | – |
| both_candidates | 100 | 2 | 0.50 | 0.83 | 0.83 | 1.00 | 0.50 | 1.00 | 20.00 | 0.33 | – |
| both_candidates | 300 | 2 | 0.50 | 0.50 | 0.67 | 0.50 | 0.50 | 0.75 | 20.00 | 0.20 | – |
| lookalikes | 10 | 4 | 0.85 | 1.00* | 1.00* | 1.00 | 1.00 | – | 10.00 | 0.71 | – |
| lookalikes | 30 | 4 | 0.77 | 0.77 | 1.00 | 1.00 | 1.00 | – | 20.00 | 0.67 | – |
| lookalikes | 100 | 4 | 0.40 | 0.65 | 0.77 | 0.79 | 0.50 | – | 20.00 | 0.42 | – |
| lookalikes | 300 | 4 | 0.19 | 0.52 | 0.65 | 0.44 | 0.50 | – | 20.00 | 0.19 | – |
| set | 10 | 4 | 0.89 | 1.00* | 1.00* | 1.00 | 1.00 | – | 10.00 | 0.75 | – |
| set | 30 | 4 | 0.94 | 1.00 | 1.00 | 1.00 | 1.00 | – | 20.00 | 0.71 | – |
| set | 100 | 4 | 1.00 | 1.00 | 1.00 | 0.88 | 1.00 | – | 20.00 | 0.65 | – |
| set | 300 | 4 | 0.50 | 1.00 | 1.00 | 0.94 | 1.00 | – | 20.00 | 0.57 | – |
| target | 10 | 6 | 1.00 | 1.00* | 1.00* | 1.00 | 1.00 | – | 10.00 | 0.89 | – |
| target | 30 | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 20.00 | 0.89 | – |
| target | 100 | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 20.00 | 0.83 | – |
| target | 300 | 6 | 1.00 | 1.00 | 1.00 | 0.67 | 1.00 | – | 20.00 | 0.76 | – |

## original

| kind | N | count | recall@5 | recall@10 | recall@20 | base@20 | all_found@20 | person_cover@20 | mean_len@20 | mrr | extra_referenced@20 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| both_candidates | 10 | 1 | 1.00 | 1.00* | 1.00* | 1.00 | 1.00 | 1.00 | 10.00 | 0.50 | – |
| both_candidates | 30 | 1 | 0.33 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 20.00 | 0.25 | – |
| both_candidates | 100 | 1 | 0.33 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 20.00 | 0.50 | – |
| both_candidates | 300 | 1 | 0.67 | 1.00 | 1.00 | 0.33 | 1.00 | 1.00 | 20.00 | 0.33 | – |
| lookalikes | 10 | 3 | 0.81 | 1.00* | 1.00* | 1.00 | 1.00 | – | 10.00 | 0.78 | – |
| lookalikes | 30 | 3 | 0.69 | 0.89 | 1.00 | 0.89 | 1.00 | – | 20.00 | 0.78 | – |
| lookalikes | 100 | 3 | 0.53 | 0.69 | 0.69 | 0.78 | 0.33 | – | 20.00 | 0.42 | – |
| lookalikes | 300 | 3 | 0.25 | 0.53 | 0.61 | 0.53 | 0.33 | – | 20.00 | 0.29 | – |
| set | 10 | 4 | 0.82 | 1.00* | 1.00* | 1.00 | 1.00 | – | 10.00 | 0.75 | – |
| set | 30 | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 20.00 | 0.71 | – |
| set | 100 | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 20.00 | 0.62 | – |
| set | 300 | 4 | 0.44 | 1.00 | 1.00 | 0.81 | 1.00 | – | 20.00 | 0.57 | – |
| target | 10 | 6 | 1.00 | 1.00* | 1.00* | 1.00 | 1.00 | – | 10.00 | 0.89 | – |
| target | 30 | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 20.00 | 0.83 | – |
| target | 100 | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 20.00 | 0.83 | – |
| target | 300 | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 20.00 | 0.71 | – |

## template

| kind | N | count | recall@5 | recall@10 | recall@20 | base@20 | all_found@20 | person_cover@20 | mean_len@20 | mrr | extra_referenced@20 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| both_candidates | 10 | 3 | 1.00 | 1.00* | 1.00* | 1.00 | 1.00 | 1.00 | 10.00 | 0.83 | – |
| both_candidates | 30 | 3 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 20.00 | 0.83 | – |
| both_candidates | 100 | 3 | 0.67 | 0.89 | 1.00 | 1.00 | 1.00 | 1.00 | 20.00 | 0.75 | – |
| both_candidates | 300 | 3 | 0.44 | 0.78 | 1.00 | 0.78 | 1.00 | 1.00 | 20.00 | 0.72 | – |
| lookalikes | 10 | 78 | 0.71 | 1.00* | 1.00* | 1.00 | 1.00 | – | 10.00 | 0.50 | – |
| lookalikes | 30 | 78 | 0.53 | 0.83 | 0.97 | 0.89 | 0.92 | – | 20.00 | 0.45 | – |
| lookalikes | 100 | 78 | 0.31 | 0.52 | 0.72 | 0.64 | 0.51 | – | 20.00 | 0.31 | – |
| lookalikes | 300 | 78 | 0.18 | 0.29 | 0.46 | 0.41 | 0.23 | – | 20.01 | 0.21 | – |
| set | 10 | 61 | 0.83 | 1.00* | 1.00* | 1.00 | 1.00 | – | 10.00 | 0.65 | – |
| set | 30 | 61 | 0.75 | 0.99 | 1.00 | 1.00 | 1.00 | – | 20.00 | 0.61 | – |
| set | 100 | 61 | 0.65 | 0.92 | 0.99 | 0.95 | 0.95 | – | 20.00 | 0.56 | – |
| set | 300 | 61 | 0.42 | 0.73 | 0.94 | 0.68 | 0.85 | – | 20.00 | 0.47 | – |
| target | 10 | 159 | 0.99 | 1.00* | 1.00* | 1.00 | 1.00 | – | 10.00 | 0.66 | – |
| target | 30 | 159 | 0.99 | 1.00 | 1.00 | 0.98 | 1.00 | – | 20.00 | 0.66 | – |
| target | 100 | 159 | 0.96 | 0.98 | 1.00 | 0.95 | 1.00 | – | 20.00 | 0.62 | – |
| target | 300 | 159 | 0.74 | 0.95 | 0.99 | 0.83 | 0.99 | – | 20.01 | 0.54 | – |

## unrelated_history

| kind | N | count | recall@5 | recall@10 | recall@20 | base@20 | all_found@20 | person_cover@20 | mean_len@20 | mrr | extra_referenced@20 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| lookalikes | 10 | 2 | 0.62 | 1.00* | 1.00* | 1.00 | 1.00 | – | 10.00 | 0.38 | 1.00 |
| lookalikes | 30 | 2 | 0.62 | 0.62 | 1.00 | 1.00 | 1.00 | – | 20.00 | 0.60 | 1.00 |
| lookalikes | 100 | 2 | 0.25 | 0.50 | 0.50 | 0.88 | 0.50 | – | 20.00 | 0.52 | 1.00 |
| lookalikes | 300 | 2 | 0.25 | 0.25 | 0.50 | 0.50 | 0.50 | – | 20.00 | 0.51 | 1.00 |
| set | 10 | 1 | 0.80 | 1.00* | 1.00* | 1.00 | 1.00 | – | 10.00 | 1.00 | 1.00 |
| set | 30 | 1 | 0.60 | 1.00 | 1.00 | 1.00 | 1.00 | – | 20.00 | 0.50 | 1.00 |
| set | 100 | 1 | 0.40 | 1.00 | 1.00 | 0.80 | 1.00 | – | 20.00 | 0.50 | 1.00 |
| set | 300 | 1 | 0.20 | 0.60 | 1.00 | 0.40 | 1.00 | – | 20.00 | 0.50 | 1.00 |
| target | 10 | 1 | 1.00 | 1.00* | 1.00* | 1.00 | 1.00 | – | 10.00 | 0.33 | 1.00 |
| target | 30 | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 20.00 | 0.33 | 1.00 |
| target | 100 | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 20.00 | 0.25 | 1.00 |
| target | 300 | 1 | 0.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 20.00 | 0.11 | 1.00 |

## recall@20 without referenced queries (frozen group)

| kind | N | recall@20 |
|---|---|---|
| lookalikes | 10 | 1.00 |
| lookalikes | 30 | 1.00 |
| lookalikes | 100 | 0.88 |
| lookalikes | 300 | 0.62 |
| set | 10 | 1.00 |
| set | 30 | 1.00 |
| set | 100 | 1.00 |
| set | 300 | 1.00 |
| target | 10 | 1.00 |
| target | 30 | 1.00 |
| target | 100 | 1.00 |
| target | 300 | 1.00 |

## What we learned

BM25 query now drops stopwords (`_fts_query`, Task 16e, changes.md 2026-11-09). No other retrieval value changed (k=20, rrf_k=60, history_turns=2, embedding query unchanged). Compared with `20261109T214830Z` (v2 fastembed, same cases and descriptions).

- **Headline recall@20 is unchanged: 1.00/1.00/1.00/0.96 at N=10/30/100/300.** Per group, frozen is identical (0.87 recall, 0.81 all_found at N=300). Template moves slightly up (N=100 0.91→0.92, all_found 0.84→0.86; N=300 all_found 0.75→0.76). Original N=300 goes 0.93→0.92. unrelated_history (4 queries) goes 0.94→1.00 at N=30 and 0.81→0.75 at N=100: one expected agent in one query.
- **`multi-person-006` is not fixed on v2.** Sam Rivera's agent is fused #16 at N=300 (was #18). Sam Okafor's two agents are #23 and #53 (were #26 and #56), so both are still outside the top 20. At N=100 the second Okafor agent is #23 (was #26). Probe: scratch script, same roster and descriptions, full fused ranking.
- **Why the v1 counterfactual did not carry over.** On v1, the query's history was weather chat, and once stopwords were dropped BM25 matched 9 of 300 agents, with the Sams at BM25 #3–5. On v2, the history is "ag_qtqviwbs Update on getting the car serviced: Noor replied that the slot is confirmed." followed by the same reply again. Its content words ("Update", "replied", "slot", "confirmed") appear in many template descriptions ("X replied that …"). BM25 still matches 130 of 300 agents, and the Sams sit at BM25 #20–22 (they were #20–22 with stopwords too). Dropping stopwords cut the match count 300→130 but did not move the Sams in BM25. The remaining gap is the agent-update wording in history, a v2 property. Fixing it would need a new retrieval design (e.g. down-weighting history relative to the message, or document-frequency pruning), which is Siddharth's call.
