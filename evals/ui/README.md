# Eval UI

Browse end-to-end eval runs (`evals/e2e/results/`) and test cases (`evals/e2e/cases.json`).

    evals/ui/start.sh          # build if needed, serve API + app on http://localhost:8765
    evals/ui/start.sh --dev    # hot reload during UI work

Views: **Runs** (all past runs, pass rate per strategy), **Test cases** (search/filter, drawer with
seeded history, worker logs, mailbox seed, checks), **Run detail** (stress grid, cells table, per-cell
drawer with checks, judge rubric, event log, every LLM call).

`server.py` is a read-only FastAPI app: four GET routes over the results folder plus static hosting of `dist/`.
