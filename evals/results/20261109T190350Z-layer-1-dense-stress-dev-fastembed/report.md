# Retrieval eval (dense stress roster): layer-1 dense stress dev fastembed

- command: `python -m evals.run retrieval --world dense --embedder fastembed --purpose 'layer-1 dense stress dev fastembed'`
- split: dev; embedder: fastembed; descriptions: world (forced for dense)
- counts: {'dense': 168, 'target_exact': 48, 'target_para': 48, 'topic_noname': 24, 'history_pull': 48, 'referenced': 48, 'skipped_n_below_required': 0}
- paraphrase file sha256: ec5ae4f8eb9958d2b4e6bcba9333ee6c13ccd607bd6a317efde5f53cb17e3db0; dropped at load: []; topics without a paraphrase: []
- dense dev target_para recall@20 at N=100/200/300: 0.73/0.69/0.73 (base@20 0.21/0.48/0.23)

Two contacts own 48 agents each (96 in all); base@20 is the name-overlap baseline. median rank is the median rank of the first expected agent in the full fused ranking.

| kind | N | count | recall@5 | recall@10 | recall@20 | base@20 | mrr | median rank |
|---|---|---|---|---|---|---|---|---|
| history_pull | 100 | 48 | 0.77 | 0.83 | 0.88 | 0.62 | 0.59 | 2 |
| history_pull | 200 | 48 | 0.73 | 0.81 | 0.85 | 0.58 | 0.54 | 2 |
| history_pull | 300 | 48 | 0.71 | 0.81 | 0.83 | 0.62 | 0.53 | 2 |
| target_exact | 100 | 48 | 1.00 | 1.00 | 1.00 | 1.00 | 0.98 | 1 |
| target_exact | 200 | 48 | 1.00 | 1.00 | 1.00 | 1.00 | 0.97 | 1 |
| target_exact | 300 | 48 | 1.00 | 1.00 | 1.00 | 1.00 | 0.95 | 1 |
| target_para | 100 | 48 | 0.29 | 0.48 | 0.73 | 0.21 | 0.21 | 11 |
| target_para | 200 | 48 | 0.33 | 0.50 | 0.69 | 0.48 | 0.24 | 10.5 |
| target_para | 300 | 48 | 0.38 | 0.52 | 0.73 | 0.23 | 0.25 | 9 |
| topic_noname | 100 | 24 | 0.25 | 0.35 | 0.56 | 0.08 | 0.25 | 11.5 |
| topic_noname | 200 | 24 | 0.15 | 0.25 | 0.46 | 0.08 | 0.20 | 17.5 |
| topic_noname | 300 | 24 | 0.12 | 0.19 | 0.35 | 0.06 | 0.14 | 18.5 |

## What we learned

- **The dense roster does what the base eval could not: it separates retrieval from name-matching.** With 48 agents per person, naming the person no longer gets the right agent into the top 20 for free. target_para recall@20 is 0.73/0.69/0.73 at N=100/200/300, against 0.96–1.00 on the base world. The median rank of the right agent is about 10 (rank 1 when the topic words are used: target_exact 1.00, MRR 0.95–0.98).
- **The name-overlap baseline is at chance on target_para (base@20 0.21/0.48/0.23).** The query shares one word, the first name, with all 48 of the person's agents, so the baseline picks 20 of 48 tied agents at random (expected ≈ 0.42; it swings because ties are broken by a per-query RNG, and there are only 48 queries). So the paraphrases don't leak topic words, and fastembed adds ~0.3–0.5 over chance.
- **Real gap for `hybrid`: about 1 in 4 paraphrased requests to a heavy user misses the top 20.** These need the `search_agents` tool (or a better-worded query from the IA). The misses cluster on loose paraphrases: proposal → "that pitch doc from before", flight change → "my trip back home", expense report → "that reimbursement thing from last week". In all 13 target_para misses at N=300, 18–20 of the top 20 are the right person's agents on other topics. The person is found but the topic is not, and the IA can see that from the cards.
- **topic_noname degrades with N (recall@20 0.56 → 0.46 → 0.35).** With no person, base email fillers on the same topics (other people) take the slots. This is the intended hard negative.
- **history_pull is easier than target_para (0.88/0.85/0.83 vs 0.73), not harder; that's a defect in how the queries were built (ruling R4).** The last exchange "{Other} replied {reply}." carries the topic's own words (the reply phrase), which BM25 matches on both people's same-topic agents. So this kind measures "a topic hint in history", not "history pulls toward the wrong person". The referenced agent is always appended, so the wrong-person pull never costs a slot anyway.
- **Paraphrase caveats.** `w-9 form` → "that W-9 thing" leaks (the tokenizer drops one-character tokens) and scores 1.00. Excluding it moves target_para@300 from 0.73 to ≈0.72. The two paraphrases that add person names (moving boxes → "…from Jen", parent-teacher meeting → "Jake's…") are test-split topics and don't affect this dev run. Query template glitch: "regarding the the food…" (template "the {topic}" + a paraphrase that starts with "the").
- **No retrieval value changed.** These are dev numbers; test runs once per final configuration.
