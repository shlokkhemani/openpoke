# Retrieval eval: layer 1 retrieval, dev, fastembed, after 12b simplification + Task 13

- command: `python -m evals.run retrieval --embedder fastembed --purpose 'layer 1 retrieval, dev, fastembed, after 12b simplification + Task 13'`
- split: dev; embedder: fastembed; descriptions: regen
- counts: {'frozen': 16, 'original': 14, 'unrelated_history': 14, 'template': 301, 'frozen_cases_in_split': 16, 'skipped_empty_expected': 0, 'referenced': 23, 'skipped_n_below_required': 0}
- dev recall@20 (rrf) at N=10/30/100/300: 1.00/1.00/1.00/0.96

Cells marked `*` have N <= K and are trivially 1.0. all_found, person_cover, mean_len and extra_referenced are at K=20; mrr is on the full fused ranking. Referenced ids from the last exchange are always appended.

## frozen

| kind | N | count | recall@5 | recall@10 | recall@20 | all_found@20 | person_cover@20 | mean_len@20 | mrr | extra_referenced@20 |
|---|---|---|---|---|---|---|---|---|---|---|
| both_candidates | 10 | 2 | 0.50 | 1.00* | 1.00* | 1.00 | 1.00 | 10.00 | 0.32 | – |
| both_candidates | 30 | 2 | 0.67 | 0.67 | 1.00 | 1.00 | 1.00 | 20.00 | 0.60 | – |
| both_candidates | 100 | 2 | 0.50 | 0.67 | 1.00 | 1.00 | 1.00 | 20.00 | 0.56 | – |
| both_candidates | 300 | 2 | 0.33 | 0.50 | 0.67 | 0.50 | 0.75 | 20.00 | 0.53 | – |
| lookalikes | 10 | 4 | 1.00 | 1.00* | 1.00* | 1.00 | – | 10.00 | 0.83 | – |
| lookalikes | 30 | 4 | 0.77 | 0.83 | 1.00 | 1.00 | – | 20.00 | 0.75 | – |
| lookalikes | 100 | 4 | 0.27 | 0.65 | 0.77 | 0.50 | – | 20.00 | 0.40 | – |
| lookalikes | 300 | 4 | 0.12 | 0.40 | 0.65 | 0.50 | – | 20.00 | 0.17 | – |
| set | 10 | 4 | 0.89 | 1.00* | 1.00* | 1.00 | – | 10.00 | 0.88 | – |
| set | 30 | 4 | 0.89 | 1.00 | 1.00 | 1.00 | – | 20.00 | 0.80 | – |
| set | 100 | 4 | 0.69 | 0.94 | 1.00 | 1.00 | – | 20.00 | 0.78 | – |
| set | 300 | 4 | 0.62 | 0.69 | 1.00 | 1.00 | – | 20.00 | 0.77 | – |
| target | 10 | 6 | 1.00 | 1.00* | 1.00* | 1.00 | – | 10.00 | 0.83 | – |
| target | 30 | 6 | 1.00 | 1.00 | 1.00 | 1.00 | – | 20.00 | 0.92 | – |
| target | 100 | 6 | 1.00 | 1.00 | 1.00 | 1.00 | – | 20.00 | 0.92 | – |
| target | 300 | 6 | 1.00 | 1.00 | 1.00 | 1.00 | – | 20.00 | 0.92 | – |

## original

