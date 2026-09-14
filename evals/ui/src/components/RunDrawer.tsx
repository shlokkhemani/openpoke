import { useEffect, useState } from 'react'
import { api, k, resultKind, resultLabel, type Case, type LlmCall, type RunRecord, type Trace } from '../api'
import Drawer from './Drawer'
import Timeline from './Timeline'

const evClass = (e: string) => {
  if (e.includes('REQUEST BLOCKED')) return 'blocked'
  if (e.includes('LLM ERROR')) return 'error'
  if (e.startsWith('[gmail]')) return 'gmail'
  if (e.includes("worker '")) return 'worker'
  if (e.includes('email_search')) return 'search'
  return 'ia'
}

export default function RunDrawer({ runId, rec, c, onClose }: { runId: string; rec: RunRecord; c?: Case; onClose: () => void }) {
  const [tab, setTab] = useState('Overview')
  const [trace, setTrace] = useState<Trace | null | 'loading' | 'error'>(null)
  const cellId = `${rec.run_id}|${rec.strategy}`
  useEffect(() => { setTab('Overview'); setTrace(null) }, [cellId])
  useEffect(() => {
    if ((tab === 'LLM calls' || tab === 'Event log') && trace === null && rec.trace_file) {
      setTrace('loading')
      api.trace(runId, rec.trace_file).then(setTrace).catch(() => setTrace('error'))
    }
  }, [tab, trace, rec.trace_file, runId])

  const cnt = rec.counters
  const kind = resultKind(rec)
  return (
    <Drawer onClose={onClose} tabs={['Overview', 'Trajectory', 'Event log', 'LLM calls']} tab={tab} setTab={setTab}
      title={<>{rec.run_id} <span className="muted">{rec.strategy}</span></>}
      meta={<span className={`pill ${kind}`}>{resultLabel(rec)}</span>}>
      {tab === 'Overview' && (
        <>
          {c && <div className="section"><h3>{c.id} · {c.name}</h3><p className="muted" style={{ margin: 0 }}>{c.description}</p></div>}
          {rec.failures?.length > 0 && (
            <div className="section"><h3>Why it failed</h3><ul className="plain">{rec.failures.map((f, i) => <li key={i} className="mono">{f}</li>)}</ul></div>
          )}
          <div className="two">
            <div>
              <div className="section"><h3>Verdict</h3>
                {rec.outcome && !rec.outcome.error ? (
                  <div className="box">
                    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', marginBottom: 6 }}>
                      <span className={`pill ${rec.outcome.task_done ? 'pass' : 'fail'}`}>task {rec.outcome.task_done ? 'done' : 'NOT done'}</span>
                      <span className={`pill ${rec.outcome.reply_accurate ? 'pass' : 'fail'}`}>replies {rec.outcome.reply_accurate ? 'accurate' : 'inaccurate'}</span>
                      <span className={`pill ${(rec.outcome.side_effects ?? []).some(x => x.severity === 'major') ? 'side' : 'pass'}`}>{(rec.outcome.side_effects ?? []).length} side effect(s)</span>
                      <span className="muted mono" style={{ marginLeft: 'auto', fontSize: 11 }}>outcome judge · {rec.outcome.model}</span>
                    </div>
                    <div>{rec.outcome.reason}</div>
                    {(rec.outcome.side_effects ?? []).length > 0 && <ul style={{ margin: '6px 0 0', paddingLeft: 18 }}>{rec.outcome.side_effects!.map((x, i) => <li key={i}><span className={`pill ${x.severity === 'major' ? 'side' : 'neutral'}`}>{x.severity}</span> {x.what}</li>)}</ul>}
                  </div>
                ) : <span className="muted">outcome judge {rec.outcome?.error ? `error: ${rec.outcome.error}` : 'not run'}; verdict from mechanical checks</span>}
              </div>
              <div className="section"><h3>Mechanical checks <span className="faint" style={{ textTransform: 'none', letterSpacing: 0 }}>· hints, not the verdict</span></h3>
                {Object.entries(rec.checks ?? {}).map(([n, ok]) => <span key={n} className={`pill ${ok ? 'pass' : 'fail'}`} style={{ marginRight: 6 }}>{n}</span>)}
              </div>
              <div className="section"><h3>Turns</h3>
                <ul className="plain">{rec.turns.map(t => (
                  <li key={t.turn}>{t.success ? '✓' : '✗'} <b>turn {t.turn}</b> “{t.text}” <span className="muted">· {(t.wall_ms / 1000).toFixed(1)}s</span>
                    {t.error && <div className="pill fail" style={{ marginTop: 4, whiteSpace: 'normal' }}>{t.error}</div>}</li>
                ))}</ul>
                {rec.aborted && <div className="pill warn" style={{ marginTop: 6 }}>aborted: {rec.aborted}</div>}
              </div>
              <div className="section"><h3>Replies the user saw</h3>
                {rec.replies.length ? <div className="chat">{rec.replies.map((r, i) => <div key={i} className="bubble reply">{r}</div>)}</div> : <span className="faint">(none)</span>}
              </div>
            </div>
            <div>
              <div className="section"><h3>Final mailbox</h3>
                <b>sent ({rec.world?.sent.length ?? 0})</b>
                {rec.world?.sent.map(s => (
                  <div key={s.id} className="box"><div className="kv">
                    <div>to</div><div>{s.to}</div><div>cc</div><div>{s.cc?.join(', ') || <span className="faint">none</span>}</div>
                    <div>thread</div><div className="mono">{s.thread_id ?? <span className="faint">none</span>}</div>
                    <div>via</div><div className="mono">{s.via}{s.draft_id ? ` (${s.draft_id})` : ''}</div>
                    <div>subject</div><div>{s.subject}</div><div>body</div><div style={{ whiteSpace: 'pre-wrap' }}>{s.body}</div>
                  </div></div>
                ))}
                <div style={{ marginTop: 8 }}><b>drafts remaining ({rec.world?.drafts.length ?? 0})</b> <span className="muted">· created during run: {rec.world?.drafts_created}</span></div>
                {rec.world?.drafts.map(d => <div key={d.id} className="box mono">{d.id} → {d.to} cc={JSON.stringify(d.cc)} thread={d.thread_id ?? '—'} · {d.subject}</div>)}
              </div>
              {cnt && (
                <div className="section"><h3>Counters</h3>
                  <div className="kv">
                    <div>LLM calls</div><div>{cnt.llm_calls} <span className="muted">({Object.entries(cnt.llm_calls_by_component).map(([a, b]) => `${a} ${b}`).join(', ')})</span></div>
                    <div>steps</div><div>{cnt.steps} <span className="muted">= {cnt.ia_tool_calls} interaction tool calls + {cnt.worker_tool_calls} gmail calls</span></div>
                    <div>dispatches / recalls</div><div>{cnt.dispatches} / {cnt.recalls}</div>
                    <div>new workers</div><div>{cnt.new_workers.length ? cnt.new_workers.join(', ') : <span className="faint">none</span>}</div>
                    <div>duplicate gmail calls</div><div>{cnt.duplicate_worker_tool_calls}</div>
                    <div>input tokens (billed)</div><div>{cnt.input_tokens.toLocaleString()} <span className="muted">max prompt {k(cnt.max_prompt_tokens)}{cnt.blocked_input_tokens_est ? ` · ${k(cnt.blocked_input_tokens_est)} est. in blocked requests, not billed` : ''}</span></div>
                    <div>output tokens</div><div>{cnt.output_tokens.toLocaleString()}</div>
                    <div>blocked / errors</div><div>{cnt.gate_blocks} / {cnt.llm_errors}</div>
                    <div>wall</div><div>{rec.timed_out ? <span className="pill warn">&gt; {rec.cell_timeout_s}s cap · cancelled</span> : `${((rec.wall_ms ?? 0) / 1000).toFixed(1)}s`} <span className="muted">LLM {(cnt.llm_wall_ms / 1000).toFixed(1)}s</span></div>
                    <div>seeded</div><div>conv {k(rec.seeded_tokens?.conversation)} · worker logs {k(rec.seeded_tokens?.worker_logs)} · summary {rec.summary_state?.summary_chars ? `${k(Math.round(rec.summary_state.summary_chars / 4))} tok` : 'none'}</div>
                  </div>
                </div>
              )}
            </div>
          </div>
        </>
      )}
      {tab === 'Trajectory' && <Rubric rec={rec} runId={runId} />}
      {tab === 'Event log' && (
        trace === 'loading' ? <div className="spin">loading trace…</div>
        : trace && trace !== 'error' ? <Timeline trace={trace} rec={rec} />
        : (
          <div className="events">
            <p className="muted" style={{ fontFamily: 'var(--sans)' }}>Trace unavailable; showing the flat event log.</p>
            {rec.events.length ? rec.events.map((e, i) => <div key={i} className={`ev ${evClass(e)}`}>{e}</div>) : <span className="faint">(no events)</span>}
          </div>
        )
      )}
      {tab === 'LLM calls' && (
        trace === 'loading' ? <div className="spin">loading trace…</div> : trace === 'error' || !trace ? <div className="empty">trace unavailable</div> : <Calls calls={trace.llm_calls} />
      )}
    </Drawer>
  )
}

