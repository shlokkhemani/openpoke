// LIVE comparison console: one composer → two live OpenPoke backends → "What happened?" for the LTM turn.
// Presentation first (chats + simple story + current memory); technical drill-down in collapsed sections below.
// Everything about memory is read from the LTM backend's debug endpoints. Nothing here decides an outcome.

import { h, clear } from "./dom.js";
import * as T from "./trace.js";
import { resolveConfig, Backend, LtmDebug, Session, sleep } from "./live.js";
import { PRESETS } from "./presentation.js";
import * as S from "./story.js";
import { richText, detectorText, heroTimeline, renderPipeline, renderMemoryInspector, renderRetrievalInspector } from "./components.js";

const { arr, obj } = T;
const CFG = { title: "Live", flags: {} };
const params = new URLSearchParams(location.search);

const ui = {
  cfg: null,
  base: null,
  ltm: null,
  dbg: null,
  session: new Session(),
  selected: null,
  busy: { base: false, ltm: false, any: false },
  queue: null,
  hookArmed: null,
  present: params.get("presentation") === "1",
  folds: {},
  st: {},
  seen: new Map(), // stage-line signatures already shown, for the subtle "new" highlight
};

const root = document.getElementById("app");
const el = {};

// ================================================================== shell

function shell() {
  clear(root);
  el.presets = h("nav", { class: "seg" });
  el.right = h("div", { class: "top-right" });
  el.scenario = h("div", { class: "scenario" });
  el.input = h("input", {
    class: "op-input",
    placeholder: "Message both OpenPokes…",
    onkeydown: (e) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        sendFromComposer();
      }
    },
  });
  el.send = h("button", { class: "op-btn", onclick: sendFromComposer }, "Send");
  el.notice = h("div", { class: "notice" });
  el.base = h("section", { class: "op-col" });
  el.ltm = h("section", { class: "op-col ltm" });
  el.what = h("section", { class: "what" });
  el.below = h("div", { class: "below dev-only" });

  el.view = h("div", { class: "viewport" });
  root.append(el.view);
  el.view.append(
    h(
      "header",
      { class: "top" },
      h("div", { class: "top-brand" }, h("span", { class: "op-title" }, "OpenPoke 🌴"), h("span", { class: "top-sub" }, "Long-term memory · live comparison")),
      el.presets,
      el.right,
    ),
    el.scenario,
    h("div", { class: "composer-row" }, el.input, el.send),
    el.notice,
    h("main", { class: "stage3" }, el.base, el.ltm, el.what),
  );
  root.append(el.below);
  applyPresent();
}

function applyPresent() {
  document.body.classList.toggle("present", ui.present);
  const u = new URL(location.href);
  if (ui.present) u.searchParams.set("presentation", "1");
  else u.searchParams.delete("presentation");
  history.replaceState(null, "", u);
}

let noticeTimer = null;
function setNotice(text, tone = "neutral") {
  clearTimeout(noticeTimer);
  if (text && (tone === "good" || tone === "neutral")) noticeTimer = setTimeout(() => setNotice(null), 5000);
  clear(el.notice);
  if (text) el.notice.append(h("div", { class: ["note-bar", `t-${tone}`] }, h("span", null, text), h("button", { class: "x", onclick: () => setNotice(null) }, "×")));
}

// ================================================================== top bar

function renderTop() {
  clear(el.presets).append(
    ...PRESETS.map((p) => h("button", { class: ["seg-btn", ui.queue?.preset === p.id && "on"], onclick: () => loadPreset(p) }, p.title)),
  );
  const dot = (ok) => h("span", { class: ["sdot", ok === true ? "on" : ok === false ? "off" : ""] });
  const mode = ui.cfg.launched?.model_mode;
  clear(el.right).append(
    h("span", { class: "status dev-only", title: `${ui.base.base} · ${ui.ltm.base}` }, dot(ui.base.connected && ui.ltm.connected), mode === "real" ? "Live · real model" : mode === "mock" ? "Live · mock model" : "Live"),
    h("button", { class: "op-ghost", disabled: ui.busy.any || null, onclick: newChat, title: "Clear chat history on both; long-term memory is kept" }, "New chat"),
    h("button", { class: "op-ghost danger", disabled: ui.busy.any || null, onclick: resetBoth, title: "Wipe both chats, long-term memory and the trace panel" }, "Reset all"),
    advancedMenu(dot),
    h("button", { class: ["op-ghost", ui.present && "on"], onclick: togglePresent, title: "Presentation mode (P)" }, ui.present ? "Exit presentation" : "Presentation"),
  );
}

