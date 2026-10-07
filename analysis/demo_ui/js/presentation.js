// Presentation mapping ONLY: titles, wording, which hero view to use, and how to label flag keys.
// No outcomes live here. Every status, decision, score, and pass/fail on screen comes from the trace JSON.

export const SCENARIO_ORDER = ["conflict", "privacy", "selective", "forget"];

export const SCENARIOS = {
  conflict: {
    title: "Conflict",
    question: "Which value is true after the user changes their mind?",
    hero: "chain",
    flags: { old_value: { label: "old value", tone: "bad" }, new_value: { label: "new value", tone: "good" } },
  },
  privacy: {
    title: "Privacy",
    question: "Does a secret or contact detail reach durable memory?",
    hero: "clauses",
    flags: {
      secret: { label: "API key", tone: "bad" },
      contact_pii: { label: "email", tone: "warn" },
      useful_fact: { label: "preference", tone: "good" },
    },
  },
  selective: {
    title: "Selective Memory",
    question: "Is everything remembered, or only what is worth remembering?",
    hero: "clauses",
    flags: { preference: { label: "meeting pref", tone: "good" }, sandwich: { label: "sandwich", tone: "warn" } },
  },
  forget: {
    title: "Forgetting",
    question: "Can a late background write resurrect a forgotten memory?",
    hero: "timeline",
    flags: { preference: { label: "meeting pref", tone: "warn" } },
    // Assertion ids used as evidence for timeline steps that have no event of their own (pass/fail still read from data).
    timelineEvidence: { purge: "forget.row_deleted_content_null", index: "forget.fts_row_removed", tombstone: "forget.tombstone_written" },
  },
};

export function scenarioConfig(id) {
  return (
    SCENARIOS[id] || {
      title: id.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase()),
      question: "",
      hero: "clauses",
      flags: {},
    }
  );
}

export function flagLabel(cfg, key) {
  return cfg.flags?.[key]?.label || key.replace(/_/g, " ");
}
export function flagTone(cfg, key) {
  return cfg.flags?.[key]?.tone || "neutral";
}

// The seven pipeline columns the demo shows, and how trace stages / nodes map onto them.
export const LANES = [
  { id: "privacy", label: "Privacy" },
  { id: "extract", label: "Extract" },
  { id: "policy", label: "Policy" },
  { id: "consolidate", label: "Consolidate" },
  { id: "store", label: "Store" },
  { id: "retrieve", label: "Retrieve" },
  { id: "agent", label: "Agent" },
];

const STAGE_LANE = {
  "ingress.scrub": "privacy",
  "privacy.scrub": "privacy",
  "privacy.classify": "privacy",
  extract: "extract",
  "extract.clause": "extract",
  validate: "extract",
  policy: "policy",
  consolidate: "consolidate",
  store: "store",
  index: "store",
  fence_drop: "store",
  "forget.detect": "store",
  "forget.apply": "store",
  purge: "store",
  expire: "store",
  "retrieve.query": "retrieve",
  "retrieve.filter": "retrieve",
  "retrieve.candidates": "retrieve",
  "retrieve.rank": "retrieve",
  "retrieve.select": "retrieve",
  "privacy.egress": "retrieve",
  "prompt.render": "agent",
};
const NODE_LANE = {
  ingress_scrub: "privacy",
  privacy: "privacy",
  reject: "privacy",
  extract: "extract",
  ignore: "extract",
  policy: "policy",
  consolidate: "consolidate",
  supersede: "consolidate",
  store: "store",
  delete: "store",
  fence_drop: "store",
  retrieve: "retrieve",
  agent: "agent",
};

export function laneOf(event) {
  return STAGE_LANE[event.stage] || NODE_LANE[event.node] || null;
}

// A consolidate decision that commits a row also shows in the Store column (same event, second view).
const COMMITS = new Set(["INSERT", "SUPERSEDE", "MERGE", "CONTEST"]);
export function lanesOf(event) {
  const l = laneOf(event);
  if (event.stage === "consolidate" && COMMITS.has(String(event.decision || "").toUpperCase())) return [l, "store"];
  return l ? [l] : [];
}

export const BASELINE_LANES = [
  { id: "conversation", label: "Conversation" },
  { id: "raw_persistence", label: "Raw log" },
  { id: "working_memory", label: "Working memory" },
  { id: "broad_context", label: "Model context" },
  { id: "agent", label: "Agent" },
];