function Rubric({ rec, runId }: { rec: RunRecord; runId: string }) {
  const v = rec.judge_v2
  if (!v) return <div className="section"><h3>Trajectory</h3><span className="muted">not scored (run <code>evals/e2e/judge_v2.py &lt;results dir&gt;</code>)</span></div>
  if (v.error && !v.questions?.length) return <div className="section"><h3>Trajectory</h3><span className="pill fail">error</span> <pre>{v.error}</pre></div>
  if (v.not_scored) return <div className="section"><h3>Trajectory</h3><span className="pill neutral">not scored</span> <span className="muted">{v.not_scored}</span></div>
  const groups = Array.from(new Set(v.questions.map(q => q.criterion)))
  return (
    <div className="section">
      <h3>Trajectory · 16 yes/no questions</h3>
      <p className="muted" style={{ margin: '0 0 8px' }}>Grades <b>how</b> the run got there, separately from pass/fail. Weight 2 = doing the task wrong, weight 1 = waste. Score = weighted yes ÷ weighted applicable. Harness questions are computed from the trace; judge questions are answered by the model with a reason.</p>
      <div style={{ display: 'flex', gap: 24, alignItems: 'center', marginBottom: 10 }}>
        <div><span className="score">{v.score ?? '—'}%</span> <span className="muted">= {v.earned} of {v.applicable} weighted yes</span></div>
        {v.error && <span className="pill warn">judge questions failed: {v.error}</span>}
        <span className="muted mono" style={{ marginLeft: 'auto' }}>{v.model ?? 'harness only'}</span>
      </div>
      <table className="tbl">
        <thead><tr><th>#</th><th>question</th><th>by</th><th>w</th><th>answer</th><th>reason</th></tr></thead>
        <tbody>
          {groups.map(g => v.questions.filter(q => q.criterion === g).map((q, i) => (
            <tr key={q.id}>
              <td className="mono nowrap">{i === 0 ? <b>{g}</b> : ''}<div className="faint">{q.id}</div></td>
              <td style={{ minWidth: 260 }}>{q.question}</td>
              <td><span className={`pill ${q.by === 'harness' ? 'neutral' : 'accent'}`}>{q.by}</span></td>
              <td>{q.weight}</td>
              <td><span className={`pill ${q.answer === 'yes' ? 'pass' : q.answer === 'no' ? 'fail' : 'neutral'}`}>{q.answer}</span></td>
              <td className="muted">{q.reason}</td>
            </tr>
          )))}
        </tbody>
      </table>
      <JudgePrompt runId={runId} file={rec.trace_file} which="judge_v2_prompt" label="what the trajectory judge was given" />
    </div>
  )
}