function advancedMenu(dot) {
  return h(
    "details",
    { class: "menu dev-only" },
    h("summary", { class: "op-ghost" }, "Advanced"),
    h(
      "div",
      { class: "menu-body" },
      h("div", { class: "small" }, dot(ui.base.connected), " Original OpenPoke ", h("span", { class: "mono dim" }, ui.base.base)),
      h("div", { class: "small" }, dot(ui.ltm.connected), " OpenPoke + LTM ", h("span", { class: "mono dim" }, ui.ltm.base), ui.dbg.available === false ? " (debug off)" : ""),
      h("button", { class: "op-ghost", onclick: armDuplicateWriter }, "Trigger delayed duplicate writer"),
      h("div", { class: "dim small" }, "The next LTM ingest job runs twice; the copy sleeps 4 s, then must pass the tombstone fence."),
      ui.hookArmed ? h("div", { class: "small" }, chip("ARMED", "warn"), " ", ui.hookArmed) : null,
      h("a", { class: "small", href: "?mode=replay" }, "Open replay (gated traces)"),
    ),
  );
}

function togglePresent() {
  ui.present = !ui.present;
  applyPresent();
  renderTop();
  renderWhat();
}

async function pollHealth() {
  await Promise.all([ui.base.health(), ui.ltm.health()]);
  if (ui.ltm.connected && ui.dbg.available !== true) await ui.dbg.traces(1).catch(() => {});
  if (!document.querySelector(".top-right details[open]")) renderTop();
}

// ================================================================== presets

function loadPreset(p) {
  ui.queue = { preset: p.id, steps: p.steps.slice(), next: 0 };
  renderScenario();
  renderTop();
}

function renderScenario() {
  clear(el.scenario);
  const q = ui.queue;
  if (!q) return;
  const p = PRESETS.find((x) => x.id === q.preset);
  const done = q.next >= q.steps.length;
  el.scenario.append(
    h("div", { class: "scn-head" }, h("b", null, p?.title), h("span", null, p?.objective || "")),
    h(
      "div",
      { class: "scn-steps" },
      q.steps.map((s, i) => h("span", { class: ["scn-step", i < q.next && "done", i === q.next && "next"], title: s }, h("i", null, i + 1), s)),
      h("button", { class: "op-btn", disabled: ui.busy.any || done || null, onclick: runNext }, done ? "Done" : "Run next"),
      h("button", { class: "op-ghost", disabled: ui.busy.any || done || null, onclick: runScenario }, "Run full scenario"),
      h("button", { class: "op-ghost quiet", title: "Close", onclick: () => ((ui.queue = null), renderScenario(), renderTop()) }, "×"),
    ),
  );
}

async function runNext() {
  const q = ui.queue;
  if (!q || q.next >= q.steps.length || ui.busy.any) return;
  const text = q.steps[q.next++];
  renderScenario();
  await runTurn(text);
}

async function runScenario() {
  while (ui.queue && ui.queue.next < ui.queue.steps.length) {
    await runNext();
    await sleep(400);
  }
}

async function armDuplicateWriter() {
  const r = await ui.dbg.ingestDelay(4000).catch((e) => ({ ok: false, status: String(e) }));
  ui.hookArmed = r.ok ? "next message's LTM write runs twice (delay 4000 ms)" : null;
  if (!r.ok) setNotice(`Test hook unavailable (HTTP ${r.status}). Start the LTM backend with OPENPOKE_LTM_TEST_HOOKS=1.`, "warn");
  renderTop();
}

// ================================================================== live turn

function sendFromComposer() {
  const text = el.input.value.trim();
  if (!text || ui.busy.any) return;
  el.input.value = "";
  runTurn(text);
}

function setBusy(side, v) {
  ui.busy[side] = v;
  ui.busy.any = ui.busy.base || ui.busy.ltm;
  el.send.disabled = ui.busy.any || null;
  renderTop();
  renderScenario();
}

