# Retrieval eval: Task 16f layer-1 retrieval dev fastembed v2, A3 message weighting

- command: `python -m evals.run retrieval --embedder fastembed --purpose 'Task 16f layer-1 retrieval dev fastembed v2, A3 message weighting'`
- split: dev; embedder: fastembed; descriptions: regen
- counts: {'frozen': 16, 'original': 14, 'unrelated_history': 4, 'template': 301, 'frozen_cases_in_split': 16, 'skipped_empty_expected': 0, 'referenced': 252, 'skipped_n_below_required': 0}
- dev recall@20 (rrf) at N=10/30/100/300: 1.00/1.00/1.00/1.00

Cells marked `*` have N <= K and are trivially 1.0. all_found, person_cover, mean_len and extra_referenced are at K=20; mrr is on the full fused ranking. Referenced ids from the last exchange are always appended.

## frozen

| kind | N | count | recall@5 | recall@10 | recall@20 | base@20 | all_found@20 | person_cover@20 | mean_len@20 | mrr | extra_referenced@20 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| both_candidates | 10 | 2 | 1.00 | 1.00* | 1.00* | 1.00 | 1.00 | 1.00 | 10.00 | 0.67 | – |
| both_candidates | 30 | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 20.00 | 0.67 | – |
| both_candidates | 100 | 2 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 20.50 | 0.67 | – |
| both_candidates | 300 | 2 | 0.83 | 0.83 | 1.00 | 0.50 | 1.00 | 1.00 | 20.00 | 0.67 | – |
| lookalikes | 10 | 4 | 0.94 | 1.00* | 1.00* | 1.00 | 1.00 | – | 10.00 | 1.00 | – |
| lookalikes | 30 | 4 | 0.77 | 1.00 | 1.00 | 1.00 | 1.00 | – | 20.25 | 1.00 | – |
| lookalikes | 100 | 4 | 0.65 | 0.71 | 0.85 | 0.79 | 0.50 | – | 20.50 | 0.80 | – |
| lookalikes | 300 | 4 | 0.58 | 0.65 | 0.71 | 0.44 | 0.50 | – | 20.50 | 0.54 | – |
| set | 10 | 4 | 1.00 | 1.00* | 1.00* | 1.00 | 1.00 | – | 10.00 | 1.00 | – |
| set | 30 | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 20.50 | 1.00 | – |
| set | 100 | 4 | 1.00 | 1.00 | 1.00 | 0.88 | 1.00 | – | 20.75 | 1.00 | – |
| set | 300 | 4 | 1.00 | 1.00 | 1.00 | 0.94 | 1.00 | – | 20.75 | 1.00 | – |
| target | 10 | 6 | 1.00 | 1.00* | 1.00* | 1.00 | 1.00 | – | 10.00 | 0.81 | – |
| target | 30 | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 20.00 | 0.78 | – |
| target | 100 | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 20.00 | 0.75 | – |
| target | 300 | 6 | 1.00 | 1.00 | 1.00 | 0.67 | 1.00 | – | 20.33 | 0.64 | – |

## original

| kind | N | count | recall@5 | recall@10 | recall@20 | base@20 | all_found@20 | person_cover@20 | mean_len@20 | mrr | extra_referenced@20 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| both_candidates | 10 | 1 | 1.00 | 1.00* | 1.00* | 1.00 | 1.00 | 1.00 | 10.00 | 1.00 | – |
| both_candidates | 30 | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 20.00 | 1.00 | – |
| both_candidates | 100 | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 20.00 | 1.00 | – |
| both_candidates | 300 | 1 | 1.00 | 1.00 | 1.00 | 0.33 | 1.00 | 1.00 | 20.00 | 1.00 | – |
| lookalikes | 10 | 3 | 0.92 | 1.00* | 1.00* | 1.00 | 1.00 | – | 10.00 | 0.83 | – |
| lookalikes | 30 | 3 | 0.81 | 1.00 | 1.00 | 0.89 | 1.00 | – | 20.33 | 1.00 | – |
| lookalikes | 100 | 3 | 0.61 | 0.81 | 0.92 | 0.78 | 0.67 | – | 20.33 | 0.83 | – |
| lookalikes | 300 | 3 | 0.53 | 0.64 | 0.81 | 0.53 | 0.33 | – | 20.33 | 0.58 | – |
| set | 10 | 4 | 1.00 | 1.00* | 1.00* | 1.00 | 1.00 | – | 10.00 | 1.00 | – |
| set | 30 | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 20.50 | 1.00 | – |
| set | 100 | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 20.50 | 1.00 | – |
| set | 300 | 4 | 1.00 | 1.00 | 1.00 | 0.81 | 1.00 | – | 20.50 | 1.00 | – |
| target | 10 | 6 | 1.00 | 1.00* | 1.00* | 1.00 | 1.00 | – | 10.00 | 0.81 | – |
| target | 30 | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 20.00 | 0.72 | – |
| target | 100 | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 20.17 | 0.69 | – |
| target | 300 | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 20.33 | 0.56 | – |

## template

