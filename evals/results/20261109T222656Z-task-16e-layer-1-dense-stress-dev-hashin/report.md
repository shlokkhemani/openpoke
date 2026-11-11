# Retrieval eval (dense stress roster): Task 16e layer-1 dense stress dev hashing, BM25 stopwords dropped

- command: `python -m evals.run retrieval --world dense --embedder hashing --purpose 'Task 16e layer-1 dense stress dev hashing, BM25 stopwords dropped'`
- split: dev; embedder: hashing; descriptions: world (forced for dense)
- counts: {'dense': 163, 'target_exact': 48, 'target_para': 46, 'topic_noname': 23, 'history_pull': 46, 'referenced': 46, 'skipped_n_below_required': 0}
- paraphrase file sha256: ec5ae4f8eb9958d2b4e6bcba9333ee6c13ccd607bd6a317efde5f53cb17e3db0; dropped at load: ['w-9 form']; topics without a paraphrase: ['w-9 form']
- dense dev target_para recall@20 at N=100/200/300: 0.35/0.37/0.37 (base@20 0.22/0.50/0.24)

Two contacts own 48 agents each (96 in all); base@20 is the name-overlap baseline. median rank is the median rank of the first expected agent in the full fused ranking.

| kind | N | count | recall@5 | recall@10 | recall@20 | base@20 | mrr | median rank |
|---|---|---|---|---|---|---|---|---|
| history_pull | 100 | 46 | 0.00 | 0.00 | 0.00 | 0.28 | 0.01 | 78 |
| history_pull | 200 | 46 | 0.00 | 0.00 | 0.00 | 0.13 | 0.01 | 78.5 |
| history_pull | 300 | 46 | 0.00 | 0.00 | 0.00 | 0.20 | 0.01 | 77.5 |
| target_exact | 100 | 48 | 1.00 | 1.00 | 1.00 | 1.00 | 0.97 | 1 |
| target_exact | 200 | 48 | 1.00 | 1.00 | 1.00 | 1.00 | 0.97 | 1 |
| target_exact | 300 | 48 | 1.00 | 1.00 | 1.00 | 1.00 | 0.96 | 1 |
| target_para | 100 | 46 | 0.09 | 0.20 | 0.35 | 0.22 | 0.09 | 27.5 |
| target_para | 200 | 46 | 0.11 | 0.20 | 0.37 | 0.50 | 0.11 | 26 |
| target_para | 300 | 46 | 0.13 | 0.15 | 0.37 | 0.24 | 0.10 | 25.5 |
| topic_noname | 100 | 23 | 0.00 | 0.07 | 0.28 | 0.09 | 0.04 | 37 |
| topic_noname | 200 | 23 | 0.00 | 0.00 | 0.00 | 0.09 | 0.01 | 78 |
| topic_noname | 300 | 23 | 0.00 | 0.00 | 0.00 | 0.07 | 0.01 | 121 |

## What we learned

BM25 query now drops stopwords (`_fts_query`, Task 16e, changes.md 2026-11-09). No other retrieval value changed (k=20, rrf_k=60, history_turns=2, embedding query unchanged). Compared with `20261109T192308Z` (dense, hashing).

- **target_para recall@20 is 0.35/0.37/0.37 (was 0.39/0.41/0.41).** recall@5 went 0.15 → 0.09–0.13 and MRR 0.11–0.13 → 0.09–0.11. history_pull is still 0.00 at k≤20. This is a small loss, on the same pattern as the fastembed dense run: stopword matches had been helping the target person's agents in this two-person roster.