async function runTurn(text) {
  const t = ui.session.newTurn(text);
  setBusy("base", true);
  setBusy("ltm", true);
  select(t.n);
  const [bh, lh, before] = await Promise.all([
    ui.base.loadHistory().catch(() => ui.base.history),
    ui.ltm.loadHistory().catch(() => ui.ltm.history),
    ui.dbg.traces(50).catch(() => []),
  ]);
  t.from = { base: bh.length, ltm: lh.length };
  const beforeIds = new Set(before.map((x) => x.trace_id));
  renderChats();

  // Both backends get the identical text at the same time; each side then finishes on its own.
  const basePath = (async () => {
    const r = await ui.base.send(text).catch((e) => ({ ok: false, status: String(e) }));
    if (!r.ok) return t.errors.push(`baseline send failed (${r.status})`);
    try {
      t.baseUserIndex = (await ui.base.waitReply(t.from.base, { onUpdate: renderChats })).userIndex;
    } catch (e) {
      t.errors.push(String(e.message || e));
    }
  })().finally(() => {
    setBusy("base", false);
    renderChats();
  });

  const ltmPath = (async () => {
    const r = await ui.ltm.send(text).catch((e) => ({ ok: false, status: String(e) }));
    if (!r.ok) return t.errors.push(`LTM send failed (${r.status})`);
    // The trace exists as soon as the server prepares the turn: show privacy + retrieval early.
    const early = findTrace(t, beforeIds).then(async () => {
      if (t.traceId && !t.trace) {
        await refreshTrace(t);
        renderWhat();
        renderChats();
      }
    });
    try {
      t.ltmUserIndex = (await ui.ltm.waitReply(t.from.ltm, { onUpdate: renderChats })).userIndex;
    } catch (e) {
      t.errors.push(String(e.message || e));
    }
    await early;
    if (!t.traceId) return t.errors.push("no LTM trace found for this turn (debug endpoints off?)");
    const idle = await ui.dbg.awaitIdle(false);
    if (idle === null) await sleep(800);
    await refreshTrace(t);
    await refreshState(t.n);
  })().finally(() => {
    t.status = t.errors.length ? "error" : "done";
    setBusy("ltm", false);
    renderAll();
  });

  await Promise.all([basePath, ltmPath]);
  settleLater();
}

/**
 * TEMPORARY trace matching: /chat/send returns an empty 202, so the new trace is found by diffing
 * GET /memory/debug/traces before/after the send (oldest new user_message trace). Assumes this page is the only client.
 */
async function findTrace(t, beforeIds) {
  const end = Date.now() + 20000;
  while (!t.traceId && Date.now() < end) {
    const list = await ui.dbg.traces(50).catch(() => []);
    const fresh = list.filter((x) => !beforeIds.has(x.trace_id) && x.source_kind === "user_message");
    if (fresh.length) t.traceId = fresh[fresh.length - 1].trace_id;
    else await sleep(250);
  }
}

async function refreshTrace(t) {
  try {
    t.trace = await ui.dbg.trace(t.traceId);
  } catch (e) {
    t.errors.push(String(e.message || e));
  }
}

async function refreshState(afterTurn) {
  try {
    ui.session.recordState(afterTurn, await ui.dbg.state());
  } catch {
    /* debug off */
  }
}

let settling = false;
async function settleLater() {
  if (settling) return;
  settling = true;
  try {
    const idle = await ui.dbg.awaitIdle(true);
    if (idle === null) return;
    const last = ui.session.turns.length - 1;
    await Promise.all(ui.session.turns.filter((t) => t.traceId).map(refreshTrace));
    if (last >= 0) await refreshState(last);
    if (ui.hookArmed && T.pipeline(currentDoc()).some((p) => obj(p.detail).duplicate === true)) ui.hookArmed = null;
    renderAll();
    renderTop();
  } finally {
    settling = false;
  }
}

// ================================================================== reset / new chat / clear

/** Forget this page's turn/trace state. Long-term memory is re-read from the backend, never assumed. */
async function clearPanels() {
  ui.seenMsgs = { base: null, ltm: null };
  await Promise.all([ui.base.loadWaits(), ui.ltm.loadWaits()]);
  ui.session = new Session();
  ui.selected = null;
  ui.st = {};
  ui.seen.clear();
  if (ui.queue) ui.queue.next = 0;
  await refreshState(-1);
}

async function newChat() {
  if (ui.busy.any) return;
  await Promise.all([ui.base.clearHistory(), ui.ltm.clearHistory()]);
  await Promise.all([ui.base.loadHistory().catch(() => {}), ui.ltm.loadHistory().catch(() => {})]);
  await clearPanels();
  const kept = arr(ui.session.latestState?.memories).filter((m) => m.status === "active").length;
  setNotice(`New chat on both: chat history cleared. Long-term memory kept (${kept} active).`, "neutral");
  renderAll();
  renderScenario();
}

async function clearSide(side) {
  if (ui.busy.any) return;
  const be = side === "ltm" ? ui.ltm : ui.base;
  await be.clearHistory();
  for (const t of ui.session.turns) t[side === "ltm" ? "ltmUserIndex" : "baseUserIndex"] = null;
  await be.loadHistory().catch(() => {});
  if (!ui.base.history.length && !ui.ltm.history.length) await clearPanels();
  renderAll();
}

