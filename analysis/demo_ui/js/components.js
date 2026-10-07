// Renderers. One set of components for every scenario; scenario differences come from presentation.js
// (wording / hero kind) and from the trace data itself.

import { h, fmt } from "./dom.js";
import * as T from "./trace.js";
import {
  LANES,
  BASELINE_LANES,
  STORE_LABEL,
  TURN_KIND_LABEL,
  PLACEHOLDER_RE,
  placeholderFlag,
  laneOf,
  lanesOf,
  toneOf,
  statusTone,
  stageShort,
  flagLabel,
  flagTone,
} from "./presentation.js";

const { arr, obj } = T;

// ---------------------------------------------------------------- primitives

export const badge = (text, tone = "neutral", extra) =>
  h("span", { class: ["badge", `t-${tone}`, extra] }, String(text));

const pill = (passed) =>
  passed === true
    ? h("span", { class: "pill t-good" }, "PASS")
    : passed === false
      ? h("span", { class: "pill t-bad" }, "FAIL")
      : h("span", { class: "pill t-muted" }, "—");

const missing = (what) => h("div", { class: "missing" }, `Not in trace: ${what}`);

function section(id, title, sub, ...body) {
  return h(
    "section",
    { class: "panel", id },
    h("header", { class: "panel-head" }, h("h2", null, title), sub ? h("p", { class: "sub" }, sub) : null),
    ...body,
  );
}

/** Render trace text, styling placeholder tokens. Baseline: the trace is redacted, but the real store held the raw value. */
export function richText(text, mode, rawFlags) {
  if (typeof text !== "string") return h("span", { class: "dim" }, "—");
  const out = [];
  let last = 0;
  for (const m of text.matchAll(PLACEHOLDER_RE)) {
    out.push(text.slice(last, m.index));
    const flag = placeholderFlag(m[1]);
    if (mode === "baseline" && flag && rawFlags?.[flag]) {
      out.push(
        h(
          "span",
          { class: "ph ph-raw", title: "Stored verbatim by baseline (redacted only in this trace file)" },
          `raw ${m[1].startsWith("SECRET") ? "secret" : "email"}`,
        ),
      );
    } else {
      out.push(h("span", { class: "ph", title: "placeholder — the real value never enters this trace" }, m[0]));
    }
    last = m.index + m[0].length;
  }
  out.push(text.slice(last));
  return h("span", null, ...out);
}

export const bubble = (text, mode, rawFlags) => h("div", { class: "bubble" }, richText(text, mode, rawFlags));

export function flagChips(cfg, flags, { onlyTrue = true } = {}) {
  const entries = Object.entries(obj(flags)).filter(([, v]) => typeof v === "boolean");
  const shown = onlyTrue ? entries.filter(([, v]) => v) : entries;
  if (!shown.length) return h("span", { class: "dim" }, "none");
  return shown.map(([k, v]) =>
    h("span", { class: ["chip", v ? `t-${flagTone(cfg, k)}` : "t-off"] }, flagLabel(cfg, k)),
  );
}

// ---------------------------------------------------------------- header

export function renderHeader(run, scenarioIds, current, cfgOf, onSelect) {
  const idx = run.index;
  return h(
    "header",
    { class: "topbar" },
    h(
      "div",
      { class: "brand" },
      h("div", { class: "title" }, "OpenPoke ", h("span", { class: "dim" }, "·"), " Long-Term Memory"),
      h("div", { class: "subtitle" }, "Baseline vs LTM, rendered from demo traces"),
    ),
    h(
      "nav",
      { class: "tabs" },
      scenarioIds.map((id) =>
        h("button", { class: ["tab", id === current && "active"], onclick: () => onSelect(id) }, cfgOf(id).title),
      ),
    ),
    h(
      "div",
      { class: "runmeta" },
      idx
        ? [
            h("span", null, "gate "),
            pill(idx.gate_passed),
            h("span", { class: "dim mono" }, ` ${idx.extractor || ""} · ${fmt.shortId(idx.git_commit)}${idx.git_dirty ? "*" : ""}`),
            h("div", { class: "dim mono small" }, idx.generated_at || ""),
          ]
        : h("span", { class: "dim" }, "no index.json"),
    ),
  );
}

// ---------------------------------------------------------------- hero

export function renderHero(id, cfg, base, ltm) {
  const left = h("div", { class: "hero-col" }, h("div", { class: "lane-tag base" }, "Current OpenPoke"), heroBaseline(cfg, base, ltm));
  let right;
  if (!ltm) right = missing("ltm trace file");
  else if (cfg.hero === "chain") right = heroChain(cfg, ltm);
  else if (cfg.hero === "timeline") right = heroTimeline(cfg, ltm);
  else right = heroClauses(cfg, ltm);
  return h(
    "section",
    { class: "hero" },
    h("div", { class: "hero-q" }, h("h1", null, cfg.title), cfg.question ? h("p", null, cfg.question) : null),
    h(
      "div",
      { class: "hero-grid" },
      left,
      h("div", { class: "hero-col ltm" }, h("div", { class: "lane-tag ltm" }, "New LTM"), right),
    ),
  );
}

/** Baseline side: where the headline turn's content ended up, and what the headline probe sent to the model. */
function heroBaseline(cfg, base, ltm) {
  if (!base) return missing("baseline trace file");
  const ht = T.headlineTurn(ltm || base);
  const bt = ht ? T.alignTurns(base, ltm || base).find((r) => r.ltm === ht || r.base === ht)?.base : null;
  const obsTurn = bt || T.headlineTurn(base);
  const obs = obsTurn ? T.observationsForTurn(base, obsTurn.turn_index) : [];
  const probeTurns = T.turns(base).filter((x) => x.kind === "probe");
  const noDb = T.assertionById(base, "baseline.no_ltm_db");
  return h(
    "div",
    { class: "hero-base" },
    obsTurn ? bubble(obsTurn.text_safe, "baseline", mergedObsFlags(obs)) : null,
    obs.length
      ? presenceMatrix(cfg, obs)
      : missing("baseline_observations for this turn"),
    probeTurns.length
      ? h(
          "div",
          { class: "hero-probe" },
          h("div", { class: "label" }, "Reached the model at each probe"),
          probeTurns.map((p) => {
            const mc = T.modelContextForTurn(base, p.turn_index);
            return h(
              "div",
              { class: "rsum-row" },
              h("span", { class: "rsum-k" }, `“${p.text_safe}”`, h("div", { class: "dim small" }, p.probe || p.label || "probe")),
              mc ? h("span", { class: "chips big" }, flagChips(cfg, topFlags(mc))) : missing("model_context"),
            );
          }),
        )
      : null,
    noDb ? h("div", { class: "note" }, pill(noDb.passed), " ", noDb.name || noDb.id) : null,
  );
}

const topFlags = (mc) =>
  Object.fromEntries(Object.entries(obj(mc)).filter(([k, v]) => k.startsWith("contains_") && typeof v === "boolean").map(([k, v]) => [k.slice(9), v]));