| kind | N | count | recall@5 | recall@10 | recall@20 | base@20 | all_found@20 | person_cover@20 | mean_len@20 | mrr | extra_referenced@20 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| both_candidates | 10 | 3 | 1.00 | 1.00* | 1.00* | 1.00 | 1.00 | 1.00 | 10.00 | 1.00 | – |
| both_candidates | 30 | 3 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 20.00 | 1.00 | – |
| both_candidates | 100 | 3 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 20.00 | 1.00 | – |
| both_candidates | 300 | 3 | 1.00 | 1.00 | 1.00 | 0.78 | 1.00 | 1.00 | 20.00 | 1.00 | – |
| lookalikes | 10 | 78 | 0.86 | 1.00* | 1.00* | 1.00 | 1.00 | – | 10.00 | 0.87 | – |
| lookalikes | 30 | 78 | 0.72 | 0.93 | 0.98 | 0.89 | 0.94 | – | 20.05 | 0.84 | – |
| lookalikes | 100 | 78 | 0.52 | 0.65 | 0.82 | 0.64 | 0.67 | – | 20.37 | 0.72 | – |
| lookalikes | 300 | 78 | 0.45 | 0.51 | 0.61 | 0.41 | 0.36 | – | 20.40 | 0.65 | – |
| set | 10 | 61 | 0.95 | 1.00* | 1.00* | 1.00 | 1.00 | – | 10.00 | 0.99 | – |
| set | 30 | 61 | 0.96 | 1.00 | 1.00 | 1.00 | 1.00 | – | 20.00 | 1.00 | – |
| set | 100 | 61 | 0.95 | 1.00 | 1.00 | 0.95 | 1.00 | – | 20.07 | 1.00 | – |
| set | 300 | 61 | 0.95 | 1.00 | 1.00 | 0.68 | 1.00 | – | 20.07 | 0.99 | – |
| target | 10 | 159 | 1.00 | 1.00* | 1.00* | 1.00 | 1.00 | – | 10.00 | 0.94 | – |
| target | 30 | 159 | 1.00 | 1.00 | 1.00 | 0.98 | 1.00 | – | 20.00 | 0.92 | – |
| target | 100 | 159 | 1.00 | 1.00 | 1.00 | 0.95 | 1.00 | – | 20.30 | 0.92 | – |
| target | 300 | 159 | 0.98 | 1.00 | 1.00 | 0.83 | 1.00 | – | 20.35 | 0.91 | – |

## unrelated_history

| kind | N | count | recall@5 | recall@10 | recall@20 | base@20 | all_found@20 | person_cover@20 | mean_len@20 | mrr | extra_referenced@20 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| lookalikes | 10 | 2 | 0.88 | 1.00* | 1.00* | 1.00 | 1.00 | – | 10.00 | 1.00 | 1.00 |
| lookalikes | 30 | 2 | 0.75 | 1.00 | 1.00 | 1.00 | 1.00 | – | 20.00 | 0.75 | 1.00 |
| lookalikes | 100 | 2 | 0.50 | 0.75 | 0.88 | 0.88 | 0.50 | – | 21.00 | 0.57 | 1.00 |
| lookalikes | 300 | 2 | 0.50 | 0.62 | 0.62 | 0.50 | 0.50 | – | 21.00 | 0.56 | 1.00 |
| set | 10 | 1 | 1.00 | 1.00* | 1.00* | 1.00 | 1.00 | – | 10.00 | 1.00 | 1.00 |
| set | 30 | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 20.00 | 1.00 | 1.00 |
| set | 100 | 1 | 1.00 | 1.00 | 1.00 | 0.80 | 1.00 | – | 20.00 | 1.00 | 1.00 |
| set | 300 | 1 | 1.00 | 1.00 | 1.00 | 0.40 | 1.00 | – | 20.00 | 1.00 | 1.00 |
| target | 10 | 1 | 1.00 | 1.00* | 1.00* | 1.00 | 1.00 | – | 10.00 | 1.00 | 1.00 |
| target | 30 | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 20.00 | 1.00 | 1.00 |
| target | 100 | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 20.00 | 0.50 | 1.00 |
| target | 300 | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 20.00 | 0.50 | 1.00 |

## recall@20 without referenced queries (frozen group)

| kind | N | recall@20 |
|---|---|---|
| lookalikes | 10 | 1.00 |
| lookalikes | 30 | 1.00 |
| lookalikes | 100 | 0.88 |
| lookalikes | 300 | 0.75 |
| set | 10 | 1.00 |
| set | 30 | 1.00 |
| set | 100 | 1.00 |
| set | 300 | 1.00 |
| target | 10 | 1.00 |
| target | 30 | 1.00 |
| target | 100 | 1.00 |
| target | 300 | 1.00 |

## What we learned

Retrieval now also ranks on the message alone (A3, Task 16f, changes.md 2026-11-09): RRF over BM25(message), emb(message), BM25(history+message), emb(history+message). No constant changed (k=20, rrf_k=60, history_turns=2). `queries.jsonl` is byte-identical to the measured scratch A3 run (Experiment 16f, FUTURE_WORK §1). Compared with `20261109T222346Z` (Task 16e, v2 fastembed).

- **Headline recall@20 at N=300 is 1.00 (was 0.96); every group × N is level or up.** Frozen N=100/300 0.922/0.870 → 0.964/0.927 (all_found 0.81 → 0.88). Template N=100/300 0.924/0.842 → 0.954/0.900 (all_found 0.76 → 0.83 at N=300). Original N=300 0.917 → 0.958. unrelated_history (4 queries) N=100/300 0.750 → 0.938/0.812.
- **`multi-person-006` is fixed on v2.** In the Experiment 16f probe (same roster and descriptions) the Sams' fused ranks at N=300 went 16/23/53 → 3/4/11, all inside the top 20. The message ("Ask Sam and Alice Chen …") now has rankings of its own, so the agent-update wording in history ("Noor replied that the slot is confirmed") no longer outvotes it.