async function resetBoth() {
  if (ui.busy.any) return;
  ui.busy.any = true;
  renderTop();
  try {
    if (ui.cfg.launched?.reset_endpoint) {
      setNotice("Resetting both backends…", "warn");
      const r = await fetch(ui.cfg.launched.reset_endpoint, { method: "POST" });
      const b = await r.json().catch(() => ({}));
      if (!r.ok || !b.ok) throw new Error(b.error || `reset failed (${r.status})`);
      setNotice("Reset: both chats, long-term memory and the trace panel are empty.", "good");
    } else {
      await Promise.all([ui.base.clearHistory(), ui.ltm.clearHistory()]);
      setNotice("Chat cleared on both. Long-term memory is kept (restart with live_demo.sh --fresh to wipe it).", "warn");
    }
    ui.hookArmed = null;
    await Promise.all([ui.base.loadHistory().catch(() => {}), ui.ltm.loadHistory().catch(() => {})]);
    await clearPanels();
  } catch (e) {
    setNotice(String(e.message || e), "bad");
  } finally {
    ui.busy.any = false;
    renderAll();
    renderTop();
    renderScenario();
    pollHealth();
  }
}

// ================================================================== reload recovery (no fabricated state)

async function recover() {
  await Promise.all([ui.base.loadHistory().catch(() => {}), ui.ltm.loadHistory().catch(() => {}), ui.base.loadWaits(), ui.ltm.loadWaits()]);
  const list = (await ui.dbg.traces(200).catch(() => [])).filter((x) => x.source_kind === "user_message").reverse();
  const lUser = ui.ltm.history.map((m, i) => (m.role === "user" ? i : -1)).filter((i) => i >= 0);
  const bUser = ui.base.history.map((m, i) => (m.role === "user" ? i : -1)).filter((i) => i >= 0);
  const k = Math.min(lUser.length, list.length);
  const traces = list.slice(list.length - k);
  const lIdx = lUser.slice(lUser.length - k);
  const bIdx = bUser.slice(Math.max(0, bUser.length - k));
  for (let i = 0; i < k; i++) {
    const t = ui.session.newTurn(ui.ltm.history[lIdx[i]].content);
    t.traceId = traces[i].trace_id;
    t.ltmUserIndex = lIdx[i];
    t.baseUserIndex = bIdx[i - (k - bIdx.length)];
    t.status = "recovered";
  }
  await Promise.all(ui.session.turns.map(refreshTrace));
  if (ui.session.turns.length) await refreshState(ui.session.turns.length - 1);
  if (ui.session.turns.length) select(ui.session.turns.length - 1, false);
}

// ================================================================== rendering

function renderAll() {
  renderChats();
  renderWhat();
  renderBelow();
}

function currentDoc() {
  return ui.session.toDoc(ui.ltm.history);
}

function select(n, render = true) {
  ui.scrollToSel = ui.selected !== n;
  ui.selected = n;
  ui.st.pipelineTurn = n;
  ui.st.snapshot = undefined;
  ui.st.retrieval = undefined;
  if (render) renderAll();
  ui.scrollToSel = false;
}

// ------------------------------------------------------------------ chats (OpenPoke look)

function renderChats() {
  const doc = currentDoc();
  renderChat(el.base, ui.base, "base", doc);
  renderChat(el.ltm, ui.ltm, "ltm", doc);
}

function turnAt(side, idx) {
  return ui.session.turns.find((t) => (side === "ltm" ? t.ltmUserIndex : t.baseUserIndex) === idx) || null;
}