| kind | N | count | recall@5 | recall@10 | recall@20 | all_found@20 | person_cover@20 | mean_len@20 | mrr | extra_referenced@20 |
|---|---|---|---|---|---|---|---|---|---|---|
| both_candidates | 10 | 1 | 1.00 | 1.00* | 1.00* | 1.00 | 1.00 | 10.00 | 0.50 | – |
| both_candidates | 30 | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 20.00 | 0.50 | – |
| both_candidates | 100 | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 20.00 | 1.00 | – |
| both_candidates | 300 | 1 | 0.33 | 0.67 | 1.00 | 1.00 | 1.00 | 20.00 | 1.00 | – |
| lookalikes | 10 | 3 | 0.81 | 1.00* | 1.00* | 1.00 | – | 10.00 | 1.00 | – |
| lookalikes | 30 | 3 | 0.69 | 0.78 | 1.00 | 1.00 | – | 20.00 | 1.00 | – |
| lookalikes | 100 | 3 | 0.44 | 0.69 | 0.69 | 0.33 | – | 20.00 | 0.61 | – |
| lookalikes | 300 | 3 | 0.25 | 0.36 | 0.69 | 0.33 | – | 20.00 | 0.30 | – |
| set | 10 | 4 | 0.65 | 1.00* | 1.00* | 1.00 | – | 10.00 | 0.79 | – |
| set | 30 | 4 | 0.64 | 1.00 | 1.00 | 1.00 | – | 20.00 | 0.78 | – |
| set | 100 | 4 | 0.57 | 0.88 | 1.00 | 1.00 | – | 20.00 | 0.78 | – |
| set | 300 | 4 | 0.62 | 0.88 | 0.94 | 0.75 | – | 20.00 | 0.78 | – |
| target | 10 | 6 | 1.00 | 1.00* | 1.00* | 1.00 | – | 10.00 | 0.72 | – |
| target | 30 | 6 | 1.00 | 1.00 | 1.00 | 1.00 | – | 20.00 | 0.92 | – |
| target | 100 | 6 | 1.00 | 1.00 | 1.00 | 1.00 | – | 20.00 | 0.92 | – |
| target | 300 | 6 | 1.00 | 1.00 | 1.00 | 1.00 | – | 20.00 | 1.00 | – |

## template

| kind | N | count | recall@5 | recall@10 | recall@20 | all_found@20 | person_cover@20 | mean_len@20 | mrr | extra_referenced@20 |
|---|---|---|---|---|---|---|---|---|---|---|
| both_candidates | 10 | 3 | 0.89 | 1.00* | 1.00* | 1.00 | 1.00 | 10.00 | 0.83 | – |
| both_candidates | 30 | 3 | 0.78 | 0.89 | 1.00 | 1.00 | 1.00 | 20.00 | 0.83 | – |
| both_candidates | 100 | 3 | 0.56 | 0.67 | 0.89 | 0.67 | 1.00 | 20.00 | 0.73 | – |
| both_candidates | 300 | 3 | 0.56 | 0.78 | 0.89 | 0.67 | 1.00 | 20.00 | 0.78 | – |
| lookalikes | 10 | 78 | 0.81 | 1.00* | 1.00* | 1.00 | – | 10.00 | 0.85 | – |
| lookalikes | 30 | 78 | 0.69 | 0.87 | 0.99 | 0.99 | – | 20.00 | 0.83 | – |
| lookalikes | 100 | 78 | 0.39 | 0.57 | 0.77 | 0.51 | – | 20.00 | 0.59 | – |
| lookalikes | 300 | 78 | 0.33 | 0.41 | 0.56 | 0.27 | – | 20.00 | 0.51 | – |
| set | 10 | 61 | 0.79 | 1.00* | 1.00* | 1.00 | – | 10.00 | 0.90 | – |
| set | 30 | 61 | 0.83 | 0.96 | 1.00 | 1.00 | – | 20.00 | 0.94 | – |
| set | 100 | 61 | 0.74 | 0.88 | 0.98 | 0.93 | – | 20.00 | 0.84 | – |
| set | 300 | 61 | 0.70 | 0.83 | 0.93 | 0.85 | – | 20.00 | 0.84 | – |
| target | 10 | 159 | 0.99 | 1.00* | 1.00* | 1.00 | – | 10.00 | 0.90 | – |
| target | 30 | 159 | 0.99 | 1.00 | 1.00 | 1.00 | – | 20.00 | 0.93 | – |
| target | 100 | 159 | 0.97 | 0.98 | 1.00 | 1.00 | – | 20.00 | 0.89 | – |
| target | 300 | 159 | 0.95 | 0.97 | 0.99 | 0.99 | – | 20.00 | 0.87 | – |

## unrelated_history

