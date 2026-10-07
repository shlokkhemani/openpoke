// Presentation summaries derived from the live trace + memory state of ONE turn.
//
// Everything here is a pure function of the data passed in: it groups raw events into six semantic stages and turns
// outcomes / retrieval / state into short state-transition "chains". The wording templates are fixed; every status,
// decision, score and subject comes from the trace or the state. If the data doesn't contain something, it isn't shown.

import * as T from "./trace.js";

const { arr, obj } = T;

// ---------------------------------------------------------------- vocabulary (presentation only)

export const STAGES = [
  { id: "privacy", label: "Privacy" },
  { id: "extract", label: "Extract" },
  { id: "decide", label: "Decide" },
  { id: "store", label: "Store" },
  { id: "retrieve", label: "Retrieve" },
  { id: "agent", label: "Agent" },
];

// green = active/store/selected/pass · red = reject/delete · amber = ignore/contested · grey = inactive/no-op · blue = scrub/info
const TONE = {
  ACTIVE: "good", STORE: "good", STORED: "good", INSERT: "good", SELECTED: "good", PASS: "good", MERGE: "good", INJECTED: "good",
  REJECT: "bad", REJECTED: "bad", DELETE: "bad", DELETED: "bad", FENCE_DROP: "bad", TOMBSTONE: "bad", TOMBSTONED: "bad", FILTERED: "bad", EXPIRED: "muted",
  IGNORE: "warn", IGNORED: "warn", CONTESTED: "warn", CONTEST: "warn",
  SUPERSEDED: "muted", "NO-OP": "muted", NONE: "muted",
  SCRUBBED: "accent", SUPERSEDE: "accent", PURGED: "accent", MASKED: "accent", INFO: "accent",
};
export const tone = (w) => TONE[String(w || "").toUpperCase().split(" ")[0]] || "neutral";

const DETECTOR_NAME = { API_KEY: "API key", EMAIL: "email", PHONE: "phone number", AWS_KEY: "AWS key", JWT: "token", PRIVATE_KEY: "private key" };
export const detectorName = (t) => DETECTOR_NAME[String(t).replace(/^[A-Z]+:/, "")] || String(t).replace(/^[A-Z]+:/, "").toLowerCase().replace(/_/g, " ");

const REASON_NOTE = {
  CONTACT_IDENTIFIER_NOT_NEEDED: "kept out of long-term memory · short-term chat context only",
  TRANSIENT_STATE: "transient",
  POISONING_SUSPECTED: "looks like an injected instruction",
  CAPABILITY_WIDENING: "would widen what the agent may do",
};
export function reasonNote(code) {
  if (!code) return "";
  if (REASON_NOTE[code]) return REASON_NOTE[code];
  if (/^SECRET/.test(code)) return "secret · never stored";
  return String(code).toLowerCase().replace(/_/g, " ");
}
const QUIET_REASONS = new Set(["QUESTION", "SMALL_TALK", "COMMAND"]);

/** A clause label that is only numbering / punctuation (e.g. "1." from "1. My …") is not worth showing. */
const meaningful = (s) => typeof s === "string" && /[A-Za-z]{2,}/.test(s);

export function humanSlot(slot) {
  if (!slot) return "memory";
  return String(slot).replace(/^[^|]*\|/, "").replace(/^(pref|profile|fact|constraint)\./, "").replace(/_/g, " ");
}

/** Short subject for an outcome label: "favorite programming language = Python" → {topic, value}. */
function splitLabel(label) {
  const [topic, value] = String(label || "").split(/\s*=\s*/);
  return { topic: topic || "", value: value || "" };
}

// ---------------------------------------------------------------- context

export function makeContext(doc, n) {
  const cat = T.memoryCatalog(doc);
  const snaps = T.snapshots(doc);
  const snapAt = snaps.filter((s) => s.after_turn <= n).pop() || null;
  const latest = snaps[snaps.length - 1] || null;
  const turn = T.turnByIndex(doc, n);
  const evs = T.eventsForTurn(doc, n);
  return { doc, n, cat, snapAt, latest, turn, evs, r: T.retrievalForTurn(doc, n) };
}

