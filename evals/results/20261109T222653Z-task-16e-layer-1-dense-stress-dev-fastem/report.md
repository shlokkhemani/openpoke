# Retrieval eval (dense stress roster): Task 16e layer-1 dense stress dev fastembed, BM25 stopwords dropped

- command: `python -m evals.run retrieval --world dense --embedder fastembed --purpose 'Task 16e layer-1 dense stress dev fastembed, BM25 stopwords dropped'`
- split: dev; embedder: fastembed; descriptions: world (forced for dense)
- counts: {'dense': 163, 'target_exact': 48, 'target_para': 46, 'topic_noname': 23, 'history_pull': 46, 'referenced': 46, 'skipped_n_below_required': 0}
- paraphrase file sha256: ec5ae4f8eb9958d2b4e6bcba9333ee6c13ccd607bd6a317efde5f53cb17e3db0; dropped at load: ['w-9 form']; topics without a paraphrase: ['w-9 form']
- dense dev target_para recall@20 at N=100/200/300: 0.70/0.70/0.70 (base@20 0.22/0.50/0.24)

Two contacts own 48 agents each (96 in all); base@20 is the name-overlap baseline. median rank is the median rank of the first expected agent in the full fused ranking.

| kind | N | count | recall@5 | recall@10 | recall@20 | base@20 | mrr | median rank |
|---|---|---|---|---|---|---|---|---|
| history_pull | 100 | 46 | 0.00 | 0.07 | 0.20 | 0.28 | 0.03 | 55.5 |
| history_pull | 200 | 46 | 0.00 | 0.04 | 0.22 | 0.13 | 0.03 | 55 |
| history_pull | 300 | 46 | 0.00 | 0.04 | 0.22 | 0.20 | 0.03 | 55 |
| target_exact | 100 | 48 | 1.00 | 1.00 | 1.00 | 1.00 | 0.97 | 1 |
| target_exact | 200 | 48 | 1.00 | 1.00 | 1.00 | 1.00 | 0.97 | 1 |
| target_exact | 300 | 48 | 1.00 | 1.00 | 1.00 | 1.00 | 0.98 | 1 |
| target_para | 100 | 46 | 0.24 | 0.39 | 0.70 | 0.22 | 0.14 | 14.5 |
| target_para | 200 | 46 | 0.22 | 0.39 | 0.70 | 0.50 | 0.14 | 14 |
| target_para | 300 | 46 | 0.24 | 0.41 | 0.70 | 0.24 | 0.15 | 13.5 |
| topic_noname | 100 | 23 | 0.15 | 0.26 | 0.57 | 0.09 | 0.24 | 11 |
| topic_noname | 200 | 23 | 0.04 | 0.09 | 0.26 | 0.09 | 0.08 | 21 |
| topic_noname | 300 | 23 | 0.04 | 0.04 | 0.15 | 0.07 | 0.06 | 29 |

## What we learned

BM25 query now drops stopwords (`_fts_query`, Task 16e, changes.md 2026-11-09). No other retrieval value changed (k=20, rrf_k=60, history_turns=2, embedding query unchanged). Compared with `20261109T192304Z` (dense, fastembed).

- **target_para recall@20 is 0.70/0.70/0.70 at N=100/200/300 (was 0.67/0.67/0.72).** Higher ranks got worse: recall@5 went 0.28/0.35/0.37 → 0.24/0.22/0.24, recall@10 went 0.48/0.48/0.50 → 0.39/0.39/0.41, MRR went 0.18–0.21 → 0.14–0.15, and the median rank went 10–13.5 → 13.5–14.5.
- **history_pull recall@20 is 0.20/0.22/0.22 (was 0.22/0.11/0.13).** At N=200/300 more target agents get into the top 20, but recall@5 drops to 0.00 at every N and recall@10 drops to 0.04–0.07.
- **Reading.** In the dense world the two people share topics, so the person name is the one discriminating word. Stopwords had been adding BM25 signal that, in this roster, happened to favour the target's agents at the top ranks. Without them, BM25 ranks by name plus topic words only, and the target's agents spread more evenly through the top 20. Net: about the same at k=20 (the injected size), worse at k≤10. Not investigated further; the cause above is a hypothesis.