function mergedObsFlags(obs) {
  const out = {};
  for (const o of obs) for (const [k, v] of Object.entries(obj(o.contains))) out[k] = out[k] || v === true;
  return out;
}

/** stores × flags, filled dot when the value is present in that store. */
function presenceMatrix(cfg, obs) {
  const flags = [...new Set(obs.flatMap((o) => Object.keys(obj(o.contains))))];
  return h(
    "table",
    { class: "matrix" },
    h("thead", null, h("tr", null, h("th", null, ""), flags.map((f) => h("th", null, flagLabel(cfg, f))))),
    h(
      "tbody",
      null,
      obs.map((o) =>
        h(
          "tr",
          null,
          h("th", null, STORE_LABEL[o.store] || o.store || o.node),
          flags.map((f) => {
            const v = obj(o.contains)[f];
            return h("td", null, h("span", { class: ["dot", v === true ? `t-${flagTone(cfg, f)}` : v === false ? "off" : "unk"] }));
          }),
        ),
      ),
    ),
  );
}

/** Conflict hero: supersession chains from the final memory snapshot + what the headline probe retrieved. */
function heroChain(cfg, ltm) {
  const snap = T.finalSnapshot(ltm);
  if (!snap) return missing("memory_state");
  const { chains, singles } = T.supersessionChains(snap);
  const probe = T.headlineProbe(ltm);
  const r = probe ? T.retrievalForTurn(ltm, probe.turn_index) : null;
  const cat = T.memoryCatalog(ltm);
  return h(
    "div",
    { class: "hero-ltm" },
    chains.length
      ? chains.map((c) =>
          h(
            "div",
            { class: "chain" },
            c.map((m, i) => [
              i ? h("div", { class: "chain-arrow" }, h("span", null, "superseded by"), h("span", { class: "arrow" }, "→")) : null,
              memNode(m),
            ]),
          ),
        )
      : h("div", { class: "chain" }, singles.map(memNode)),
    chains.length && singles.length ? h("div", { class: "chain" }, singles.map(memNode)) : null,
    r ? retrievalSummary(r, cat, probe) : null,
  );
}

function memNode(m) {
  return h(
    "div",
    { class: ["memnode", `s-${statusTone(m.status)}`] },
    h("div", { class: "memval" }, m.display ?? m.canonical_text ?? "∅"),
    badge(String(m.status || "?").toUpperCase(), statusTone(m.status), "lg"),
    h(
      "div",
      { class: "hist" },
      arr(m.status_history).map((s, i) => [i ? " → " : "", `${s.status} @t${s.turn_index ?? "?"}`]),
    ),
  );
}

export function retrievalSummary(r, cat, probeTurn) {
  const selected = arr(r.candidates).filter((c) => c.selected);
  return h(
    "div",
    { class: "rsum" },
    h("div", { class: "label" }, `Retrieval for “${probeTurn?.text_safe ?? "probe"}”`, h("span", { class: "dim" }, ` (${r.probe || r.label || "turn " + r.turn_index})`)),
    h(
      "div",
      { class: "rsum-row" },
      h("span", { class: "rsum-k" }, "Filtered before ranking"),
      arr(r.excluded_by_filters).length
        ? arr(r.excluded_by_filters).map((x) =>
            h("span", { class: "chip t-bad strike" }, x.display || T.memoryLabel(cat, x.memory_id), h("small", null, ` ${x.filter || ""}`)),
          )
        : h("span", { class: "dim" }, "nothing"),
    ),
    h(
      "div",
      { class: "rsum-row" },
      h("span", { class: "rsum-k" }, "Retrieved"),
      selected.length
        ? selected.map((c) => h("span", { class: "chip t-good" }, c.display || T.memoryLabel(cat, c.memory_id), h("small", null, ` ${fmt.num(c.total)}`)))
        : h("span", { class: "chip t-off" }, `${arr(r.candidates).length} candidates → no block`),
    ),
  );
}

/** Privacy / selective hero: the headline message split into clauses, each clause's decision, and what survives. */
function heroClauses(cfg, ltm) {
  const t = T.headlineTurn(ltm);
  if (!t) return missing("message turns");
  const evs = T.eventsForTurn(ltm, t.turn_index);
  const rows = T.groupTurnEvents(evs).filter((r) => r.kind === "clause" && !r.duplicate);
  const scrub = evs.find((e) => e.stage === "ingress.scrub");
  const cat = T.memoryCatalog(ltm);
  const snap = T.finalSnapshot(ltm);
  const outcomes = arr(t.outcomes);

  const clauseRows = (rows.length ? rows : outcomes.map((o) => ({ clause_index: o.clause_index, events: [], label: o.label })))
    .slice()
    .sort((a, b) => (a.clause_index ?? 0) - (b.clause_index ?? 0))
    .map((r) => {
      const o =
        outcomes.find((x) => r.candidate_id && x.candidate_id === r.candidate_id && !x.duplicate) ||
        outcomes.find((x) => x.clause_index === r.clause_index && !x.duplicate) ||
        null;
      const cls = r.events.find((e) => e.stage === "privacy.classify");
      const clauseEv = r.events.find((e) => e.stage === "extract.clause");
      const detectors = arr(obj(cls?.detail).detectors);
      const classTxt = detectors.length ? detectors.join(", ") : obj(cls?.detail).sensitivity || (clauseEv?.decision === "NO_CANDIDATE" ? "—" : "none");
      const decision = o?.decision || cls?.decision || clauseEv?.decision;
      const mem = o?.memory_id ? cat.get(o.memory_id) : null;
      const finalMem = o?.memory_id ? arr(snap?.memories).find((m) => m.id === o.memory_id) : null;
      return h(
        "div",
        { class: ["clause", `t-${toneOf(decision)}-edge`] },
        h("div", { class: "clause-text" }, richText(r.text ?? o?.label ?? "", "ltm")),
        h("div", { class: "clause-class" }, h("span", { class: "k" }, "class"), classTxt),
        h("div", { class: "clause-dec" }, badge(decision || "?", toneOf(decision), "lg")),
        h(
          "div",
          { class: "clause-res" },
          o?.reason && toneOf(decision) !== "good" ? h("div", { class: "mono" }, o.reason) : null,
          mem
            ? h("div", null, h("b", null, mem.display || mem.canonical_text), " ", badge(String(finalMem?.status || mem.status || "?").toUpperCase(), statusTone(finalMem?.status || mem.status)))
            : toneOf(decision) === "good"
              ? null
              : h("div", { class: "dim" }, "nothing written"),
        ),
      );
    });

  const active = arr(snap?.memories).filter((m) => m.status === "active");
  const probeRetrievals = T.turns(ltm)
    .filter((x) => x.kind === "probe")
    .map((p) => ({ p, r: T.retrievalForTurn(ltm, p.turn_index) }))
    .filter((x) => x.r);

  return h(
    "div",
    { class: "hero-ltm" },
    h(
      "div",
      { class: "msg-line" },
      bubble(t.text_safe, "ltm"),
      scrub ? h("div", { class: "scrubnote" }, badge(scrub.decision || "?", toneOf(scrub.decision)), " ingress scrub ", detectorText(scrub)) : null,
    ),
    h("div", { class: "clauses" }, clauseRows),
    h(
      "div",
      { class: "durable" },
      h("span", { class: "rsum-k" }, "Durable memory now"),
      active.length ? active.map((m) => h("span", { class: "chip t-good" }, m.display || m.canonical_text)) : h("span", { class: "dim" }, "empty"),
    ),
    probeRetrievals.map(({ p, r }) =>
      h(
        "div",
        { class: "rsum-row" },
        h("span", { class: "rsum-k" }, `“${p.text_safe}”`, h("div", { class: "dim small" }, p.probe || p.label || "probe")),
        arr(r.candidates).filter((c) => c.selected).length
          ? arr(r.candidates)
              .filter((c) => c.selected)
              .map((c) => h("span", { class: "chip t-good" }, c.display || T.memoryLabel(cat, c.memory_id), h("small", null, ` score ${fmt.num(c.total)}`)))
          : h("span", { class: "chip t-off" }, `${arr(r.candidates).length} candidates → no block`),
      ),
    ),
  );
}