const memIn = (snap, id) => arr(snap?.memories).find((m) => m.id === id) || null;
const nameOf = (ctx, id) => {
  const m = ctx.cat.get(id);
  return m?.display || (m?.slot_key ? humanSlot(m.slot_key) : "memory");
};
const statusUpper = (m) => (m?.status ? String(m.status).toUpperCase() : null);

// ---------------------------------------------------------------- chains (the hero transitions)

/**
 * Each chain: {title, subject, steps: [{text, tone}], note}. Built from this turn's outcomes, its forget/fence events,
 * and (for turns that only read memory) its retrieval.
 */
export function chains(ctx) {
  const out = [];
  const { evs, turn, snapAt, latest } = ctx;
  const outs = arr(turn?.outcomes);
  const ingress = evs.find((e) => e.stage === "ingress.scrub");
  const scrubbedTypes = new Set(arr(obj(ingress?.detail).detectors).map((d) => (typeof d === "string" ? d : d.type)));
  let wrote = false;

  for (const o of outs) {
    const { topic, value } = splitLabel(o.label);
    const result = String(o.result || "").toUpperCase();
    const decision = String(o.decision || "").toUpperCase();
    if (o.duplicate && result !== "FENCE_DROP") continue;

    if (result === "SUPERSEDE" && o.memory_id) {
      wrote = true;
      const oldM = memIn(snapAt, o.supersedes) || ctx.cat.get(o.supersedes);
      const newM = memIn(snapAt, o.memory_id) || ctx.cat.get(o.memory_id);
      out.push({
        title: topic,
        steps: [
          { text: nameOf(ctx, o.supersedes), strong: true, tone: "muted" },
          { text: statusUpper(oldM) || "SUPERSEDED?", tone: tone(statusUpper(oldM)) },
          { arrow: true },
          { text: nameOf(ctx, o.memory_id) || value, strong: true },
          { text: statusUpper(newM) || "?", tone: tone(statusUpper(newM)) },
        ],
        vertical: true,
      });
    } else if (decision === "STORE" && (result === "INSERT" || result === "MERGE") && o.memory_id) {
      wrote = true;
      const m = memIn(snapAt, o.memory_id) || ctx.cat.get(o.memory_id);
      out.push({
        title: topic,
        steps: [{ text: nameOf(ctx, o.memory_id) || value, strong: true }, { text: "STORE", tone: "good" }, { arrow: true }, { text: statusUpper(m) || "?", tone: tone(statusUpper(m)) }],
      });
    } else if (decision === "REJECT") {
      wrote = true;
      const cls = evs.find((e) => e.stage === "privacy.classify" && e.candidate_id === o.candidate_id);
      const types = arr(obj(cls?.detail).detectors).map((d) => String(d).replace(/^[A-Z]+:/, ""));
      const scrubbed = types.some((t) => scrubbedTypes.has(t));
      out.push({
        title: topic,
        steps: [{ text: meaningful(o.label) ? o.label : "clause", strong: true }, ...(scrubbed ? [{ text: "SCRUBBED", tone: "accent" }, { arrow: true }] : []), { text: "REJECTED", tone: "bad" }],
        note: reasonNote(o.reason),
      });
    } else if (decision === "IGNORE" && !QUIET_REASONS.has(o.reason) && meaningful(o.label)) {
      out.push({ title: "", steps: [{ text: o.label, strong: true }, { text: "IGNORE", tone: "warn" }], note: reasonNote(o.reason) });
    } else if (decision === "DELETE" || result === "DELETE") {
      wrote = true;
      for (const id of arr(o.memory_ids).length ? o.memory_ids : [null]) {
        const now = id ? memIn(latest, id) : null;
        const slot = o.slot_key || now?.slot_key;
        const hadActive = id && arr(ctx.cat.get(id)?.status_history).some((h) => h.status === "active");
        const purged = now && now.status === "deleted" && now.canonical_text == null;
        const tomb = arr(latest?.tombstones).some((t) => t.slot_key === slot);
        out.push({
          title: humanSlot(slot),
          steps: [
            { text: id ? nameOf(ctx, id) : humanSlot(slot), strong: true },
            ...(hadActive ? [{ text: "ACTIVE", tone: "good" }, { arrow: true }] : []),
            { text: "DELETE", tone: "bad" },
            ...(purged ? [{ arrow: true }, { text: "PURGED", tone: "accent" }] : []),
            ...(tomb ? [{ arrow: true }, { text: "TOMBSTONE", tone: "bad" }] : []),
          ],
          note: id ? null : "nothing stored yet · tombstone blocks future writes",
        });
        for (const f of fenceDropsFor(ctx, slot)) out.push(fenceChain(f));
      }
    } else if (result === "FENCE_DROP") {
      out.push(fenceChain({ reason_codes: [o.reason], refs: o.refs, label: o.label }));
    }
  }

  // Read-only turns: what retrieval did (only when this turn didn't write, to avoid mixing pre-write retrieval in).
  const r = ctx.r;
  if (r && !wrote) {
    const sel = arr(r.candidates).filter((c) => c.selected);
    const excluded = arr(r.excluded_by_filters);
    const covered = new Set();
    for (const c of sel) {
      const m = memIn(snapAt, c.memory_id) || ctx.cat.get(c.memory_id);
      const prev = m?.supersedes_id ? memIn(snapAt, m.supersedes_id) || ctx.cat.get(m.supersedes_id) : null;
      const prevEx = prev ? excluded.find((x) => x.memory_id === prev.id) : null;
      if (prevEx) covered.add(prevEx.memory_id);
      out.push({
        note: prevEx ? `${prevEx.display || nameOf(ctx, prev.id)} filtered before ranking · ${prevEx.filter || ""}` : null,
        title: "retrieved",
        steps: [
          ...(prev ? [{ text: nameOf(ctx, prev.id), strong: true, tone: "muted" }, { text: statusUpper(prev), tone: tone(statusUpper(prev)) }, { arrow: true }] : []),
          { text: c.display || nameOf(ctx, c.memory_id), strong: true },
          { text: statusUpper(m) || "?", tone: tone(statusUpper(m)) },
          { arrow: true },
          { text: `SELECTED · ${num(c.total)}`, tone: "good" },
        ],
        vertical: !!prev,
      });
    }
    for (const x of excluded.filter((x) => !covered.has(x.memory_id)))
      out.push({ title: "", steps: [{ text: x.display || nameOf(ctx, x.memory_id), strong: true, tone: "muted" }, { text: "FILTERED", tone: "bad" }], note: `filtered before ranking · ${x.filter || ""}` });
    if (!sel.length && ctx.turn?.kind === "probe") out.push({ title: "retrieved", steps: [{ text: "0 memories retrieved", strong: true, tone: "muted" }], note: "no memory block injected" });
  }
  return out;
}

