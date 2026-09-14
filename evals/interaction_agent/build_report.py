"""Render a results directory (results.json + traces/) into a standalone report.html.

Usage:
    python evals/interaction_agent/build_report.py <results_dir> [--open]

run_eval.py calls build() automatically after each run.
"""

from __future__ import annotations

import argparse
import json
import sys
import webbrowser
from pathlib import Path
from typing import Any, Dict, List

TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Eval Report __LABEL__</title>
<style>
  :root{
    --bg:#f6f7f9; --panel:#fff; --ink:#1b1f24; --muted:#5b6470; --line:#e3e6ea; --chip:#eef2f7;
    --ok:#16a34a; --okbg:#dcfce7; --no:#dc2626; --nobg:#fee2e2; --accent:#2563eb;
    --user:#dbeafe; --user-ink:#1e3a8a; --asst:#f1f5f9; --asst-ink:#334155; --tool:#fef3c7; --tool-ink:#78350f;
  }
  @media (prefers-color-scheme: dark){
    :root{
      --bg:#0f1216; --panel:#171b21; --ink:#e6e9ee; --muted:#9aa4b2; --line:#2a3039; --chip:#232a34;
      --ok:#4ade80; --okbg:#14532d; --no:#f87171; --nobg:#7f1d1d; --accent:#60a5fa;
      --user:#1e3a5f; --user-ink:#bfdbfe; --asst:#1f2630; --asst-ink:#cbd5e1; --tool:#4a3410; --tool-ink:#fde68a;
    }
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
  main{max-width:1280px;margin:0 auto;padding:24px 28px}
  h1{font-size:22px;margin:0 0 4px}
  .sub{color:var(--muted);font-size:13px;margin-bottom:18px}
  .kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-bottom:18px}
  .kpi{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 14px}
  .kpi .l{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
  .kpi .v{font-size:22px;font-weight:600;margin-top:2px}
  .kpi .v.ok{color:var(--ok)} .kpi .v.no{color:var(--no)}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:12px 0}
  .card h2{margin:0 0 10px;font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
  table{border-collapse:collapse;width:100%}
  th,td{padding:7px 9px;border-top:1px solid var(--line);text-align:left;vertical-align:top;font-size:13px}
  th{color:var(--muted);font-weight:500;font-size:12px;border-top:0}
  td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
  tr.run{cursor:pointer}
  tr.run:hover td{background:var(--chip)}
  .pill{display:inline-block;padding:1px 8px;border-radius:999px;font-size:11px;font-weight:600}
  .pill.ok{background:var(--okbg);color:var(--ok)} .pill.no{background:var(--nobg);color:var(--no)}
  .type{font-size:11px;color:var(--muted)}
  .fail{color:var(--no);font-size:12px}
  .detail{display:none}
  .detail.open{display:table-row}
  .detail>td{background:var(--bg);padding:12px 16px}
  .cols{display:grid;grid-template-columns:1fr 1fr;gap:12px}
  @media (max-width:900px){.cols{grid-template-columns:1fr}}
  .box{background:var(--panel);border:1px solid var(--line);border-radius:8px;padding:10px 12px}
  .box h3{margin:0 0 6px;font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
  code,pre{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px}
  code{background:var(--chip);padding:1px 5px;border-radius:4px}
  pre{white-space:pre-wrap;word-break:break-word;margin:0;max-height:320px;overflow:auto;background:var(--chip);padding:8px;border-radius:6px}
  .round{border-left:3px solid var(--line);padding:6px 10px;margin:8px 0}
  .round .hd{font-size:12px;color:var(--muted);margin-bottom:4px}
  .msg{padding:6px 10px;border-radius:8px;margin:4px 0;white-space:pre-wrap;word-break:break-word;font-size:12.5px}
  .msg.user{background:var(--user);color:var(--user-ink)}
  .msg.assistant{background:var(--asst);color:var(--asst-ink)}
  .msg.tool{background:var(--tool);color:var(--tool-ink);font-family:ui-monospace,Menlo,monospace;font-size:12px}
  .msg .who{font-size:10px;letter-spacing:.06em;text-transform:uppercase;opacity:.7;margin-bottom:2px}
  .chat{display:flex;flex-direction:column;gap:6px}
  .chat .msg{max-width:78%}
  .chat .msg.user{align-self:flex-end}
  .chat .msg.reply{align-self:flex-start;background:var(--okbg);color:var(--ok)}
  .chat .msg.agent{align-self:flex-start;background:var(--asst);color:var(--asst-ink);font-family:ui-monospace,Menlo,monospace;font-size:12px;border-left:3px solid var(--muted)}
  .chat .msg.probe{align-self:flex-end;background:var(--tool);color:var(--tool-ink);border:2px dashed var(--tool-ink)}
  .chat .divider{align-self:center;color:var(--muted);font-size:12px;border-top:1px dashed var(--line);width:100%;text-align:center;padding-top:4px}
  .case p{margin:4px 0}
  .case .k{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin-top:8px}
  details summary{cursor:pointer;color:var(--accent);font-size:12px;margin:6px 0}
  .bars{display:flex;align-items:flex-end;gap:8px;height:90px;margin-top:6px}
  .bar{flex:1;display:flex;flex-direction:column;align-items:center;justify-content:flex-end;height:100%}
  .bar .b{width:100%;border-radius:4px 4px 0 0;min-height:2px}
  .bar .b.ok{background:var(--ok)} .bar .b.no{background:var(--no)}
  .bar .x{font-size:10px;color:var(--muted);margin-top:3px}
  .bar .y{font-size:10px;color:var(--muted)}
  .sweeps{display:grid;grid-template-columns:repeat(auto-fit,minmax(320px,1fr));gap:12px}
  .muted{color:var(--muted)}
</style>
</head>
<body>
<main>
  <h1>Interaction Agent Eval <span class="muted">__LABEL__</span></h1>
  <div class="sub" id="sub"></div>
  <div class="kpis" id="kpis"></div>
  <div class="card" id="bytype"></div>
  <div class="card" id="sweeps" hidden></div>
  <div class="card"><h2>Runs <span class="muted" style="text-transform:none;letter-spacing:0">(click a row for details)</span></h2>
    <table id="runs"></table>
  </div>
</main>
<script id="data" type="application/json">__DATA__</script>
<script>
const D = JSON.parse(document.getElementById('data').textContent);
const R = D.results, T = D.traces;
const esc = s => String(s ?? '').replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const n = v => (v == null ? '–' : Number(v).toLocaleString());
const pill = ok => `<span class="pill ${ok?'ok':'no'}">${ok?'PASS':'FAIL'}</span>`;

document.getElementById('sub').textContent =
  `${R.strategy ? 'strategy ' + R.strategy + ' · ' : ''}${R.model} · judge ${R.judge_model || 'none (deterministic checks)'} · summarizer ${R.summarizer_model} · threshold ${R.summary_threshold}+${R.summary_tail} · ${R.generated_at}`;

const runs = R.runs;
const sum = k => runs.reduce((a,r)=>a+(r.metrics[k]||0),0);
const avg = k => runs.length ? Math.round(sum(k)/runs.length) : 0;
document.getElementById('kpis').innerHTML = [
  ['passed', `${R.passed} / ${R.total}`, R.passed===R.total?'ok':'no'],
  ['avg rounds', avg('llm_rounds'), ''],
  ['avg input tokens', n(avg('input_tokens')), ''],
  ['total input tokens', n(sum('input_tokens')), ''],
  ['avg wall ms', n(avg('wall_ms')), ''],
].map(([l,v,c])=>`<div class="kpi"><div class="l">${l}</div><div class="v ${c}">${v}</div></div>`).join('');

document.getElementById('bytype').innerHTML = `<h2>By type</h2><table>
  <tr><th>type</th><th class="num">passed</th><th class="num">total</th><th class="num">avg rounds</th><th class="num">avg input tokens</th></tr>
  ${Object.entries(R.by_type).map(([t,v])=>{
    const rs = runs.filter(r=>r.type===t);
    const a = k => Math.round(rs.reduce((x,r)=>x+(r.metrics[k]||0),0)/rs.length);
    return `<tr><td>${esc(t)}</td><td class="num">${v.passed}</td><td class="num">${v.total}</td><td class="num">${a('llm_rounds')}</td><td class="num">${n(a('input_tokens'))}</td></tr>`;
  }).join('')}</table>`;

// sweep charts
const sweepCases = {};
for (const r of runs) if (r.sweep) (sweepCases[r.case_id] ||= []).push(r);
if (Object.keys(sweepCases).length){
  const el = document.getElementById('sweeps'); el.hidden = false;
  el.innerHTML = `<h2>Sweeps · input tokens vs distance, colored by pass/fail</h2><div class="sweeps">` +
    Object.entries(sweepCases).map(([cid, rs])=>{
      rs.sort((a,b)=>a.sweep.value-b.sweep.value);
      const max = Math.max(...rs.map(r=>r.metrics.input_tokens||0), 1);
      return `<div class="box"><h3>${esc(cid)}</h3><div class="bars">${rs.map(r=>
        `<div class="bar"><div class="y">${n(r.metrics.input_tokens)}</div><div class="b ${r.pass?'ok':'no'}" style="height:${Math.max(2, 70*(r.metrics.input_tokens||0)/max)}px"></div><div class="x">${r.sweep.param.replace('_count','')}=${r.sweep.value}</div></div>`
      ).join('')}</div></div>`;
    }).join('') + `</div>`;
}

// case + history rendering
function caseHtml(trace, r){
  const c = trace?.case;
  if (!c) return '<span class="muted">case not embedded</span>';
  const sweep = r.sweep ? `<p class="k">sweep</p><p><code>${esc(r.sweep.param)}</code> = ${esc(r.sweep.value)}</p>` : '';
  return `<div class="case"><p class="k">what this tests</p><p>${esc(c.description)}</p>
    <p class="k">expected result</p><p>${esc(c.expected_result)}</p>${c.baseline_note?`<p class="k">baseline prediction (not shown to judge)</p><p class="muted">${esc(c.baseline_note)}</p>`:''}${sweep}
    <p class="k">roster before probe (${(trace.seeded_roster||[]).length})</p><p>${(trace.seeded_roster||[]).map(x=>`<code>${esc(x)}</code>`).join(' ')||'<span class="muted">empty</span>'}</p></div>`;
}
function historyHtml(trace, r){
  const h = trace?.seeded_history || [];
  const MAX = 30, HEAD = 6;
  let shown = h, note = '';
  if (h.length > MAX){ shown = h.slice(0, HEAD).concat([{omitted: h.length - MAX}], h.slice(-(MAX - HEAD))); }
  const who = {user:'user', reply:'poke reply', agent:'agent message'};
  const rows = shown.map(e => e.omitted != null
    ? `<div class="divider">⋯ ${e.omitted} entries omitted (${h.length} total) ⋯</div>`
    : `<div class="msg ${e.role}"><div class="who">${who[e.role]||e.role}</div>${esc(e.content.length > 1200 ? e.content.slice(0,1200)+' …['+e.content.length.toLocaleString()+' chars]' : e.content)}</div>`);
  if (!h.length) rows.push('<div class="muted">empty history</div>');
  rows.push(`<div class="msg probe"><div class="who">probe (new user message)</div>${esc(trace?.case?.probe || r.case_id)}</div>`);
  return `<div class="chat">${rows.join('')}</div>`;
}

function judgeHtml(full, brief){
  const j = full || brief;
  if (!j) return '<span class="muted">judge not run</span>';
  const verdict = j.pass == null ? `<span class="fail">error: ${esc(j.error)}</span>` : pill(j.pass);
  const meta = j.skipped ? 'skipped: turn failed, hard fail' : `${esc(j.model||'')} · in ${n(j.input_tokens)} · out ${n(j.output_tokens)} · ${n(j.wall_ms)} ms`;
  return `<div>${verdict} <span class="muted" style="font-size:12px">${meta}</span></div>
    <div style="margin:6px 0">${esc(j.rationale)}</div>
    ${j.prompt ? `<details><summary>what the judge was given</summary><pre>${esc(j.prompt)}</pre></details>
    <details><summary>judge system prompt</summary><pre>${esc(j.system||'')}</pre></details>` : ''}`;
}

// run table
function roundsHtml(trace){
  if (!trace) return '<div class="muted">trace not embedded</div>';
  const probe = trace.llm_calls.filter(c=>c.phase==='probe');
  const seedc = trace.llm_calls.filter(c=>c.phase==='seed');
  let out = '';
  if (seedc.length) out += `<div class="muted" style="font-size:12px">${seedc.length} summarizer call(s) during seeding</div>`;
  probe.forEach((c,i)=>{
    const m = (c.response.choices||[{}])[0]?.message || {};
    const tcs = (m.tool_calls||[]).map(t=>`<code>${esc(t.function.name)}</code> ${esc(t.function.arguments)}`).join('<br>');
    const msgs = c.messages.map(x=>{
      const who = x.role;
      let body = typeof x.content==='string' ? x.content : JSON.stringify(x.content);
      if (x.tool_calls) body += '\n' + x.tool_calls.map(t=>`→ ${t.function.name}(${t.function.arguments})`).join('\n');
      return `<div class="msg ${who}"><div class="who">${who}</div>${esc(body)}</div>`;
    }).join('');
    out += `<div class="round"><div class="hd">round ${i+1} · in ${n(c.usage.prompt_tokens)} · out ${n(c.usage.completion_tokens)} · ${c.wall_ms} ms${c.error?` · <span class="fail">${esc(c.error)}</span>`:''}</div>
      <div><strong>response:</strong> ${esc(m.content||'')}${tcs?'<br>'+tcs:''}</div>
      <details><summary>prompt sent (${c.messages.length} message${c.messages.length>1?'s':''})</summary>${msgs}</details></div>`;
  });
  const sys = probe[0]?.system;
  if (sys) out += `<details><summary>system prompt (${sys.length.toLocaleString()} chars)</summary><pre>${esc(sys)}</pre></details>`;
  return out;
}

const checksCell = r => {
  const c = r.checks || {pass: r.pass, failures: r.failures};
  return c.pass ? '<span class="muted" style="font-size:12px">checks ok</span>' : c.failures.map(f=>`<div class="fail">✗ ${esc(f)}</div>`).join('');
};
const judgeCell = r => {
  if (!r.judge) return '<span class="muted">–</span>';
  if (r.judge.pass == null) return `<div class="fail">judge error: ${esc(r.judge.error)}</div>`;
  return `${pill(r.judge.pass)}<div style="font-size:12px;margin-top:4px">${esc(r.judge.rationale)}</div>`;
};
document.getElementById('runs').innerHTML = `<tr><th>run</th><th>result</th><th style="width:38%">judge</th><th class="num">rounds</th><th class="num">in tok</th><th class="num">wall ms</th><th>checks</th></tr>` +
  runs.map((r,i)=>`
  <tr class="run" data-i="${i}"><td><strong>${esc(r.run_id)}</strong><div class="type">${esc(r.type)}</div></td>
    <td>${pill(r.pass)}</td><td>${judgeCell(r)}</td><td class="num">${r.metrics.llm_rounds}</td><td class="num">${n(r.metrics.input_tokens)}</td><td class="num">${n(r.metrics.wall_ms)}</td>
    <td>${checksCell(r)}</td></tr>
  <tr class="detail" id="d${i}"><td colspan="7">
    <div class="cols" style="margin-bottom:12px">
      <div class="box"><h3>case ${esc(r.case_id)}</h3>${caseHtml(T[r.run_id], r)}</div>
      <div class="box"><h3>seeded history → probe (${(T[r.run_id]?.seeded_history||[]).length} entries)</h3>${historyHtml(T[r.run_id], r)}</div>
    </div>
    <div class="cols">
      <div class="box"><h3>tool calls (${r.observed.tool_calls.length})</h3>${r.observed.tool_calls.map(t=>`<div><code>${esc(t.name)}</code> <span class="muted">${esc(JSON.stringify(t.arguments))}</span></div>`).join('')||'<span class="muted">none</span>'}</div>
      <div class="box"><h3>dispatches (${r.observed.dispatches.length})</h3>${r.observed.dispatches.map(d=>`<div><strong>${esc(d.agent_name)}</strong><div class="muted">${esc(d.instructions)}</div></div>`).join('')||'<span class="muted">none</span>'}
        <h3 style="margin-top:8px">context</h3><div class="muted">seeded ${r.observed.seeded_entries} entries · roster ${r.observed.seeded_roster_size}${r.observed.summary_state?` · summary ${r.observed.summary_state.summary_chars} chars, last_index ${r.observed.summary_state.last_index}, tail ${r.observed.summary_state.unsummarized_entries}`:''}</div>
        <div class="muted">trace: <code>${esc(r.trace_file)}</code></div></div>
    </div>
    <div class="box" style="margin-top:12px"><h3>judge</h3>${judgeHtml(T[r.run_id]?.judge, r.judge)}</div>
    <div class="box" style="margin-top:12px"><h3>LLM rounds</h3>${roundsHtml(T[r.run_id])}</div>
  </td></tr>`).join('');

document.querySelectorAll('tr.run').forEach(tr => tr.onclick = () => document.getElementById('d'+tr.dataset.i).classList.toggle('open'));
</script>
</body>
</html>
"""


def build(results_dir: Path, open_browser: bool = False) -> Path:
    results_dir = Path(results_dir)
    results = json.loads((results_dir / "results.json").read_text(encoding="utf-8"))

    traces: Dict[str, Any] = {}
    for run in results["runs"]:
        p = results_dir / run["trace_file"]
        if not p.exists():
            continue
        t = json.loads(p.read_text(encoding="utf-8"))
        # embed only what the report renders
        traces[run["run_id"]] = {
            "judge": t.get("judge"),
            "case": t.get("case"),
            "seeded_history": t.get("seeded_history", []),
            "seeded_roster": t.get("seeded_roster", []),
            "llm_calls": [
                {
                    "phase": c["phase"],
                    "component": c["component"],
                    "wall_ms": c["wall_ms"],
                    "usage": c["usage"],
                    "error": c["error"],
                    "system": c["system"] if c["phase"] == "probe" else None,
                    "messages": c["messages"] if c["phase"] == "probe" else [],
                    "response": c["response"],
                }
                for c in t["llm_calls"]
            ]
        }

    payload = json.dumps({"results": results, "traces": traces}, ensure_ascii=False).replace("</", "<\\/")
    label = results.get("label") or results_dir.name
    html = TEMPLATE.replace("__DATA__", payload).replace("__LABEL__", label)
    out = results_dir / "report.html"
    out.write_text(html, encoding="utf-8")
    if open_browser:
        webbrowser.open(out.resolve().as_uri())
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("results_dir")
    ap.add_argument("--open", action="store_true")
    a = ap.parse_args()
    out = build(Path(a.results_dir), a.open)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
