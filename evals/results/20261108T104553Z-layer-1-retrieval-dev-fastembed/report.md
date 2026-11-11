# Retrieval eval: layer 1 retrieval, dev, fastembed

- command: `python -m evals.run retrieval --embedder fastembed --purpose 'layer 1 retrieval, dev, fastembed'`
- split: dev; embedder: fastembed; descriptions: regen
- counts: {'frozen': 16, 'original': 14, 'lowercase': 16, 'template': 301, 'frozen_cases_in_split': 16, 'skipped_empty_expected': 0, 'referenced': 11, 'skipped_n_below_required': 0}
- dev recall@5 (rrf_boosts) at N=10/30/100/300: 0.92/0.94/0.89/0.89

Cells marked `*` have N <= K and are trivially 1.0. recall, all_found, person_cover and mean_len are at K=5; mrr is on the max-K ranking. Person expansion and referenced ids are always on.

## frozen

| kind | ablation | N | count | recall@1 | recall@3 | recall@5 | recall@10 | all_found@5 | person_cover@5 | mean_len@5 | mrr |
|---|---|---|---|---|---|---|---|---|---|---|---|
| both_candidates | bm25 | 10 | 2 | 0.00 | 0.33 | 0.67 | 1.00* | 0.50 | 0.75 | 5.00 | 0.35 |
| both_candidates | bm25 | 30 | 2 | 0.00 | 0.50 | 1.00 | 1.00 | 1.00 | 1.00 | 5.00 | 0.42 |
| both_candidates | bm25 | 100 | 2 | 0.17 | 0.50 | 1.00 | 1.00 | 1.00 | 1.00 | 5.00 | 0.67 |
| both_candidates | bm25 | 300 | 2 | 0.17 | 0.33 | 0.67 | 1.00 | 0.00 | 1.00 | 5.00 | 0.62 |
| both_candidates | embeddings | 10 | 2 | 0.17 | 0.33 | 0.50 | 1.00* | 0.50 | 0.50 | 5.00 | 0.56 |
| both_candidates | embeddings | 30 | 2 | 0.17 | 0.33 | 0.33 | 0.50 | 0.00 | 0.50 | 5.50 | 0.53 |
| both_candidates | embeddings | 100 | 2 | 0.00 | 0.17 | 0.33 | 0.33 | 0.00 | 0.50 | 5.50 | 0.17 |
| both_candidates | embeddings | 300 | 2 | 0.00 | 0.00 | 0.00 | 0.17 | 0.00 | 0.00 | 5.50 | 0.05 |
| both_candidates | rrf | 10 | 2 | 0.00 | 0.33 | 0.50 | 1.00* | 0.50 | 0.50 | 5.00 | 0.32 |
| both_candidates | rrf | 30 | 2 | 0.17 | 0.33 | 0.67 | 0.67 | 0.50 | 0.75 | 5.00 | 0.60 |
| both_candidates | rrf | 100 | 2 | 0.17 | 0.33 | 0.50 | 0.67 | 0.50 | 0.50 | 5.00 | 0.56 |
| both_candidates | rrf | 300 | 2 | 0.17 | 0.33 | 0.33 | 0.50 | 0.00 | 0.50 | 5.50 | 0.53 |
| both_candidates | rrf_boosts | 10 | 2 | 0.17 | 0.17 | 0.50 | 1.00* | 0.50 | 0.50 | 5.00 | 0.57 |
| both_candidates | rrf_boosts | 30 | 2 | 0.17 | 0.33 | 0.67 | 0.67 | 0.50 | 0.75 | 5.00 | 0.60 |
| both_candidates | rrf_boosts | 100 | 2 | 0.17 | 0.17 | 0.33 | 0.67 | 0.00 | 0.50 | 5.00 | 0.57 |
| both_candidates | rrf_boosts | 300 | 2 | 0.17 | 0.17 | 0.33 | 0.50 | 0.00 | 0.50 | 5.00 | 0.53 |
| lookalikes | bm25 | 10 | 4 | 0.73 | 0.85 | 0.85 | 1.00* | 0.50 | – | 5.00 | 1.00 |
| lookalikes | bm25 | 30 | 4 | 0.73 | 0.79 | 0.79 | 0.85 | 0.50 | – | 5.25 | 1.00 |
| lookalikes | bm25 | 100 | 4 | 0.67 | 0.73 | 0.73 | 0.73 | 0.50 | – | 5.25 | 0.88 |
| lookalikes | bm25 | 300 | 4 | 0.58 | 0.67 | 0.67 | 0.73 | 0.50 | – | 5.25 | 0.67 |
| lookalikes | embeddings | 10 | 4 | 0.73 | 0.85 | 0.94 | 1.00* | 0.75 | – | 5.50 | 0.68 |
| lookalikes | embeddings | 30 | 4 | 0.65 | 0.85 | 0.85 | 0.94 | 0.50 | – | 6.00 | 0.49 |
| lookalikes | embeddings | 100 | 4 | 0.58 | 0.58 | 0.58 | 0.65 | 0.50 | – | 6.00 | 0.11 |
| lookalikes | embeddings | 300 | 4 | 0.58 | 0.58 | 0.58 | 0.58 | 0.50 | – | 6.25 | 0.03 |
| lookalikes | rrf | 10 | 4 | 0.73 | 0.85 | 1.00 | 1.00* | 1.00 | – | 5.00 | 0.83 |
| lookalikes | rrf | 30 | 4 | 0.65 | 0.79 | 0.85 | 0.92 | 0.50 | – | 5.25 | 0.75 |
| lookalikes | rrf | 100 | 4 | 0.58 | 0.58 | 0.73 | 0.79 | 0.50 | – | 6.00 | 0.40 |
| lookalikes | rrf | 300 | 4 | 0.58 | 0.58 | 0.58 | 0.73 | 0.50 | – | 6.00 | 0.15 |
| lookalikes | rrf_boosts | 10 | 4 | 0.65 | 0.79 | 1.00 | 1.00* | 1.00 | – | 5.00 | 1.00 |
| lookalikes | rrf_boosts | 30 | 4 | 0.65 | 0.79 | 0.85 | 0.92 | 0.50 | – | 5.00 | 1.00 |
| lookalikes | rrf_boosts | 100 | 4 | 0.58 | 0.58 | 0.65 | 0.79 | 0.50 | – | 5.00 | 0.80 |
| lookalikes | rrf_boosts | 300 | 4 | 0.58 | 0.58 | 0.58 | 0.65 | 0.50 | – | 5.00 | 0.78 |
| set | bm25 | 10 | 4 | 0.75 | 1.00 | 1.00 | 1.00* | 1.00 | – | 6.75 | 0.50 |
| set | bm25 | 30 | 4 | 0.75 | 1.00 | 1.00 | 1.00 | 1.00 | – | 6.50 | 0.71 |
| set | bm25 | 100 | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 6.50 | 0.88 |
| set | bm25 | 300 | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 6.25 | 0.83 |
| set | embeddings | 10 | 4 | 1.00 | 1.00 | 1.00 | 1.00* | 1.00 | – | 7.00 | 0.78 |
| set | embeddings | 30 | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 7.75 | 0.75 |
| set | embeddings | 100 | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 8.25 | 0.75 |
| set | embeddings | 300 | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 8.25 | 0.75 |
| set | rrf | 10 | 4 | 1.00 | 1.00 | 1.00 | 1.00* | 1.00 | – | 6.75 | 0.79 |
| set | rrf | 30 | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 7.50 | 0.77 |
| set | rrf | 100 | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 7.75 | 0.76 |
| set | rrf | 300 | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 8.25 | 0.75 |
| set | rrf_boosts | 10 | 4 | 0.75 | 0.75 | 1.00 | 1.00* | 1.00 | – | 5.75 | 0.65 |
| set | rrf_boosts | 30 | 4 | 0.75 | 0.75 | 1.00 | 1.00 | 1.00 | – | 5.75 | 0.60 |
| set | rrf_boosts | 100 | 4 | 0.75 | 0.75 | 1.00 | 1.00 | 1.00 | – | 5.75 | 0.60 |
| set | rrf_boosts | 300 | 4 | 0.75 | 0.75 | 1.00 | 1.00 | 1.00 | – | 5.75 | 0.60 |
| target | bm25 | 10 | 6 | 0.83 | 0.83 | 1.00 | 1.00* | 1.00 | – | 5.33 | 0.70 |
| target | bm25 | 30 | 6 | 0.83 | 1.00 | 1.00 | 1.00 | 1.00 | – | 5.33 | 0.81 |
| target | bm25 | 100 | 6 | 0.83 | 1.00 | 1.00 | 1.00 | 1.00 | – | 5.33 | 0.81 |
| target | bm25 | 300 | 6 | 0.83 | 0.83 | 0.83 | 1.00 | 0.83 | – | 5.67 | 0.85 |
| target | embeddings | 10 | 6 | 1.00 | 1.00 | 1.00 | 1.00* | 1.00 | – | 5.50 | 0.81 |
| target | embeddings | 30 | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 5.50 | 0.81 |
| target | embeddings | 100 | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 5.67 | 0.74 |
| target | embeddings | 300 | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 5.83 | 0.71 |
| target | rrf | 10 | 6 | 0.83 | 1.00 | 1.00 | 1.00* | 1.00 | – | 5.17 | 0.75 |
| target | rrf | 30 | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 5.33 | 0.92 |
| target | rrf | 100 | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 5.50 | 0.83 |
| target | rrf | 300 | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 5.50 | 0.92 |
| target | rrf_boosts | 10 | 6 | 0.83 | 1.00 | 1.00 | 1.00* | 1.00 | – | 5.00 | 0.81 |
| target | rrf_boosts | 30 | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 5.00 | 1.00 |
| target | rrf_boosts | 100 | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 5.00 | 0.92 |
| target | rrf_boosts | 300 | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 5.00 | 1.00 |

