# OpenPoke LTM: Architecture Decision Record

> **FROZEN: architecture spec v2 (2026-10-07).** This document is the binding spec for implementation. Do not edit it during implementation. Deviations go through the blocker protocol in [LTM_IMPLEMENTATION_HANDOFF.md](LTM_IMPLEMENTATION_HANDOFF.md) §2 and are recorded in `LTM_BLOCKERS.md`, not here.

Concise record of the decisions behind [LTM_SYSTEM_DESIGN.md](LTM_SYSTEM_DESIGN.md). The algorithms and thresholds are in
[LTM_ENGINEERING_DEEP_DIVE.md](LTM_ENGINEERING_DEEP_DIVE.md). Status of every decision: **Proposed** (nothing implemented).

---

### D1. Structured long-term memory *alongside* working memory (not summary-only, not replacing it)

| | |
|---|---|
| **Decision** | Add a separate LTM store of typed fact records. Leave the conversation log, working memory and summariser unchanged |
| **Why** | The summary is one free-text blob with no supersession, provenance or deletion semantics (`conflict_demo.md`; S3/S4). Working memory already answers "what's happening now" well enough, and LTM answers a different question |
| **Alternative considered** | (a) Improve the summariser prompt to resolve conflicts. (b) Replace working memory with retrieval-only context |
| **Tradeoff** | Two memory systems to reason about. Stale facts can still appear in the short-term window until it rolls over |
| **Prototype** | New package `server/services/memory/`, flag `OPENPOKE_LTM_ENABLED` (default off) |
| **Production** | Same split. Later, feed active LTM slots to the summariser so it stops restating profile facts |

### D2. Typed slot model `(subject, predicate, value, cardinality)` as the conflict key

| | |
|---|---|
| **Decision** | Every memory has a canonical `slot_key`. A partial unique index enforces ≤ 1 active value per single-valued slot |
| **Why** | Makes supersession a database invariant instead of an LLM inference. Python+Rust-both-active becomes unrepresentable |
| **Alternative considered** | Embedding similarity to detect conflicts; LLM adjudication on every write |
| **Tradeoff** | Needs a controlled predicate vocabulary. Open-ended facts go to `pref.custom:*` with weaker (fuzzy) conflict detection |
| **Prototype** | ~15 predicates covering the scenarios + `custom:*`. The extractor is shown existing slot keys (keys only) to reuse them |
| **Production** | Larger vocabulary + an LLM adjudicator for fuzzy `custom:*` conflicts |

### D3. LLM proposes, deterministic policy disposes

| | |
|---|---|
| **Decision** | The extractor outputs candidates with *categorical* fields (`durability`, `certainty`, `sensitivity_category`, `is_correction`, `is_instruction_to_assistant`). Code computes importance/confidence and makes every decision |
| **Why** | Auditable, testable, versioned decisions. LLM-reported floats are poorly calibrated and drift between models. A prompt-injected extractor can't directly write state |
| **Alternative considered** | LLM decides STORE/IGNORE/SUPERSEDE end-to-end (e.g. "memory agent" with tools) |
| **Tradeoff** | Less nuanced on edge cases; the rule tables need tuning |
| **Prototype** | `RuleExtractor` (deterministic) + `LLMExtractor` behind one interface; policy tables with reason codes |
| **Production** | Same, plus offline evaluation gating any policy/extractor version change |

### D4. Deterministic-first + semantic PII detection, before and after the extractor LLM

| | |
|---|---|
| **Decision** | P0 deterministic scrub → LLM_SAFE before extraction. P1 re-scan + LLM category + lexicon backstop (max of the two) after extraction. P2 egress scan on the rendered block |
| **Why** | Regex is reliable for secrets/IDs; semantics is needed for health/finance/etc. Scrubbing before the LLM means the extractor *cannot* copy a secret into memory. Model judgement can only raise sensitivity |
| **Alternative considered** | LLM-only PII classification; regex-only |
| **Tradeoff** | False positives (order numbers near "code" look like OTPs); regex misses names/addresses in free form |
| **Prototype** | Regex + Luhn + entropy + keyword proximity; ~10-category lexicon |
| **Production** | NER-class detector, locale-specific IDs, measured per-category recall, red-team corpus |

### D5. Secrets and regulated identifiers are never durable; no vault in the prototype

