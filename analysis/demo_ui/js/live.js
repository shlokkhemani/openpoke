// Live backends: API client + session model.
//
// The session only records what the two servers return (chat history, LTM trace ids, trace documents, memory-state
// snapshots) and restructures it into the openpoke.ltm.demo_trace.v1 shape so the existing renderers can draw it.
// No memory decision is computed here.

const DEFAULTS = { baseline: "http://127.0.0.1:8020", ltm: "http://127.0.0.1:8021" };

export async function resolveConfig() {
  const q = new URLSearchParams(location.search);
  let launched = null;
  try {
    const r = await fetch("live-config.json", { cache: "no-store" });
    if (r.ok) launched = await r.json();
  } catch {
    launched = null;
  }
  return {
    baseline: (q.get("baseline") || launched?.baseline || DEFAULTS.baseline).replace(/\/$/, ""),
    ltm: (q.get("ltm") || launched?.ltm || DEFAULTS.ltm).replace(/\/$/, ""),
    launched, // null when the page is not served by live_demo.py
  };
}

async function req(url, opts = {}, timeoutMs = 15000) {
  const ctl = new AbortController();
  const t = setTimeout(() => ctl.abort(), timeoutMs);
  try {
    const res = await fetch(url, { cache: "no-store", ...opts, signal: ctl.signal });
    const text = await res.text();
    let body = null;
    try {
      body = text ? JSON.parse(text) : null;
    } catch {
      body = text;
    }
    return { ok: res.ok, status: res.status, body };
  } finally {
    clearTimeout(t);
  }
}
const json = (method, body) => ({ method, headers: { "content-type": "application/json" }, body: JSON.stringify(body ?? {}) });

export class Backend {
  constructor(name, base, labSide = null) {
    this.name = name;
    this.base = base;
    this.api = base + "/api/v1";
    this.history = [];
    this.connected = null;
    this.labSide = labSide; // set when served by live_demo.py, which can read this instance's conversation log
    this.waits = new Map(); // user-message ordinal → reason the agent gave for not replying (wait tool)
  }
  /**
   * OpenPoke's interaction agent may answer with the silent `wait` tool (e.g. "already said that"). /chat/history omits
   * those entries, so read the entry kinds from the lab supervisor and map each wait to the user message it follows.
   */
  async loadWaits() {
    if (!this.labSide) return this.waits;
    try {
      const r = await req(`/lab/convlog?side=${this.labSide}`, {}, 4000);
      const map = new Map();
      let users = -1;
      for (const e of r.body?.entries || []) {
        if (e.kind === "user_message") users++;
        else if (e.kind === "wait" && users >= 0) map.set(users, e.reason || "");
        else if (e.kind === "poke_reply" && users >= 0) map.delete(users);
      }
      this.waits = map;
    } catch {
      /* keep previous */
    }
    return this.waits;
  }
  userOrdinal(index) {
    let k = -1;
    for (let i = 0; i <= index && i < this.history.length; i++) if (this.history[i].role === "user") k++;
    return k;
  }
  async health() {
    try {
      const r = await req(this.api + "/health", {}, 2500);
      this.connected = r.ok;
    } catch {
      this.connected = false;
    }
    return this.connected;
  }
  async loadHistory() {
    const r = await req(this.api + "/chat/history");
    if (!r.ok) throw new Error(`${this.name}: GET /chat/history ${r.status}`);
    this.history = Array.isArray(r.body?.messages) ? r.body.messages : [];
    return this.history;
  }
  send(text) {
    return req(this.api + "/chat/send", json("POST", { messages: [{ role: "user", content: text }] }));
  }
  clearHistory() {
    return req(this.api + "/chat/history", { method: "DELETE" });
  }
  /** Poll /chat/history until an assistant message follows the first user message at index >= from. */
  async waitReply(from, { timeoutMs = 120000, onUpdate } = {}) {
    const end = Date.now() + timeoutMs;
    let polls = 0;
    while (Date.now() < end) {
      const before = JSON.stringify(this.history);
      const h = await this.loadHistory().catch(() => this.history);
      if (JSON.stringify(h) !== before) onUpdate?.();
      const ui = h.findIndex((m, i) => i >= from && m.role === "user");
      if (ui >= 0) {
        const ai = h.findIndex((m, i) => i > ui && m.role === "assistant");
        if (ai >= 0) return { userIndex: ui, replyIndex: ai };
        if (this.labSide && polls++ % 3 === 0) {
          await this.loadWaits();
          if (this.waits.has(this.userOrdinal(ui))) {
            onUpdate?.();
            return { userIndex: ui, replyIndex: null, wait: this.waits.get(this.userOrdinal(ui)) };
          }
        }
      }
      await sleep(400);
    }
    throw new Error(`${this.name}: no reply within ${Math.round(timeoutMs / 1000)} s`);
  }
}