| kind | N | count | recall@5 | recall@10 | recall@20 | all_found@20 | person_cover@20 | mean_len@20 | mrr | extra_referenced@20 |
|---|---|---|---|---|---|---|---|---|---|---|
| both_candidates | 10 | 2 | 0.67 | 1.00* | 1.00* | 1.00 | 1.00 | 10.00 | 0.38 | 1.00 |
| both_candidates | 30 | 2 | 0.50 | 0.83 | 1.00 | 1.00 | 1.00 | 20.00 | 0.38 | 1.00 |
| both_candidates | 100 | 2 | 0.33 | 0.67 | 0.83 | 0.50 | 1.00 | 20.00 | 0.19 | 1.00 |
| both_candidates | 300 | 2 | 0.00 | 0.17 | 0.50 | 0.00 | 0.75 | 20.00 | 0.10 | 1.00 |
| lookalikes | 10 | 4 | 0.85 | 1.00* | 1.00* | 1.00 | – | 10.00 | 0.46 | 1.00 |
| lookalikes | 30 | 4 | 0.46 | 0.92 | 1.00 | 1.00 | – | 20.00 | 0.32 | 1.00 |
| lookalikes | 100 | 4 | 0.27 | 0.46 | 0.85 | 0.50 | – | 20.00 | 0.21 | 1.00 |
| lookalikes | 300 | 4 | 0.00 | 0.21 | 0.40 | 0.00 | – | 20.00 | 0.09 | 1.00 |
| set | 10 | 4 | 0.59 | 1.00* | 1.00* | 1.00 | – | 10.00 | 0.54 | 1.00 |
| set | 30 | 4 | 0.84 | 0.95 | 1.00 | 1.00 | – | 20.00 | 0.55 | 1.00 |
| set | 100 | 4 | 0.59 | 1.00 | 1.00 | 1.00 | – | 20.00 | 0.49 | 1.00 |
| set | 300 | 4 | 0.42 | 0.65 | 0.75 | 0.75 | – | 20.00 | 0.31 | 1.00 |
| target | 10 | 4 | 1.00 | 1.00* | 1.00* | 1.00 | – | 10.00 | 0.58 | 1.00 |
| target | 30 | 4 | 1.00 | 1.00 | 1.00 | 1.00 | – | 20.00 | 0.58 | 1.00 |
| target | 100 | 4 | 1.00 | 1.00 | 1.00 | 1.00 | – | 20.00 | 0.52 | 1.00 |
| target | 300 | 4 | 0.50 | 1.00 | 1.00 | 1.00 | – | 20.00 | 0.45 | 1.00 |

## recall@20 without referenced queries (frozen group)

| kind | N | recall@20 |
|---|---|---|
| both_candidates | 10 | 1.00 |
| both_candidates | 30 | 1.00 |
| both_candidates | 100 | 1.00 |
| both_candidates | 300 | 0.67 |
| lookalikes | 10 | 1.00 |
| lookalikes | 30 | 1.00 |
| lookalikes | 100 | 0.77 |
| lookalikes | 300 | 0.65 |
| set | 10 | 1.00 |
| set | 30 | 1.00 |
| set | 100 | 1.00 |
| set | 300 | 1.00 |
| target | 10 | 1.00 |
| target | 30 | 1.00 |
| target | 100 | 1.00 |
| target | 300 | 1.00 |

## What we learned

- First run of the Task 12b retrieval (BM25 + embeddings, RRF, K=20, last exchange, no boosts) with fastembed, the production embedder. The headline (frozen, lookalikes excluded, person_cover for clarify) is 1.00/1.00/1.00/0.96 at N=10/30/100/300. The earlier K=5 run with boosts scored 0.92/0.94/0.89/0.89, so K=20 fixes the K=5 clarify misses (amb-person-006, multi-person-006) at N ≤ 100.
- The only headline miss is `both_candidates` at N=300 (frozen person_cover 0.75): one of the two people in an ambiguous-name clarify case drops out of the top 20.
- `target` (reuse one agent) is 0.99–1.00 at every N in every group. `set` stays ≥ 0.93 except `unrelated_history` at N=300 (0.75).
- `lookalikes` (create cases; expected = the near-miss agents the IA should see before creating) falls to 0.56–0.77 at N=100/300. Missing a look-alike makes a create more likely, not less, so it is not a routing error by itself. It is the reason the headline excludes this kind.
- `unrelated_history` (the last exchange is about a different agent) is the weakest group at N=300: `both_candidates` 0.50, `lookalikes` 0.40. The history pulls the query toward the old topic. The referenced agent is always kept (extra_referenced 1.00).
- No retrieval value was changed. In `hybrid` the safety net for these misses is the once-per-turn `search_agents` tool (Task 13), and the routing eval in Task 14 measures whether the IA uses it.