| | |
|---|---|
| **Decision** | API keys, passwords, tokens, OTPs, card/SSN/IBAN-like values → REJECT, even if the user says "remember it" |
| **Why** | Memory is replayed into third-party LLM prompts; that is the wrong place for credentials. Baseline shows secrets replayed for ~55 turns (F-3) |
| **Alternative considered** | Encrypt and store; mask (`••••1111`) |
| **Tradeoff** | The user can't use the assistant as a password manager. The agent tells them so via `<memory_notice>` |
| **Prototype** | REJECT + notice |
| **Production** | Optional TOKENIZE into a KMS-encrypted vault for declared uses, detokenised only at tool execution, never in prompts |

### D6. Only user-authored turns can create memories

| | |
|---|---|
| **Decision** | `source_kind = user_message` is the only allowed source. Gmail, watcher summaries, tool and execution-agent output are not extraction sources |
| **Why** | Email content is attacker-controlled (poisoning). It is mostly third-party PII. The watcher already over-collects (F-4) |
| **Alternative considered** | Extract from all `agent_message` entries with lower trust |
| **Tradeoff** | Misses useful facts the assistant learns from email ("Alice's new role is VP") |
| **Prototype** | Allowlist of one |
| **Production** | Low-trust third-party source that can never write `constraint`, never supersede user-sourced facts, and needs user confirmation for durable storage |

### D7. SQLite + FTS5 for the prototype, Postgres (+pgvector, RLS) for production

| | |
|---|---|
| **Decision** | `server/data/memory/ltm.db` with WAL, `secure_delete=ON`, FTS5 (porter), partial unique index, `BEGIN IMMEDIATE` writes |
| **Why** | Zero dependencies (stdlib; FTS5 verified available). Transactions for fencing; partial indexes for invariants; secure delete addresses S1. OpenPoke already uses SQLite (`triggers/store.py`) |
| **Alternative considered** | A vector DB (Chroma/Qdrant/pgvector) from day one; JSON files |
| **Tradeoff** | No semantic similarity; single-node |
| **Prototype** | SQLite, separate file from `triggers.db` |
| **Production** | Postgres with RLS, tsvector/GIN, pgvector HNSW, envelope encryption. Column-for-column migration via dual-write |

### D8. Hybrid retrieval (slot routing + lexical), embeddings deferred

| | |
|---|---|
| **Decision** | Candidates = predicate-family match ∪ FTS5 BM25 top-50 ∪ entity-matched constraints. No vectors in the prototype |
| **Why** | Small per-user stores; explainable; no new external boundary (the client only implements `/chat/completions`, `client.py:68`) |
| **Alternative considered** | Pure embeddings; embed every memory at write time |
| **Tradeoff** | Paraphrase recall gap, tracked as an eval metric |
| **Prototype** | Intent lexicon doubles as FTS `keywords` column |
| **Production** | Add a vector generator over MEMORY_SAFE text of non-`high` memories; learned reranker |

### D9. Privacy/authorization are hard filters, never ranking weights

| | |
|---|---|
| **Decision** | `user_id`, `status`, `expires_at`, `sensitivity`, `allowed_uses` are SQL `WHERE` clauses applied before scoring; P2 scans output |
| **Why** | A weighted score lets a highly relevant forbidden memory outrank the threshold. Authorization is binary |
| **Alternative considered** | Sensitivity penalty in the score |
| **Tradeoff** | None worth taking the other way |
| **Prototype / Production** | Same |

### D10. Ranking: 0.55 relevance / 0.20 importance / 0.15 confidence / 0.10 recency; k ≤ 8, ≤ 400 tokens, relevance floor

| | |
|---|---|
| **Decision** | Relevance-dominant score with a hard floor (`rel ≥ 0.25`) and an absolute score threshold (0.45). Frequency weight 0. Up to 3 slots reserved for constraints |
| **Why** | Irrelevant-but-important memories are noise. Staleness is structural (supersession/TTL), so recency needs little weight. Frequency causes rich-get-richer loops. Typical needs are 0–3 facts |
| **Alternative considered** | 0.50/0.20/0.15/0.15 with frequency; fixed k = 5 always filled |
| **Tradeoff** | Weights are hand-set until the eval set is large enough to fit them |
| **Prototype** | Constants in `retrieval.py`, logged per candidate |
| **Production** | Tune on labelled data; consider a learned reranker |

### D11. Supersede with provenance (status chain), not overwrite

