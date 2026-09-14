"""Render cases.json into a standalone viewer.html (no server needed).

Usage: python evals/interaction_agent/build_viewer.py
"""

from __future__ import annotations

import json
from pathlib import Path

HERE = Path(__file__).parent
CASES = HERE / "cases.json"
OUT = HERE / "viewer.html"

TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Interaction Agent Eval Cases</title>
<style>
  :root{
    --bg:#f6f7f9; --panel:#ffffff; --ink:#1b1f24; --muted:#5b6470; --line:#e3e6ea;
    --user:#dbeafe; --user-ink:#1e3a8a; --reply:#dcfce7; --reply-ink:#14532d;
    --agent:#f1f5f9; --agent-ink:#334155; --probe:#fef3c7; --probe-ink:#78350f;
    --accent:#2563eb; --ok:#16a34a; --no:#dc2626; --chip:#eef2f7;
  }
  @media (prefers-color-scheme: dark){
    :root{
      --bg:#0f1216; --panel:#171b21; --ink:#e6e9ee; --muted:#9aa4b2; --line:#2a3039;
      --user:#1e3a5f; --user-ink:#bfdbfe; --reply:#14532d; --reply-ink:#bbf7d0;
      --agent:#1f2630; --agent-ink:#cbd5e1; --probe:#4a3410; --probe-ink:#fde68a;
      --accent:#60a5fa; --ok:#4ade80; --no:#f87171; --chip:#232a34;
    }
  }
  *{box-sizing:border-box}
  body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
  .app{display:grid;grid-template-columns:280px 1fr;height:100vh}
  aside{border-right:1px solid var(--line);background:var(--panel);overflow:auto;padding:14px}
  aside h1{font-size:15px;margin:0 0 10px}
  aside input{width:100%;padding:7px 9px;border:1px solid var(--line);border-radius:6px;background:var(--bg);color:var(--ink);margin-bottom:10px}
  .group{margin-bottom:12px}
  .group h2{font-size:11px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted);margin:8px 0 4px}
  .item{display:block;width:100%;text-align:left;border:0;background:transparent;color:var(--ink);padding:6px 8px;border-radius:6px;cursor:pointer;font:inherit}
  .item:hover{background:var(--chip)}
  .item.active{background:var(--accent);color:#fff}
  .item small{display:block;color:inherit;opacity:.75;font-size:12px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  main{overflow:auto;padding:22px 28px}
  .head{display:flex;align-items:center;gap:10px;margin-bottom:6px}
  .head h2{margin:0;font-size:20px}
  .badge{font-size:11px;padding:2px 8px;border-radius:999px;background:var(--chip);color:var(--muted);letter-spacing:.04em}
  .card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin:12px 0}
  .card h3{margin:0 0 6px;font-size:12px;letter-spacing:.06em;text-transform:uppercase;color:var(--muted)}
  .chips{display:flex;flex-wrap:wrap;gap:6px}
  .chip{background:var(--chip);border-radius:6px;padding:2px 8px;font-size:12px}
  .chip.hit{outline:2px solid var(--ok)}
  .chat{display:flex;flex-direction:column;gap:8px}
  .msg{max-width:78%;padding:8px 12px;border-radius:12px;white-space:pre-wrap;word-break:break-word}
  .msg .who{font-size:10px;letter-spacing:.06em;text-transform:uppercase;opacity:.7;margin-bottom:2px}
  .msg.user{align-self:flex-end;background:var(--user);color:var(--user-ink);border-bottom-right-radius:3px}
  .msg.reply{align-self:flex-start;background:var(--reply);color:var(--reply-ink);border-bottom-left-radius:3px}
  .msg.agent{align-self:flex-start;background:var(--agent);color:var(--agent-ink);font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px;border-left:3px solid var(--muted)}
  .msg.probe{align-self:flex-end;background:var(--probe);color:var(--probe-ink);border:2px dashed var(--probe-ink)}
  .msg.agent.probe{align-self:flex-start;background:var(--probe);color:var(--probe-ink);border:2px dashed var(--probe-ink);font-family:ui-monospace,Menlo,monospace;font-size:12px}
  .divider{align-self:center;color:var(--muted);font-size:12px;border-top:1px dashed var(--line);width:100%;text-align:center;padding-top:6px}
  .note{font-size:11px;opacity:.75;margin-top:4px;font-style:italic}
  table{border-collapse:collapse;width:100%}
  td{padding:5px 8px;border-top:1px solid var(--line);vertical-align:top;font-size:13px}
  td:first-child{color:var(--muted);width:210px;font-family:ui-monospace,Menlo,monospace;font-size:12px}
  .ok{color:var(--ok)} .no{color:var(--no)}
  code{background:var(--chip);padding:1px 5px;border-radius:4px;font-size:12px}
  .empty{color:var(--muted);font-style:italic}
  .sweep{background:var(--chip);border-radius:6px;padding:6px 10px;font-size:12px;margin-top:8px}
</style>
</head>
<body>
<div class="app">
  <aside>
    <h1>Interaction Agent Evals</h1>
    <input id="q" placeholder="filter by id, type, text…">
    <div id="list"></div>
  </aside>
  <main id="main"></main>
</div>
<script id="data" type="application/json">__CASES__</script>
<script>
const DATA = JSON.parse(document.getElementById('data').textContent);
const CASES = DATA.cases;
const esc = s => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
let active = CASES[0]?.id;

function renderList(filter=''){
  const f = filter.toLowerCase();
  const groups = {};
  for (const c of CASES){
    const hay = (c.id+' '+c.type+' '+c.description+' '+c.probe).toLowerCase();
    if (f && !hay.includes(f)) continue;
    (groups[c.type] ||= []).push(c);
  }
  const el = document.getElementById('list');
  el.innerHTML = Object.entries(groups).map(([t, cs]) => `
    <div class="group"><h2>${esc(t.replace(/_/g,' '))}</h2>
      ${cs.map(c => `<button class="item ${c.id===active?'active':''}" data-id="${c.id}">
        <strong>${esc(c.id)}</strong><small>${esc(c.probe)}</small></button>`).join('')}
    </div>`).join('') || '<div class="empty">no matches</div>';
  el.querySelectorAll('.item').forEach(b => b.onclick = () => { active = b.dataset.id; renderList(document.getElementById('q').value); renderCase(); });
}

function msg(cls, who, text, note){
  return `<div class="msg ${cls}"><div class="who">${who}</div>${esc(text)}${note?`<div class="note">${esc(note)}</div>`:''}</div>`;
}

function renderHistory(c){
  const rows = [];
  for (const h of c.history || []){
    if (h.filler){
      const sw = c.sweep ? ` (sweep: ${c.sweep.values.join(', ')})` : '';
      rows.push(`<div class="divider">⋯ N filler chat entries inserted by harness${esc(sw)} ⋯</div>`);
      continue;
    }
    const note = h.generate ? `harness generates ${h.generate.kind}, ~${h.generate.approx_tokens} tokens` : '';
    const who = {user:'user', reply:'poke reply', agent:'agent message'}[h.role] || h.role;
    rows.push(msg(h.role, who, h.content, note));
  }
  if (!rows.length) rows.push('<div class="empty">empty history</div>');
  const viaAgent = c.probe_role === 'agent';
  rows.push(msg(viaAgent ? 'agent probe' : 'probe', viaAgent ? 'probe (agent message via handle_agent_message)' : 'probe (new user message)', c.probe));
  return rows.join('');
}

function renderAssert(a){
  if (!a) return '<div class="empty">none</div>';
  const rows = [];
  const add = (k, v, cls='') => rows.push(`<tr><td>${esc(k)}</td><td class="${cls}">${v}</td></tr>`);
  const list = v => Array.isArray(v) ? v.map(x=>`<code>${esc(x)}</code>`).join(' ') : `<code>${esc(v)}</code>`;
  if (a.must_call) add('must_call', list(a.must_call), 'ok');
  if (a.must_not_call) add('must_not_call', list(a.must_not_call), 'no');
  if (a.reply_contains_any) add('reply_contains_any', list(a.reply_contains_any));
  for (const [k,v] of Object.entries(a.dispatch || {})){
    add('dispatch.'+k, typeof v === 'boolean' ? (v?'true':'false') : list(v), k.startsWith('instructions_not')?'no':'');
  }
  return `<table>${rows.join('')}</table>`;
}

function renderCase(){
  const c = CASES.find(x => x.id === active);
  if (!c) return;
  const hits = new Set(c.assert?.dispatch?.agent_name_in || []);
  const roster = (c.roster||[]).map(r => `<span class="chip ${hits.has(r)?'hit':''}">${esc(r)}</span>`).join('');
  const rg = c.roster_generate ? `<div class="sweep">+ ${c.roster_generate.count} generated decoys, pattern <code>${esc(c.roster_generate.pattern)}</code></div>` : '';
  const sweep = c.sweep ? `<div class="sweep">sweep <code>${esc(c.sweep.param)}</code> over ${c.sweep.values.join(', ')}</div>` : '';
  document.getElementById('main').innerHTML = `
    <div class="head"><h2>${esc(c.id)}</h2><span class="badge">${esc(c.type)}</span></div>
    <div class="card"><h3>What this tests</h3>${esc(c.description)}${sweep}</div>
    <div class="card"><h3>Expected result</h3>${esc(c.expected_result)}${c.baseline_note?`<div class="note" style="margin-top:6px">baseline prediction (not shown to judge): ${esc(c.baseline_note)}</div>`:''}</div>
    <div class="card"><h3>Roster before probe</h3>${roster || '<span class="empty">empty</span>'}${rg}</div>
    <div class="card"><h3>Seeded history → probe</h3><div class="chat">${renderHistory(c)}</div></div>
    <div class="card"><h3>Assertions</h3>${renderAssert(c.assert)}</div>`;
}

document.getElementById('q').addEventListener('input', e => renderList(e.target.value));
renderList(); renderCase();
</script>
</body>
</html>
"""


def main() -> None:
    cases = json.loads(CASES.read_text(encoding="utf-8"))
    payload = json.dumps(cases).replace("</", "<\\/")
    OUT.write_text(TEMPLATE.replace("__CASES__", payload), encoding="utf-8")
    print(f"wrote {OUT} ({len(cases['cases'])} cases)")


if __name__ == "__main__":
    main()
