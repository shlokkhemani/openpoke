"""Render results/<run>/results.json into a standalone report.html with the overload stress grid."""

from __future__ import annotations

import html
import json
import sys
import webbrowser
from pathlib import Path
from typing import Any, Dict, List

CRITERIA = ["planning", "execution", "observation_interpretation", "replanning", "termination", "loops", "unnecessary_actions"]

_CSS = """
:root{--bg:#f7f7f5;--card:#fff;--ink:#1c1c1a;--muted:#6b6b66;--line:#e4e4df;--pass:#1f7a3f;--passbg:#e2f3e7;--fail:#b3261e;--failbg:#fbe4e2;
--warn:#8a5a00;--warnbg:#fdf0d5;--gate:#5b3fa8;--gatebg:#ece6fa;--loop:#8a5a00;--acc:#2d5bd1}
@media (prefers-color-scheme:dark){:root:not([data-theme=light]){--bg:#15150f;--card:#1f1f19;--ink:#ecece6;--muted:#a3a39b;--line:#33332c;
--passbg:#173a24;--failbg:#4a1c18;--warnbg:#45350f;--gatebg:#2e2550}}
:root[data-theme=dark]{--bg:#15150f;--card:#1f1f19;--ink:#ecece6;--muted:#a3a39b;--line:#33332c;--passbg:#173a24;--failbg:#4a1c18;--warnbg:#45350f;--gatebg:#2e2550}
body{background:var(--bg);color:var(--ink);font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Helvetica,Arial,sans-serif;margin:0;padding:24px}
h1{font-size:20px;margin:0 0 4px}h2{font-size:15px;margin:28px 0 10px}.muted{color:var(--muted)}
.kpis{display:flex;gap:12px;flex-wrap:wrap;margin:14px 0}.kpi{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 14px;min-width:120px}
.kpi b{display:block;font-size:20px}.kpi span{font-size:12px;color:var(--muted)}
table{border-collapse:collapse;width:100%;background:var(--card);border:1px solid var(--line);border-radius:8px;overflow:hidden}
th,td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}th{font-size:12px;color:var(--muted);font-weight:600}
.wrap{overflow-x:auto}
.cell{display:flex;gap:6px;align-items:stretch}.cellbox{flex:1;border-radius:6px;padding:4px 6px;font-size:12px;min-width:84px}
.cellbox small{display:block;color:inherit;opacity:.8;font-size:11px}
.p{background:var(--passbg);color:var(--pass)}.f{background:var(--failbg);color:var(--fail)}.g{background:var(--gatebg);color:var(--gate)}.l{background:var(--warnbg);color:var(--warn)}
.pill{display:inline-block;border-radius:999px;padding:1px 8px;font-size:12px;font-weight:600}
.row{cursor:pointer}.row:hover{background:rgba(127,127,127,.06)}.details{display:none;background:var(--bg)}.details.open{display:table-row}
.panel{padding:12px 14px;display:grid;grid-template-columns:1fr 1fr;gap:14px}.panel>div{background:var(--card);border:1px solid var(--line);border-radius:8px;padding:10px 12px;min-width:0}
.panel h4{margin:0 0 8px;font-size:12px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em}.full{grid-column:1/-1}
pre{white-space:pre-wrap;word-break:break-word;font:12px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;margin:0;max-height:420px;overflow:auto}
.ev{font:12px/1.5 ui-monospace,Menlo,monospace;white-space:pre-wrap;word-break:break-word}.ev .gm{color:var(--acc)}.ev .blk{color:var(--gate);font-weight:600}
.crit{display:grid;grid-template-columns:repeat(auto-fill,minmax(230px,1fr));gap:6px}.crit div{border:1px solid var(--line);border-radius:6px;padding:6px 8px;font-size:12px}
.crit .ok{border-left:4px solid var(--pass)}.crit .bad{border-left:4px solid var(--fail)}
.legend span{margin-right:14px;font-size:12px}
"""


def _pill(rec: Dict[str, Any]) -> str:
    if rec["success"]:
        return '<span class="pill p">PASS</span>'
    r = rec.get("fail_reason") or "fail"
    cls = {"overflow": "g", "loop": "l"}.get(r, "f")
    return f'<span class="pill {cls}">FAIL · {html.escape(r)}</span>'


