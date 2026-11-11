# Retrieval eval (dense stress roster): Task 16f layer-1 dense stress dev fastembed, A3 message weighting

- command: `python -m evals.run retrieval --world dense --embedder fastembed --purpose 'Task 16f layer-1 dense stress dev fastembed, A3 message weighting'`
- split: dev; embedder: fastembed; descriptions: world (forced for dense)
- counts: {'dense': 163, 'target_exact': 48, 'target_para': 46, 'topic_noname': 23, 'history_pull': 46, 'referenced': 46, 'skipped_n_below_required': 0}
- paraphrase file sha256: ec5ae4f8eb9958d2b4e6bcba9333ee6c13ccd607bd6a317efde5f53cb17e3db0; dropped at load: ['w-9 form']; topics without a paraphrase: ['w-9 form']
- dense dev target_para recall@20 at N=100/200/300: 0.72/0.72/0.78 (base@20 0.22/0.50/0.24)

Two contacts own 48 agents each (96 in all); base@20 is the name-overlap baseline. median rank is the median rank of the first expected agent in the full fused ranking.

| kind | N | count | recall@5 | recall@10 | recall@20 | base@20 | mrr | median rank |
|---|---|---|---|---|---|---|---|---|
| history_pull | 100 | 46 | 0.22 | 0.46 | 0.76 | 0.28 | 0.16 | 12 |
| history_pull | 200 | 46 | 0.22 | 0.48 | 0.76 | 0.13 | 0.17 | 11 |
| history_pull | 300 | 46 | 0.28 | 0.50 | 0.78 | 0.20 | 0.19 | 10.5 |
| target_exact | 100 | 48 | 1.00 | 1.00 | 1.00 | 1.00 | 0.98 | 1 |
| target_exact | 200 | 48 | 1.00 | 1.00 | 1.00 | 1.00 | 0.99 | 1 |
| target_exact | 300 | 48 | 1.00 | 1.00 | 1.00 | 1.00 | 0.99 | 1 |
| target_para | 100 | 46 | 0.28 | 0.46 | 0.72 | 0.22 | 0.18 | 12 |
| target_para | 200 | 46 | 0.28 | 0.48 | 0.72 | 0.50 | 0.17 | 12 |
| target_para | 300 | 46 | 0.30 | 0.48 | 0.78 | 0.24 | 0.18 | 11.5 |
| topic_noname | 100 | 23 | 0.22 | 0.41 | 0.63 | 0.09 | 0.27 | 7 |
| topic_noname | 200 | 23 | 0.02 | 0.17 | 0.43 | 0.09 | 0.09 | 15 |
| topic_noname | 300 | 23 | 0.02 | 0.04 | 0.24 | 0.07 | 0.07 | 23 |

## What we learned

Retrieval now also ranks on the message alone (A3, Task 16f, changes.md 2026-11-09): RRF over BM25(message), emb(message), BM25(history+message), emb(history+message). No constant changed (k=20, rrf_k=60, history_turns=2). `queries.jsonl` is byte-identical to the measured scratch A3 run (Experiment 16f, FUTURE_WORK §1). Compared with `20261109T222653Z` (Task 16e, dense fastembed).

- **history_pull recall@20 is 0.76/0.76/0.78 at N=100/200/300 (was 0.20/0.22/0.22).** recall@5 0.00 → 0.22–0.28, recall@10 0.04–0.07 → 0.46–0.50, MRR 0.03 → 0.16–0.19. The follow-up's own words now rank by themselves instead of being diluted by the history turn.
- **target_para holds and its top ranks recover what Task 16e lost.** recall@20 0.70/0.70/0.70 → 0.72/0.72/0.78; recall@5 0.24/0.22/0.24 → 0.28/0.28/0.30; recall@10 0.39–0.41 → 0.46–0.48; MRR 0.14–0.15 → 0.17–0.18. target_exact stays 1.00; topic_noname rises (N=200 0.26 → 0.43).