export function detectorText(e) {
  const d = arr(obj(e?.detail).detectors);
  if (!d.length) return h("span", { class: "dim" }, "nothing detected");
  return d.map((x) => (typeof x === "string" ? x : `${x.type}×${x.count ?? 1}`)).join(", ");
}

// ---------------------------------------------------------------- forget timeline

const ms = (ts) => {
  const v = Date.parse(ts);
  return Number.isFinite(v) ? v : null;
};

/** Build timeline lanes + ordered milestones purely from events, snapshots and assertions. */
export function buildTimeline(ltm, cfg) {
  const evs = T.pipeline(ltm).filter((e) => ms(e.ts) != null);
  const byTrace = new Map();
  for (const e of evs.slice().sort((a, b) => (a.seq ?? 0) - (b.seq ?? 0))) {
    if (!byTrace.has(e.trace_id)) byTrace.set(e.trace_id, []);
    byTrace.get(e.trace_id).push(e);
  }
  const cat = T.memoryCatalog(ltm);
  const lanes = [];
  const steps = [];
  const turnText = (i) => T.turnByIndex(ltm, i)?.text_safe;

  for (const [tid, list] of byTrace) {
    const ti = list[0]?.turn_index;
    const ingest = list.find((e) => e.stage === "ingest");
    const observed = obj(ingest?.detail).observed_at || ingest?.ts;
    let dup = false;
    const primary = [];
    const duplicate = [];
    for (const e of list) {
      if (e.stage === "extract" && obj(e.detail).duplicate === true) dup = true;
      (dup ? duplicate : primary).push(e);
    }
    const writes = primary.filter((e) => ["consolidate", "fence_drop"].includes(e.stage));
    const forgets = primary.filter((e) => e.stage.startsWith("forget."));
    if (writes.length) {
      lanes.push({
        key: tid + ":w",
        label: `Ingest job · turn ${ti}`,
        start: observed,
        points: writes.map((e) => ({ ts: e.ts, text: `${e.decision}${e.memory_id ? " → " + (T.memoryLabel(cat, e.memory_id)) : ""}`, tone: toneOf(e.decision) })),
      });
      for (const e of writes)
        steps.push({ ts: e.ts, tone: toneOf(e.decision), title: e.decision === "INSERT" ? "Memory written → ACTIVE" : `${e.stage} ${e.decision}`, body: `${T.memoryLabel(cat, e.memory_id)} · ${obj(e.detail).slot_key || ""}`, src: "event" });
    }
    if (forgets.length) {
      const apply = forgets.find((e) => e.stage === "forget.apply");
      const tomb = obj(apply?.detail).tombstone_at;
      lanes.push({
        key: tid + ":f",
        label: `Forget · turn ${ti}`,
        start: observed,
        points: forgets.map((e) => ({ ts: e.ts, text: `${stageShort(e.stage)} ${e.decision || ""}`, tone: toneOf(e.decision) })),
        wall: tomb || apply?.ts,
      });
      steps.push({ ts: observed, tone: "neutral", title: "Forget request", body: `“${turnText(ti) ?? ""}”`, src: "event" });
      for (const e of forgets) {
        const d = obj(e.detail);
        steps.push({
          ts: e.ts,
          tone: toneOf(e.decision),
          title: e.stage === "forget.apply" ? `DELETE ${d.count ?? arr(d.memory_ids).length} memory` : `${stageShort(e.stage)} → ${e.decision || ""}`,
          body: e.stage === "forget.apply" ? `${d.slot_key || ""} ${arr(d.memory_ids).map((id) => T.memoryLabel(cat, id)).join(", ")}` : d.kind || "",
          src: "event",
        });
      }
    }
    if (duplicate.length) {
      const fence = duplicate.find((e) => e.stage === "fence_drop");
      const wake = duplicate[0];
      const commit = duplicate.find((e) => e.stage === "consolidate");
      const end = fence || commit;
      const refs = obj(fence?.refs);
      lanes.push({
        key: tid + ":d",
        label: `Duplicate job · turn ${ti} (delayed)`,
        start: refs.job_observed_at || observed,
        sleepUntil: wake?.ts,
        points: [
          { ts: wake?.ts, text: "wakes", tone: "neutral" },
          end ? { ts: end.ts, text: `${end.stage === "fence_drop" ? "FENCE_DROP" : end.decision} ${arr(end.reason_codes).join(",")}`, tone: toneOf(end.stage === "fence_drop" ? "FENCE_DROP" : end.decision) } : null,
        ].filter(Boolean),
        dup: true,
      });
      steps.push({ ts: wake?.ts, tone: "warn", title: "Delayed duplicate writer wakes", body: `same turn ${ti}, observed_at ${fmt.time(refs.job_observed_at || observed)}`, src: "event" });
      if (fence)
        steps.push({
          ts: fence.ts,
          tone: "bad",
          title: `FENCE_DROP · ${arr(fence.reason_codes).join(", ") || fence.decision}`,
          body: fence.reason || `job ${fmt.time(refs.job_observed_at)} ≤ tombstone ${fmt.time(refs.tombstone_at)}`,
          src: "event",
        });
      else if (commit) steps.push({ ts: commit.ts, tone: toneOf(commit.decision), title: `Duplicate committed: ${commit.decision}`, body: "", src: "event" });
    }
  }

  // Snapshot-derived milestones: purge + tombstones (first snapshot where they appear).
  const ev = cfg.timelineEvidence || {};
  let purged = false;
  let tombSeen = new Set();
  for (const snap of T.snapshots(ltm)) {
    for (const m of arr(snap.memories)) {
      if (!purged && m.status === "deleted") {
        purged = true;
        steps.push({
          ts: m.deleted_at,
          tone: "accent",
          title: `Content purged · canonical_text = ${m.canonical_text == null ? "NULL" : "still set"}`,
          body: `${T.memoryLabel(cat, m.id)} → status ${m.status}`,
          src: `memory_state after turn ${snap.after_turn}`,
          assertion: ev.purge,
          fromSnapshot: true,
        });
        steps.push({ ts: m.deleted_at, tone: "accent", title: "Index row removed (FTS)", body: "", src: "assertion", assertion: ev.index, needsAssertion: true, fromSnapshot: true });
      }
    }
    for (const tb of arr(snap.tombstones)) {
      const k = `${tb.scope}|${tb.slot_key}`;
      if (tombSeen.has(k)) continue;
      tombSeen.add(k);
      steps.push({ ts: tb.deleted_at, tone: "bad", title: `Tombstone (${tb.scope || "?"})`, body: `${tb.slot_key || ""} · ${tb.reason || ""}`, src: `memory_state after turn ${snap.after_turn}`, assertion: ev.tombstone, fromSnapshot: true });
    }
  }

  // Probes after the forget: retrieval outcome.
  for (const t of T.turns(ltm).filter((x) => x.kind === "probe")) {
    const r = T.retrievalForTurn(ltm, t.turn_index);
    const sel = T.eventsForTurn(ltm, t.turn_index).find((e) => e.stage === "retrieve.select");
    if (!r) continue;
    const n = arr(r.candidates).length;
    steps.push({
      ts: sel?.ts,
      tone: n ? "warn" : "good",
      title: `Probe (${t.probe || t.label}): ${n} candidates${r.ltm_block ? "" : " → no LTM block"}`,
      body: `“${t.text_safe}”`,
      src: "retrieval",
    });
  }

  // State changes committed inside a forget transaction are reported by the forget.apply event emitted right
  // after commit; order them after that event so the story reads request → delete → purge → tombstone.
  const applyAt = new Map(
    T.eventsByStage(ltm, "forget.apply")
      .filter((e) => obj(e.detail).tombstone_at)
      .map((e) => [obj(e.detail).tombstone_at, e.ts]),
  );
  steps.forEach((s, i) => {
    s.order = i;
    s.sortTs = s.fromSnapshot && applyAt.has(s.ts) ? applyAt.get(s.ts) : s.ts;
  });
  steps.sort((a, b) => (ms(a.sortTs) ?? Infinity) - (ms(b.sortTs) ?? Infinity) || a.order - b.order);
  const firstPoint = (l) => Math.min(...l.points.map((p) => ms(p.ts)).filter((v) => v != null));
  lanes.sort((a, b) => firstPoint(a) - firstPoint(b));
  return { lanes, steps };
}