def _cellbox(rec: Dict[str, Any] | None, strategy: str) -> str:
    if rec is None:
        return f'<div class="cellbox" style="opacity:.4">{strategy[:3]} —</div>'
    cnt = rec.get("counters") or {}
    j = rec.get("judge") or {}
    if rec["success"]:
        cls, mark = "p", "✓"
    else:
        r = rec.get("fail_reason") or "fail"
        cls, mark = ({"overflow": ("g", "⛔"), "loop": ("l", "↻")}.get(r, ("f", "✗")))
    score = f" · j{j['score']}" if j and not j.get("error") else ""
    return (f'<div class="cellbox {cls}"><b>{mark}</b> {strategy[:3]}{score}'
            f'<small>{cnt.get("llm_calls", "?")} calls · {cnt.get("steps", "?")} steps</small>'
            f'<small>max {_k(cnt.get("max_prompt_tokens"))} tok</small></div>')


def _k(n: Any) -> str:
    try:
        n = int(n)
    except (TypeError, ValueError):
        return "?"
    return f"{n / 1000:.0f}k" if n >= 1000 else str(n)


def _events_html(events: List[str]) -> str:
    out = []
    for e in events:
        s = html.escape(e)
        if e.startswith("[gmail]"):
            s = f'<span class="gm">{s}</span>'
        elif "REQUEST BLOCKED" in e or "LLM ERROR" in e:
            s = f'<span class="blk">{s}</span>'
        out.append(s)
    return "<br>".join(out) or "(no events)"


def _judge_html(j: Dict[str, Any] | None) -> str:
    if not j:
        return '<span class="muted">judge skipped</span>'
    if j.get("error"):
        return f'<span class="pill f">judge error</span> <pre>{html.escape(str(j["error"]))}</pre>'
    crit = "".join(
        f'<div class="{"ok" if j[c]["ok"] else "bad"}"><b>{c.replace("_", " ")}</b><br>{html.escape(j[c]["note"])}</div>'
        for c in CRITERIA)
    return (f'<p><b>score {j["score"]}/5</b> · judge thinks task {"completed" if j["task_completed"] else "NOT completed"} · '
            f'<span class="muted">{html.escape(j.get("model", ""))}</span></p><p>{html.escape(j["summary"])}</p><div class="crit">{crit}</div>')


