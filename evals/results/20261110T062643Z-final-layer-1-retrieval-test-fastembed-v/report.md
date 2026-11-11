# Retrieval eval: Final layer-1 retrieval test fastembed v2, frozen config 39a1439

- command: `python -m evals.run retrieval --split test --embedder fastembed --purpose 'Final layer-1 retrieval test fastembed v2, frozen config 39a1439'`
- split: test; embedder: fastembed; descriptions: regen
- counts: {'frozen': 33, 'original': 19, 'unrelated_history': 9, 'template': 301, 'frozen_cases_in_split': 33, 'skipped_empty_expected': 0, 'referenced': 272, 'skipped_n_below_required': 0}
- test recall@20 (rrf) at N=10/30/100/300: 1.00/1.00/0.95/0.90

Cells marked `*` have N <= K and are trivially 1.0. all_found, person_cover, mean_len and extra_referenced are at K=20; mrr is on the full fused ranking. Referenced ids from the last exchange are always appended.

## frozen

| kind | N | count | recall@5 | recall@10 | recall@20 | base@20 | all_found@20 | person_cover@20 | mean_len@20 | mrr | extra_referenced@20 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| both_candidates | 10 | 4 | 0.75 | 1.00* | 1.00* | 1.00 | 1.00 | 1.00 | 10.00 | 0.67 | – |
| both_candidates | 30 | 4 | 0.75 | 0.88 | 1.00 | 1.00 | 1.00 | 1.00 | 20.00 | 0.65 | – |
| both_candidates | 100 | 4 | 0.75 | 0.75 | 0.75 | 0.88 | 0.75 | 0.75 | 20.00 | 0.63 | – |
| both_candidates | 300 | 4 | 0.75 | 0.75 | 0.75 | 0.75 | 0.75 | 0.75 | 20.00 | 0.63 | – |
| lookalikes | 10 | 12 | 0.96 | 1.00* | 1.00* | 1.00 | 1.00 | – | 10.00 | 0.90 | – |
| lookalikes | 30 | 12 | 0.91 | 1.00 | 1.00 | 1.00 | 1.00 | – | 20.08 | 0.85 | – |
| lookalikes | 100 | 12 | 0.74 | 0.86 | 1.00 | 0.81 | 1.00 | – | 20.25 | 0.79 | – |
| lookalikes | 300 | 12 | 0.64 | 0.79 | 0.83 | 0.73 | 0.83 | – | 20.25 | 0.77 | – |
| set | 10 | 9 | 0.98 | 1.00* | 1.00* | 1.00 | 1.00 | – | 10.00 | 1.00 | – |
| set | 30 | 9 | 0.98 | 1.00 | 1.00 | 1.00 | 1.00 | – | 20.00 | 1.00 | – |
| set | 100 | 9 | 0.98 | 1.00 | 1.00 | 0.69 | 1.00 | – | 20.44 | 1.00 | – |
| set | 300 | 9 | 0.96 | 1.00 | 1.00 | 0.44 | 1.00 | – | 20.56 | 1.00 | – |
| target | 10 | 8 | 1.00 | 1.00* | 1.00* | 1.00 | 1.00 | – | 10.00 | 0.88 | – |
| target | 30 | 8 | 1.00 | 1.00 | 1.00 | 0.88 | 1.00 | – | 20.12 | 0.80 | – |
| target | 100 | 8 | 0.88 | 0.88 | 1.00 | 0.88 | 1.00 | – | 20.25 | 0.77 | – |
| target | 300 | 8 | 0.88 | 0.88 | 0.88 | 0.88 | 0.88 | – | 20.38 | 0.76 | – |

## original

