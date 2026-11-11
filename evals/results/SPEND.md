# Spend ledger: company OpenRouter key

Every paid API call made on the company key, for reporting where the budget went. All amounts are in USD.

- **Key:** the company OpenRouter key (the one with the 50 USD limit). No part of the key is recorded here.
- **Budget:** 50.00 USD, starting 2026-11-08 (Siddharth). Spend before that date was on a personal key
  (4.17 USD: experiments 1–7 and the description regen) and is excluded.
- **Baseline:** OpenRouter `GET /api/v1/key` at 2026-11-08T00:36:46Z: limit 50.00, usage 0.00, remaining 50.00.

**Method.** For every paid command the ledger records:

- **Estimate:** the cost the command prints before it runs.
- **Runner actual:** tokens from every response's `usage` block × the list price in `evals/pricing.py`.
- **Billed:** the key's OpenRouter `usage` after the command minus before it. This figure is authoritative.

On the personal key, runner totals matched OpenRouter billing to within 0.01. OpenRouter's usage figure lags by
more than 20 s, so the "after" read is repeated until two reads agree. Nothing else uses the key while a command
runs, so each billed amount belongs to that one command.

## Ledger

| # | UTC start | run folder | estimate | runner actual | key usage before → after | billed | cumulative billed | remaining |
|---|---|---|---|---|---|---|---|---|
| 1 | 2026-11-08T00:37:48Z | `20261108T003748Z-experiment-7-full-with-ids-prompt-pronou` | 1.0766 | 1.0805 | 0.000000 → 1.080513 | **1.0805** | **1.0805** | 48.9195 |
| 2 | 2026-11-08T08:43:17Z | `20261108T084317Z-experiment-8-legacy-rules-with-the-names` | 0.3753 | 0.4399 | 1.080513 → 1.520387 | **0.4399** | **1.5204** | 48.4796 |
| 3 | 2026-11-09T18:51:55Z | – (writes `evals/world/stress/dense_paraphrases.json`) | 0.0021 | 0.0053 | 1.520387 → 1.525605 | **0.0052** | **1.5256** | 48.4744 |
| 4 | 2026-11-09T19:48:41Z | `20261109T194841Z-task-14-smoke-legacy-full-hybrid-on-the` | 0.2313 | 0.2013 | 1.525710 → 1.726976 | **0.2013** | **1.7270** | 48.2730 |
| 5 | 2026-11-09T20:06:08Z | `20261109T200608Z-task-15-dev-check-full-vs-hybrid-at-n-10` | 1.0972 | 1.1504 | 1.726976 → 2.877339 | **1.1504** | **2.8773** | 47.1227 |
| 6 | 2026-11-09T21:45:57Z | `20261109T214557Z-task-16-v2-baseline-agent-backed-history` | 1.4519 | 1.5420 | 2.877339 → 4.419306 | **1.5420** | **4.4193** | 45.5807 |
| 7 | 2026-11-10T00:08:01Z | `20261110T000801Z-task-16f-hybrid-on-v2-with-a3-message-we` | 0.4928 | 0.4668 | 4.419306 → 4.886077 | **0.4668** | **4.8861** | 45.1139 |
| 8 | 2026-11-10T19:35:19Z | `20261110T193519Z-final-test-run-haiku-legacy-rules-full-h` | 4.0110 | 4.1160 | 4.886077 → 9.002066 | **4.1160** | **9.0021** | 40.9979 |

## Commands

1. Experiment 7 (Haiku 5.5, dev split, `full` mode; a re-run after the ids-prompt edits). The "after" read was
   taken at 2026-11-08T00:42:12Z.

   ```
   python -m evals.run routing --split dev --modes full --sizes 10,30,100,300 --runs 3 --max-cost 3 --purpose "Experiment 7: full with ids-prompt pronoun rule and reply rule limited to existing threads, dev, 4 sizes x 3 runs (Haiku)" --yes
   ```

2. Experiment 8 (Haiku 5.5, dev split, `legacy_rules` mode; after the names prompt was made parallel to the ids
   prompt). The "before" read was taken at 2026-11-08T08:42:51Z, and the "after" reads at 08:48:21Z, 08:48:51Z and
   08:49:22Z all gave 1.5203865.

   ```
   python -m evals.run routing --split dev --modes legacy_rules --sizes 10,30,100,300 --runs 3 --max-cost 3 --purpose "Experiment 8: legacy_rules with the names prompt made parallel to the ids prompt, dev, 4 sizes x 3 runs (Haiku)" --yes
   ```

3. Task 12c dense-stress topic paraphrases (Haiku 5.5, 48 calls, 0 retries, 0 dropped, 0 errors; 10,236 prompt +
   8,600 completion tokens). The "before" read was taken at 2026-11-09T18:51:51Z, and the "after" reads at
   18:55:06Z and 18:55:36Z both gave 1.5256046. The estimate was low because it budgeted ~32 completion tokens
   per call and the model averaged ~180.

   ```
   python -m evals.run stress-paraphrase --yes
   ```

