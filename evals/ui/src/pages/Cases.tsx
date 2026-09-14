import { useEffect, useMemo, useState } from 'react'
import { api, type Case } from '../api'
import Drawer from '../components/Drawer'
import Chat from '../components/Chat'

export default function Cases() {
  const [cases, setCases] = useState<Case[] | null>(null)
  const [q, setQ] = useState('')
  const [axis, setAxis] = useState<string>('')
  const [workerOnly, setWorkerOnly] = useState(false)
  const [multi, setMulti] = useState(false)
  const [open, setOpen] = useState<Case | null>(null)
  const [err, setErr] = useState('')

  useEffect(() => { api.cases().then(d => setCases(d.cases)).catch(e => setErr(String(e))) }, [])

  const axes = useMemo(() => Array.from(new Set((cases ?? []).map(c => c.axis.split(':')[0].trim()))), [cases])
  const shown = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return (cases ?? []).filter(c => {
      if (axis && !c.axis.startsWith(axis)) return false
      if (workerOnly && !c.worker_logs) return false
      if (multi && c.turns.length < 2) return false
      if (!needle) return true
      const hay = [c.id, c.name, c.axis, c.description, ...c.turns, ...(c.roster ?? []), JSON.stringify(c.success)].join(' ').toLowerCase()
      return hay.includes(needle)
    })
  }, [cases, q, axis, workerOnly, multi])

  if (err) return <div className="empty">{err}</div>
  if (!cases) return <div className="spin">loading…</div>

  return (
    <>
      <div className="page-head"><h1>Test cases</h1><span className="sub">evals/e2e/cases.json</span></div>
      <div className="toolbar">
        <input type="search" placeholder="Search id, name, description, turns, checks…" value={q} onChange={e => setQ(e.target.value)} />
        <select value={axis} onChange={e => setAxis(e.target.value)}>
          <option value="">all axes</option>
          {axes.map(a => <option key={a} value={a}>{a}</option>)}
        </select>
        <button className={`chip ${workerOnly ? 'on' : ''}`} onClick={() => setWorkerOnly(v => !v)}>has worker log filler</button>
        <button className={`chip ${multi ? 'on' : ''}`} onClick={() => setMulti(v => !v)}>multi-turn</button>
        <span className="count">{shown.length} / {cases.length}</span>
      </div>
      <div className="tbl-wrap">
        <table className="tbl">
          <thead><tr><th>id</th><th>name</th><th>overflows</th><th>size</th><th>what it tests</th><th>turns</th><th>filler goes to</th></tr></thead>
          <tbody>
            {shown.map(c => (
              <tr key={c.id} className="clickable" onClick={() => setOpen(c)} style={c.tier === 'disabled' ? { opacity: .5 } : undefined}>
                <td className="mono nowrap">{c.id}</td>
                <td className="nowrap">{c.name}{c.tier === 'hard' && <span className="pill warn" style={{ marginLeft: 6 }}>hard · opt-in</span>}{c.tier === 'disabled' && <span className="pill neutral" style={{ marginLeft: 6 }}>disabled</span>}{c.extends_from && <div className="faint" style={{ fontSize: 11 }}>extends {c.extends_from}</div>}</td>
                <td className="nowrap">{(c.target ?? '').split(',').map(t => <span key={t} className="pill accent" style={{ marginRight: 4 }}>{t.trim()}</span>)}</td>
                <td className="nowrap">{c.size != null ? `${Math.round(c.size / 1000)}k` : '—'}</td>
                <td style={{ minWidth: 420, maxWidth: 640 }}>{c.description}</td>
                <td className="nowrap">{c.turns.length}</td>
                <td className="nowrap">{c.history?.some(h => h.filler) ? `conversation (${c.filler_entry_tokens ?? 2000}-tok entries)` : ''}{c.worker_logs && Object.values(c.worker_logs).some(es => es.some(e => e.filler)) ? ` + ${Object.keys(c.worker_logs).join(', ')}` : ''}{c.world?.emails?.some(e => typeof e.body !== 'string') ? ' + mailbox thread' : ''}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {open && <CaseDrawer c={open} onClose={() => setOpen(null)} />}
    </>
  )
}

export function CaseDrawer({ c, onClose }: { c: Case; onClose: () => void }) {
  const [tab, setTab] = useState('Scenario')
  return (
    <Drawer title={<>{c.id} <span className="muted">{c.name}</span></>} onClose={onClose}
      tabs={['Scenario', 'Seeded history', 'Worker logs', 'Mailbox seed', 'Checks']} tab={tab} setTab={setTab}
      meta={<span className="pill neutral">{c.axis}</span>}>
      {tab === 'Scenario' && (
        <>
          <div className="section"><h3>What it tests</h3><p>{c.description}</p></div>
          <div className="section"><h3>User turns</h3>
            <ol>{c.turns.map((t, i) => <li key={i}>“{t}”</li>)}</ol>
            <p className="muted">Each turn is sent only after the previous turn and all worker callbacks have settled.</p></div>
          <div className="section"><h3>Roster before the run</h3>{(c.roster ?? []).map(r => <span key={r} className="tag">{r}</span>) || '—'}</div>
          <div className="section"><h3>Ideal trajectory (judge reference only)</h3><div className="box">{c.ideal_trajectory}</div></div>
          {c.baseline_note && <div className="section"><h3>Expected legacy failure (write-up note, hidden from judges)</h3><div className="box muted">{c.baseline_note}</div></div>}
          {c.disabled_reason && <div className="section"><h3>Disabled</h3><div className="box muted">{c.disabled_reason}</div></div>}
        </>
      )}
      {tab === 'Seeded history' && (
        <div className="section"><h3>Conversation log at the start of the run</h3><Chat history={c.history} turns={c.turns} /></div>
      )}
      {tab === 'Worker logs' && (
        c.worker_logs ? Object.entries(c.worker_logs).map(([agent, entries]) => (
          <div className="section" key={agent}><h3>{agent}</h3>
            <ul className="plain">{entries.map((e, i) => e.filler
              ? <li key={i} className="faint"><i>… N tokens of old unrelated requests inserted here at size N …</i></li>
              : <li key={i}><span className="tag">{e.tag}</span><span className="mono">{e.content}</span></li>)}</ul>
          </div>
        )) : <div className="empty">This case seeds no worker logs; only the conversation log grows with size.</div>
      )}
      {tab === 'Mailbox seed' && (
        <>
          <div className="section"><h3>Emails in the fake inbox</h3>
            <table className="tbl"><thead><tr><th>id</th><th>thread</th><th>from</th><th>subject</th><th>age</th><th>body</th></tr></thead>
              <tbody>{(c.world?.emails ?? []).map(e => <tr key={e.id}><td className="mono">{e.id}</td><td className="mono">{e.thread_id}</td><td>{e.from}</td><td>{e.subject}</td><td className="nowrap">{e.days_ago}d ago</td><td>{typeof e.body === 'string' ? e.body : <i className="muted">generated {e.body.generate}, {String(e.body.tokens)} tokens{e.body.terms ? ` · ${Object.entries(e.body.terms).map(([k, v]) => `${k} ${v}`).join(', ')}` : ''}</i>}</td></tr>)}</tbody></table>
          </div>
          {c.world?.drafts?.length ? <div className="section"><h3>Pre-existing drafts</h3><pre className="box">{JSON.stringify(c.world.drafts, null, 1)}</pre></div> : null}
          {c.world?.contacts?.length ? <div className="section"><h3>Contacts</h3>{c.world.contacts.map(p => <span key={p.email} className="tag">{p.name} &lt;{p.email}&gt;</span>)}</div> : null}
        </>
      )}
      {tab === 'Checks' && (
        <div className="section"><h3>Deterministic success checks (all must hold)</h3>
          <pre className="box">{JSON.stringify(c.success, null, 1)}</pre>
          <p className="muted">Pass/fail comes only from these checks on the final mailbox state and replies. The judge grades the path separately.</p></div>
      )}
    </Drawer>
  )
}