## lowercase

| kind | ablation | N | count | recall@1 | recall@3 | recall@5 | recall@10 | all_found@5 | person_cover@5 | mean_len@5 | mrr |
|---|---|---|---|---|---|---|---|---|---|---|---|
| both_candidates | bm25 | 10 | 2 | 0.00 | 0.33 | 0.67 | 1.00* | 0.50 | 0.75 | 5.00 | 0.35 |
| both_candidates | bm25 | 30 | 2 | 0.00 | 0.50 | 1.00 | 1.00 | 1.00 | 1.00 | 5.00 | 0.42 |
| both_candidates | bm25 | 100 | 2 | 0.17 | 0.50 | 1.00 | 1.00 | 1.00 | 1.00 | 5.00 | 0.67 |
| both_candidates | bm25 | 300 | 2 | 0.17 | 0.33 | 0.67 | 1.00 | 0.00 | 1.00 | 5.00 | 0.62 |
| both_candidates | embeddings | 10 | 2 | 0.17 | 0.33 | 0.50 | 1.00* | 0.50 | 0.50 | 5.00 | 0.56 |
| both_candidates | embeddings | 30 | 2 | 0.17 | 0.33 | 0.33 | 0.50 | 0.00 | 0.50 | 5.50 | 0.53 |
| both_candidates | embeddings | 100 | 2 | 0.00 | 0.17 | 0.33 | 0.33 | 0.00 | 0.50 | 5.50 | 0.17 |
| both_candidates | embeddings | 300 | 2 | 0.00 | 0.00 | 0.00 | 0.17 | 0.00 | 0.00 | 5.50 | 0.05 |
| both_candidates | rrf | 10 | 2 | 0.00 | 0.33 | 0.50 | 1.00* | 0.50 | 0.50 | 5.00 | 0.32 |
| both_candidates | rrf | 30 | 2 | 0.17 | 0.33 | 0.67 | 0.67 | 0.50 | 0.75 | 5.00 | 0.60 |
| both_candidates | rrf | 100 | 2 | 0.17 | 0.33 | 0.50 | 0.67 | 0.50 | 0.50 | 5.00 | 0.56 |
| both_candidates | rrf | 300 | 2 | 0.17 | 0.33 | 0.33 | 0.50 | 0.00 | 0.50 | 5.50 | 0.53 |
| both_candidates | rrf_boosts | 10 | 2 | 0.17 | 0.17 | 0.50 | 1.00* | 0.50 | 0.50 | 5.00 | 0.57 |
| both_candidates | rrf_boosts | 30 | 2 | 0.17 | 0.33 | 0.67 | 0.67 | 0.50 | 0.75 | 5.00 | 0.60 |
| both_candidates | rrf_boosts | 100 | 2 | 0.17 | 0.17 | 0.33 | 0.67 | 0.00 | 0.50 | 5.00 | 0.57 |
| both_candidates | rrf_boosts | 300 | 2 | 0.17 | 0.17 | 0.33 | 0.50 | 0.00 | 0.50 | 5.00 | 0.53 |
| lookalikes | bm25 | 10 | 4 | 0.73 | 0.85 | 0.85 | 1.00* | 0.50 | – | 5.00 | 1.00 |
| lookalikes | bm25 | 30 | 4 | 0.73 | 0.79 | 0.79 | 0.85 | 0.50 | – | 5.25 | 1.00 |
| lookalikes | bm25 | 100 | 4 | 0.67 | 0.73 | 0.73 | 0.73 | 0.50 | – | 5.25 | 0.88 |
| lookalikes | bm25 | 300 | 4 | 0.58 | 0.67 | 0.67 | 0.73 | 0.50 | – | 5.25 | 0.67 |
| lookalikes | embeddings | 10 | 4 | 0.73 | 0.85 | 0.94 | 1.00* | 0.75 | – | 5.50 | 0.68 |
| lookalikes | embeddings | 30 | 4 | 0.65 | 0.85 | 0.85 | 0.94 | 0.50 | – | 6.00 | 0.49 |
| lookalikes | embeddings | 100 | 4 | 0.58 | 0.58 | 0.58 | 0.65 | 0.50 | – | 6.00 | 0.11 |
| lookalikes | embeddings | 300 | 4 | 0.58 | 0.58 | 0.58 | 0.58 | 0.50 | – | 6.25 | 0.03 |
| lookalikes | rrf | 10 | 4 | 0.73 | 0.85 | 1.00 | 1.00* | 1.00 | – | 5.00 | 0.83 |
| lookalikes | rrf | 30 | 4 | 0.65 | 0.79 | 0.85 | 0.92 | 0.50 | – | 5.25 | 0.75 |
| lookalikes | rrf | 100 | 4 | 0.58 | 0.58 | 0.73 | 0.79 | 0.50 | – | 6.00 | 0.40 |
| lookalikes | rrf | 300 | 4 | 0.58 | 0.58 | 0.58 | 0.73 | 0.50 | – | 6.00 | 0.15 |
| lookalikes | rrf_boosts | 10 | 4 | 0.65 | 0.79 | 1.00 | 1.00* | 1.00 | – | 5.00 | 1.00 |
| lookalikes | rrf_boosts | 30 | 4 | 0.65 | 0.79 | 0.85 | 0.92 | 0.50 | – | 5.00 | 1.00 |
| lookalikes | rrf_boosts | 100 | 4 | 0.58 | 0.58 | 0.65 | 0.79 | 0.50 | – | 5.00 | 0.80 |
| lookalikes | rrf_boosts | 300 | 4 | 0.58 | 0.58 | 0.58 | 0.65 | 0.50 | – | 5.00 | 0.78 |
| set | bm25 | 10 | 4 | 0.75 | 1.00 | 1.00 | 1.00* | 1.00 | – | 6.75 | 0.50 |
| set | bm25 | 30 | 4 | 0.75 | 1.00 | 1.00 | 1.00 | 1.00 | – | 6.50 | 0.71 |
| set | bm25 | 100 | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 6.50 | 0.88 |
| set | bm25 | 300 | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 6.25 | 0.83 |
| set | embeddings | 10 | 4 | 1.00 | 1.00 | 1.00 | 1.00* | 1.00 | – | 7.00 | 0.78 |
| set | embeddings | 30 | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 7.75 | 0.75 |
| set | embeddings | 100 | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 8.25 | 0.75 |
| set | embeddings | 300 | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 8.25 | 0.75 |
| set | rrf | 10 | 4 | 1.00 | 1.00 | 1.00 | 1.00* | 1.00 | – | 6.75 | 0.79 |
| set | rrf | 30 | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 7.50 | 0.77 |
| set | rrf | 100 | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 7.75 | 0.76 |
| set | rrf | 300 | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 8.25 | 0.75 |
| set | rrf_boosts | 10 | 4 | 0.75 | 0.75 | 1.00 | 1.00* | 1.00 | – | 5.75 | 0.65 |
| set | rrf_boosts | 30 | 4 | 0.75 | 0.75 | 1.00 | 1.00 | 1.00 | – | 5.75 | 0.60 |
| set | rrf_boosts | 100 | 4 | 0.75 | 0.75 | 1.00 | 1.00 | 1.00 | – | 5.75 | 0.60 |
| set | rrf_boosts | 300 | 4 | 0.75 | 0.75 | 1.00 | 1.00 | 1.00 | – | 5.75 | 0.60 |
| target | bm25 | 10 | 6 | 0.83 | 0.83 | 1.00 | 1.00* | 1.00 | – | 5.33 | 0.70 |
| target | bm25 | 30 | 6 | 0.83 | 1.00 | 1.00 | 1.00 | 1.00 | – | 5.33 | 0.81 |
| target | bm25 | 100 | 6 | 0.83 | 1.00 | 1.00 | 1.00 | 1.00 | – | 5.33 | 0.81 |
| target | bm25 | 300 | 6 | 0.83 | 0.83 | 0.83 | 1.00 | 0.83 | – | 5.67 | 0.85 |
| target | embeddings | 10 | 6 | 1.00 | 1.00 | 1.00 | 1.00* | 1.00 | – | 5.50 | 0.81 |
| target | embeddings | 30 | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 5.50 | 0.81 |
| target | embeddings | 100 | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 5.67 | 0.74 |
| target | embeddings | 300 | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 5.83 | 0.71 |
| target | rrf | 10 | 6 | 0.83 | 1.00 | 1.00 | 1.00* | 1.00 | – | 5.17 | 0.75 |
| target | rrf | 30 | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 5.33 | 0.92 |
| target | rrf | 100 | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 5.50 | 0.83 |
| target | rrf | 300 | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 5.50 | 0.92 |
| target | rrf_boosts | 10 | 6 | 0.83 | 1.00 | 1.00 | 1.00* | 1.00 | – | 5.00 | 0.81 |
| target | rrf_boosts | 30 | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 5.00 | 1.00 |
| target | rrf_boosts | 100 | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 5.00 | 0.92 |
| target | rrf_boosts | 300 | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 5.00 | 1.00 |