/** Merge points that would overlap on screen (events milliseconds apart) into one labelled marker. */
function clusterPoints(points, pct) {
  const pts = points.map((p) => ({ ...p, x: pct(p.ts) })).filter((p) => p.x != null).sort((a, b) => a.x - b.x);
  const out = [];
  for (const p of pts) {
    const last = out[out.length - 1];
    if (last && p.x - last.x < 8) {
      last.text += " · " + p.text;
      if (p.tone === "bad" || last.tone === "neutral") last.tone = p.tone;
      last.x = p.x;
    } else out.push({ ...p });
  }
  return out;
}

export function heroTimeline(cfg, ltm) {
  const { lanes, steps } = buildTimeline(ltm, cfg);
  if (!lanes.length) return missing("timestamped write / forget events");
  const times = lanes.flatMap((l) => [l.start, l.sleepUntil, l.wall, ...l.points.map((p) => p.ts)]).map(ms).filter((v) => v != null);
  const t0 = Math.min(...times);
  const t1 = Math.max(...times);
  const span = Math.max(1, t1 - t0);
  const pct = (ts) => (ms(ts) == null ? null : 3 + ((ms(ts) - t0) / span) * 94);
  const wall = lanes.find((l) => l.wall)?.wall;
  const wallX = pct(wall);
  const assertionsById = new Map(T.assertions(ltm).map((a) => [a.id, a]));

  return h(
    "div",
    { class: "hero-ltm" },
    h(
      "div",
      { class: "race" },
      wallX != null ? h("div", { class: "race-overlay" }, h("div", { class: "wall", style: { left: wallX + "%" } }, h("span", null, "tombstone ", fmt.time(wall)))) : null,
      lanes.map((l) => {
        const sx = pct(l.start);
        const wx = pct(l.sleepUntil);
        return h(
          "div",
          { class: ["race-lane", l.dup && "dup"] },
          h("div", { class: "race-label" }, l.label),
          h(
            "div",
            { class: "race-track" },
            sx != null ? h("div", { class: "race-start", style: { left: sx + "%" }, title: "observed_at " + l.start }) : null,
            sx != null && wx != null ? h("div", { class: "race-sleep", style: { left: sx + "%", width: Math.max(0.5, wx - sx) + "%" } }, h("span", null, `sleeping ${((ms(l.sleepUntil) - ms(l.start)) / 1000).toFixed(1)} s`)) : null,
            clusterPoints(l.points, pct).map((c) =>
              h(
                "div",
                { class: ["race-pt", `t-${c.tone}`, c.x > 70 ? "lab-r" : c.x < 25 ? "lab-l" : null], style: { left: c.x + "%" } },
                h("span", null, c.text),
              ),
            ),
          ),
        );
      }),
      h("div", { class: "race-axis" }, h("span", null, fmt.time(new Date(t0).toISOString())), h("span", null, `+${(span / 1000).toFixed(2)} s`)),
    ),
    h(
      "ol",
      { class: "steps" },
      steps.map((s) => {
        const a = s.assertion ? assertionsById.get(s.assertion) : null;
        if (s.needsAssertion && !a) return null;
        return h(
          "li",
          { class: `t-${s.tone}-edge` },
          h("span", { class: "step-t mono" }, s.ts ? `+${(((ms(s.ts) ?? t0) - t0) / 1000).toFixed(3)}s` : ""),
          h("span", { class: "step-title" }, s.title),
          s.body ? h("span", { class: "step-body" }, s.body) : null,
          a ? h("span", { class: "step-ev" }, pill(a.passed), " ", h("span", { class: "mono" }, a.id)) : h("span", { class: "step-ev dim" }, s.src),
        );
      }),
    ),
  );
}

// ---------------------------------------------------------------- comparison