function JudgePrompt({ runId, file, which = 'judge_prompt', label = 'what the judge was given' }: { runId: string; file?: string; which?: 'judge_prompt' | 'judge_v2_prompt'; label?: string }) {
  const [p, setP] = useState<string | null>(null)
  const [open, setOpen] = useState(false)
  useEffect(() => { if (open && p === null && file) api.trace(runId, file).then(t => setP(t[which] ?? '(not stored)')).catch(() => setP('(unavailable)')) }, [open, p, file, runId, which])
  return (
    <details className="mini section" open={open} onToggle={e => setOpen((e.target as HTMLDetailsElement).open)}>
      <summary>{label}</summary>
      {open && <pre className="box" style={{ marginTop: 8, maxHeight: 480, overflow: 'auto' }}>{p ?? 'loading…'}</pre>}
    </details>
  )
}

function Calls({ calls }: { calls: LlmCall[] }) {
  const [showSeed, setShowSeed] = useState(false)
  const shown = calls.filter(c => showSeed || c.phase !== 'seed')
  const seedCount = calls.length - calls.filter(c => c.phase !== 'seed').length
  return (
    <>
      <div className="toolbar" style={{ marginTop: 0 }}>
        <span className="muted">{shown.length} calls</span>
        {seedCount > 0 && <button className={`chip ${showSeed ? 'on' : ''}`} onClick={() => setShowSeed(v => !v)}>include {seedCount} seed summarizer calls</button>}
      </div>
      {shown.map((c, i) => (
        <details key={i} className="call">
          <summary>
            <span className="pill neutral">{c.phase}</span>
            <b>{c.agent ? `worker · ${c.agent}` : c.component}</b>
            <span className="muted">{(c.usage.prompt_tokens ?? c.estimated_input_tokens).toLocaleString()} in{c.usage.completion_tokens ? ` · ${c.usage.completion_tokens} out` : ''} · {c.wall_ms}ms</span>
            {c.gate_blocked && <span className="pill gate">blocked</span>}
            {c.error && !c.gate_blocked && <span className="pill fail">error</span>}
            <span className="mono" style={{ marginLeft: 'auto', color: 'var(--muted)' }}>{c.tool_calls.map(t => t.name).join(', ') || (c.assistant_text ? 'text' : '')}</span>
          </summary>
          <div className="body">
            {c.error && <div className="box" style={{ color: 'var(--fail)' }}>{c.error}</div>}
            {c.tool_calls.length > 0 && <div className="msg"><div className="role">tool calls</div><pre>{c.tool_calls.map(t => `${t.name}(${pretty(t.arguments)})`).join('\n\n')}</pre></div>}
            {c.assistant_text && <div className="msg"><div className="role">assistant text</div><pre>{c.assistant_text}</pre></div>}
            <details className="mini" style={{ marginTop: 8 }}><summary>prompt: system + {c.messages.length} messages · tools: {c.tools.join(', ') || 'none'}</summary>
              {c.system && <div className="msg"><div className="role">system</div><pre>{c.system}</pre></div>}
              {c.messages.map((m, j) => <div key={j} className="msg"><div className="role">{m.role}</div><pre>{typeof m.content === 'string' ? m.content : JSON.stringify(m.content, null, 1)}{m.tool_calls ? `\n\n[tool_calls] ${JSON.stringify(m.tool_calls)}` : ''}</pre></div>)}
            </details>
          </div>
        </details>
      ))}
    </>
  )
}

function pretty(args: string) {
  try { return JSON.stringify(JSON.parse(args), null, 1) } catch { return args }
}