function renderChat(col, be, side, doc) {
  const head = h(
    "header",
    { class: "op-head" },
    h("div", { class: "op-head-l" }, h("span", { class: "op-title" }, "OpenPoke 🌴"), h("span", { class: ["op-tag", side] }, side === "ltm" ? "OpenPoke + LTM" : "Original OpenPoke")),
    h(
      "div",
      { class: "op-head-r" },
      settingsMenu(be, side),
      h("button", { class: "op-ghost sm", onclick: () => clearSide(side), title: "Clear this chat's history (as in OpenPoke)" }, "Clear"),
    ),
  );
  const msgs = h("div", { class: "op-msgs" });
  const hist = be.history;
  // Animate only messages this column hasn't shown before (re-renders must not replay the entrance).
  const seen = (ui.seenMsgs ||= { base: null, ltm: null });
  const firstPaint = seen[side] == null;
  const shown = new Set();
  const isNew = (key) => {
    shown.add(key);
    return !firstPaint && !seen[side].has(key);
  };
  let ordinal = -1;
  let owner = null; // the turn the current run of messages belongs to
  hist.forEach((m, i) => {
    const isUser = m.role === "user";
    if (isUser) owner = turnAt(side, i);
    const next = hist[i + 1];
    const tail = !next || next.role !== m.role;
    const t = owner;
    const sel = side === "ltm" && t && t.n === ui.selected;
    if (isUser) ordinal++;
    const fresh = isNew(`${i}:${m.role}:${m.content.length}`);
    msgs.append(
      h(
        "div",
        { class: ["op-row", isUser ? "out" : "in", sel && "sel", side === "ltm" && t && "clickable"], onclick: side === "ltm" && t ? () => select(t.n) : null },
        h("div", { class: ["bubble2", isUser ? "out" : "in", tail && "tail", fresh && "new"] }, side === "ltm" && isUser ? richText(m.content, "ltm") : m.content),
      ),
    );
    if (isUser) {
      const marks = side === "ltm" ? ltmMarks(t, doc) : baseMarks(m.content);
      if (marks) msgs.append(marks);
      const nextMsg = hist[i + 1];
      if (be.waits.has(ordinal) && (!nextMsg || nextMsg.role !== "assistant"))
        msgs.append(
          h(
            "div",
            { class: ["op-wait", isNew(`wait:${ordinal}`) && "new"] },
            h("b", null, "OpenPoke chose not to reply"),
            h("span", null, " (wait tool) · ", be.waits.get(ordinal)),
          ),
        );
    }
  });
  seen[side] = shown;
  // In-flight turn: the user's message shows immediately; typing dots until this side's reply arrives.
  const pending = ui.busy[side] ? ui.session.turns.find((t) => t.from && (side === "ltm" ? t.ltmUserIndex : t.baseUserIndex) == null && t.status !== "done") : null;
  if (pending) {
    const from = pending.from[side];
    if (!hist.some((m, i) => i >= from && m.role === "user")) msgs.append(h("div", { class: "op-row out pending" }, h("div", { class: "bubble2 out tail" }, pending.text)));
    msgs.append(h("div", { class: "op-row in" }, h("div", { class: "bubble2 in tail typing" }, h("i"), h("i"), h("i"))));
  }
  if (!hist.length && !pending) msgs.append(h("div", { class: "op-empty" }, h("h3", null, "Start a conversation"), h("p", null, "Your messages will appear here. Send something to get started.")));
  const foot = h(
    "footer",
    { class: "op-foot" },
    side === "ltm"
      ? h("span", { class: "foot-badge ltm" }, "Structured long-term memory")
      : h("span", { class: "foot-badge" }, "Broad history + working memory · no structured LTM"),
  );
  // Keep the reader's place: follow new messages, otherwise restore the previous scroll position.
  const prev = col.querySelector(".op-msgs");
  const prevTop = prev ? prev.scrollTop : null;
  const grew = col.dataset.n !== String(hist.length) || !!pending;
  col.dataset.n = String(hist.length);
  clear(col).append(head, msgs, foot);
  msgs.scrollTop = grew || prevTop == null ? msgs.scrollHeight : prevTop;
  if (ui.scrollToSel && side === "ltm") msgs.querySelector(".op-row.sel")?.scrollIntoView({ block: "nearest" });
}

function settingsMenu(be, side) {
  const flags = ui.cfg.launched?.flags?.[side === "ltm" ? "ltm" : "baseline"];
  return h(
    "details",
    { class: "menu" },
    h("summary", { class: "op-ghost sm" }, "Settings"),
    h(
      "div",
      { class: "menu-body" },
      h("div", { class: "small" }, h("b", null, side === "ltm" ? "OpenPoke + LTM" : "Original OpenPoke")),
      h("div", { class: "mono small" }, be.base),
      flags ? h("div", { class: "mono small dim" }, Object.entries(flags).map(([k, v]) => h("div", null, `${k}=${v}`))) : null,
      h("div", { class: "small dim" }, `${be.history.length} messages in GET /chat/history`),
    ),
  );
}

/** Subtle chips under the LTM user bubble: what this message did to memory (from its trace). */
function ltmMarks(t, doc) {
  if (!t) return null;
  if (!t.trace) return t.traceId || ui.busy.ltm ? h("div", { class: "marks" }, h("span", { class: "mark dim" }, "tracing…")) : null;
  const ctx = S.makeContext(doc, t.n);
  const ing = ctx.evs.find((e) => e.stage === "ingress.scrub" && e.decision === "SCRUBBED");
  const chips = S.bubbleChips(ctx);
  if (!chips.length && !ing) return null;
  return h(
    "div",
    { class: "marks" },
    ing ? h("span", { class: "mark" }, dotTone("accent"), "secret scrubbed before storage") : null,
    chips.map((c) => h("span", { class: "mark" }, dotTone(c.tone), h("b", null, c.subject), ` ${c.status}`)),
  );
}