| | |
|---|---|
| **Decision** | Changes of value create a new row and mark the old one `superseded` (linked both ways). Superseded content is kept 30 days, then purged to a skeleton. Never retrievable to the agent |
| **Why** | Current truth + explainability + undo, without retaining old values forever |
| **Alternative considered** | In-place UPDATE (loses history); keep all versions forever (maximises data) |
| **Tradeoff** | 30-day window where an old value still exists at rest |
| **Prototype / Production** | Same; production adds encryption at rest |

### D12. Ambiguity → CONTEST, not silent overwrite

| | |
|---|---|
| **Decision** | A hedged or lower-trust newer value doesn't supersede an explicit one. It's stored as `contested` and rendered as an explicit conflict |
| **Why** | Recency should win among comparable statements, but a vague remark shouldn't erase a clear one. Surfacing the ambiguity lets the agent ask |
| **Alternative considered** | Always newest wins; always highest confidence wins |
| **Tradeoff** | The occasional clarifying question |
| **Prototype / Production** | Same |

### D13. Tombstone + content purge + epoch fencing, not hard delete alone

| | |
|---|---|
| **Decision** | Delete = null content, remove the FTS row, scrub events, write a content-free tombstone (slot key + keyed value hash), checkpoint the WAL. Every async writer checks epoch + tombstone inside its commit transaction |
| **Why** | The baseline proved unfenced deletes get resurrected (S2, S6). The source utterance still exists in the conversation log, so re-processing must be blockable |
| **Alternative considered** | `DELETE FROM` only (S1 shows bytes survive in the DB/WAL); soft-delete flag only (retains content) |
| **Tradeoff** | Tombstones accumulate (small). A slot key reveals *that* e.g. a meeting preference was deleted |
| **Prototype** | As above; guarantees listed in design §14.5 |
| **Production** | + crypto-shredding with per-user DEKs, backup expiry SLA, propagate forget to the conversation log and summary |

### D14. Async extraction; synchronous scrub, forget and retrieval

| | |
|---|---|
| **Decision** | The turn path runs P0, forget detection and retrieval synchronously (no LLM). Extraction runs as a background task under a per-user lock, ordered by `observed_at` |
| **Why** | Zero added LLM latency per turn. Facts from this turn are already in working memory, so no read-your-writes gap. Forget must take effect before the same turn's retrieval |
| **Alternative considered** | Synchronous LLM extraction before replying |
| **Tradeoff** | Memory becomes retrievable from the next turn; out-of-order completion must be handled (DROP_STALE) |
| **Prototype** | `asyncio.create_task` (same pattern as `scheduler.py`) |
| **Production** | Durable queue with idempotency keys and backoff (avoid repeating the F-6 retry storm) |

### D15. LTM is rendered as escaped data in the user message, never the system prompt

| | |
|---|---|
| **Decision** | A `<long_term_memory>` block between `<conversation_history>` and `<active_agents>` in the single user-role message from `prepare_message_with_history` (`agent.py:20-33`), with a "data, not instructions; may be stale; conversation wins" header. Rendered from canonical fields, HTML-escaped, per-prompt aliases instead of database ids |
| **Why** | Memory must not gain system authority. Canonical rendering shrinks the injection surface |
| **Alternative considered** | Append memories to the system prompt; give the agent a `search_memory` tool |
| **Tradeoff** | The model may still be influenced by memory text; mitigated, not eliminated |
| **Prototype** | As above + a `system_prompt.md` paragraph |
| **Production** | + a `search_memory` tool for deliberate deep lookups (read-only, scoped), red-team suite |

### D16. Memories may narrow behaviour, never widen it

| | |
|---|---|
| **Decision** | `constraint` memories may only add restrictions/confirmations. Anything adding recipients, permissions, auto-actions or external destinations is REJECT `CAPABILITY_WIDENING` |
| **Why** | This is the core poisoning defence: even a fully poisoned memory store can't make the assistant do *more* than the user asks in the moment |
| **Alternative considered** | Allow "always CC my assistant" style rules |
| **Tradeoff** | Legitimate automation rules ("always CC my EA") need a separate, explicit settings flow |
| **Prototype** | Pattern + extractor-flag check |
| **Production** | Settings-based automation rules with explicit confirmation; tool-layer enforcement |

### D17. `user_id` on everything; scope resolved server-side in one place