function fenceDropsFor(ctx, slot) {
  return T.pipeline(ctx.doc).filter((e) => e.stage === "fence_drop" && (!slot || obj(e.detail).slot_key === slot));
}
function fenceChain(f) {
  return {
    title: "delayed duplicate write",
    steps: [{ text: "Delayed writer", strong: true }, { arrow: true }, { text: `FENCE_DROP · ${arr(f.reason_codes).filter(Boolean).join(", ") || "dropped"}`, tone: "bad" }],
    note: "stale background job blocked by the tombstone",
  };
}

const num = (v) => (typeof v === "number" ? v.toFixed(2) : "?");

// ---------------------------------------------------------------- the six semantic stages

/** [{id, label, lines: [{text, tone, badge}], quiet}] — one or two lines per stage, never raw event dumps. */
export function stages(ctx) {
  const { evs, cat } = ctx;
  const prim = primaryEvents(evs);
  const dup = evs.filter((e) => !prim.includes(e));
  const S = Object.fromEntries(STAGES.map((s) => [s.id, []]));
  const labelOf = (cid) => obj(prim.find((e) => e.candidate_id === cid && obj(e.detail).label)?.detail).label || cid;

  // Privacy
  const ing = prim.find((e) => e.stage === "ingress.scrub");
  for (const d of arr(obj(ing?.detail).detectors)) S.privacy.push({ text: `${detectorName(d.type || d)} → SCRUBBED`, badge: "SCRUBBED" });
  const p0 = prim.find((e) => e.stage === "privacy.scrub");
  for (const d of arr(obj(p0?.detail).detectors)) S.privacy.push({ text: `${detectorName(d.type || d)} masked for the extractor`, badge: "MASKED", minor: true });
  if (ing && !S.privacy.length) S.privacy.push({ text: "clean", quiet: true });

  // Extract
  const ex = prim.find((e) => e.stage === "extract");
  const clauses = prim.filter((e) => e.stage === "extract.clause");
  const nCand = obj(ex?.detail).n_candidates ?? clauses.filter((c) => c.candidate_id).length;
  const transient = clauses.filter((c) => !c.candidate_id && c.reason && !QUIET_REASONS.has(c.reason) && meaningful(c.input_safe ?? "x"));
  if (nCand) S.extract.push({ text: `${nCand} ${nCand === 1 ? "fact" : "facts"} identified` });
  if (transient.length) S.extract.push({ text: `${transient.length} transient ${transient.length === 1 ? "clause" : "clauses"} ignored`, badge: "IGNORE" });
  if (ex && !nCand && !transient.length) S.extract.push({ text: "No new memory", quiet: true });

  // Decide (policy / classify rejects / forget)
  const seen = new Set();
  for (const e of prim) {
    if ((e.stage === "policy" || (e.stage === "privacy.classify" && e.decision === "REJECT")) && e.candidate_id && !seen.has(e.candidate_id)) {
      seen.add(e.candidate_id);
      const d = String(e.decision || "").toUpperCase();
      S.decide.push({ text: `${cap(labelOf(e.candidate_id))} → ${d}`, badge: d });
    }
  }
  const fa = prim.find((e) => e.stage === "forget.apply");
  if (fa) S.decide.push({ text: `Forget ${humanSlot(obj(fa.detail).slot_key)} → DELETE`, badge: "DELETE" });
  else if (prim.find((e) => e.stage === "forget.detect")) S.decide.push({ text: "Forget request → nothing matched", badge: "NONE" });

  // Store
  for (const e of prim.filter((x) => x.stage === "consolidate")) {
    const d = String(e.decision || "").toUpperCase();
    const st = arr(cat.get(e.memory_id)?.status_history).find((h) => h.trace_id === e.trace_id)?.status;
    const name = obj(e.detail).display || nameOf(ctx, e.memory_id);
    if (d === "SUPERSEDE") S.store.push({ text: `${name} → ${String(st || "active").toUpperCase()}, replaces ${nameOf(ctx, obj(e.refs).old_id || obj(e.detail).refs?.old_id)}`, badge: "SUPERSEDE" });
    else if (st) S.store.push({ text: `${name} → ${st.toUpperCase()}`, badge: st.toUpperCase() });
    else S.store.push({ text: `${name} → ${d}`, badge: d });
  }
  if (fa) {
    const slot = obj(fa.detail).slot_key;
    const tomb = arr(ctx.latest?.tombstones).filter((t) => t.slot_key === slot).map((t) => t.scope);
    S.store.push({ text: `${obj(fa.detail).count ?? arr(obj(fa.detail).memory_ids).length} deleted · content purged${tomb.length ? ` · tombstone (${tomb.join(", ")})` : ""}`, badge: "DELETED" });
  }
  for (const e of dup.filter((x) => x.stage === "fence_drop").concat(prim.filter((x) => x.stage === "fence_drop")))
    S.store.push({ text: `Delayed duplicate write → FENCE_DROP · ${arr(e.reason_codes).join(", ")}`, badge: "FENCE_DROP" });

  // Retrieve
  const r = ctx.r;
  const wroteHere = prim.some((e) => ["consolidate", "forget.apply"].includes(e.stage) || (e.stage === "privacy.classify" && e.decision === "REJECT"));
  if (r) {
    if (wroteHere && arr(r.candidates).length) S.retrieve.push({ text: "read before this message was stored:", minor: true });
    for (const x of arr(r.excluded_by_filters)) S.retrieve.push({ text: `${x.display || nameOf(ctx, x.memory_id)} filtered · ${x.filter || ""}`, badge: "FILTERED" });
    const sel = arr(r.candidates).filter((c) => c.selected);
    for (const c of sel) S.retrieve.push({ text: `${c.display || nameOf(ctx, c.memory_id)} → SELECTED · ${num(c.total)}`, badge: "SELECTED" });
    const unsel = arr(r.candidates).filter((c) => !c.selected).length;
    if (unsel) S.retrieve.push({ text: `${unsel} candidate${unsel === 1 ? "" : "s"} not selected`, minor: true });
    if (!sel.length && !arr(r.excluded_by_filters).length) S.retrieve.push({ text: "0 memories retrieved", quiet: true });
  }

  // Agent
  const rendered = prim.filter((e) => e.stage === "prompt.render");
  if (rendered.length) {
    const tok = rendered.reduce((s, e) => s + (obj(e.detail).tokens || 0), 0);
    S.agent.push({ text: `${rendered.length} ${rendered.length === 1 ? "memory" : "memories"} injected${tok ? ` · ${tok} tok` : ""}`, badge: "INJECTED" });
  } else if (r) S.agent.push({ text: "no memory injected", quiet: true });

  return STAGES.map((s) => ({ ...s, lines: S[s.id], quiet: !S[s.id].length || S[s.id].every((l) => l.quiet) }));
}