export class LtmDebug {
  constructor(base) {
    this.api = base + "/api/v1/memory/debug";
    this.available = null;
    this.hooks = null;
  }
  async traces(limit = 50) {
    const r = await req(`${this.api}/traces?limit=${limit}`);
    this.available = r.ok;
    if (!r.ok) throw new Error(`GET /memory/debug/traces ${r.status}`);
    return Array.isArray(r.body) ? r.body : [];
  }
  async trace(id) {
    const r = await req(`${this.api}/trace/${encodeURIComponent(id)}`);
    if (!r.ok) throw new Error(`GET /memory/debug/trace ${r.status}`);
    return r.body;
  }
  async state() {
    const r = await req(`${this.api}/state`);
    if (!r.ok) throw new Error(`GET /memory/debug/state ${r.status}`);
    return r.body;
  }
  /** Returns true/false when the hook exists, null when test hooks are off (404). */
  async awaitIdle(includeDelayed, timeoutMs = 12000) {
    try {
      const r = await req(`${this.api}/test/await-idle`, json("POST", { include_delayed: includeDelayed, timeout_s: 10 }), timeoutMs);
      if (r.status === 404 || r.status === 403) {
        this.hooks = false;
        return null;
      }
      this.hooks = true;
      return !!r.body?.idle;
    } catch {
      return null;
    }
  }
  async ingestDelay(ms) {
    const r = await req(`${this.api}/test/ingest-delay`, json("POST", { duplicate_next_job_with_delay_ms: ms }));
    this.hooks = r.ok;
    return r;
  }
}

export const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

/**
 * The live session. turns[] are the messages sent from this page (or recovered on reload), each with the LTM trace id
 * the server assigned and the trace document it returned.
 */
export class Session {
  constructor() {
    this.turns = []; // {n, text, status, traceId, trace, ltmUserIndex, baseUserIndex, error}
    this.snapshots = []; // {after_turn, ...state}
    this.latestState = null;
  }
  newTurn(text) {
    const t = { n: this.turns.length, text, status: "sending", traceId: null, trace: null, errors: [] };
    this.turns.push(t);
    return t;
  }
  recordState(afterTurn, state) {
    this.latestState = state;
    const i = this.snapshots.findIndex((s) => s.after_turn === afterTurn);
    const snap = { after_turn: afterTurn, ...state };
    if (i >= 0) this.snapshots[i] = snap;
    else this.snapshots.push(snap);
  }

  /** Assemble the live data into the demo-trace shape (mode "ltm") for the shared renderers. */
  toDoc(ltmHistory) {
    const byTrace = new Map();
    const turns = [];
    const pipeline = [];
    const retrieval = [];
    for (const t of this.turns) {
      if (t.traceId) byTrace.set(t.traceId, t.n);
      const tr = t.trace || {};
      const stored = t.ltmUserIndex != null ? ltmHistory?.[t.ltmUserIndex]?.content : null;
      turns.push({
        turn_index: t.n,
        kind: tr.kind || (t.trace ? "setup" : "pending"),
        probe: tr.kind === "probe" ? "live" : undefined,
        session: "live",
        text_safe: stored ?? t.text,
        trace_id: t.traceId,
        path: tr.path || [],
        outcomes: tr.outcomes || [],
      });
      for (const p of tr.pipeline || []) pipeline.push({ ...p, turn_index: t.n });
      if (tr.retrieval) retrieval.push({ ...tr.retrieval, turn_index: t.n, probe: tr.kind === "probe" ? "live" : null });
    }
    const enrich = (snap) => ({
      ...snap,
      memories: (snap.memories || []).map((m) => ({
        ...m,
        status_history: (m.status_history || []).map((h) => ({ ...h, turn_index: h.turn_index ?? byTrace.get(h.trace_id) })),
      })),
    });
    return {
      schema: "openpoke.ltm.demo_trace.v1",
      scenario: "live",
      mode: "ltm",
      meta: { headline_probe: "live" },
      turns,
      pipeline,
      retrieval,
      memory_state: this.snapshots.map(enrich),
      retrieved: [],
      probes: [],
      baseline_observations: [],
      canary_scan: { canaries: [], sinks: [] },
      assertions: [],
    };
  }
}