export function renderComparison(cfg, base, ltm) {
  const rows = T.alignTurns(base, ltm);
  const lCat = ltm ? T.memoryCatalog(ltm) : new Map();
  const grid = h("div", { class: "cmp" });
  grid.append(h("div", { class: "cmp-h base" }, "Current OpenPoke"), h("div", { class: "cmp-h ltm" }, "New LTM"));

  for (const row of rows) {
    const any = row.ltm || row.base;
    if (!T.isMessageTurn(any)) {
      const label = TURN_KIND_LABEL[any.kind] || any.kind;
      const hook = any.hook ? Object.entries(any.hook).map(([k, v]) => `${k}=${v}`).join(", ") : "";
      grid.append(
        h(
          "div",
          { class: "cmp-divider" },
          h("span", null, label, hook ? h("span", { class: "mono dim" }, ` (${hook})`) : null),
          row.base?.skipped ? h("span", { class: "dim" }, ` — baseline: ${row.base.skipped}`) : null,
        ),
      );
      continue;
    }
    grid.append(cmpBaseCell(cfg, base, row.base), cmpLtmCell(cfg, ltm, row.ltm, lCat));
  }

  // Durable state row
  grid.append(
    h(
      "div",
      { class: "cmp-cell base final" },
      h("div", { class: "label" }, "Durable long-term memory"),
      (() => {
        const a = base && T.assertionById(base, "baseline.no_ltm_db");
        return a
          ? h("div", null, a.passed ? h("b", null, "None — no memory store exists") : h("b", null, "Unexpected memory store"), h("div", { class: "dim small" }, a.id, " ", pill(a.passed)))
          : h("div", { class: "dim" }, "memory_state: ", base ? `${arr(base.memory_state).length} snapshots` : "—");
      })(),
    ),
    h(
      "div",
      { class: "cmp-cell ltm final" },
      h("div", { class: "label" }, "Durable long-term memory"),
      ltm ? stateChips(T.finalSnapshot(ltm), lCat) : missing("ltm trace"),
    ),
  );
  return section("comparison", "Same inputs, two systems", "Each row is the same user message sent to both. Left: where it ended up. Right: what the LTM pipeline decided.", grid);
}

export function stateChips(snap, cat) {
  if (!snap) return missing("memory_state");
  const mems = arr(snap.memories);
  return h(
    "div",
    { class: "chips" },
    mems.length
      ? mems.map((m) =>
          h(
            "span",
            { class: ["chip", `t-${statusTone(m.status)}`, m.status === "superseded" && "strike"] },
            m.display ?? T.memoryLabel(cat, m.id),
            h("small", null, ` ${String(m.status || "").toUpperCase()}`),
          ),
        )
      : h("span", { class: "dim" }, "empty"),
    arr(snap.tombstones).map((t) => h("span", { class: "chip t-bad" }, `tombstone ${t.scope || ""}`, h("small", null, ` ${t.slot_key || ""}`))),
  );
}

function cmpBaseCell(cfg, base, t) {
  if (!t) return h("div", { class: "cmp-cell base" }, missing("matching baseline turn"));
  const obs = T.observationsForTurn(base, t.turn_index);
  const mc = t.kind === "probe" ? T.modelContextForTurn(base, t.turn_index) : null;
  return h(
    "div",
    { class: "cmp-cell base" },
    t.kind === "probe" ? h("div", { class: "kind" }, "probe · ", t.probe || t.label || "") : null,
    bubble(t.text_safe, "baseline", mergedObsFlags(obs)),
    obs.length
      ? h(
          "div",
          { class: "stores" },
          obs.map((o) => h("div", { class: "store" }, h("span", { class: "store-k" }, STORE_LABEL[o.store] || o.store || o.node), flagChips(cfg, o.contains))),
        )
      : null,
    mc ? modelContextView(cfg, mc) : null,
  );
}

function cmpLtmCell(cfg, ltm, t, cat) {
  if (!t) return h("div", { class: "cmp-cell ltm" }, missing("matching ltm turn"));
  const evs = T.eventsForTurn(ltm, t.turn_index);
  const scrub = evs.find((e) => e.stage === "ingress.scrub");
  const outs = arr(t.outcomes);
  const showOuts = t.kind === "probe" ? [] : outs;
  const r = t.kind === "probe" ? T.retrievalForTurn(ltm, t.turn_index) : null;
  const mc = t.kind === "probe" ? T.modelContextForTurn(ltm, t.turn_index) : null;
  return h(
    "div",
    { class: "cmp-cell ltm" },
    t.kind === "probe" ? h("div", { class: "kind" }, "probe · ", t.probe || t.label || "") : null,
    bubble(t.text_safe, "ltm"),
    scrub && scrub.decision && scrub.decision !== "CLEAN" ? h("div", { class: "scrubnote" }, badge(scrub.decision, toneOf(scrub.decision)), " before persistence: ", detectorText(scrub)) : null,
    showOuts.length
      ? h(
          "div",
          { class: "outs" },
          showOuts.map((o) =>
            h(
              "div",
              { class: "out" },
              h("span", { class: "out-label" }, o.label || "—"),
              badge(o.decision || "?", toneOf(o.decision)),
              o.result && o.result !== o.decision ? badge(o.result, toneOf(o.result)) : null,
              o.duplicate ? h("span", { class: "chip t-warn" }, "duplicate job") : null,
              h(
                "span",
                { class: "out-why" },
                o.supersedes ? `replaces ${T.memoryLabel(cat, o.supersedes)}` : toneOf(o.decision) === "good" && !o.duplicate ? "" : o.reason || "",
              ),
            ),
          ),
        )
      : t.kind !== "probe"
        ? h("div", { class: "dim small" }, "no memory outcomes")
        : null,
    r ? retrievalSummary(r, cat, null) : null,
    mc ? modelContextView(cfg, mc) : null,
  );
}

const SECTION_LABEL = {
  conversation_history: "conversation history",
  long_term_memory: "long-term memory block",
  new_user_message: "new message",
  active_agents: "active agents",
  memory_notice: "memory notice",
};

export function modelContextView(cfg, mc) {
  const secs = Object.entries(obj(mc.sections));
  const shown = secs.filter(
    ([name, s]) => name === "long_term_memory" || Object.entries(obj(s)).some(([k, v]) => k.startsWith("contains_") && v === true),
  );
  return h(
    "div",
    { class: "mctx" },
    h("div", { class: "label" }, "Reached the model"),
    shown.length ? null : h("div", { class: "dim" }, "none of the tracked values"),
    secs
      .filter(([name, s]) => name === "long_term_memory" || Object.entries(obj(s)).some(([k, v]) => k.startsWith("contains_") && v === true))
      .map(([name, s]) =>
        h(
          "div",
          { class: "mctx-row" },
          h("span", { class: "mctx-k" }, SECTION_LABEL[name] || name),
          obj(s).present === false ? h("span", { class: "dim" }, "absent") : flagChips(cfg, Object.fromEntries(Object.entries(obj(s)).filter(([k]) => k.startsWith("contains_")).map(([k, v]) => [k.slice(9), v]))),
        ),
      ),
    mc.note ? h("div", { class: "caveat" }, "caveat: ", mc.note) : null,
  );
}

// ---------------------------------------------------------------- pipeline

