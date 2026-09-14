import { useMemo, useState } from 'react'
import type { LlmCall, RunRecord, Trace } from '../api'

type Actor = 'ia' | 'worker' | 'search' | 'digest' | 'gmail' | 'summarizer'
type ToolStep = { name: string; args: Record<string, unknown> | string; summary: string }
type Step = {
  i: number; phase: string; actor: Actor; label: string; callback: boolean
  tokensIn?: number | null; tokensOut?: number | null; wallMs?: number
  text?: string; tools: ToolStep[]; result?: string; blocked?: boolean; error?: string | null; ok?: boolean
}

const ACTOR_LABEL: Record<Actor, string> = { ia: 'interaction agent', worker: 'worker', search: 'email search', digest: 'digest (chunk read)', gmail: 'Gmail', summarizer: 'summarizer' }

function parseArgs(a: unknown): Record<string, unknown> | string {
  if (a && typeof a === 'object') return a as Record<string, unknown>
  if (typeof a !== 'string') return String(a ?? '')
  try { return JSON.parse(a) } catch { return a }
}
const s = (v: unknown, n = 90) => { const t = typeof v === 'string' ? v : JSON.stringify(v); return t.length > n ? t.slice(0, n) + '…' : t }

function summarize(name: string, a: Record<string, unknown> | string): string {
  if (typeof a === 'string') return s(a)
  switch (name) {
    case 'send_message_to_agent': return `→ ${a.agent_name}: ${s(a.instructions, 110)}`
    case 'send_message_to_user': return `"${s(a.message, 110)}"`
    case 'send_draft': return `to ${a.to} · ${s(a.subject, 50)}`
    case 'wait': return `${s(a.reason, 90)}`
    case 'recall_history': return a.entry_ids ? `ids ${JSON.stringify(a.entry_ids)}` : `query "${s(a.query, 60)}"`
    case 'gmail_create_draft': case 'GMAIL_CREATE_EMAIL_DRAFT':
      return `to ${a.recipient_email}${a.cc ? ` cc ${JSON.stringify(a.cc)}` : ''}${a.thread_id ? ` thread ${a.thread_id}` : ''} · ${s(a.subject, 40)}`
    case 'gmail_execute_draft': case 'GMAIL_SEND_DRAFT': case 'gmail_delete_draft': case 'GMAIL_DELETE_DRAFT': return `${a.draft_id}`
    case 'gmail_reply_to_thread': case 'GMAIL_REPLY_TO_THREAD': return `thread ${a.thread_id} → ${a.recipient_email}${a.cc ? ` cc ${JSON.stringify(a.cc)}` : ''}`
    case 'gmail_forward_email': case 'GMAIL_FORWARD_MESSAGE': return `${a.message_id} → ${a.recipient_email}`
    case 'task_email_search': return `"${s(a.search_query, 80)}"`
    case 'gmail_fetch_emails': case 'GMAIL_FETCH_EMAILS': return `"${s(a.query, 80)}"${a.max_results ? ` · max ${a.max_results}` : ''}`
    case 'return_search_results': return `${JSON.stringify(a.message_ids ?? a)}`
    case 'createTrigger': return `${s(a.start_time ?? '', 30)} ${s(a.payload ?? a.description ?? '', 50)}`
    default: {
      const keys = Object.keys(a).slice(0, 3)
      return keys.map(k => `${k}=${s(a[k], 40)}`).join(' ')
    }
  }
}

export function buildSteps(trace: Trace, events: string[]): Step[] {
  const llm = trace.llm_calls.filter(c => c.phase !== 'seed').slice().sort((a, b) => a.t0 - b.t0)
  const world = trace.world_calls ?? []
  // record.events is already time-ordered and interleaves LLM rounds with [gmail] calls; walk it to merge.
  const steps: Step[] = []
  let li = 0, wi = 0
  const pushLlm = (c: LlmCall) => {
    const actor: Actor = c.component === 'interaction_agent' ? 'ia' : c.component === 'execution_agent' ? 'worker' : c.component === 'email_search' ? 'search' : c.component === 'digest' ? 'digest' : 'summarizer'
    const first = c.messages?.[0]?.content
    const callback = actor === 'ia' && typeof first === 'string' && first.includes('<new_agent_message>')
    steps.push({
      i: steps.length + 1, phase: c.phase, actor, label: c.agent ? `worker · ${c.agent}` : ACTOR_LABEL[actor], callback,
      tokensIn: c.usage?.prompt_tokens ?? c.estimated_input_tokens, tokensOut: c.usage?.completion_tokens, wallMs: c.wall_ms,
      text: c.assistant_text || undefined, blocked: c.gate_blocked, error: c.error,
      tools: (c.tool_calls ?? []).map(t => { const a = parseArgs(t.arguments); return { name: t.name, args: a, summary: summarize(t.name, a) } }),
    })
  }
  const pushWorld = (w: Trace['world_calls'][number], phase: string) => {
    const a = parseArgs(w.args)
    steps.push({ i: steps.length + 1, phase, actor: 'gmail', label: 'Gmail', callback: false, ok: w.ok, result: w.result_brief,
      tools: [{ name: w.tool, args: a, summary: summarize(w.tool, a) }] })
  }
  let phase = llm[0]?.phase ?? 'turn1'
  for (const e of events) {
    if (e.startsWith('[gmail]')) { if (wi < world.length) pushWorld(world[wi++], phase) }
    else if (li < llm.length) { phase = llm[li].phase; pushLlm(llm[li++]) }
  }
  while (li < llm.length) pushLlm(llm[li++])
  while (wi < world.length) pushWorld(world[wi++], phase)
  return steps
}

