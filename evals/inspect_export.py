"""Convert a run folder into Inspect AI .eval logs (one per mode and N), for ``inspect view``. No model calls."""
import json
from collections import defaultdict
from pathlib import Path


def _message(m: dict):
    from inspect_ai.model import ChatMessageAssistant, ChatMessageSystem, ChatMessageTool, ChatMessageUser
    from inspect_ai.tool import ToolCall

    content, role = m.get("content") or "", m["role"]
    if role == "system":
        return ChatMessageSystem(content=content)
    if role == "user":
        return ChatMessageUser(content=content)
    if role == "tool":
        return ChatMessageTool(content=content, tool_call_id=m.get("tool_call_id"))
    calls = [ToolCall(id=t["id"], function=t["function"]["name"],
                      arguments=json.loads(t["function"]["arguments"] or "{}"), type="function")
             for t in m.get("tool_calls") or []]
    return ChatMessageAssistant(content=content, tool_calls=calls or None)


def _jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()] \
        if path.exists() else []


def export_run(run_dir: Path, out_dir: Path) -> list[Path]:
    from inspect_ai.log import (EvalConfig, EvalDataset, EvalLog, EvalMetric, EvalResults, EvalSample,
                                EvalScore, EvalSpec, EvalStats, write_eval_log)
    from inspect_ai.model import ModelOutput
    from inspect_ai.scorer import CORRECT, INCORRECT, Score

    run_dir, out = Path(run_dir), Path(out_dir) / Path(run_dir).name
    out.mkdir(parents=True, exist_ok=True)
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
    records = {(r["case_id"], r["mode"], r["n"], r["run_idx"]): r for r in _jsonl(run_dir / "records.jsonl")}
    infra_errors = len(_jsonl(run_dir / "errors.jsonl"))
    groups = defaultdict(list)
    for g in _jsonl(run_dir / "grades.jsonl"):
        groups[(g["mode"], g["n"])].append(g)

    paths = []
    for (mode, n), grades in sorted(groups.items()):
        samples = []
        for g in sorted(grades, key=lambda g: (g["case_id"], g["run_idx"])):
            r = records[(g["case_id"], mode, n, g["run_idx"])]
            tfile = run_dir / "transcripts" / f"{g['case_id']}-{r.get('reused_from') or mode}-{n}-{g['run_idx']}.json"
            missing = not tfile.exists()
            msgs = [] if missing else [_message(m) for m in json.loads(tfile.read_text(encoding="utf-8"))["messages"]]
            first_user = next((m.content for m in msgs if m.role == "user"), "")
            meta = {"category": g["category"], "N": n, "mode": mode, "latency_s": r["latency_s"],
                    "round_trips": r["round_trips"], "calls": r["calls"], "error": r["error"]}
            if missing:
                meta["transcript_missing"] = True
            score = Score(value=CORRECT if g["passed"] else INCORRECT, answer=g["outcome_kind"],
                          explanation=", ".join(g["flags"]) or None,
                          metadata={k: g[k] for k in ("person_ok", "clarify_named_ok", "set_recall",
                                                      "set_precision", "slots_filled", "slots_total", "flags")})
            samples.append(EvalSample(
                id=g["case_id"], epoch=g["run_idx"] + 1, input=first_user, target=g["category"], messages=msgs,
                output=ModelOutput.from_content(r["model"], r.get("final_text") or ""),
                scores={"grader": score}, metadata=meta, total_time=r["latency_s"]))
        accuracy = sum(g["passed"] for g in grades) / len(grades)
        spec = EvalSpec(created=summary["date_utc"], task=f"{run_dir.name}-{mode}-N{n}", model=summary["model"],
                        dataset=EvalDataset(name=summary.get("case_set", {}).get("dir", "evals/cases/v1"), samples=len(samples)), config=EvalConfig(),
                        metadata={"N": n, "mode": mode, "purpose": summary["purpose"], "infra_errors": infra_errors})
        results = EvalResults(total_samples=len(samples), completed_samples=len(samples), scores=[EvalScore(
            name="grader", scorer="grader", metrics={"accuracy": EvalMetric(name="accuracy", value=accuracy)})])
        path = out / f"{mode}-N{n}.eval"
        write_eval_log(EvalLog(status="success", eval=spec, results=results, stats=EvalStats(), samples=samples),
                       str(path))
        paths.append(path)
    return paths