export function renderPipeline(cfg, base, ltm, state, rerender) {
  if (!ltm) return section("pipeline", "LTM pipeline", null, missing("ltm trace"));
  const msgTurns = T.turns(ltm).filter(T.isMessageTurn);
  const sel = state.pipelineTurn ?? T.headlineTurn(ltm)?.turn_index ?? msgTurns[0]?.turn_index;
  const t = T.turnByIndex(ltm, sel);
  const evs = T.eventsForTurn(ltm, sel);
  const rows = T.groupTurnEvents(evs);
  const cat = T.memoryCatalog(ltm);
  const fired = new Set(evs.flatMap(lanesOf));
  const bt = base ? T.alignTurns(base, ltm).find((r) => r.ltm === t)?.base : null;

  const chooser = h(
    "div",
    { class: "turnpick" },
    msgTurns.map((x) =>
      h(
        "button",
        { class: ["tp", x.turn_index === sel && "active"], onclick: () => ((state.pipelineTurn = x.turn_index), rerender()) },
        h("span", { class: "mono dim" }, `t${x.turn_index} `),
        x.text_safe.length > 46 ? x.text_safe.slice(0, 44) + "…" : x.text_safe,
      ),
    ),
  );

  const baseStrip = bt
    ? h(
        "div",
        { class: "bstrip" },
        h("div", { class: "lane-tag base" }, "Baseline path"),
        h(
          "div",
          { class: "bflow" },
          BASELINE_LANES.map((l, i) => {
            const on = arr(bt.path).includes(l.id);
            const o = T.observationsForTurn(base, bt.turn_index).find((x) => x.node === l.id);
            return [
              i ? h("span", { class: "flow-arrow" }, "→") : null,
              h("div", { class: ["bnode", on ? "on" : "off"] }, h("div", null, l.label), o ? h("div", { class: "chips" }, flagChips(cfg, o.contains)) : null),
            ];
          }),
        ),
      )
    : null;

  const table = h(
    "div",
    { class: "pipe", style: { gridTemplateColumns: `minmax(180px, 1.3fr) repeat(${LANES.length}, minmax(0, 1fr))` } },
    h("div", { class: "pipe-h corner" }, h("div", { class: "lane-tag ltm" }, "LTM pipeline")),
    LANES.map((l, i) =>
      h("div", { class: ["pipe-h", fired.has(l.id) ? "on" : "off"] }, l.label, i < LANES.length - 1 ? h("span", { class: "flow-arrow" }, "→") : null),
    ),
    rows.map((r) => [
      h(
        "div",
        { class: ["pipe-row-h", r.duplicate && "dup"] },
        r.kind === "turn"
          ? h("div", null, h("b", null, r.duplicate ? "Duplicate ingest job" : "Turn"), h("div", { class: "dim small" }, r.duplicate ? "same turn, delayed" : "message-level"))
          : h("div", null, h("div", { class: "clause-mini" }, richText(r.text || r.label || r.candidate_id || "clause", "ltm")), h("div", { class: "dim small mono" }, r.candidate_id || `clause ${r.clause_index ?? "?"}`, r.duplicate ? " · duplicate job" : "")),
      ),
      LANES.map((l) => {
        const cell = r.events.filter((e) => lanesOf(e).includes(l.id));
        return h(
          "div",
          { class: ["pipe-cell", !fired.has(l.id) && "off"] },
          cell.map((e) => (l.id === "store" && laneOf(e) !== "store" ? commitChip(e, ltm, cat) : eventChip(e, cat))),
        );
      }),
    ]),
  );

  return section(
    "pipeline",
    "LTM pipeline",
    "Privacy → Extract → Policy → Consolidate → Store → Retrieve → Agent. Every chip is one trace event for the selected turn; grey columns did not fire.",
    chooser,
    baseStrip,
    table,
  );
}

/** Store-column view of a committing consolidate event: the row's status as recorded by that trace. */
export function commitChip(e, ltm, cat) {
  const m = cat.get(e.memory_id);
  const h0 = arr(m?.status_history).find((x) => x.trace_id === e.trace_id);
  const st = h0?.status;
  return h(
    "div",
    { class: ["ev", st && `t-${statusTone(st)}-edge`], title: `row written by ${e.stage} ${e.decision}` },
    h("div", { class: "ev-top" }, h("span", { class: "ev-stage" }, "row written"), st ? badge(String(st).toUpperCase(), statusTone(st)) : null),
    h("div", { class: "ev-info" }, `${T.memoryLabel(cat, e.memory_id)} · ${fmt.shortId(e.memory_id)}`),
  );
}

export function eventChip(e, cat) {
  const d = obj(e.detail);
  let info = "";
  switch (e.stage) {
    case "ingress.scrub":
    case "privacy.scrub":
      info = arr(d.detectors).map((x) => (typeof x === "string" ? x : `${x.type}×${x.count ?? 1}`)).join(", ") || "clean";
      break;
    case "privacy.classify":
      info = [arr(d.detectors).join(", "), d.sensitivity].filter(Boolean).join(" · ");
      break;
    case "extract":
      info = d.n_candidates != null ? `${d.n_candidates} candidate${d.n_candidates === 1 ? "" : "s"}` : "";
      break;
    case "extract.clause":
      info = e.reason || d.label || "";
      break;
    case "policy":
      info = d.importance != null ? `imp ${fmt.num(d.importance)} · conf ${fmt.num(d.confidence)}` : arr(e.reason_codes).join(", ");
      break;
    case "consolidate":
      info = `${d.display || T.memoryLabel(cat, e.memory_id)} · ${arr(e.reason_codes).join(", ")}`;
      break;
    case "fence_drop":
      info = arr(e.reason_codes).join(", ");
      break;
    case "forget.detect":
      info = d.kind || "";
      break;
    case "forget.apply":
      info = `${d.count ?? arr(d.memory_ids).length} × ${d.slot_key || ""}`;
      break;
    case "retrieve.query":
      info = arr(d.families).join(", ") || `${arr(d.terms).length} terms`;
      break;
    case "retrieve.filter":
      info = `${d.display || T.memoryLabel(cat, e.memory_id)} · ${d.filter || ""}`;
      break;
    case "retrieve.candidates":
      info = `${d.total ?? "?"} found`;
      break;
    case "retrieve.rank":
      info = `${d.display || T.memoryLabel(cat, e.memory_id)} · ${fmt.num(d.total ?? obj(e.scores).total)}`;
      break;
    case "retrieve.select":
      info = `${arr(d.selected).length} selected · ${d.tokens ?? 0} tok`;
      break;
    case "privacy.egress":
      info = `${d.count ?? "?"} items`;
      break;
    case "prompt.render":
      info = `${d.alias || ""} ${d.tokens != null ? d.tokens + " tok" : ""}`;
      break;
    default:
      info = arr(e.reason_codes).join(", ");
  }
  const dec = e.decision;
  return h(
    "div",
    { class: ["ev", dec && `t-${toneOf(dec)}-edge`], title: `${e.stage} · node ${e.node}${e.reason ? "\n" + e.reason : ""}` },
    h("div", { class: "ev-top" }, h("span", { class: "ev-stage" }, stageShort(e.stage)), dec ? badge(dec, toneOf(dec)) : null),
    info ? h("div", { class: "ev-info" }, info) : null,
  );
}

// ---------------------------------------------------------------- memory inspector