/** Baseline: only what its own /chat/history proves — raw secret-/contact-looking text kept verbatim. */
const RAW = [
  ["raw API key kept in history", /\bsk-[A-Za-z0-9_-]{8,}/, "bad"],
  ["email kept in history", /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/, "warn"],
];
function baseMarks(text) {
  const hits = RAW.filter(([, rx]) => rx.test(String(text || "")));
  if (!hits.length) return null;
  return h("div", { class: "marks" }, hits.map(([label, , tn]) => h("span", { class: "mark" }, dotTone(tn), label)));
}

const dotTone = (tn) => h("span", { class: ["mdot", `t-${tn}`] });
const chip = (text, tn) => h("span", { class: ["st", `t-${tn}`] }, text);

// ------------------------------------------------------------------ What happened?

function renderWhat() {
  const doc = currentDoc();
  const t = ui.session.turns[ui.selected] || null;
  const head = h("header", { class: "what-head" }, h("h2", null, "What happened?"));
  clear(el.what).append(head);
  if (!t) {
    el.what.append(
      h(
        "div",
        { class: "what-body" },
        h("div", { class: "what-empty" }, ui.dbg.available === false ? "LTM debug endpoints are not reachable." : "Send a message. This panel explains what the long-term memory did with it."),
        memoryBlock(doc),
      ),
    );
    return;
  }
  const n = ui.session.turns.length;
  head.append(
    h(
      "div",
      { class: "turn-nav" },
      h("button", { class: "op-ghost sm", disabled: t.n === 0 || null, onclick: () => select(t.n - 1), title: "Previous message" }, "‹"),
      h("span", { class: "turn-quote", title: t.text }, "“", richText(doc.turns[t.n]?.text_safe ?? t.text, "ltm"), "”"),
      h("button", { class: "op-ghost sm", disabled: t.n >= n - 1 || null, onclick: () => select(t.n + 1), title: "Next message" }, "›"),
    ),
  );
  const body = h("div", { class: "what-body" });
  for (const e of t.errors) body.append(h("div", { class: "missing" }, e));
  const ctx = S.makeContext(doc, t.n);
  if (t.trace) {
    const cs = S.chains(ctx);
    if (cs.length) body.append(h("div", { class: "stories" }, cs.map(renderChain)));
  }
  body.append(stageList(ctx, t));
  body.append(memoryBlock(doc));
  el.what.append(body);
}

function renderChain(c) {
  const steps = [];
  for (const s of c.steps) {
    if (s.arrow) steps.push(h("span", { class: "arrow" }, c.vertical ? "↓" : "→"));
    else if (s.strong) steps.push(h("span", { class: ["subj", s.tone === "muted" && "muted"] }, s.text));
    else steps.push(chip(s.text, s.tone || S.tone(s.text)));
  }
  const subj = c.steps.find((x) => x.strong)?.text || "";
  const title = c.title === "retrieved" ? "Retrieved for this message" : c.title && c.title.toLowerCase() !== String(subj).toLowerCase() ? c.title : "";
  return h(
    "div",
    { class: ["story", c.vertical && "vertical"] },
    title ? h("div", { class: "story-title" }, title) : null,
    h("div", { class: "story-steps" }, c.vertical ? groupVertical(steps) : steps),
    c.note ? h("div", { class: "story-note" }, c.note) : null,
  );
}

/** In vertical chains, keep "subject + status" on one line and each arrow on its own line. */
function groupVertical(steps) {
  const out = [];
  let line = [];
  for (const s of steps) {
    if (s.classList.contains("arrow")) {
      if (line.length) out.push(h("div", { class: "vline" }, line));
      out.push(h("div", { class: "vline arrowline" }, s));
      line = [];
    } else line.push(s);
  }
  if (line.length) out.push(h("div", { class: "vline" }, line));
  return out;
}

function stageList(ctx, t) {
  const rows = S.stages(ctx);
  const loading = !t.trace;
  // Consecutive stages with nothing to say collapse into one quiet line instead of a column of dashes.
  const grouped = [];
  for (const s of rows) {
    const prev = grouped[grouped.length - 1];
    if (!s.lines.length && !loading && prev && prev.empty) prev.label += " · " + s.label;
    else grouped.push({ ...s, empty: !s.lines.length && !loading });
  }
  return h(
    "div",
    { class: "stages" },
    grouped.map((s) => {
      if (s.empty) return h("div", { class: "stg quiet" }, h("div", { class: "stg-name" }, s.label), h("div", { class: "stg-lines" }, h("span", null, "no change")));
      const lines = s.lines.filter((l) => !l.minor || !ui.present);
      const key = `${t.n}:${s.id}`;
      const sig = lines.map((l) => l.text).join("|");
      const fresh = sig && ui.seen.get(key) !== sig;
      if (sig) ui.seen.set(key, sig);
      return h(
        "div",
        { class: ["stg", s.quiet && "quiet", loading && "loading", fresh && "fresh"] },
        h("div", { class: "stg-name" }, s.label),
        h(
          "div",
          { class: "stg-lines" },
          lines.length
            ? lines.map((l) =>
                h(
                  "div",
                  { class: ["stg-line", l.quiet && "dim", l.minor && "minor"] },
                  l.badge ? chip(l.badge, S.tone(l.badge)) : null,
                  h("span", null, l.badge ? stripBadge(l.text, l.badge) : l.text),
                  l.note ? h("span", { class: "stg-note" }, ` · ${l.note}`) : null,
                ),
              )
            : h("span", { class: "dim" }, loading ? "…" : "—"),
        ),
      );
    }),
  );
}