def _run_row(rec: Dict[str, Any], idx: int, trace: Dict[str, Any] | None) -> str:
    cnt = rec.get("counters") or {}
    j = rec.get("judge") or {}
    jcell = (f'{j["score"]}/5' if j and not j.get("error") else ("err" if j else "—"))
    checks = " ".join(f'<span class="pill {"p" if v else "f"}">{html.escape(k)}</span>' for k, v in (rec.get("checks") or {}).items())
    replies = "".join(f"<li>{html.escape(r)}</li>" for r in rec.get("replies") or []) or "<li class='muted'>(none)</li>"
    world = rec.get("world") or {}
    sent = "".join(f"<li>to={html.escape(str(s.get('to')))} cc={html.escape(str(s.get('cc')))} thread={html.escape(str(s.get('thread_id')))} "
                   f"via={html.escape(str(s.get('via')))}<br><span class='muted'>{html.escape(str(s.get('subject')))} — {html.escape(str(s.get('body'))[:300])}</span></li>"
                   for s in world.get("sent", [])) or "<li class='muted'>(nothing sent)</li>"
    drafts = "".join(f"<li>{html.escape(str(d.get('id')))} to={html.escape(str(d.get('to')))} cc={html.escape(str(d.get('cc')))} thread={html.escape(str(d.get('thread_id')))}</li>"
                     for d in world.get("drafts", [])) or "<li class='muted'>(no drafts remaining)</li>"
    turns = "".join(f"<li>{'✓' if t['success'] else '✗'} <b>turn {t['turn']}</b> “{html.escape(t['text'])}” · {t['wall_ms']}ms"
                    + (f"<br><span class='pill f'>{html.escape(str(t['error']))}</span>" if t.get("error") else "") + "</li>"
                    for t in rec.get("turns") or [])
    judge_prompt = (trace or {}).get("judge_prompt")
    jp = f'<details><summary class="muted">what the judge was given</summary><pre>{html.escape(judge_prompt)}</pre></details>' if judge_prompt else ""
    failures = "".join(f"<li>{html.escape(f)}</li>" for f in rec.get("failures") or [])
    return f"""
<tr class="row" onclick="document.getElementById('d{idx}').classList.toggle('open')">
 <td>{html.escape(rec['run_id'])}</td><td>{html.escape(rec['strategy'])}</td><td>{_pill(rec)}</td><td>{jcell}</td>
 <td>{cnt.get('llm_calls','?')}</td><td>{cnt.get('steps','?')}</td><td>{cnt.get('dispatches','?')}/{cnt.get('recalls','?')}</td>
 <td>{_k(cnt.get('input_tokens'))} / {_k(cnt.get('max_prompt_tokens'))}</td><td>{cnt.get('duplicate_worker_tool_calls','?')}</td>
 <td>{round((rec.get('wall_ms') or 0)/1000)}s</td><td>{checks}</td>
</tr>
<tr class="details" id="d{idx}"><td colspan="11"><div class="panel">
 <div class="full"><h4>Case</h4><p>{html.escape(rec.get('name',''))} — {html.escape(_case_desc(rec))}</p>
   {f"<ul>{failures}</ul>" if failures else ""}</div>
 <div><h4>Turns</h4><ul>{turns}</ul><h4>Replies to user</h4><ul>{replies}</ul></div>
 <div><h4>Final mailbox</h4><b>sent</b><ul>{sent}</ul><b>drafts remaining</b> (created during run: {world.get('drafts_created','?')})<ul>{drafts}</ul>
   <h4>Counters</h4><pre>{html.escape(json.dumps(cnt, indent=1))}</pre></div>
 <div class="full"><h4>Trajectory judge</h4>{_judge_html(j)}{jp}</div>
 <div class="full"><h4>Event log</h4><div class="ev">{_events_html(rec.get('events') or [])}</div></div>
</div></td></tr>"""


_CASE_DESC: Dict[str, str] = {}


def _case_desc(rec: Dict[str, Any]) -> str:
    return _CASE_DESC.get(rec["case_id"], "")


