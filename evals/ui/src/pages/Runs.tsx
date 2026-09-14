import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { api, fmtDate, fmtDur, k, type RunSummary } from '../api'

export default function Runs() {
  const [runs, setRuns] = useState<RunSummary[] | null>(null)
  const [q, setQ] = useState('')
  const [err, setErr] = useState('')

  const load = () => api.runs().then(setRuns).catch(e => setErr(String(e)))
  useEffect(() => { load(); const t = setInterval(load, 15000); return () => clearInterval(t) }, [])

  const shown = useMemo(() => {
    const n = q.trim().toLowerCase()
    return (runs ?? []).filter(r => !n || [r.id, r.label, r.model, r.judge_model, ...(r.strategies ?? [])].join(' ').toLowerCase().includes(n))
  }, [runs, q])

  if (err) return <div className="empty">{err}</div>
  if (!runs) return <div className="spin">loading…</div>

  return (
    <>
      <div className="page-head"><h1>Runs</h1><span className="sub">evals/e2e/results/ · refreshes every 15s</span></div>
      <div className="toolbar">
        <input type="search" placeholder="Search label, model, strategy…" value={q} onChange={e => setQ(e.target.value)} />
        <span className="count">{shown.length} runs</span>
      </div>
      {shown.length === 0 ? <div className="empty">No runs yet. Start one with <code>.venv/bin/python evals/e2e/run_e2e.py</code>.</div> : (
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>started</th><th>label</th><th>model</th><th>judge</th><th>window</th><th>sizes</th><th>pass rate by strategy</th><th>cells</th><th></th></tr></thead>
            <tbody>
              {shown.map(r => (
                <tr key={r.id}>
                  <td className="nowrap"><Link to={`/runs/${r.id}`}>{fmtDate(r.generated_at)}</Link><div className="faint mono" style={{ fontSize: 11 }}>{r.id}</div></td>
                  <td>{r.label || <span className="faint">—</span>}{r.in_progress && <span className="pill warn" style={{ marginLeft: 6 }}>in progress</span>}</td>
                  <td className="mono">{r.model}</td>
                  <td className="mono">{r.judge_model}</td>
                  <td className="nowrap">{k(r.context_window)}</td>
                  <td className="nowrap">{(r.sizes ?? []).map(k).join(' · ')}</td>
                  <td style={{ minWidth: 220 }}>
                    {Object.entries(r.by_strategy).map(([s, v]) => (
                      <div key={s} style={{ display: 'grid', gridTemplateColumns: '70px 1fr 50px', gap: 8, alignItems: 'center', marginBottom: 3 }}>
                        <span className="muted">{s}</span>
                        <div className="bar"><i style={{ width: `${v.total ? (100 * v.passed) / v.total : 0}%` }} /></div>
                        <span className="mono right">{v.passed}/{v.total}</span>
                        <span></span><span className="faint" style={{ fontSize: 11 }}>total time {fmtDur(v.wall_ms)}</span><span></span>
                      </div>
                    ))}
                  </td>
                  <td className="nowrap">{r.passed}/{r.total}</td>
                  <td><Link to={`/runs/${r.id}`}>open →</Link></td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </>
  )
}