export function renderMemoryInspector(cfg, ltm, state, rerender) {
  if (!ltm) return section("memory", "Memory inspector", null, missing("ltm trace"));
  const snaps = T.snapshots(ltm);
  if (!snaps.length) return section("memory", "Memory inspector", null, missing("memory_state"));
  const si = Math.min(state.snapshot ?? snaps.length - 1, snaps.length - 1);
  const snap = snaps[si];
  const cat = T.memoryCatalog(ltm);
  const policyFor = (m) => {
    const created = arr(m.status_history)[0];
    const commit = T.pipeline(ltm).find((e) => e.memory_id === m.id && (e.stage === "consolidate" || e.stage === "store"));
    const pol = commit ? T.pipeline(ltm).find((e) => e.stage === "policy" && e.trace_id === commit.trace_id && e.candidate_id === commit.candidate_id) : null;
    return { created, commit, pol };
  };

  const picker = h(
    "div",
    { class: "turnpick" },
    h("span", { class: "dim" }, "State after: "),
    snaps.map((s, i) => {
      const t = T.turnByIndex(ltm, s.after_turn);
      return h(
        "button",
        { class: ["tp", i === si && "active"], title: t?.text_safe || t?.kind || "", onclick: () => ((state.snapshot = i), rerender()) },
        `t${s.after_turn}`,
        h("span", { class: "dim" }, ` ${t?.kind === "probe" ? "probe" : t?.kind || ""}`),
      );
    }),
  );

  const mems = arr(snap.memories);
  const cards = mems.length
    ? mems.map((m) => {
        const { created, commit, pol } = policyFor(m);
        const srcTurn = created ? T.turnByIndex(ltm, created.turn_index) : null;
        const ib = obj(obj(pol?.detail).importance_breakdown);
        return h(
          "div",
          { class: ["memcard", `s-${statusTone(m.status)}`], "data-mem": m.id },
          h(
            "div",
            { class: "memcard-h" },
            h("div", { class: "memval" }, m.display ?? h("span", { class: "dim" }, cat.get(m.id)?.display ? `(was ${cat.get(m.id).display})` : "∅")),
            badge(String(m.status || "?").toUpperCase(), statusTone(m.status), "lg"),
          ),
          h("div", { class: "canon" }, m.canonical_text == null ? h("span", { class: "nullv" }, "canonical_text = NULL (purged)") : `“${m.canonical_text}”`),
          kv([
            ["type", m.memory_type],
            ["slot", h("span", { class: "mono" }, m.slot_key ?? "—")],
            ["confidence", fmt.num(m.confidence)],
            [
              "importance",
              h(
                "span",
                null,
                fmt.num(m.importance),
                Object.keys(ib).length ? h("span", { class: "dim" }, "  = " + Object.entries(ib).map(([k, v]) => `${k} ${fmt.num(v)}`).join(" + ")) : null,
              ),
            ],
            ["source", srcTurn ? h("span", null, `t${srcTurn.turn_index} `, h("i", null, `“${srcTurn.text_safe}”`)) : "—"],
            ["observed_at", h("span", { class: "mono" }, m.observed_at ?? "—")],
            ["history", arr(m.status_history).map((s, i) => [i ? " → " : "", badge(s.status, statusTone(s.status)), h("span", { class: "dim" }, ` t${s.turn_index ?? "?"}`)])],
            m.supersedes_id ? ["supersedes", T.memoryLabel(cat, m.supersedes_id)] : null,
            m.superseded_by_id ? ["superseded by", T.memoryLabel(cat, m.superseded_by_id)] : null,
            m.contests_id ? ["contests", T.memoryLabel(cat, m.contests_id)] : null,
            m.deleted_at ? ["deleted_at", h("span", { class: "mono" }, m.deleted_at)] : null,
            m.expires_at ? ["expires_at", h("span", { class: "mono" }, m.expires_at)] : null,
            ["id", h("span", { class: "mono dim" }, fmt.shortId(m.id))],
            commit ? ["written by", h("span", { class: "mono dim" }, `${commit.stage} ${commit.decision} · ${fmt.shortId(commit.trace_id)}`)] : null,
          ]),
        );
      })
    : [h("div", { class: "dim big" }, "No memories")];

  const extras = h(
    "div",
    { class: "mem-extras" },
    arr(snap.edges).length
      ? h("div", null, h("div", { class: "label" }, "Edges"), arr(snap.edges).map((e) => h("div", { class: "mono" }, `${T.memoryLabel(cat, e.from)} —${e.kind}→ ${T.memoryLabel(cat, e.to)}`)))
      : null,
    arr(snap.deleted).length
      ? h("div", null, h("div", { class: "label" }, "Deleted rows (metadata only)"), arr(snap.deleted).map((d) => h("div", { class: "mono" }, `${T.memoryLabel(cat, d.id)} · ${d.slot_key || ""} · ${d.deleted_at || ""}`)))
      : null,
    arr(snap.tombstones).length
      ? h(
          "div",
          null,
          h("div", { class: "label" }, "Tombstones"),
          arr(snap.tombstones).map((t) => h("div", { class: "mono" }, badge(t.scope || "?", "bad"), ` ${t.slot_key || ""} · ${t.reason || ""} · ${t.deleted_at || ""}`)),
        )
      : null,
  );

  return section("memory", "Memory inspector", "Sanitised LTM state as captured after each turn.", picker, h("div", { class: "memgrid" }, cards), extras);
}

export function kv(pairs) {
  return h(
    "dl",
    { class: "kv" },
    pairs.filter(Boolean).map(([k, v]) => [h("dt", null, k), h("dd", null, v ?? "—")]),
  );
}

// ---------------------------------------------------------------- retrieval inspector