| | |
|---|---|
| **Decision** | `MemoryScope` is required by every store method. `resolve_memory_scope()` is the single seam (constant `local-user` in the prototype). Never taken from LLM/tool arguments or the request body |
| **Why** | The baseline has no identity (F-1); LTM shouldn't deepen that debt |
| **Alternative considered** | Defer `user_id` until multi-user |
| **Tradeoff** | Slight API verbosity |
| **Prototype** | Column + scope + two-scope isolation tests |
| **Production** | Auth principal + Postgres RLS |

### D18. Execution agents don't receive LTM directly

| | |
|---|---|
| **Decision** | Only the interaction agent gets the LTM block. It forwards what a task needs in its instructions |
| **Why** | Execution-agent logs are unbounded and persisted verbatim (F-7); they process attacker-controlled email |
| **Alternative considered** | Inject LTM into every execution agent's system prompt |
| **Tradeoff** | The interaction agent must remember to pass constraints along |
| **Prototype** | No change to execution agents |
| **Production** | Tool-layer constraint enforcement (e.g. Gmail send checks `confirm_before_email`) |

### D19. Confidence and importance are computed from categorical signals

| | |
|---|---|
| **Decision** | `certainty ∈ {explicit, hedged, inferred}` × source trust → confidence; type base + signal deltas → importance |
| **Why** | Reproducible across models; explainable in the inspector |
| **Alternative considered** | Ask the LLM for 0–1 scores |
| **Tradeoff** | Coarse granularity |
| **Prototype / Production** | Same; production may calibrate the mappings on labelled data |

### D20. Type-specific retention, enforced at query time *and* by a sweeper

| | |
|---|---|
| **Decision** | Preferences/profile/constraints don't expire (with confidence decay for the first two); projects 90 d sliding; `high` sensitivity 180 d unless re-confirmed; superseded 30 d; expired 7 d grace |
| **Why** | Different facts age differently; query-time filtering stays correct even if the sweeper doesn't run |
| **Alternative considered** | One global TTL; no TTL |
| **Tradeoff** | Policy constants to maintain |
| **Prototype / Production** | Same; production adds user-configurable retention |

### D21. "Clear chat" ≠ "forget me"

| | |
|---|---|
| **Decision** | `DELETE /chat/history` bumps the LTM epoch (cancelling in-flight extraction from that chat) but keeps existing memories. Forgetting is a separate action (`DELETE /memory`, or by chat) |
| **Why** | Different user intents; avoids accidental loss of long-lived preferences |
| **Alternative considered** | Clear chat also wipes LTM |
| **Tradeoff** | Users may expect "clear" to wipe everything; the UI must say so |
| **Prototype** | As decided; trivially flippable |
| **Production** | Explicit UI copy + memory settings page |

### D22. Observability by events, LOG_SAFE by default

| | |
|---|---|
| **Decision** | One event per stage per item with `trace_id`, reason codes and score breakdowns. MEMORY_SAFE text only in dev mode, scrubbed on delete. Never values of rejected items |
| **Why** | The inspector demo is built from data, not ad-hoc prints. Logs must not become a new leak (F-12) |
| **Alternative considered** | Verbose debug logging |
| **Tradeoff** | Less raw detail when debugging extraction |
| **Prototype** | `memory_events` table + optional JSONL |
| **Production** | Metrics/alerts (egress violations must be 0), access-controlled audit log |

---

## Revision 2 decisions (presentation proofs and ingress boundary)

### D23. Minimal ingress-persistence boundary for prohibited classes

| | |
|---|---|
| **Decision** | Scrub SECRET (API keys, passwords, tokens, JWTs, private keys, secret URLs, OTPs, high-entropy) and REGULATED_ID (gov IDs, Luhn-valid cards, IBAN) to typed placeholders **before** the turn is written to the conversation log / working memory **and before the interaction LLM call**. Chokepoints: the top of `InteractionAgentRuntime.execute`/`handle_agent_message` (I1) and `ConversationLog.record_*` (I2) |
| **Why** | The presentation proof needs secrets to not be persisted or replayed. Today they are in 2+ durable files and re-sent for ~55 turns (S1, F-3). Scrubbing before the interaction LLM means the model can't echo the value into replies, drafts, execution instructions or triggers, which closes the indirect paths without editing each one |
| **Alternative considered** | (a) Scrub only the persisted copy but send the raw value to the LLM this turn. (b) Scrub all PII including contacts. (c) A full privacy rewrite of OpenPoke persistence |
| **Tradeoff** | The agent can't use or repeat a secret, which is acceptable because no OpenPoke tool consumes secrets today. The user sees their own message redacted in `/chat/history`. Contact PII stays in short-term history (it's needed for drafts) |
| **Prototype** | `OPENPOKE_INGRESS_SCRUB` (defaults to the LTM flag). New entries only. Optional stretch: the same scrub in `ExecutionAgentLogStore._append` |
| **Production** | Full PII classification at ingress with tokenisation of operational identifiers, a per-turn ephemeral value map for tools that legitimately need a raw value, retroactive migration of old entries, client-side handling |