4. Task 14 smoke run (Haiku 5.5, dev split, `legacy`/`full`/`hybrid` × N = 10, 30 × 1 run; 96 case-runs, 0 infra
   errors). The "before" read was taken at 2026-11-09T19:48:36Z and gave 1.5257101, which is 0.0001 above row 3's
   "after" figure (late-settling usage from row 3). That 0.0001 is excluded from this row. The "after" reads at
   19:51:14Z and 19:51:44Z both gave 1.7269757.

   ```
   python -m evals.run routing --modes legacy,full,hybrid --sizes 10,30 --split dev --runs 1 --embedder fastembed --max-cost 1 --purpose "Task 14 smoke: legacy/full/hybrid on the real code path, dev, N=10/30 (Haiku)" --yes
   ```

5. Task 15 dev check (Haiku 5.5, dev split, `full`/`hybrid` × N = 100, 300 × 3 runs; 192 case-runs, 0 infra
   errors). The estimate used the recalibrated hybrid factor (×1.1, Task 15a). The "before" read was taken at
   2026-11-09T20:06:04Z and gave 1.7269757, equal to row 4's "after" figure. Usage settled slowly: reads from
   20:10:52Z to 20:14:31Z climbed from 2.7284678, and the reads at 20:14:31Z and 20:15:01Z both gave 2.8773393.
   The overrun against the estimate is mostly `full` at N=300 (more third round trips than in Experiment 7).

   ```
   python -m evals.run routing --modes full,hybrid --sizes 100,300 --split dev --runs 3 --embedder fastembed --max-cost 3 --purpose "Task 15 dev check: full vs hybrid at N=100/300 (Haiku), search rate and crossover" --yes
   ```

6. Task 16 v2 baseline (Haiku 5.5, dev split, case set v2, `legacy_rules`/`full` × N = 10, 30, 100, 300 × 3 runs;
   384 case-runs, 0 infra errors). The "before" read was taken at 2026-11-09T21:45:52Z and gave 2.8773393, equal to
   row 5's "after" figure. Reads at 21:54:37Z (4.3313518) and 21:55:11Z (4.364189) were still settling; the reads at
   21:55:42Z, 21:56:12Z and 21:56:43Z all gave 4.4193055. Billed 1.5419662 matches the runner's 1.541966. The 6%
   overrun against the estimate is mostly `legacy_rules` (prompt tokens per case-run 9–21% over its estimate at
   N = 10…300, likely the longer v2 histories); `full` was within −3% to +4%. `hybrid` was left out at Siddharth's request.

   ```
   python -m evals.run routing --modes legacy_rules,full --sizes 10,30,100,300 --split dev --runs 3 --max-cost 5 --cases-dir evals/cases/v2 --purpose "Task 16: v2 baseline (agent-backed history), dev, legacy_rules+full x 4 sizes x 3 runs (Haiku)" --yes
   ```

7. Task 16f layer-2 check (Haiku 5.5, dev split, case set v2, `hybrid` with A3 retrieval, fastembed, N = 10, 30, 100,
   300 × 3 runs; 192 case-runs, 0 infra errors). Siddharth approved it after the proposal estimate of about $0.50. The
   "before" read was taken at 2026-11-10T00:07:56Z and gave 4.4193055, equal to row 6's "after" figure. Usage
   settled slowly: the reads at 00:11:53Z, 00:12:02Z and 00:12:33Z all gave 4.859961, a false plateau 0.027 below
   the runner. The reads at 00:14:07Z and 00:15:38Z both gave 4.8860774. Billed 0.4667719 matches the runner's
   0.4668, 5% under the estimate. Lesson: two agreeing reads 30 s apart are not enough; wait until a read matches
   the runner, or until two reads 90 s apart agree.

   ```
   python -m evals.run routing --modes hybrid --sizes 10,30,100,300 --split dev --runs 3 --embedder fastembed --max-cost 1 --purpose "Task 16f: hybrid on v2 with A3 message weighting, dev, 4 sizes x 3 runs (Haiku)" --yes
   ```

8. Final test-split run (Haiku 5.5, test split, case set v2, frozen config `39a1439`; `legacy_rules`/`full`/`hybrid` ×
   N = 10, 30, 100, 300 × 3 runs; 1,188 case-runs, 0 infra errors). Siddharth chose Haiku over Sonnet: the work is for
   an interview, not production, and the Sonnet grid (N=30/300 × 2 runs) was estimated at 32.1982. The runner's
   estimate for this grid was 4.0110, printed when Siddharth ran the command without `--yes`. The "before" read was
   taken at 2026-11-10T19:35:13Z and gave 4.8860774, equal to row 7's "after" figure. A read at 20:01:17Z gave
   8.9241443, still settling; the read at 20:02:15Z gave 9.0020655. Billed 4.1159881 matches the runner's 4.1160,
   2.6% over the estimate.

   ```
   python -m evals.run routing --modes legacy_rules,full,hybrid --sizes 10,30,100,300 --split test --runs 3 --embedder fastembed --max-cost 6 --purpose "Final test run: Haiku, legacy_rules+full+hybrid x N=10,30,100,300 x 3 runs, frozen 39a1439" --yes
   ```
