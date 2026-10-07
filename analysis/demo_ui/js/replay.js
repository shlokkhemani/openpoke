import { h, clear } from "./dom.js";
import { loadRun, deriveFlagLabels } from "./trace.js";
import { SCENARIO_ORDER, scenarioConfig } from "./presentation.js";
import {
  renderHeader,
  renderHero,
  renderComparison,
  renderPipeline,
  renderMemoryInspector,
  renderRetrievalInspector,
  renderCanary,
  renderAssertions,
} from "./components.js";

// Trace directory, relative to this page. Override with ?dir=../lab/results/ltm_demo/llm_extractor/
const params = new URLSearchParams(location.search);
const DIR = params.get("dir") || "../lab/results/ltm_demo/";

const root = document.getElementById("app");
const uiState = new Map(); // per-scenario UI selections (turn, snapshot, retrieval)

let run = null;
let current = null;

function scenarioIds() {
  const present = [...run.scenarios.keys()];
  return [...SCENARIO_ORDER.filter((s) => present.includes(s)), ...present.filter((s) => !SCENARIO_ORDER.includes(s)).sort()];
}

function select(id) {
  current = id;
  const u = new URL(location.href);
  u.hash = id;
  history.replaceState(null, "", u);
  render();
}

function render() {
  clear(root);
  const ids = scenarioIds();
  root.append(renderHeader(run, ids, current, scenarioConfig, select));
  const entry = run.scenarios.get(current);
  if (!entry) {
    root.append(h("main", null, h("div", { class: "panel missing" }, "No trace files found in ", h("code", null, run.base), run.errors.length ? h("pre", null, run.errors.join("\n")) : null)));
    return;
  }
  const { baseline: base, ltm } = entry;
  const cfg0 = scenarioConfig(current);
  const derived = deriveFlagLabels(ltm, base);
  const flags = { ...cfg0.flags };
  for (const [k, label] of Object.entries(derived)) flags[k] = { ...(flags[k] || {}), label };
  const cfg = { ...cfg0, flags };
  if (!uiState.has(current)) uiState.set(current, {});
  const st = uiState.get(current);

  const main = h("main");
  const slot = () => h("div");
  const pipe = slot();
  const mem = slot();
  const ret = slot();
  const drawPipe = () => clear(pipe).append(renderPipeline(cfg, base, ltm, st, drawPipe));
  const drawMem = () => clear(mem).append(renderMemoryInspector(cfg, ltm, st, drawMem));
  const drawRet = () => clear(ret).append(renderRetrievalInspector(cfg, base, ltm, st, drawRet));
  drawPipe();
  drawMem();
  drawRet();

  main.append(
    renderHero(current, cfg, base, ltm),
    renderComparison(cfg, base, ltm),
    pipe,
    mem,
    ret,
    renderCanary(base, ltm, current === "privacy") || "",
    renderAssertions(base, ltm, run.index, current),
    h(
      "footer",
      { class: "foot dim" },
      "Rendered from ",
      h("code", null, run.base),
      " · schema ",
      h("code", null, (ltm || base)?.schema || "?"),
      " · run ",
      h("code", null, (ltm || base)?.meta?.run_id || "?"),
      run.errors.length ? h("div", { class: "bad" }, "Load errors: ", run.errors.join("; ")) : null,
    ),
  );
  root.append(main);
}

document.addEventListener("keydown", (e) => {
  if (!run || e.target.closest("input, textarea")) return;
  const ids = scenarioIds();
  const n = Number(e.key);
  if (n >= 1 && n <= ids.length) select(ids[n - 1]);
  if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
    const i = ids.indexOf(current) + (e.key === "ArrowRight" ? 1 : -1);
    if (ids[i]) select(ids[i]);
  }
});

(async () => {
  root.append(h("div", { class: "loading" }, "Loading traces…"));
  run = await loadRun(DIR, SCENARIO_ORDER);
  const ids = scenarioIds();
  const fromHash = location.hash.slice(1);
  current = ids.includes(fromHash) ? fromHash : ids[0];
  render();
})();