## original

| kind | ablation | N | count | recall@1 | recall@3 | recall@5 | recall@10 | all_found@5 | person_cover@5 | mean_len@5 | mrr |
|---|---|---|---|---|---|---|---|---|---|---|---|
| both_candidates | bm25 | 10 | 1 | 0.00 | 0.67 | 1.00 | 1.00* | 1.00 | 1.00 | 5.00 | 0.50 |
| both_candidates | bm25 | 30 | 1 | 0.00 | 0.67 | 0.67 | 1.00 | 0.00 | 1.00 | 5.00 | 0.50 |
| both_candidates | bm25 | 100 | 1 | 0.33 | 0.67 | 1.00 | 1.00 | 1.00 | 1.00 | 5.00 | 1.00 |
| both_candidates | bm25 | 300 | 1 | 0.33 | 0.33 | 0.33 | 1.00 | 0.00 | 0.50 | 5.00 | 1.00 |
| both_candidates | embeddings | 10 | 1 | 0.33 | 0.67 | 0.67 | 1.00* | 0.00 | 1.00 | 5.00 | 1.00 |
| both_candidates | embeddings | 30 | 1 | 0.33 | 0.33 | 0.67 | 1.00 | 0.00 | 1.00 | 5.00 | 1.00 |
| both_candidates | embeddings | 100 | 1 | 0.00 | 0.33 | 0.33 | 0.67 | 0.00 | 0.50 | 5.00 | 0.33 |
| both_candidates | embeddings | 300 | 1 | 0.00 | 0.00 | 0.00 | 0.33 | 0.00 | 0.00 | 5.00 | 0.12 |
| both_candidates | rrf | 10 | 1 | 0.00 | 0.67 | 1.00 | 1.00* | 1.00 | 1.00 | 5.00 | 0.50 |
| both_candidates | rrf | 30 | 1 | 0.00 | 0.67 | 1.00 | 1.00 | 1.00 | 1.00 | 5.00 | 0.50 |
| both_candidates | rrf | 100 | 1 | 0.33 | 0.67 | 1.00 | 1.00 | 1.00 | 1.00 | 5.00 | 1.00 |
| both_candidates | rrf | 300 | 1 | 0.33 | 0.33 | 0.33 | 0.67 | 0.00 | 0.50 | 5.00 | 1.00 |
| both_candidates | rrf_boosts | 10 | 1 | 0.33 | 0.33 | 0.67 | 1.00* | 0.00 | 1.00 | 5.00 | 1.00 |
| both_candidates | rrf_boosts | 30 | 1 | 0.33 | 0.67 | 1.00 | 1.00 | 1.00 | 1.00 | 5.00 | 1.00 |
| both_candidates | rrf_boosts | 100 | 1 | 0.33 | 0.67 | 0.67 | 1.00 | 0.00 | 1.00 | 5.00 | 1.00 |
| both_candidates | rrf_boosts | 300 | 1 | 0.33 | 0.33 | 0.33 | 0.67 | 0.00 | 0.50 | 5.00 | 1.00 |
| lookalikes | bm25 | 10 | 3 | 0.64 | 0.81 | 1.00 | 1.00* | 1.00 | – | 5.00 | 1.00 |
| lookalikes | bm25 | 30 | 3 | 0.64 | 0.72 | 0.81 | 0.89 | 0.33 | – | 5.00 | 1.00 |
| lookalikes | bm25 | 100 | 3 | 0.44 | 0.64 | 0.64 | 0.72 | 0.33 | – | 5.33 | 0.61 |
| lookalikes | bm25 | 300 | 3 | 0.44 | 0.53 | 0.64 | 0.64 | 0.33 | – | 5.33 | 0.57 |
| lookalikes | embeddings | 10 | 3 | 0.64 | 0.81 | 0.81 | 1.00* | 0.33 | – | 5.33 | 0.83 |
| lookalikes | embeddings | 30 | 3 | 0.53 | 0.81 | 0.81 | 0.81 | 0.33 | – | 5.67 | 0.61 |
| lookalikes | embeddings | 100 | 3 | 0.44 | 0.44 | 0.61 | 0.61 | 0.33 | – | 6.00 | 0.16 |
| lookalikes | embeddings | 300 | 3 | 0.44 | 0.44 | 0.44 | 0.53 | 0.33 | – | 6.00 | 0.06 |
| lookalikes | rrf | 10 | 3 | 0.64 | 0.81 | 0.89 | 1.00* | 0.67 | – | 5.00 | 1.00 |
| lookalikes | rrf | 30 | 3 | 0.64 | 0.81 | 0.81 | 0.81 | 0.33 | – | 5.33 | 1.00 |
| lookalikes | rrf | 100 | 3 | 0.44 | 0.64 | 0.72 | 0.81 | 0.33 | – | 5.67 | 0.61 |
| lookalikes | rrf | 300 | 3 | 0.44 | 0.53 | 0.53 | 0.64 | 0.33 | – | 5.67 | 0.30 |
| lookalikes | rrf_boosts | 10 | 3 | 0.53 | 0.72 | 1.00 | 1.00* | 1.00 | – | 5.00 | 1.00 |
| lookalikes | rrf_boosts | 30 | 3 | 0.53 | 0.81 | 0.81 | 0.81 | 0.33 | – | 5.00 | 1.00 |
| lookalikes | rrf_boosts | 100 | 3 | 0.44 | 0.53 | 0.72 | 0.81 | 0.33 | – | 5.00 | 0.83 |
| lookalikes | rrf_boosts | 300 | 3 | 0.44 | 0.53 | 0.53 | 0.64 | 0.33 | – | 5.00 | 0.83 |
| set | bm25 | 10 | 4 | 0.75 | 1.00 | 1.00 | 1.00* | 1.00 | – | 7.00 | 0.51 |
| set | bm25 | 30 | 4 | 0.75 | 1.00 | 1.00 | 1.00 | 1.00 | – | 6.75 | 0.53 |
| set | bm25 | 100 | 4 | 0.75 | 1.00 | 1.00 | 1.00 | 1.00 | – | 7.00 | 0.45 |
| set | bm25 | 300 | 4 | 0.75 | 1.00 | 1.00 | 1.00 | 1.00 | – | 7.00 | 0.44 |
| set | embeddings | 10 | 4 | 1.00 | 1.00 | 1.00 | 1.00* | 1.00 | – | 6.75 | 0.78 |
| set | embeddings | 30 | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 8.00 | 0.75 |
| set | embeddings | 100 | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 8.25 | 0.75 |
| set | embeddings | 300 | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 8.25 | 0.75 |
| set | rrf | 10 | 4 | 1.00 | 1.00 | 1.00 | 1.00* | 1.00 | – | 7.00 | 0.78 |
| set | rrf | 30 | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 7.50 | 0.76 |
| set | rrf | 100 | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 8.25 | 0.75 |
| set | rrf | 300 | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 8.25 | 0.75 |
| set | rrf_boosts | 10 | 4 | 0.75 | 0.75 | 1.00 | 1.00* | 1.00 | – | 5.75 | 0.60 |
| set | rrf_boosts | 30 | 4 | 0.75 | 0.75 | 1.00 | 1.00 | 1.00 | – | 5.75 | 0.59 |
| set | rrf_boosts | 100 | 4 | 0.75 | 0.75 | 1.00 | 1.00 | 1.00 | – | 5.75 | 0.59 |
| set | rrf_boosts | 300 | 4 | 0.75 | 0.75 | 1.00 | 1.00 | 1.00 | – | 5.75 | 0.59 |
| target | bm25 | 10 | 6 | 0.83 | 0.83 | 0.83 | 1.00* | 0.83 | – | 5.33 | 0.64 |
| target | bm25 | 30 | 6 | 0.83 | 1.00 | 1.00 | 1.00 | 1.00 | – | 5.17 | 0.69 |
| target | bm25 | 100 | 6 | 0.83 | 1.00 | 1.00 | 1.00 | 1.00 | – | 5.50 | 0.69 |
| target | bm25 | 300 | 6 | 0.83 | 0.83 | 0.83 | 1.00 | 0.83 | – | 5.67 | 0.74 |
| target | embeddings | 10 | 6 | 1.00 | 1.00 | 1.00 | 1.00* | 1.00 | – | 5.50 | 0.81 |
| target | embeddings | 30 | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 5.50 | 0.79 |
| target | embeddings | 100 | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 5.67 | 0.64 |
| target | embeddings | 300 | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 5.83 | 0.60 |
| target | rrf | 10 | 6 | 0.83 | 1.00 | 1.00 | 1.00* | 1.00 | – | 5.33 | 0.69 |
| target | rrf | 30 | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 5.33 | 0.81 |
| target | rrf | 100 | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 5.50 | 0.83 |
| target | rrf | 300 | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 5.50 | 0.92 |
| target | rrf_boosts | 10 | 6 | 0.83 | 1.00 | 1.00 | 1.00* | 1.00 | – | 5.00 | 0.69 |
| target | rrf_boosts | 30 | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 5.00 | 0.92 |
| target | rrf_boosts | 100 | 6 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 5.00 | 0.89 |
| target | rrf_boosts | 300 | 6 | 0.83 | 1.00 | 1.00 | 1.00 | 1.00 | – | 5.00 | 0.83 |