export function renderRetrievalInspector(cfg, base, ltm, state, rerender) {
  if (!ltm) return section("retrieval", "Retrieval inspector", null, missing("ltm trace"));
  const rs = T.retrievals(ltm);
  if (!rs.length) return section("retrieval", "Retrieval inspector", null, missing("retrieval[]"));
  const cat = T.memoryCatalog(ltm);
  const defaultIdx = Math.max(0, rs.findIndex((r) => r.turn_index === T.headlineProbe(ltm)?.turn_index));
  const ri = Math.min(state.retrieval ?? defaultIdx, rs.length - 1);
  const r = rs[ri];
  const t = T.turnByIndex(ltm, r.turn_index);

  const picker = h(
    "div",
    { class: "turnpick" },
    rs.map((x, i) => {
      const tt = T.turnByIndex(ltm, x.turn_index);
      return h(
        "button",
        { class: ["tp", i === ri && "active", tt?.kind !== "probe" && "minor"], onclick: () => ((state.retrieval = i), rerender()) },
        h("span", { class: "mono dim" }, `t${x.turn_index} `),
        tt?.kind === "probe" ? x.probe || x.label || "probe" : tt?.kind || "setup",
        h("span", { class: "dim" }, ` · ${arr(x.candidates).length}`),
      );
    }),
  );

  const q = obj(r.query);
  const hf = obj(r.hard_filters);
  const cands = arr(r.candidates).slice().sort((a, b) => (b.total ?? 0) - (a.total ?? 0));
  const bar = (v) =>
    h("div", { class: "bar" }, h("div", { class: "bar-fill", style: { width: (typeof v === "number" ? Math.max(0, Math.min(1, v)) * 100 : 0) + "%" } }), h("span", null, fmt.num(v)));

  const baseNote = base && T.retrievals(base).length === 0
    ? h("div", { class: "note" }, h("b", null, "Baseline: "), "no retrieval step — the whole short-term history goes to the model.")
    : null;

  return section(
    "retrieval",
    "Retrieval inspector",
    "Hard filters run before ranking; candidates are scored on relevance, importance, confidence and recency.",
    picker,
    h(
      "div",
      { class: "rgrid" },
      h(
        "div",
        { class: "rq" },
        h("div", { class: "label" }, "Query"),
        h("div", { class: "bubble small" }, t?.text_safe ?? "—"),
        kv([
          ["terms", h("span", { class: "mono" }, arr(q.terms).join(" · ") || "—")],
          ["families", h("span", { class: "mono" }, arr(q.families).join(", ") || "—")],
          ["entities", h("span", { class: "mono" }, arr(q.entities).join(", ") || "—")],
        ]),
        h("div", { class: "label" }, "Hard filters"),
        h(
          "div",
          { class: "chips" },
          Object.entries(hf).map(([k, v]) => h("span", { class: "chip t-neutral" }, `${k}: ${Array.isArray(v) ? v.join("|") : String(v)}`)),
        ),
      ),
      h(
        "div",
        { class: "rc" },
        h("div", { class: "label" }, "Filtered out before ranking"),
        arr(r.excluded_by_filters).length
          ? h(
              "table",
              { class: "tbl" },
              h("tbody", null, arr(r.excluded_by_filters).map((x) => h("tr", { class: "excluded" }, h("td", null, h("b", { class: "strike" }, x.display || T.memoryLabel(cat, x.memory_id))), h("td", null, badge(x.filter || "filtered", "bad")), h("td", { class: "mono dim" }, fmt.shortId(x.memory_id))))),
            )
          : h("div", { class: "dim" }, "none"),
        h("div", { class: "label" }, `Ranked candidates (${cands.length})`),
        cands.length
          ? h(
              "table",
              { class: "tbl scores" },
              h("thead", null, h("tr", null, ["memory", "via", "relevance", "importance", "confidence", "recency", "total", ""].map((c) => h("th", null, c)))),
              h(
                "tbody",
                null,
                cands.map((c) =>
                  h(
                    "tr",
                    { class: c.selected ? "sel" : "unsel" },
                    h("td", null, h("b", null, c.display || T.memoryLabel(cat, c.memory_id))),
                    h("td", { class: "mono dim" }, arr(c.generators).join("+")),
                    h("td", null, bar(c.rel)),
                    h("td", null, bar(c.imp)),
                    h("td", null, bar(c.conf)),
                    h("td", null, bar(c.rec)),
                    h("td", { class: "total" }, fmt.num(c.total)),
                    h("td", null, c.selected ? badge("SELECTED", "good") : badge(c.drop_reason || "not selected", "warn")),
                  ),
                ),
              ),
            )
          : h("div", { class: "big dim" }, "0 candidates"),
        h("div", { class: "label" }, `LTM block sent to the model${r.ltm_block_tokens != null ? ` · ${r.ltm_block_tokens} tokens` : ""}`),
        r.ltm_block ? h("pre", { class: "block" }, r.ltm_block) : h("div", { class: "big dim" }, "no block — nothing injected"),
        baseNote,
      ),
    ),
  );
}

// ---------------------------------------------------------------- canary scan

export function renderCanary(base, ltm, open) {
  const key = (s) => `${s.canary}|${String(s.sink).replace(/:\d+$/, "")}`;
  const rowsMap = new Map();
  for (const [mode, doc] of [["baseline", base], ["ltm", ltm]]) {
    for (const s of arr(doc?.canary_scan?.sinks)) {
      const k = key(s);
      const r = rowsMap.get(k) || { canary: s.canary, sink: String(s.sink).replace(/:\d+$/, "") };
      r[mode] = s;
      rowsMap.set(k, r);
    }
  }
  const rows = [...rowsMap.values()];
  if (!rows.length) return null;
  const cell = (s) =>
    !s
      ? h("td", { class: "dim" }, "—")
      : h(
          "td",
          { class: ["num", s.hits > 0 ? (s.expected === "zero" || String(s.canary).startsWith("SECRET") ? "hit-bad" : "hit") : "zero"] },
          String(s.hits),
          s.expected ? h("span", { class: "dim small" }, ` ${s.expected}`) : null,
        );
  const body = h(
    "table",
    { class: "tbl canary" },
    h("thead", null, h("tr", null, h("th", null, "canary"), h("th", null, "sink"), h("th", null, "baseline hits"), h("th", null, "LTM hits"))),
    h("tbody", null, rows.map((r) => h("tr", null, h("td", { class: "mono" }, r.canary || "—"), h("td", { class: "mono" }, r.sink), cell(r.baseline), cell(r.ltm)))),
  );
  return h(
    "details",
    { class: "panel", id: "canary", open: open || null },
    h("summary", { class: "panel-head" }, h("h2", null, "Canary scan"), h("p", { class: "sub" }, "Byte / SQL search for each synthetic canary label across every sink. Values are never in the trace — only labels and counts.")),
    body,
  );
}

// ---------------------------------------------------------------- assertions

export function renderAssertions(base, ltm, index, scenario) {
  const col = (title, doc, mode) => {
    const as = T.assertions(doc);
    const passed = as.filter((a) => a.passed === true).length;
    return h(
      "div",
      { class: "acol" },
      h("div", { class: "acol-h" }, h("div", { class: ["lane-tag", mode] }, title), h("span", { class: "big" }, `${passed}/${as.length}`), h("span", { class: "dim" }, " passed")),
      as.length
        ? as.map((a) =>
            h(
              "details",
              { class: ["assert", a.passed ? "ok" : "fail"] },
              h("summary", null, pill(a.passed), h("span", { class: "aname" }, a.name || a.id), h("span", { class: "aid mono" }, a.id)),
              h(
                "div",
                { class: "adetail" },
                "expected" in a ? h("div", null, h("span", { class: "k" }, "expected "), h("code", null, fmt.json(a.expected))) : null,
                "actual" in a ? h("div", null, h("span", { class: "k" }, "actual "), h("code", null, fmt.json(a.actual))) : null,
                a.evidence ? h("pre", { class: "block small" }, fmt.json(a.evidence)) : null,
              ),
            ),
          )
        : missing("assertions[]"),
    );
  };
  const failed = arr(index?.failed).filter((f) => String(f.file || "").startsWith(scenario + "."));
  return section(
    "assertions",
    "Assertions",
    "Baseline assertions pass when the original failure is reproduced. LTM assertions pass when it is fixed.",
    failed.length ? h("div", { class: "note bad" }, `index.json lists ${failed.length} failed assertion(s) for this scenario`) : null,
    h("div", { class: "agrid" }, col("Current OpenPoke", base, "base"), col("New LTM", ltm, "ltm")),
  );
}