def build(results_dir: Path, open_browser: bool = True) -> Path:
    data = json.loads((results_dir / "results.json").read_text(encoding="utf-8"))
    runs: List[Dict[str, Any]] = data["runs"]
    cases_path = Path(__file__).resolve().parent / "cases.json"
    if cases_path.exists():
        for c in json.loads(cases_path.read_text(encoding="utf-8"))["cases"]:
            _CASE_DESC[c["id"]] = c["description"]
    traces: Dict[str, Dict[str, Any]] = {}
    for r in runs:
        tf = r.get("trace_file")
        if tf and (results_dir / tf).exists():
            try:
                t = json.loads((results_dir / tf).read_text(encoding="utf-8"))
                traces[r["run_id"] + r["strategy"]] = {"judge_prompt": t.get("judge_prompt")}
            except Exception:
                pass

    sizes = sorted({r["size"] for r in runs})
    strategies = data.get("strategies") or sorted({r["strategy"] for r in runs})
    case_ids = []
    for r in runs:
        if r["case_id"] not in case_ids:
            case_ids.append(r["case_id"])
    by = {(r["case_id"], r["size"], r["strategy"]): r for r in runs if "#" not in r["run_id"]}
    # with repeats, aggregate pass rate instead of a single record
    reps: Dict[tuple, List[Dict[str, Any]]] = {}
    for r in runs:
        reps.setdefault((r["case_id"], r["size"], r["strategy"]), []).append(r)

    def grid_cell(cid: str, size: int) -> str:
        boxes = []
        for s in strategies:
            group = reps.get((cid, size, s))
            if not group:
                boxes.append(_cellbox(None, s))
            elif len(group) == 1:
                boxes.append(_cellbox(group[0], s))
            else:
                passed = sum(1 for g in group if g["success"])
                cls = "p" if passed == len(group) else ("f" if passed == 0 else "l")
                calls = sum((g.get("counters") or {}).get("llm_calls", 0) for g in group) / len(group)
                boxes.append(f'<div class="cellbox {cls}"><b>{passed}/{len(group)}</b> {s[:3]}<small>avg {calls:.1f} calls</small></div>')
        return f'<div class="cell">{"".join(boxes)}</div>'

    grid_rows = "".join(
        f"<tr><td><b>{cid}</b><br><span class='muted'>{html.escape(next((r['name'] for r in runs if r['case_id']==cid), ''))}</span></td>"
        + "".join(f"<td>{grid_cell(cid, sz)}</td>" for sz in sizes) + "</tr>"
        for cid in case_ids)

    per_strat = []
    for s in strategies:
        rs = [r for r in runs if r["strategy"] == s]
        if not rs:
            continue
        passed = sum(1 for r in rs if r["success"])
        calls = sum((r.get("counters") or {}).get("llm_calls", 0) for r in rs)
        toks = sum((r.get("counters") or {}).get("input_tokens", 0) for r in rs)
        scores = [r["judge"]["score"] for r in rs if r.get("judge") and not r["judge"].get("error")]
        reasons: Dict[str, int] = {}
        for r in rs:
            if not r["success"]:
                reasons[r.get("fail_reason") or "fail"] = reasons.get(r.get("fail_reason") or "fail", 0) + 1
        per_strat.append(f'<div class="kpi"><b>{passed}/{len(rs)}</b><span>{html.escape(s)} pass</span></div>'
                         f'<div class="kpi"><b>{calls/len(rs):.1f}</b><span>{html.escape(s)} avg LLM calls</span></div>'
                         f'<div class="kpi"><b>{_k(toks/len(rs))}</b><span>{html.escape(s)} avg input tokens</span></div>'
                         f'<div class="kpi"><b>{(sum(scores)/len(scores)):.1f}</b><span>{html.escape(s)} avg judge score</span></div>' if scores else ""
                         )
        per_strat.append(f'<div class="kpi"><b>{html.escape(", ".join(f"{k} {v}" for k, v in reasons.items()) or "—")}</b><span>{html.escape(s)} fail reasons</span></div>')

    rows = "".join(_run_row(r, i, traces.get(r["run_id"] + r["strategy"])) for i, r in enumerate(runs))

    page = f"""<title>E2E Overload Curve</title><style>{_CSS}</style>
<h1>End-to-end overload curve</h1>
<div class="muted">{html.escape(data.get('label') or '')} · model {html.escape(data.get('model',''))} · judge {html.escape(data.get('judge_model',''))}
 · simulated context window {data.get('context_window', 0):,} tokens · call cap {data.get('max_calls')} · {html.escape(data.get('generated_at',''))}</div>
<div class="kpis">{''.join(per_strat)}</div>
<h2>Stress grid — filler tokens across the top, one box per strategy</h2>
<div class="legend"><span class="pill p">✓ pass</span><span class="pill f">✗ quality/error</span><span class="pill g">⛔ overflow (request blocked at window)</span><span class="pill l">↻ loop / call cap / deadline</span><span class="muted">jN = trajectory judge score /5</span></div>
<div class="wrap"><table><tr><th>case</th>{''.join(f'<th>{_k(sz)} tokens</th>' for sz in sizes)}</tr>{grid_rows}</table></div>
<h2>Runs (click a row)</h2>
<div class="wrap"><table>
<tr><th>run</th><th>strategy</th><th>result</th><th>judge</th><th>LLM calls</th><th>steps</th><th>dispatch/recall</th><th>tokens in / max prompt</th><th>dup tool calls</th><th>wall</th><th>checks</th></tr>
{rows}</table></div>
"""
    out = results_dir / "report.html"
    out.write_text(page, encoding="utf-8")
    if open_browser:
        webbrowser.open(out.resolve().as_uri())
    return out


if __name__ == "__main__":
    build(Path(sys.argv[1]), open_browser="--no-open" not in sys.argv)