## template

| kind | ablation | N | count | recall@1 | recall@3 | recall@5 | recall@10 | all_found@5 | person_cover@5 | mean_len@5 | mrr |
|---|---|---|---|---|---|---|---|---|---|---|---|
| both_candidates | bm25 | 10 | 3 | 0.11 | 0.33 | 0.78 | 1.00* | 0.33 | 0.83 | 5.00 | 0.61 |
| both_candidates | bm25 | 30 | 3 | 0.11 | 0.56 | 0.56 | 0.67 | 0.33 | 0.67 | 5.00 | 0.67 |
| both_candidates | bm25 | 100 | 3 | 0.11 | 0.44 | 0.44 | 0.67 | 0.33 | 0.50 | 5.00 | 0.56 |
| both_candidates | bm25 | 300 | 3 | 0.11 | 0.44 | 0.56 | 0.67 | 0.33 | 0.67 | 5.00 | 0.56 |
| both_candidates | embeddings | 10 | 3 | 0.33 | 0.56 | 0.67 | 1.00* | 0.33 | 0.83 | 5.00 | 1.00 |
| both_candidates | embeddings | 30 | 3 | 0.33 | 0.44 | 0.56 | 0.67 | 0.33 | 0.67 | 5.00 | 1.00 |
| both_candidates | embeddings | 100 | 3 | 0.11 | 0.33 | 0.56 | 0.56 | 0.33 | 0.67 | 5.00 | 0.57 |
| both_candidates | embeddings | 300 | 3 | 0.11 | 0.33 | 0.33 | 0.56 | 0.00 | 0.50 | 5.00 | 0.56 |
| both_candidates | rrf | 10 | 3 | 0.11 | 0.56 | 0.78 | 1.00* | 0.33 | 1.00 | 5.00 | 0.67 |
| both_candidates | rrf | 30 | 3 | 0.11 | 0.56 | 0.67 | 0.78 | 0.33 | 0.83 | 5.00 | 0.67 |
| both_candidates | rrf | 100 | 3 | 0.22 | 0.56 | 0.56 | 0.67 | 0.33 | 0.67 | 5.00 | 0.83 |
| both_candidates | rrf | 300 | 3 | 0.33 | 0.56 | 0.56 | 0.56 | 0.33 | 0.67 | 5.00 | 1.00 |
| both_candidates | rrf_boosts | 10 | 3 | 0.11 | 0.33 | 0.67 | 1.00* | 0.00 | 1.00 | 5.00 | 0.61 |
| both_candidates | rrf_boosts | 30 | 3 | 0.22 | 0.56 | 0.67 | 0.78 | 0.33 | 0.83 | 5.00 | 0.83 |
| both_candidates | rrf_boosts | 100 | 3 | 0.22 | 0.56 | 0.56 | 0.56 | 0.33 | 0.67 | 5.00 | 0.83 |
| both_candidates | rrf_boosts | 300 | 3 | 0.33 | 0.56 | 0.56 | 0.56 | 0.33 | 0.67 | 5.00 | 1.00 |
| lookalikes | bm25 | 10 | 78 | 0.48 | 0.68 | 0.79 | 1.00* | 0.47 | – | 5.19 | 0.79 |
| lookalikes | bm25 | 30 | 78 | 0.45 | 0.65 | 0.72 | 0.83 | 0.40 | – | 5.18 | 0.77 |
| lookalikes | bm25 | 100 | 78 | 0.38 | 0.46 | 0.53 | 0.60 | 0.33 | – | 5.18 | 0.55 |
| lookalikes | bm25 | 300 | 78 | 0.36 | 0.42 | 0.46 | 0.52 | 0.33 | – | 5.15 | 0.49 |
| lookalikes | embeddings | 10 | 78 | 0.48 | 0.67 | 0.86 | 1.00* | 0.60 | – | 5.32 | 0.79 |
| lookalikes | embeddings | 30 | 78 | 0.46 | 0.58 | 0.67 | 0.83 | 0.37 | – | 5.47 | 0.73 |
| lookalikes | embeddings | 100 | 78 | 0.37 | 0.42 | 0.46 | 0.54 | 0.33 | – | 5.68 | 0.35 |
| lookalikes | embeddings | 300 | 78 | 0.36 | 0.40 | 0.43 | 0.47 | 0.33 | – | 5.77 | 0.25 |
| lookalikes | rrf | 10 | 78 | 0.50 | 0.72 | 0.85 | 1.00* | 0.60 | – | 5.21 | 0.85 |
| lookalikes | rrf | 30 | 78 | 0.49 | 0.63 | 0.73 | 0.88 | 0.44 | – | 5.23 | 0.83 |
| lookalikes | rrf | 100 | 78 | 0.40 | 0.49 | 0.51 | 0.60 | 0.33 | – | 5.35 | 0.59 |
| lookalikes | rrf | 300 | 78 | 0.40 | 0.46 | 0.48 | 0.51 | 0.33 | – | 5.44 | 0.49 |
| lookalikes | rrf_boosts | 10 | 78 | 0.50 | 0.66 | 0.86 | 1.00* | 0.62 | – | 5.01 | 0.93 |
| lookalikes | rrf_boosts | 30 | 78 | 0.49 | 0.61 | 0.73 | 0.88 | 0.42 | – | 5.01 | 0.91 |
| lookalikes | rrf_boosts | 100 | 78 | 0.38 | 0.49 | 0.51 | 0.60 | 0.33 | – | 5.01 | 0.65 |
| lookalikes | rrf_boosts | 300 | 78 | 0.40 | 0.46 | 0.48 | 0.51 | 0.33 | – | 5.01 | 0.63 |
| set | bm25 | 10 | 61 | 1.00 | 1.00 | 1.00 | 1.00* | 1.00 | – | 6.57 | 0.70 |
| set | bm25 | 30 | 61 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 6.20 | 0.82 |
| set | bm25 | 100 | 61 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 6.36 | 0.78 |
| set | bm25 | 300 | 61 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 6.44 | 0.80 |
| set | embeddings | 10 | 61 | 1.00 | 1.00 | 1.00 | 1.00* | 1.00 | – | 5.95 | 0.93 |
| set | embeddings | 30 | 61 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 6.34 | 0.88 |
| set | embeddings | 100 | 61 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 7.18 | 0.61 |
| set | embeddings | 300 | 61 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 7.69 | 0.51 |
| set | rrf | 10 | 61 | 1.00 | 1.00 | 1.00 | 1.00* | 1.00 | – | 6.03 | 0.87 |
| set | rrf | 30 | 61 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 6.03 | 0.88 |
| set | rrf | 100 | 61 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 6.44 | 0.79 |
| set | rrf | 300 | 61 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 6.51 | 0.77 |
| set | rrf_boosts | 10 | 61 | 1.00 | 1.00 | 1.00 | 1.00* | 1.00 | – | 5.23 | 1.00 |
| set | rrf_boosts | 30 | 61 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 5.23 | 1.00 |
| set | rrf_boosts | 100 | 61 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 5.23 | 1.00 |
| set | rrf_boosts | 300 | 61 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 5.23 | 1.00 |
| target | bm25 | 10 | 159 | 0.81 | 0.92 | 0.97 | 1.00* | 0.97 | – | 5.54 | 0.76 |
| target | bm25 | 30 | 159 | 0.87 | 0.96 | 0.99 | 0.99 | 0.99 | – | 5.37 | 0.83 |
| target | bm25 | 100 | 159 | 0.86 | 0.92 | 0.96 | 0.99 | 0.96 | – | 5.36 | 0.82 |
| target | bm25 | 300 | 159 | 0.86 | 0.89 | 0.91 | 0.96 | 0.91 | – | 5.41 | 0.83 |
| target | embeddings | 10 | 159 | 0.94 | 0.99 | 1.00 | 1.00* | 1.00 | – | 5.39 | 0.88 |
| target | embeddings | 30 | 159 | 0.94 | 0.99 | 0.99 | 1.00 | 0.99 | – | 5.67 | 0.86 |
| target | embeddings | 100 | 159 | 0.84 | 0.94 | 0.96 | 0.99 | 0.96 | – | 6.05 | 0.71 |
| target | embeddings | 300 | 159 | 0.83 | 0.91 | 0.93 | 0.99 | 0.93 | – | 6.26 | 0.66 |
| target | rrf | 10 | 159 | 0.93 | 0.99 | 1.00 | 1.00* | 1.00 | – | 5.45 | 0.89 |
| target | rrf | 30 | 159 | 0.95 | 0.98 | 1.00 | 1.00 | 1.00 | – | 5.40 | 0.91 |
| target | rrf | 100 | 159 | 0.91 | 0.96 | 0.99 | 0.99 | 0.99 | – | 5.58 | 0.86 |
| target | rrf | 300 | 159 | 0.91 | 0.95 | 0.96 | 0.99 | 0.96 | – | 5.80 | 0.82 |
| target | rrf_boosts | 10 | 159 | 0.85 | 0.96 | 0.99 | 1.00* | 0.99 | – | 5.08 | 0.81 |
| target | rrf_boosts | 30 | 159 | 0.90 | 0.97 | 0.99 | 1.00 | 0.99 | – | 5.08 | 0.87 |
| target | rrf_boosts | 100 | 159 | 0.87 | 0.95 | 0.97 | 0.99 | 0.97 | – | 5.08 | 0.85 |
| target | rrf_boosts | 300 | 159 | 0.87 | 0.94 | 0.96 | 0.98 | 0.96 | – | 5.08 | 0.84 |

