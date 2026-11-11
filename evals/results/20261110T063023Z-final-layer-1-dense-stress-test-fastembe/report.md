# Retrieval eval (dense stress roster): Final layer-1 dense stress test fastembed, frozen config 39a1439

- command: `python -m evals.run retrieval --split test --world dense --embedder fastembed --purpose 'Final layer-1 dense stress test fastembed, frozen config 39a1439'`
- split: test; embedder: fastembed; descriptions: world (forced for dense)
- counts: {'dense': 168, 'target_exact': 48, 'target_para': 48, 'topic_noname': 24, 'history_pull': 48, 'referenced': 48, 'skipped_n_below_required': 0}
- paraphrase file sha256: ec5ae4f8eb9958d2b4e6bcba9333ee6c13ccd607bd6a317efde5f53cb17e3db0; dropped at load: ['w-9 form']; topics without a paraphrase: []
- dense test target_para recall@20 at N=100/200/300: 0.85/0.85/0.85 (base@20 0.42/0.44/0.44)

Two contacts own 48 agents each (96 in all); base@20 is the name-overlap baseline. median rank is the median rank of the first expected agent in the full fused ranking.

| kind | N | count | recall@5 | recall@10 | recall@20 | base@20 | mrr | median rank |
|---|---|---|---|---|---|---|---|---|
| history_pull | 100 | 48 | 0.42 | 0.60 | 0.85 | 0.23 | 0.31 | 8 |
| history_pull | 200 | 48 | 0.44 | 0.62 | 0.85 | 0.10 | 0.32 | 7 |
| history_pull | 300 | 48 | 0.44 | 0.65 | 0.85 | 0.12 | 0.32 | 7 |
| target_exact | 100 | 48 | 1.00 | 1.00 | 1.00 | 1.00 | 0.99 | 1 |
| target_exact | 200 | 48 | 1.00 | 1.00 | 1.00 | 1.00 | 0.99 | 1 |
| target_exact | 300 | 48 | 1.00 | 1.00 | 1.00 | 1.00 | 0.99 | 1 |
| target_para | 100 | 48 | 0.44 | 0.56 | 0.85 | 0.42 | 0.27 | 8 |
| target_para | 200 | 48 | 0.42 | 0.56 | 0.85 | 0.44 | 0.28 | 8.5 |
| target_para | 300 | 48 | 0.44 | 0.58 | 0.85 | 0.44 | 0.27 | 8.5 |
| topic_noname | 100 | 24 | 0.44 | 0.52 | 0.77 | 0.27 | 0.41 | 3 |
| topic_noname | 200 | 24 | 0.27 | 0.38 | 0.58 | 0.06 | 0.21 | 6.5 |
| topic_noname | 300 | 24 | 0.17 | 0.35 | 0.44 | 0.04 | 0.16 | 8.5 |

## What we learned

This is the first run on the dense test topics (24 topics, 168 queries). Frozen config `39a1439`. Compared with dense dev, `20261110T000150Z`.

- **Test scores are higher than dev on every kind:**

  | kind | test | dev |
  |---|---|---|
  | `target_para` | 0.85 / 0.85 / 0.85 | 0.72 / 0.72 / 0.78 |
  | `history_pull` | 0.85 / 0.85 / 0.85 | 0.76 / 0.76 / 0.78 |
  | `target_exact` | 1.00 | 1.00 |

  The test topics' paraphrases seem easier, so dev was the harder split here and A3's dev result doesn't look overfit.
- **Names-free questions are still the weak spot.** `topic_noname` recall@20 is 0.77 / 0.58 / 0.44 at N=100/200/300 (dev 0.63 / 0.43 / 0.24). It falls steeply with N on both splits. MRR is 0.16–0.41.
- **Ranks within the top 20 stay low.** `target_para` and `history_pull` MRR is about 0.3, so the target is usually inside the 20 cards but not near the top.