/** Events of the turn's own job (a delayed duplicate job inside the same trace is split off). */
function primaryEvents(evs) {
  const out = [];
  let dup = false;
  for (const e of evs) {
    if (e.stage === "extract" && obj(e.detail).duplicate === true) dup = true;
    if (!dup) out.push(e);
  }
  return out;
}

const cap = (s) => (s ? String(s).charAt(0).toUpperCase() + String(s).slice(1) : s);

// ---------------------------------------------------------------- current memory rows

export function currentMemory(doc) {
  const latest = T.finalSnapshot(doc);
  const cat = T.memoryCatalog(doc);
  if (!latest) return null;
  const order = { active: 0, contested: 1, superseded: 2, deleted: 3, expired: 4 };
  const rows = arr(latest.memories)
    .slice()
    .sort((a, b) => (order[a.status] ?? 9) - (order[b.status] ?? 9))
    .map((m) => ({
      id: m.id,
      name: m.display || cat.get(m.id)?.display || humanSlot(m.slot_key),
      status: statusUpper(m),
      sub: [m.memory_type, humanSlot(m.slot_key), typeof m.confidence === "number" ? `confidence ${m.confidence.toFixed(2)}` : null].filter(Boolean).join(" · "),
      purged: m.canonical_text == null,
    }));
  const tombs = [...new Set(arr(latest.tombstones).map((t) => t.slot_key))].map((slot) => ({
    name: `${humanSlot(slot)}`,
    status: "TOMBSTONE",
    sub: arr(latest.tombstones).filter((t) => t.slot_key === slot).map((t) => t.scope).join(" + ") + " tombstone",
  }));
  return { rows, tombs };
}

/** One-line chips for the LTM chat bubble of a turn (max 3), from the same chains. */
export function bubbleChips(ctx) {
  return chains(ctx)
    .filter((c) => c.title !== "retrieved" || c.steps.some((s) => /SELECTED/.test(s.text || "")))
    .slice(0, 3)
    .map((c) => {
      const words = c.steps.filter((s) => !s.arrow);
      const last = words[words.length - 1];
      const subj = words.filter((s) => s.strong).pop()?.text || c.title;
      return { subject: subj, status: last?.text, tone: last?.tone || "neutral" };
    });
}