export const STORE_LABEL = {
  "poke_conversation.log": "Conversation log",
  "poke_working_memory.log": "Working memory",
  interaction_payload: "Model payload",
};

// Decision words → visual tone. Unknown decisions render neutral.
const TONE = {
  STORE: "good",
  INSERT: "good",
  SELECTED: "good",
  PASS: "good",
  OK: "neutral",
  CANDIDATE: "neutral",
  CLEAN: "neutral",
  MERGE: "good",
  SUPERSEDE: "accent",
  SCRUBBED: "accent",
  DELETE: "accent",
  TARGETED: "accent",
  REJECT: "bad",
  EXCLUDED: "bad",
  TOMBSTONED: "bad",
  FENCE_DROP: "bad",
  DROP_STALE: "bad",
  CONTEST: "warn",
  IGNORE: "warn",
  NO_CANDIDATE: "warn",
};
export const toneOf = (word) => TONE[String(word || "").toUpperCase()] || "neutral";

const STATUS_TONE = { active: "good", superseded: "muted", deleted: "bad", contested: "warn", expired: "muted" };
export const statusTone = (s) => STATUS_TONE[String(s || "").toLowerCase()] || "neutral";

// Short human labels for stage ids (falls back to the raw id).
const STAGE_SHORT = {
  ingest: "ingest",
  "ingress.scrub": "ingress scrub",
  "privacy.scrub": "P0 scrub",
  "privacy.classify": "classify",
  "privacy.egress": "egress",
  "extract.clause": "clause",
  "retrieve.query": "query",
  "retrieve.filter": "filter",
  "retrieve.candidates": "candidates",
  "retrieve.rank": "rank",
  "retrieve.select": "select",
  "prompt.render": "render",
  "forget.detect": "forget detect",
  "forget.apply": "forget apply",
  fence_drop: "fence",
};
export const stageShort = (s) => STAGE_SHORT[s] || s;

// Placeholder tokens that the trace uses instead of raw values. Maps token → baseline flag key.
export const PLACEHOLDER_RE = /\[(SECRET:[A-Z_]+|[A-Z]+_\d+)\]/g;
export function placeholderFlag(token) {
  if (token.startsWith("SECRET:")) return "secret";
  if (token.startsWith("EMAIL") || token.startsWith("PHONE")) return "contact_pii";
  return null;
}

export const TURN_KIND_LABEL = {
  new_conversation: "New conversation — chat history cleared",
  restart: "Server restart",
  hook: "Test hook",
  wait_duplicate: "Waiting for the delayed duplicate write",
};

// Synthetic privacy-demo values (the same ones the gated harness uses), assembled at runtime so no committed file holds a
// secret-shaped or contact-shaped string (handoff ground rule 6 / contract.leak_free).
const SYNTH = {
  key: ["sk", "test", "SYNTHETIC", "12345"].join("-"),
  email: ["test.user", "example.com"].join("@"),
};

// Live-mode presets: message scripts only. Each step is sent to both live backends; nothing here is an outcome.
export const PRESETS = [
  {
    id: "conflict",
    objective: "Can the system maintain one current truth when the user changes a fact?",
    title: "Conflict",
    steps: [
      "My favorite programming language is Python.",
      "Actually, my favorite programming language is Rust.",
      "What's my favorite programming language?",
    ],
  },
  {
    id: "privacy",
    objective: "Can it keep useful personalization while excluding secrets and contact identifiers?",
    title: "Privacy",
    steps: [
      `My email is ${SYNTH.email}, my test API key is ${SYNTH.key}, and I prefer concise emails.`,
      "Draft a short email to Sam about the launch.",
    ],
  },
  {
    id: "selective",
    objective: "Can it remember durable preferences and ignore temporary chatter?",
    title: "Selective",
    steps: [
      "I prefer meetings after 10 AM. I'm eating a turkey sandwich right now.",
      "When should I schedule a meeting?",
      "What's 2+2?",
    ],
  },
  {
    id: "forget",
    objective: "Can it delete a memory and prevent stale work from recreating it?",
    title: "Forget",
    steps: ["I prefer meetings after 10 AM.", "Forget my meeting preference.", "When do I prefer meetings?"],
    hint: "For the stale-writer race: Advanced → arm the delayed duplicate writer before step 1.",
  },
];