// "Email → REJECT" next to a REJECT chip reads twice; drop the trailing decision word when the chip shows it.
const stripBadge = (text, badge) => String(text).replace(new RegExp(`\\s*→\\s*${badge}\\b`), "");

function memoryBlock(doc) {
  const cm = S.currentMemory(doc);
  const box = h("div", { class: "curmem" }, h("div", { class: "cm-title" }, "Current memory", ui.session.turns.length ? null : h("span", { class: "cm-hint" }, " · kept across chats")));
  if (!cm || (!cm.rows.length && !cm.tombs.length)) {
    box.append(h("div", { class: "dim small" }, cm ? "empty" : "—"));
    return box;
  }
  for (const r of cm.rows)
    box.append(
      h(
        "button",
        { class: ["cm-row", r.status === "SUPERSEDED" && "inactive"], onclick: () => openMemory(r.id), title: "Open memory details" },
        h("span", { class: "cm-name" }, r.name, r.purged && r.status === "DELETED" ? h("span", { class: "dim" }, " · content purged") : null),
        chip(r.status, S.tone(r.status)),
        h("span", { class: "cm-sub" }, r.sub),
      ),
    );
  for (const tb of cm.tombs) box.append(h("div", { class: "cm-row static" }, h("span", { class: "cm-name" }, tb.name), chip("TOMBSTONE", "bad"), h("span", { class: "cm-sub" }, tb.sub)));
  return box;
}

function openMemory(id) {
  if (ui.present) return;
  ui.folds["f-mem"] = true;
  ui.st.snapshot = undefined;
  ui.st.focusMemory = id;
  renderBelow();
  document.querySelector(`[data-mem="${CSS.escape(id)}"]`)?.scrollIntoView({ behavior: "smooth", block: "center" });
}

// ------------------------------------------------------------------ technical drill-down

function fold(id, title, sub, content) {
  const d = h("details", { class: "fold", id, open: ui.folds[id] ? true : null }, h("summary", null, h("span", null, title), sub ? h("span", { class: "fold-sub" }, sub) : null), content);
  d.addEventListener("toggle", () => (ui.folds[id] = d.open));
  return d;
}

function renderBelow() {
  clear(el.below);
  const doc = currentDoc();
  if (!ui.session.turns.some((t) => t.trace)) return;
  const st = ui.st;
  if (st.pipelineTurn == null || !ui.session.turns[st.pipelineTurn]) st.pipelineTurn = ui.selected;
  const ri = T.retrievals(doc).findIndex((r) => r.turn_index === ui.selected);
  if (st.retrieval == null && ri >= 0) st.retrieval = ri;

  const memBox = h("div");
  const retBox = h("div");
  const pipeBox = h("div");
  const drawMem = () => clear(memBox).append(renderMemoryInspector(CFG, doc, st, drawMem));
  const drawRet = () => clear(retBox).append(renderRetrievalInspector(CFG, null, doc, st, drawRet));
  const drawPipe = () => clear(pipeBox).append(renderPipeline(CFG, null, doc, st, drawPipe));
  drawMem();
  drawRet();
  drawPipe();
  if (st.focusMemory) {
    memBox.querySelector(`[data-mem="${CSS.escape(st.focusMemory)}"]`)?.classList.add("focus");
    st.focusMemory = null;
  }
  const t = ui.session.turns[ui.selected];
  const hasRace = doc.pipeline.some((p) => p.stage === "fence_drop" || p.stage.startsWith("forget."));
  el.below.append(
    fold("f-mem", "Memory details", "every record, status history, provenance", memBox),
    fold("f-ret", "Retrieval details", "hard filters, candidates, score parts, final LTM block", retBox),
    fold("f-safety", "Safety / privacy details", "scrub events, PII classification, rejected data", safetyPanel(doc)),
    fold("f-basectx", "Baseline context", "what the original OpenPoke keeps", baselineContext()),
    fold(
      "f-adv",
      "Advanced trace",
      "per-clause engineering pipeline, ids, raw events",
      h(
        "div",
        null,
        h("div", { class: "adv-ids mono small" }, t?.traceId ? `selected turn t${t.n} · trace ${t.traceId} · kind ${t.trace?.kind ?? "?"} · ${arr(t.trace?.pipeline).length} events` : ""),
        pipeBox,
        hasRace ? h("div", { class: "panel" }, h("h3", null, "Write / forget timeline (this session)"), heroTimeline({}, doc)) : null,
        t?.trace ? h("details", { class: "raw" }, h("summary", null, "Raw trace JSON (selected turn)"), h("pre", { class: "block" }, JSON.stringify(t.trace, null, 2))) : null,
      ),
    ),
  );
}

