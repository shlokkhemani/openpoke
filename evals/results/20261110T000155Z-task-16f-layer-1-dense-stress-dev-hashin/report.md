# Retrieval eval (dense stress roster): Task 16f layer-1 dense stress dev hashing, A3 message weighting

- command: `python -m evals.run retrieval --world dense --embedder hashing --purpose 'Task 16f layer-1 dense stress dev hashing, A3 message weighting'`
- split: dev; embedder: hashing; descriptions: world (forced for dense)
- counts: {'dense': 163, 'target_exact': 48, 'target_para': 46, 'topic_noname': 23, 'history_pull': 46, 'referenced': 46, 'skipped_n_below_required': 0}
- paraphrase file sha256: ec5ae4f8eb9958d2b4e6bcba9333ee6c13ccd607bd6a317efde5f53cb17e3db0; dropped at load: ['w-9 form']; topics without a paraphrase: ['w-9 form']
- dense dev target_para recall@20 at N=100/200/300: 0.35/0.33/0.35 (base@20 0.22/0.50/0.24)

Two contacts own 48 agents each (96 in all); base@20 is the name-overlap baseline. median rank is the median rank of the first expected agent in the full fused ranking.

| kind | N | count | recall@5 | recall@10 | recall@20 | base@20 | mrr | median rank |
|---|---|---|---|---|---|---|---|---|
| history_pull | 100 | 46 | 0.07 | 0.15 | 0.28 | 0.28 | 0.07 | 33 |
| history_pull | 200 | 46 | 0.09 | 0.15 | 0.28 | 0.13 | 0.08 | 30.5 |
| history_pull | 300 | 46 | 0.07 | 0.17 | 0.28 | 0.20 | 0.08 | 31.5 |
| target_exact | 100 | 48 | 1.00 | 1.00 | 1.00 | 1.00 | 0.98 | 1 |
| target_exact | 200 | 48 | 1.00 | 1.00 | 1.00 | 1.00 | 0.98 | 1 |
| target_exact | 300 | 48 | 1.00 | 1.00 | 1.00 | 1.00 | 0.98 | 1 |
| target_para | 100 | 46 | 0.11 | 0.20 | 0.35 | 0.22 | 0.11 | 26.5 |
| target_para | 200 | 46 | 0.13 | 0.20 | 0.33 | 0.50 | 0.13 | 27 |
| target_para | 300 | 46 | 0.15 | 0.20 | 0.35 | 0.24 | 0.10 | 25 |
| topic_noname | 100 | 23 | 0.02 | 0.04 | 0.24 | 0.09 | 0.05 | 34 |
| topic_noname | 200 | 23 | 0.00 | 0.00 | 0.00 | 0.09 | 0.02 | 87 |
| topic_noname | 300 | 23 | 0.00 | 0.00 | 0.00 | 0.07 | 0.01 | 143 |

## What we learned

Retrieval now also ranks on the message alone (A3, Task 16f, changes.md 2026-11-09): RRF over BM25(message), emb(message), BM25(history+message), emb(history+message). No constant changed (k=20, rrf_k=60, history_turns=2). `queries.jsonl` is byte-identical to the measured scratch A3 run (Experiment 16f, FUTURE_WORK §1). Compared with `20261109T222656Z` (Task 16e, dense hashing). Hashing is informational only (Siddharth's ruling: guards are judged on fastembed).

- **history_pull recall@20 is 0.28 at every N (was 0.00).**
- **Small losses, as Experiment 16f measured.** target_para recall@20 0.35/0.37/0.37 → 0.35/0.33/0.35 (−2 and −1 of 46 queries at N=200/300); topic_noname at N=100 0.28 → 0.24. On a short message alone the token-hash embedder is noisier than on the longer history-plus-message string. These do not block, because the guards are judged on fastembed only.
