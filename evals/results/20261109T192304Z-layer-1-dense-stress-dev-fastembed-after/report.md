# Retrieval eval (dense stress roster): layer-1 dense stress dev fastembed after fixes

- command: `python -m evals.run retrieval --world dense --embedder fastembed --purpose 'layer-1 dense stress dev fastembed after fixes'`
- split: dev; embedder: fastembed; descriptions: world (forced for dense)
- counts: {'dense': 163, 'target_exact': 48, 'target_para': 46, 'topic_noname': 23, 'history_pull': 46, 'referenced': 46, 'skipped_n_below_required': 0}
- paraphrase file sha256: ec5ae4f8eb9958d2b4e6bcba9333ee6c13ccd607bd6a317efde5f53cb17e3db0; dropped at load: ['w-9 form']; topics without a paraphrase: ['w-9 form']
- dense dev target_para recall@20 at N=100/200/300: 0.67/0.67/0.72 (base@20 0.22/0.50/0.24)

Two contacts own 48 agents each (96 in all); base@20 is the name-overlap baseline. median rank is the median rank of the first expected agent in the full fused ranking.

| kind | N | count | recall@5 | recall@10 | recall@20 | base@20 | mrr | median rank |
|---|---|---|---|---|---|---|---|---|
| history_pull | 100 | 46 | 0.09 | 0.15 | 0.22 | 0.28 | 0.09 | 41 |
| history_pull | 200 | 46 | 0.00 | 0.09 | 0.11 | 0.13 | 0.03 | 55 |
| history_pull | 300 | 46 | 0.04 | 0.11 | 0.13 | 0.20 | 0.04 | 52 |
| target_exact | 100 | 48 | 1.00 | 1.00 | 1.00 | 1.00 | 0.98 | 1 |
| target_exact | 200 | 48 | 1.00 | 1.00 | 1.00 | 1.00 | 0.98 | 1 |
| target_exact | 300 | 48 | 1.00 | 1.00 | 1.00 | 1.00 | 0.97 | 1 |
| target_para | 100 | 46 | 0.28 | 0.48 | 0.67 | 0.22 | 0.18 | 12 |
| target_para | 200 | 46 | 0.35 | 0.48 | 0.67 | 0.50 | 0.21 | 13.5 |
| target_para | 300 | 46 | 0.37 | 0.50 | 0.72 | 0.24 | 0.21 | 10 |
| topic_noname | 100 | 23 | 0.22 | 0.33 | 0.50 | 0.09 | 0.24 | 12 |
| topic_noname | 200 | 23 | 0.13 | 0.22 | 0.37 | 0.09 | 0.18 | 20 |
| topic_noname | 300 | 23 | 0.11 | 0.15 | 0.28 | 0.07 | 0.11 | 28 |

## What we learned

Re-run after the three eval-set fixes (changes.md, 2026-11-09): history_pull history is now topic-free ("{Other Full Name} got back to you."), templates no longer double determiners, and the tokenizer keeps one-character tokens, so `w-9 form` → "that W-9 thing" is dropped at load (47 topics; dev has 23 paraphrased topics). The paraphrase file is unchanged (same sha256). This run supersedes 20261109T190350Z.

- **target_para recall@20 is 0.67/0.67/0.72 at N=100/200/300 (was 0.73/0.69/0.73).** The drop comes from removing the leaking w-9 topic and from the cleaner query wording. The median rank is about 10–13 and MRR about 0.2. The name-overlap baseline is still at chance (0.22/0.50/0.24; 20 of 48 tied agents ≈ 0.42), so there's no leak.
- **New, real failure: history pulls retrieval toward the previous person.** history_pull recall@20 is 0.22/0.11/0.13, far below target_para's 0.67–0.72 on the same messages, and below the name-overlap baseline (0.28/0.13/0.20). The last exchange names the other person in full twice ("Tavish Kellerman got back to you." on the agent and assistant lines). The new message names the target once, by first name, with a paraphrased topic. At N=300, 846 of the 935 top-20 slots go to the OTHER person's agents, 89 to the target person's, and 0 to the base world. This is the cost of the fixed history window (last exchange in the query; global constraints): after an agent reports back about person A, a paraphrased request about person B retrieves A's cluster. Only `search_agents` can recover from this in `hybrid`. Any retrieval change, such as weighting the message above history, needs Siddharth's approval and a changes.md entry. Nothing was changed here.
- **The setup is harsh by design.** Both people own 48 agents on the same 48 topics, and the request paraphrases the topic. With exact topic words, target_exact stays at 1.00 (MRR 0.97–0.98).
- **topic_noname: 0.50/0.37/0.28**, degrading with N as base fillers on the same topics take slots.