function baselineContext() {
  const hist = ui.base.history;
  const users = hist.filter((m) => m.role === "user").length;
  return h(
    "div",
    { class: "panel" },
    h("div", null, h("b", null, `${hist.length}`), " messages in conversation history ", h("span", { class: "dim" }, `(${users} from the user) · GET /chat/history`)),
    h("div", { class: "dim" }, "Working memory: not exposed by any live endpoint, so not shown."),
    h("div", { class: "dim" }, "Structured memory state: none (LTM flags off on this instance)."),
    hist.length ? h("pre", { class: "block small" }, hist.map((m) => `${m.role}: ${m.content}`).join("\n")) : null,
  );
}

const RAW_PATTERNS = [
  ["secret-like (sk-…)", /\bsk-[A-Za-z0-9_-]{8,}/g],
  ["email address", /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}/g],
  ["AWS key id", /\bAKIA[0-9A-Z]{16}\b/g],
];

function safetyPanel(doc) {
  const rows = [];
  for (const t of doc.turns) {
    const fx = [];
    for (const e of T.eventsForTurn(doc, t.turn_index)) {
      if (e.stage === "ingress.scrub" && e.decision && e.decision !== "CLEAN") fx.push([chip(e.decision, "accent"), ` before storage: ${textOf(detectorText(e))}`]);
      if (e.stage === "privacy.scrub" && arr(obj(e.detail).detectors).length) fx.push([chip("MASKED", "accent"), ` for the extractor: ${textOf(detectorText(e))}`]);
      if (e.stage === "privacy.classify" && e.decision === "REJECT")
        fx.push([chip("REJECT", "bad"), ` ${obj(e.detail).label || "clause"}: ${arr(obj(e.detail).detectors).join(", ")} · ${S.reasonNote(arr(e.reason_codes)[0])}`]);
      if (e.stage === "privacy.egress" && e.decision && e.decision !== "PASS") fx.push([chip(e.decision, "warn"), " egress"]);
    }
    const q = String(t.text_safe || "");
    if (fx.length) rows.push(h("div", { class: "srow" }, h("span", { class: "srow-q" }, `“${q.slice(0, 60)}${q.length > 60 ? "…" : ""}”`), h("div", null, fx.map((f) => h("div", null, ...f)))));
  }
  const blob = JSON.stringify({ state: ui.session.latestState, traces: ui.session.turns.map((t) => t.trace) });
  const scan = RAW_PATTERNS.map(([name, rx]) => [name, (blob.match(rx) || []).length]);
  return h(
    "div",
    { class: "panel" },
    h("h3", null, "Privacy events (from LTM traces)"),
    rows.length ? rows : h("div", { class: "dim" }, "No privacy findings in this session."),
    h("h3", null, "Raw-value scan of everything the LTM debug API returned (state + traces)"),
    h("div", { class: "chips" }, scan.map(([name, n]) => chip(`${name}: ${n}`, n ? "bad" : "good"))),
    h("div", { class: "dim small" }, "Client-side regex over the debug responses. The gated canary scan across every sink is in replay mode."),
  );
}

const textOf = (node) => (typeof node === "string" ? node : node?.textContent || "");

// ================================================================== boot

export async function start() {
  ui.cfg = await resolveConfig();
  const lab = !!ui.cfg.launched && !params.get("baseline") && !params.get("ltm");
  ui.base = new Backend("baseline", ui.cfg.baseline, lab ? "baseline" : null);
  ui.ltm = new Backend("ltm", ui.cfg.ltm, lab ? "ltm" : null);
  ui.dbg = new LtmDebug(ui.cfg.ltm);
  shell();
  renderTop();
  await pollHealth();
  await recover();
  renderAll();
  setInterval(pollHealth, 5000);
  document.addEventListener("keydown", (e) => {
    if (e.target.closest("input, textarea")) return;
    if (e.key === "p" || e.key === "P") togglePresent();
  });
  el.input.focus();
}
