# OpenPoke eval harness

This harness compares the **original** OpenPoke (`~/Repositories/openpoke`) with **this fork**, using the 22 scenarios in `scenarios/`. The design is documented in `docs/3-evaluation-plan.md`, and the cases are described in `docs/4-test-cases.md`.

Use the OpenPoke virtualenv's python for everything. It already has fastapi, uvicorn, httpx, PyYAML and dateutil installed.

```bash
PY=~/Repositories/openpoke/.venv/bin/python

# 1. Validate the scenarios. This starts no server and makes no LLM calls.
$PY -m evals.run --dry-run

# 2. Smoke test: one cheap case, one run per version, no judge.
$PY -m evals.run --cases R1 --repeats 1

# 3. Full comparison (defaults: 3 repeats, 4 parallel workers).
$PY -m evals.run --judge-model anthropic/claude-sonnet-5.5

# Rebuild the report from an existing runs folder.
$PY -m evals.run --report-only runs/<timestamp>
```

**Defaults:**
- `--original ~/Repositories/openpoke`
- `--fork .`
- `--env-file ~/Repositories/openpoke/.env`: supplies the OpenRouter key for both versions and the judge
- `--python ~/Repositories/openpoke/.venv/bin/python`
- `--timezone America/Los_Angeles`

**Other options:**
- `--repeats` (default 3) and `--workers` (default 4 scenario runs in parallel; every run has its own temp copy and port).
- `--cases` takes `all`, group letters (`A,B,C,R`) or case IDs (`A1,R2`).
- `--model <id>` pins every agent model in both versions to the same ID.
- Leave out `--judge-model` to skip judging.

## Cost

These are real LLM calls through your OpenRouter key.
- **Full run:** 22 cases × 2 versions × 3 repeats = 132 scenario runs, plus one judge call per run. About $1.20 in total with `deepseek-v4.1-flash` agents and the `openai/gpt-oss-120b` judge.
- **Long cases:** C2 (21 turns), R6 (17 turns) and C1 (13 steps) are the expensive ones. Use `--cases A,B,R1,R2` for a cheaper first pass.
- **Run time:** roughly 1–3 minutes per scenario run. With 12 workers (`--workers 12`), a full run takes about 40 minutes.
- **Resuming:** runs that already finished are skipped when you re-run with the same `--out`.

## What it does

The harness never writes into either repo.
- **For each run** it copies `<checkout>/server` (without `data/`) and the env file into a temp dir.
- **The server** is started there with `harness/serve.py`, which records every LLM call (latency, tokens, role) and never starts the Gmail watcher.
- **The scenario** is played over the HTTP API.
- **Firing reminders:** reminders fire immediately, because the harness edits `triggers.db` to make them due.
- **Snapshots:** the data files are copied after every step.

Each run gets its own folder, `runs/<timestamp>/<version>/<case>/run_N/`:

| File | Contents |
|---|---|
| `transcript.json`, `steps.json`, `llm_calls.jsonl` | The raw recording |
| `snapshots/step_N/` | `triggers.db`, the roster, working memory and execution logs after step N |
| `result.json` | Check results, the judge score and metrics |
| `server.log` | Server output, useful when a run errors |

The comparison is written to `runs/<timestamp>/report.md`.

## Layout

| Path | Role |
|---|---|
| `harness/serve.py` | Server launcher with the LLM-call recorder (runs inside the OpenPoke venv) |
| `harness/runner.py` | Plays one scenario: start, chat, fire triggers, wait for quiet, snapshot |
| `harness/timeexpr.py` | Expressions like `tomorrow 16:00`, `next weekday 08:00`, `now + 30 min` |
| `evaluators/checks.py` | Deterministic checks, plus two always-on ones (every turn replied, no timeouts) |
| `evaluators/metrics.py` | Latency, calls and tokens by role, agents created, wrong-agent routing |
| `evaluators/judge.py` | One 1–5 reply-quality score per run |
| `report.py` | Paired t-intervals over cases, pass/fail flips, per-group and per-case tables |
| `scenarios/*.yaml` | The test cases |

## Notes

- **Latency** is the time from the user's message to the *last* assistant message of that turn, which is usually the result rather than an "on it" acknowledgement.
- **Wrong-agent routing** counts `updateTrigger` calls that got "not found", meaning a follow-up went to an agent that doesn't own the reminder.
- **Ambiguity in A1:** a separate one-shot reminder for "tomorrow" is also accepted; see its checks.
- **A3 is the known `read_conversation` gap.** It may favor the original, and the result should be reported either way.
