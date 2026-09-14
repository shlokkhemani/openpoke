import { useEffect, useMemo, useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { api, fmtDate, fmtDur, fmtWall, k, resultKind, resultLabel, type Case, type Results, type RunRecord } from '../api'
import RunDrawer from '../components/RunDrawer'

export default function RunDetail() {
  const { id = '' } = useParams()
  const [data, setData] = useState<Results | null>(null)
  const [cases, setCases] = useState<Record<string, Case>>({})
  const [err, setErr] = useState('')
  const [params, setParams] = useSearchParams()
  const selectedId = params.get('cell')
  const [fCase, setFCase] = useState('')
  const [fStrat, setFStrat] = useState('')
  const [fSize, setFSize] = useState('')
  const [fResult, setFResult] = useState('')
  const [q, setQ] = useState('')

  const load = () => api.run(id).then(setData).catch(e => setErr(String(e)))
  useEffect(() => { load(); api.cases().then(d => setCases(Object.fromEntries(d.cases.map(c => [c.id, c])))).catch(() => {}) }, [id])
  useEffect(() => { const t = setInterval(load, 15000); return () => clearInterval(t) }, [id])

  const runs = data?.runs ?? []
  const strategies = data?.strategies ?? Array.from(new Set(runs.map(r => r.strategy)))
  const sizes = useMemo(() => Array.from(new Set(runs.map(r => r.size))).sort((a, b) => a - b), [runs])
  const caseIds = useMemo(() => Array.from(new Set(runs.map(r => r.case_id))), [runs])
  const cellKey = (r: RunRecord) => `${r.run_id}|${r.strategy}`
  const selected = runs.find(r => cellKey(r) === selectedId)

  const shown = useMemo(() => {
    const n = q.trim().toLowerCase()
    return runs.filter(r =>
      (!fCase || r.case_id === fCase) && (!fStrat || r.strategy === fStrat) && (!fSize || String(r.size) === fSize) &&
      (!fResult || (fResult === 'pass' ? r.success : fResult === 'fail' ? !r.success : r.fail_reason === fResult)) &&
      (!n || [r.run_id, r.name, r.strategy, ...(r.failures ?? []), ...(r.replies ?? [])].join(' ').toLowerCase().includes(n)))
  }, [runs, fCase, fStrat, fSize, fResult, q])

  if (err) return <div className="empty">{err}</div>
  if (!data) return <div className="spin">loading…</div>

  const expected = (data.mode === 'scenario' ? 1 : sizes.length) * strategies.length * caseIds.length
  const rs_for = (s: string) => runs.filter(r => r.strategy === s)
  const rubric_n = (rs: RunRecord[]) => rs.filter(r => typeof r.judge_v2?.score === 'number').length
  const byStrat = strategies.map(s => {
    const rs = rs_for(s)
    const rubric = rs.map(r => r.judge_v2?.score).filter((x): x is number => typeof x === 'number')
    const wall = rs.reduce((a, r) => a + (r.wall_ms ?? 0), 0)
    const reasons: Record<string, number> = {}
    rs.filter(r => !r.success).forEach(r => { const key = r.fail_reason ?? 'fail'; reasons[key] = (reasons[key] ?? 0) + 1 })
    return {
      s, n: rs.length, passed: rs.filter(r => r.success).length,
      calls: rs.reduce((a, r) => a + (r.counters?.llm_calls ?? 0), 0) / Math.max(1, rs.length),
      tokens: rs.reduce((a, r) => a + (r.counters?.input_tokens ?? 0), 0) / Math.max(1, rs.length),
      toolCalls: rs.reduce((a, r) => a + ((r.counters?.ia_tool_calls ?? 0) + (r.counters?.worker_tool_calls ?? 0)), 0),
      tokIn: rs.reduce((a, r) => a + (r.counters?.input_tokens ?? 0), 0),
      tokOut: rs.reduce((a, r) => a + (r.counters?.output_tokens ?? 0), 0),
      reasons,
      rubric: rubric.length ? rubric.reduce((a, b) => a + b, 0) / rubric.length : null, wall,
    }
  })

  return (
    <>
      <div className="page-head">
        <h1>{data.label || id}</h1>
        <span className="sub">{fmtDate(data.generated_at)} · model <code>{data.model}</code> · judge <code>{data.judge_model}</code> · window {k(data.context_window)} · call cap {data.max_calls}</span>
        <Link to="/runs" style={{ marginLeft: 'auto' }}>← all runs</Link>
      </div>
      {runs.length < expected && <div className="pill warn" style={{ marginBottom: 12 }}>in progress · {runs.length}/{expected} cells</div>}

      <div className="kpis">
        {byStrat.map(b => (
          <div key={b.s} className="kpi" style={{ minWidth: 260 }}>
            <b>{b.passed}/{b.n} <span className="muted" style={{ fontSize: 13, fontWeight: 400 }}>{b.s}</span></b>
            <span>{b.calls.toFixed(1)} avg LLM calls · {b.toolCalls} tool calls · {k(b.tokIn)} in / {k(b.tokOut)} out billed · total time {fmtDur(b.wall)}</span>
            <span style={{ display: 'block' }}>{b.rubric != null ? `avg trajectory ${b.rubric.toFixed(0)}% over ${rubric_n(rs_for(b.s))} graded cells` : 'no cells graded (all hard fails)'}</span>
            <div style={{ marginTop: 4 }}>{Object.entries(b.reasons).map(([r, n]) => <span key={r} className={`pill ${r === 'overflow' ? 'gate' : r === 'loop' ? 'warn' : r === 'side_effect' ? 'side' : 'fail'}`} style={{ marginRight: 4 }}>{r} {n}</span>)}</div>
          </div>
        ))}
      </div>

      <div className="section">
        <h3 style={{ fontSize: 14, textTransform: 'none', letterSpacing: 0, color: 'var(--ink)' }}>Stress grid</h3>
        <div className="legend"><span className="pill pass">✓ pass</span><span className="pill fail">✗ quality / error</span><span className="pill gate">⛔ overflow (request blocked at window)</span><span className="pill warn">↻ loop / call cap · ⏱ over the runtime cap</span><span className="pill side">⚠ done but with side effects</span><span>N% = trajectory score (hard fails are not graded) · click a box for details</span></div>
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>case</th>{data.mode === 'scenario' ? <><th>overflows</th><th>size</th><th>legacy · budgeted</th></> : sizes.map(s => <th key={s}>{k(s)} filler tokens</th>)}</tr></thead>
            <tbody>
              {caseIds.map(cid => (
                <tr key={cid}>
                  <td className="nowrap"><b>{cid}</b><div className="muted">{cases[cid]?.name ?? runs.find(r => r.case_id === cid)?.name}</div>
                    {strategies.map(st => { const rs = runs.filter(r => r.case_id === cid && r.strategy === st); return rs.length ? <div key={st} className="faint" style={{ fontSize: 11 }}>{st.slice(0, 3)} {fmtDur(rs.reduce((a, r) => a + (r.wall_ms ?? 0), 0))}</div> : null })}</td>
                  {data.mode === 'scenario' && <td className="nowrap">{(cases[cid]?.target ?? '').split(',').map(t => <span key={t} className="pill accent" style={{ marginRight: 4 }}>{t.trim()}</span>)}</td>}
                  {data.mode === 'scenario' && <td className="nowrap">{k(runs.find(r => r.case_id === cid)?.size)}</td>}
                  {(data.mode === 'scenario' ? [runs.find(r => r.case_id === cid)?.size ?? 0] : sizes).map(sz => (
                    <td key={sz}><div className="grid-cell">
                      {strategies.map(st => {
                        const group = runs.filter(r => r.case_id === cid && r.size === sz && r.strategy === st)
                        if (!group.length) return <div key={st} className="gbox empty">{st.slice(0, 3)} —</div>
                        if (group.length === 1) {
                          const r = group[0]; const kind = resultKind(r)
                          const mark = { pass: '✓', fail: '✗', gate: '⛔', warn: r.fail_reason === 'timeout' ? '⏱' : '↻', side: '⚠' }[kind]
                          return (
                            <div key={st} className={`gbox ${kind}`} onClick={() => setParams({ cell: cellKey(r) })}>
                              <b>{mark}</b> {st.slice(0, 3)}{typeof r.judge_v2?.score === 'number' ? ` · ${r.judge_v2.score}%` : ''}
                              <small>{r.counters?.llm_calls ?? '?'} calls · {r.counters?.steps ?? '?'} steps</small>
                              <small>max {k(r.counters?.max_prompt_tokens)} tok</small>
                            </div>
                          )
                        }
                        const p = group.filter(r => r.success).length
                        return (
                          <div key={st} className={`gbox ${p === group.length ? 'pass' : p === 0 ? 'fail' : 'warn'}`} onClick={() => setParams({ cell: cellKey(group[0]) })}>
                            <b>{p}/{group.length}</b> {st.slice(0, 3)}<small>avg {(group.reduce((a, r) => a + (r.counters?.llm_calls ?? 0), 0) / group.length).toFixed(1)} calls</small>
                          </div>
                        )
                      })}
                    </div></td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {runs.some(r => typeof r.judge_v2?.score === 'number') && (
        <div className="section">
          <h3 style={{ fontSize: 14, textTransform: 'none', letterSpacing: 0, color: 'var(--ink)' }}>Trajectory questions · pass rate per strategy</h3>
          <p className="muted" style={{ margin: '0 0 8px' }}>Share of applicable cells answering yes, per question and strategy. Low rows are the failure modes that dominate.</p>
          <div className="tbl-wrap"><table className="tbl">
            <thead><tr><th>#</th><th>criterion</th><th>question</th><th>by</th><th>w</th>{strategies.map(s => <th key={s}>{s}</th>)}</tr></thead>
            <tbody>
              {(runs.find(r => r.judge_v2?.questions?.length)?.judge_v2?.questions ?? []).map(q => (
                <tr key={q.id}>
                  <td className="mono">{q.id}</td><td className="nowrap">{q.criterion}</td><td>{q.question}</td>
                  <td><span className={`pill ${q.by === 'harness' ? 'neutral' : 'accent'}`}>{q.by}</span></td><td>{q.weight}</td>
                  {strategies.map(st => {
                    const answers = runs.filter(r => r.strategy === st).map(r => r.judge_v2?.questions?.find(x => x.id === q.id)?.answer).filter(a => a === 'yes' || a === 'no')
                    const yes = answers.filter(a => a === 'yes').length
                    const pct = answers.length ? Math.round((100 * yes) / answers.length) : null
                    return <td key={st} className="nowrap">{pct == null ? <span className="faint">n/a</span> : <><span className={`pill ${pct >= 80 ? 'pass' : pct >= 50 ? 'warn' : 'fail'}`}>{pct}%</span> <span className="faint">{yes}/{answers.length}</span></>}</td>
                  })}
                </tr>
              ))}
            </tbody>
          </table></div>
        </div>
      )}

      <div className="section">
        <h3 style={{ fontSize: 14, textTransform: 'none', letterSpacing: 0, color: 'var(--ink)' }}>Cells</h3>
        <div className="toolbar">
          <input type="search" placeholder="Search cell, failures, replies…" value={q} onChange={e => setQ(e.target.value)} />
          <select value={fCase} onChange={e => setFCase(e.target.value)}><option value="">all cases</option>{caseIds.map(c => <option key={c}>{c}</option>)}</select>
          <select value={fStrat} onChange={e => setFStrat(e.target.value)}><option value="">all strategies</option>{strategies.map(s => <option key={s}>{s}</option>)}</select>
          <select value={fSize} onChange={e => setFSize(e.target.value)}><option value="">all sizes</option>{sizes.map(s => <option key={s} value={String(s)}>{k(s)}</option>)}</select>
          <select value={fResult} onChange={e => setFResult(e.target.value)}>
            <option value="">all results</option><option value="pass">pass</option><option value="fail">any fail</option>
            <option value="quality">fail · quality</option><option value="side_effect">fail · side effect</option><option value="overflow">fail · overflow</option><option value="loop">fail · loop</option><option value="timeout">fail · timeout</option><option value="error">fail · error</option>
          </select>
          <span className="count">{shown.length} / {runs.length}</span>
        </div>
        <div className="tbl-wrap">
          <table className="tbl">
            <thead><tr><th>cell</th><th>strategy</th><th>result</th><th>trajectory</th><th>LLM calls</th><th>tool calls</th><th>tokens in / out</th><th>max prompt</th><th>time</th></tr></thead>
            <tbody>
              {shown.map(r => {
                const key = cellKey(r)
                return (
                  <tr key={key} className={`clickable ${key === selectedId ? 'selected' : ''}`} onClick={() => setParams({ cell: key })}>
                    <td className="mono nowrap">{r.run_id}</td>
                    <td>{r.strategy}</td>
                    <td><span className={`pill ${resultKind(r)}`}>{resultLabel(r)}</span></td>
                    <td className="nowrap">{typeof r.judge_v2?.score === 'number' ? <><b>{r.judge_v2.score}%</b> <span className="faint">{r.judge_v2.questions.filter(q => q.answer === 'no').length} issues</span></> : r.judge_v2?.not_scored ? <span className="faint">not graded</span> : r.judge_v2?.error ? <span className="pill fail">err</span> : '—'}</td>
                    {(() => { const c = r.counters && typeof r.counters.llm_calls === 'number' ? r.counters : null; return (<>
                    <td>{c ? c.llm_calls : '—'}{c?.gate_blocks ? <span className="faint"> ({c.gate_blocks} blocked)</span> : null}</td>
                    <td>{c ? c.ia_tool_calls + c.worker_tool_calls : '—'}{c ? <span className="faint"> ({c.dispatches} dispatch{c.recalls ? ` · ${c.recalls} recall` : ''})</span> : null}</td>
                    <td className="nowrap">{c ? `${k(c.input_tokens)} / ${k(c.output_tokens)}` : '—'}</td>
                    <td className="nowrap">{c ? k(c.max_prompt_tokens) : '—'}</td>
                    <td className="nowrap">{fmtWall(r)}</td>
                    </>) })()}
                  </tr>
                )
              })}
            </tbody>
          </table>
        </div>
      </div>

      {selected && <RunDrawer runId={id} rec={selected} c={cases[selected.case_id]} onClose={() => setParams({})} />}
    </>
  )
}