| kind | N | count | recall@5 | recall@10 | recall@20 | base@20 | all_found@20 | person_cover@20 | mean_len@20 | mrr | extra_referenced@20 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| both_candidates | 10 | 1 | 1.00 | 1.00* | 1.00* | 1.00 | 1.00 | 1.00 | 10.00 | 0.50 | – |
| both_candidates | 30 | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 20.00 | 0.50 | – |
| both_candidates | 100 | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 20.00 | 1.00 | – |
| both_candidates | 300 | 1 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | 20.00 | 1.00 | – |
| lookalikes | 10 | 6 | 0.92 | 1.00* | 1.00* | 1.00 | 1.00 | – | 10.00 | 1.00 | – |
| lookalikes | 30 | 6 | 0.92 | 1.00 | 1.00 | 1.00 | 1.00 | – | 20.00 | 1.00 | – |
| lookalikes | 100 | 6 | 0.88 | 1.00 | 1.00 | 0.88 | 1.00 | – | 20.17 | 1.00 | – |
| lookalikes | 300 | 6 | 0.85 | 0.98 | 1.00 | 0.71 | 1.00 | – | 20.17 | 0.92 | – |
| set | 10 | 8 | 0.98 | 1.00* | 1.00* | 1.00 | 1.00 | – | 10.00 | 1.00 | – |
| set | 30 | 8 | 0.98 | 1.00 | 1.00 | 1.00 | 1.00 | – | 20.00 | 1.00 | – |
| set | 100 | 8 | 0.98 | 1.00 | 1.00 | 0.94 | 1.00 | – | 20.38 | 1.00 | – |
| set | 300 | 8 | 0.96 | 1.00 | 1.00 | 0.39 | 1.00 | – | 20.62 | 1.00 | – |
| target | 10 | 4 | 1.00 | 1.00* | 1.00* | 1.00 | 1.00 | – | 10.00 | 1.00 | – |
| target | 30 | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 20.00 | 1.00 | – |
| target | 100 | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 20.25 | 1.00 | – |
| target | 300 | 4 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 20.25 | 1.00 | – |

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
| lookalikes | 10 | 6 | 1.00 | 1.00* | 1.00* | 1.00 | 1.00 | – | 10.00 | 0.78 | 1.00 |
| lookalikes | 30 | 6 | 0.83 | 1.00 | 1.00 | 0.89 | 1.00 | – | 20.00 | 0.77 | 1.00 |
| lookalikes | 100 | 6 | 0.67 | 0.78 | 1.00 | 0.74 | 1.00 | – | 20.33 | 0.70 | 1.00 |
| lookalikes | 300 | 6 | 0.62 | 0.67 | 0.72 | 0.42 | 0.67 | – | 20.67 | 0.68 | 1.00 |
| target | 10 | 3 | 1.00 | 1.00* | 1.00* | 1.00 | 1.00 | – | 10.00 | 1.00 | 1.00 |
| target | 30 | 3 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 20.00 | 1.00 | 1.00 |
| target | 100 | 3 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 20.33 | 1.00 | 1.00 |
| target | 300 | 3 | 1.00 | 1.00 | 1.00 | 1.00 | 1.00 | – | 20.00 | 1.00 | 1.00 |

## recall@20 without referenced queries (frozen group)

| kind | N | recall@20 |
|---|---|---|
| lookalikes | 10 | 1.00 |
| lookalikes | 30 | 1.00 |
| lookalikes | 100 | 1.00 |
| lookalikes | 300 | 0.83 |
| target | 10 | 1.00 |
| target | 30 | 1.00 |
| target | 100 | 1.00 |
| target | 300 | 1.00 |

## What we learned

This is the first run on the test split (33 cases), with the configuration frozen at `39a1439` (A3 retrieval, stopwords dropped, k=20, history_turns=2). Compared with dev, `20261109T235838Z`.

- **Headline recall@20 is 1.00 / 1.00 / 0.95 / 0.90 at N=10/30/100/300 (dev: 1.00 at every N).** Frozen N=300 is 0.879 (dev 0.927). Original queries are 1.00 at every N. Template queries are identical to dev (the 301 template queries don't depend on the split).
- **Three frozen test cases miss at N=300:**
  - `amb-person-005` ("Email her and ask…"; both Alices; ranks 26/53 at N=100/300). The only mention of Alice is three history items back ("Did Alice Chen approve the Q3 budget yet?"), outside the 2-item window. The last exchange is a calendar summary. This is the history-window risk in a real case: the IA's transcript has the referent but retrieval doesn't.
  - `trigger-001` ("push my evening email recap to 8"): the target "Nightly digest" is at rank 33 at N=300. "Evening email recap" and "nightly digest" share no words, so this is a paraphrase miss.
  - `newtask-002`/`newtask-003`: lookalike distractors for create cases at ranks 23–39. These are excluded from the headline, and a create case doesn't need them in the cards.
- **unrelated_history** (9 queries) is 0.815 at N=300, about the same as dev's 0.812.
- **What to watch in layer 2:** `amb-person-005` and `trigger-001` are the two test cases where `hybrid`'s initial cards lack the target at N=300. If the IA doesn't search, these are the likely `hybrid` failures.