export default function Timeline({ trace, rec }: { trace: Trace; rec: RunRecord }) {
  const steps = useMemo(() => buildSteps(trace, rec.events ?? []), [trace, rec])
  const [open, setOpen] = useState<Record<number, boolean>>({})
  const [only, setOnly] = useState<Actor | ''>('')
  const shown = only ? steps.filter(st => st.actor === only) : steps
  const counts = steps.reduce((m, st) => { m[st.actor] = (m[st.actor] ?? 0) + 1; return m }, {} as Record<string, number>)

  return (
    <>
      <div className="section">
        <h3>Tool sequence</h3>
        <div className="seq">
          {steps.map(st => (
            st.tools.length ? st.tools.map((t, j) => (
              <span key={`${st.i}-${j}`} className={`seqchip ${st.actor} ${st.blocked ? 'blocked' : ''} ${st.ok === false ? 'err' : ''}`}
                title={`#${st.i} ${st.label}: ${t.summary}`} onClick={() => { setOnly(''); setOpen(o => ({ ...o, [st.i]: true })); document.getElementById(`step-${st.i}`)?.scrollIntoView({ block: 'center' }) }}>
                <i>{st.i}</i>{t.name}
              </span>
            )) : (
              <span key={st.i} className={`seqchip ${st.actor} soft ${st.blocked ? 'blocked' : ''} ${st.error ? 'err' : ''}`} title={`#${st.i} ${st.label}: ${st.blocked ? 'blocked' : st.error ? 'error' : st.text ? 'text reply' : 'empty'}`}
                onClick={() => document.getElementById(`step-${st.i}`)?.scrollIntoView({ block: 'center' })}>
                <i>{st.i}</i>{st.blocked ? '⛔ blocked' : st.error ? '✗ error' : st.text ? '💬 text' : '∅'}
              </span>
            )
          ))}
        </div>
      </div>
      <div className="toolbar" style={{ marginTop: 0 }}>
        {(['ia', 'worker', 'search', 'digest', 'gmail'] as Actor[]).filter(a => counts[a]).map(a => (
          <button key={a} className={`chip act-${a} ${only === a ? 'on' : ''}`} onClick={() => setOnly(o => (o === a ? '' : a))}>{ACTOR_LABEL[a]} · {counts[a]}</button>
        ))}
        <span className="count">{steps.length} steps</span>
      </div>
      <div className="timeline">
        {shown.map((st, idx) => {
          const prev = shown[idx - 1]
          const newPhase = !prev || prev.phase !== st.phase
          const isOpen = !!open[st.i]
          return (
            <div key={st.i}>
              {newPhase && <div className="phase-div"><span>{st.phase}</span></div>}
              <div id={`step-${st.i}`} className={`step ${st.actor} ${st.blocked ? 'blocked' : ''} ${st.error && !st.blocked ? 'error' : ''} ${st.ok === false ? 'error' : ''}`}>
                <div className="step-l">
                  <span className="stepno">{st.i}</span>
                  <span className={`actor ${st.actor}`}>{st.label}</span>
                  {st.callback && <span className="pill accent">callback</span>}
                  {st.tokensIn != null && <span className="muted nowrap">{st.tokensIn.toLocaleString()} in{st.tokensOut ? ` · ${st.tokensOut} out` : ''}</span>}
                  {st.wallMs != null && <span className="faint nowrap">{st.wallMs}ms</span>}
                </div>
                <div className="step-r">
                  {st.blocked && <div className="pill gate" style={{ whiteSpace: 'normal' }}>{st.error}</div>}
                  {st.error && !st.blocked && <div className="pill fail" style={{ whiteSpace: 'normal' }}>{st.error}</div>}
                  {st.tools.map((t, j) => (
                    <div key={j} className="toolrow">
                      <span className={`toolname ${st.actor}`}>{t.name}</span>
                      <span className="toolsum">{t.summary}</span>
                    </div>
                  ))}
                  {st.result != null && <div className={`result ${st.ok === false ? 'bad' : ''}`}>→ {st.result}</div>}
                  {st.text && <div className="steptext">{isOpen || st.text.length <= 200 ? st.text : st.text.slice(0, 200) + '…'}</div>}
                  {!st.tools.length && !st.text && !st.blocked && !st.error && <span className="faint">(empty response)</span>}
                  {(st.tools.length > 0 || (st.text && st.text.length > 200)) && (
                    <button className="linkbtn" onClick={() => setOpen(o => ({ ...o, [st.i]: !isOpen }))}>{isOpen ? 'hide details' : 'full arguments'}</button>
                  )}
                  {isOpen && st.tools.length > 0 && <pre className="argbox">{st.tools.map(t => `${t.name}(${typeof t.args === 'string' ? t.args : JSON.stringify(t.args, null, 1)})`).join('\n\n')}</pre>}
                </div>
              </div>
            </div>
          )
        })}
      </div>
    </>
  )
}