## recall@5 without referenced queries (rrf_boosts, frozen group)

| kind | N | recall@5 |
|---|---|---|
| both_candidates | 10 | 0.50 |
| both_candidates | 30 | 0.67 |
| both_candidates | 100 | 0.33 |
| both_candidates | 300 | 0.33 |
| lookalikes | 10 | 1.00 |
| lookalikes | 30 | 0.85 |
| lookalikes | 100 | 0.65 |
| lookalikes | 300 | 0.58 |
| set | 10 | 1.00 |
| set | 30 | 1.00 |
| set | 100 | 1.00 |
| set | 300 | 1.00 |
| target | 10 | 1.00 |
| target | 30 | 1.00 |
| target | 100 | 1.00 |
| target | 300 | 1.00 |

## What we learned (hand-written, 2026-11-08)

- Pooled dev recall@5 for rrf_boosts (target + set + both_candidates; lookalikes excluded), N=10/30/100/300:
  - hashing: frozen (12) 0.97/1.00/0.89/0.97; template (223) 0.96/0.97/0.92/0.91.
  - fastembed: frozen (12) 0.92/0.94/0.89/0.89; template (223) 0.99/0.99/0.98/0.97.
- The frozen headline covers only 12 queries, so one query moves it by about 0.08. Its non-monotonic shape (N=100 below
  N=300) is noise. The 223 template queries are the stable signal.
