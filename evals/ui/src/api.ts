export type Generated = { generate: string; tokens: string | number; party?: string; company?: string; prefix?: string; terms?: Record<string, string> }
export type HistoryItem = { role?: 'user' | 'reply' | 'agent'; content?: string | Generated; filler?: boolean }
export type WorkerLogItem = { tag?: string; content?: string; filler?: boolean }
export type EmailSeed = { id: string; thread_id?: string; from: string; to?: string; subject: string; body: string | Generated; days_ago?: number }
export type Case = {
  id: string
  name: string
  axis: string
  description: string
  roster?: string[]
  world?: { emails?: EmailSeed[]; drafts?: Record<string, unknown>[]; contacts?: { name: string; email: string }[] }
  history?: HistoryItem[]
  worker_logs?: Record<string, WorkerLogItem[]>
  turns: string[]
  success: Record<string, unknown>
  ideal_trajectory?: string
  tier?: string
  extends_from?: string
  filler_entry_tokens?: number
  target?: string
  size?: number
  baseline_note?: string
  disabled_reason?: string
}
export type CasesFile = { _doc?: unknown; cases: Case[] }

export type Crit = { ok: boolean; note: string }
export type Judge = {
  error?: string
  model?: string
  task_completed?: boolean
  score?: number
  summary?: string
  planning?: Crit; execution?: Crit; observation_interpretation?: Crit; replanning?: Crit
  termination?: Crit; loops?: Crit; unnecessary_actions?: Crit
}
export type RubricQ = { id: string; criterion: string; question: string; by: 'harness' | 'judge'; weight: number; answer: 'yes' | 'no' | 'na'; reason: string }
export type JudgeV2 = { score: number | null; not_scored?: string; earned?: number; applicable?: number; questions: RubricQ[]; model?: string | null; task_completed?: boolean | null; error?: string | null }
export const CRITERIA = ['planning', 'execution', 'observation_interpretation', 'replanning', 'termination', 'loops', 'unnecessary_actions'] as const

export type Counters = {
  llm_calls: number; llm_calls_by_component: Record<string, number>; seed_llm_calls: number
  ia_tool_calls: number; worker_tool_calls: number; steps: number; dispatches: number; recalls: number
  new_workers: string[]; duplicate_worker_tool_calls: number; input_tokens: number; output_tokens: number
  max_prompt_tokens: number; gate_blocks: number; llm_errors: number; llm_wall_ms: number; blocked_input_tokens_est?: number
}
export type Sent = { id: string; to: string; subject: string; body: string; cc: string[]; thread_id?: string; via: string; draft_id?: string }
export type Draft = { id: string; to: string; subject: string; body: string; cc: string[]; thread_id?: string }
export type Turn = { turn: number; text: string; success: boolean; error?: string | null; wall_ms: number }
export type Outcome = { task_done?: boolean; reply_accurate?: boolean; side_effects?: { severity: 'major' | 'minor'; what: string }[]; major?: string[]; reason?: string; model?: string; error?: string }
export type RunRecord = {
  run_id: string; case_id: string; name: string; size: number; strategy: string; started_at: string
  seeded_tokens?: { conversation: number; worker_logs: number }
  success: boolean; timed_out?: boolean; cell_timeout_s?: number; checks_pass?: boolean; outcome?: Outcome | null; verdict_v1?: { success: boolean; fail_reason?: string | null; failures: string[] } | null; fail_reason?: string | null; checks: Record<string, boolean>; failures: string[]
  turns: Turn[]; aborted?: string | null; replies: string[]; wall_ms?: number
  summary_state?: { last_index: number; summary_chars: number; unsummarized_entries: number }
  counters?: Counters
  world?: { sent: Sent[]; drafts: Draft[]; deleted_drafts: string[]; drafts_created: number; calls: number }
  events: string[]
  judge_v2?: JudgeV2 | null
  trace_file?: string
}
export type Results = {
  label: string; model: string; judge_model: string; context_window: number; max_calls: number
  sizes: number[]; strategies: string[]; generated_at: string; total: number; passed: number; mode?: string
  runs: RunRecord[]
}
export type RunSummary = {
  id: string; label: string; model?: string; judge_model?: string; context_window?: number
  sizes?: number[]; strategies?: string[]; generated_at?: string; total: number; passed: number
  by_strategy: Record<string, { total: number; passed: number; wall_ms?: number }>; cases: string[]; in_progress: boolean
}
export type LlmCall = {
  phase: string; component: string; agent?: string | null; model: string; t0: number; wall_ms: number
  system?: string | null; messages: { role: string; content: unknown; tool_calls?: unknown }[]
  tools: string[]; assistant_text: string; tool_calls: { name: string; arguments: string }[]
  usage: { prompt_tokens?: number | null; completion_tokens?: number | null }
  estimated_input_tokens: number; gate_blocked: boolean; error?: string | null
}
export type Trace = {
  record: RunRecord; judge_prompt?: string | null; judge_v2_prompt?: string | null; outcome_prompt?: string | null; llm_calls: LlmCall[]
  world_calls: { t: number; tool: string; args: unknown; ok: boolean; result_brief: string }[]
}

async function get<T>(url: string): Promise<T> {
  const r = await fetch(url)
  if (!r.ok) throw new Error(`${r.status} ${url}`)
  return r.json() as Promise<T>
}
export const api = {
  cases: () => get<CasesFile>('/api/cases'),
  runs: () => get<RunSummary[]>('/api/runs'),
  run: (id: string) => get<Results>(`/api/runs/${id}`),
  trace: (id: string, file: string) => get<Trace>(`/api/runs/${id}/trace/${file.replace(/^traces\//, '')}`),
}

export const k = (n?: number | null) => (n == null ? '—' : n >= 1000 ? `${Math.round(n / 1000)}k` : String(n))
export const fmtDate = (iso?: string) => (iso ? new Date(iso).toLocaleString() : '')
export const resultKind = (r: RunRecord): 'pass' | 'gate' | 'warn' | 'fail' | 'side' =>
  r.success ? 'pass' : r.fail_reason === 'overflow' ? 'gate' : (r.fail_reason === 'loop' || r.fail_reason === 'timeout') ? 'warn' : r.fail_reason === 'side_effect' ? 'side' : 'fail'
export const fmtWall = (r: RunRecord) => (r.timed_out ? `> ${r.cell_timeout_s ?? '?'}s cap` : r.wall_ms != null ? `${Math.round(r.wall_ms / 1000)}s` : '—')
export const resultLabel = (r: RunRecord) => (r.success ? 'PASS' : `FAIL · ${r.fail_reason ?? 'fail'}`)

export const fmtDur = (ms?: number | null) => { if (ms == null) return '—'; const s = Math.round(ms / 1000); return s >= 3600 ? `${Math.floor(s / 3600)}h ${Math.floor((s % 3600) / 60)}m` : s >= 60 ? `${Math.floor(s / 60)}m ${s % 60}s` : `${s}s` }