### D24. Contact PII: explicit classification, never LTM by default, retained in short-term history

| | |
|---|---|
| **Decision** | Emails/phones are classified (`privacy.classify` → `CONTACT:EMAIL`) and REJECTed from LTM (`CONTACT_IDENTIFIER_NOT_NEEDED`). They are not ingress-scrubbed |
| **Why** | The user's own address is already known to the Gmail integration. Third-party addresses are needed in the same turn for drafting. Storing either in LTM adds risk without value |
| **Alternative considered** | TOKENIZE into a vault now; ingress-scrub contacts too |
| **Tradeoff** | "The email is no longer replayed" is **not** true in the same session, and the demo must say so |
| **Prototype** | REJECT + event |
| **Production** | TOKENIZE for declared uses; ingress tokenisation with tool-time detokenisation |

### D25. Observability is a first-class requirement; demo traces are a product of the system

| | |
|---|---|
| **Decision** | Every pipeline stage must emit an event (a stage without one is unfinished). Add `ingress.scrub`, `extract.clause` (NO_CANDIDATE reasons) and `retrieve.filter` (debug-only excluded-by-filter view). A trace assembler builds the `openpoke.ltm.demo_trace.v1` JSON per scenario per mode |
| **Why** | The before/after demo, the acceptance gate and the future inspector all need the *path taken* and the *reason*, not just end state. Building the contract now keeps the UI a pure renderer |
| **Alternative considered** | Instrument later, or have the UI query SQLite directly |
| **Tradeoff** | More events and more code in each stage; dev-mode events briefly contain LLM_SAFE clause text (never secrets) |
| **Prototype** | `memory_events` + `trace.py` + harness-written files under `analysis/lab/results/ltm_demo/` |
| **Production** | Event stream into the metrics/audit pipeline; an authenticated inspector |

### D26. Debug and test-hook endpoints are flag-gated and loopback-only

| | |
|---|---|
| **Decision** | `GET /memory/debug/trace/{id}`, `GET /memory/debug/state`, and the test hooks (`ingest-delay`, `await-idle`) are mounted only with `OPENPOKE_LTM_DEBUG=1` / `OPENPOKE_LTM_TEST_HOOKS=1` and reject non-loopback clients. State output is sanitised: MEMORY_SAFE text, status edges, tombstone metadata without `value_hmac`, and never rejected values |
| **Why** | The server binds `0.0.0.0` with no auth (F-1). An ungated memory-state endpoint would be a new leak |
| **Alternative considered** | Always-on endpoints; file-only traces |
| **Tradeoff** | The interactive demo must run on the same machine |
| **Prototype / Production** | As above / authenticated admin access, no test hooks |

### D27. Two-variant race protection: tombstone even when the slot is empty

| | |
|---|---|
| **Decision** | A forget that resolves (via stored rows *or* the intent lexicon) to a slot writes a slot tombstone even if no row exists yet |
| **Why** | Otherwise "forget X" issued while X's ingestion job is still in flight resolves nothing, and the late job creates X after the user asked to forget it |
| **Alternative considered** | Wait for the ingest queue to drain before forgetting (adds latency and still races with retries) |
| **Tradeoff** | A tombstone may exist for a slot that never held a value (harmless) |
| **Prototype / Production** | Same |

### D28. Gate on deterministic runs; prove context composition, not prose

| | |
|---|---|
| **Decision** | The acceptance gate runs with the lab mock OpenRouter + RuleExtractor and asserts on stored state, events, captured model payloads and byte canaries, using three probe kinds (`same_session`, `new_conversation`, `after_restart`). A `--live` run is optional, for slide answers |
| **Why** | Reproducible, CI-able. Claims stay honest: "the old value is not in the LTM block / not in a new conversation's context", rather than "the model said X" |
| **Alternative considered** | Gate on live-model answers |
| **Tradeoff** | Doesn't prove extraction generality (that's the §19 eval set) or the model's wording |
| **Prototype / Production** | Same; production adds the large eval set and online metrics |