- On templates, fastembed beats hashing at every N, and the gap grows with N (0.97 vs 0.91 at N=300). With hashing,
  `embeddings` alone collapses on both_candidates at N≥100. Production should use fastembed.
- Fused (rrf) beats either ranker alone at N=300 with fastembed: templates 0.97, against bm25 0.93 and embeddings 0.94.
- Boosts have about the same recall as plain rrf, and the list is shorter: mean_len at K=5 is 5.1 against 5.6–6.0.
  This is because boosts move contacts to the top instead of appending them.
- All dev frozen misses are the same pattern: a **bare first name** shared by two people, with 3+ agents between them.
  - amb-person-006 ("Has Daniel gotten back to you yet?"): 3 agents across Daniel Walsh and Daniel Kaplan. K=5 returns
    one Walsh agent and not the other.
  - multi-person-006 ("Ask Sam and Alice Chen …"): 3 Sam agents across Sam Okafor and Sam Rivera. With fastembed the
    full-name Alice Chen match, plus filler pulled in by "running club", pushes all the Sams out.
  - person_cover is the better metric for clarify, because the IA only needs one agent per person to ask the question.
    The full-recall numbers understate what the IA actually needs here.
- The lowercase group equals frozen exactly in both runs. Under the per-word rule (BR1 I1), all-lowercase lines don't
  lose name detection in these cases. The parked `I'm`/`I'll` gap is not exercised by this group.
- Templates dropped: 273 matched a frozen message, 100 overlapped test cases, 82 were duplicates and 4 had empty
  expected sets. No labelling errors were swallowed (controller recount).
- No retrieval value was changed. A first-name expansion for clarify cases, or a K bump, would be a change justified by
  dev failures, and needs Siddharth's approval plus a `changes.md` entry.
