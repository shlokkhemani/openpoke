# OpenPoke: Evaluation Plan

How to test the agent system, show that it works, and compare **original OpenPoke** with **this fork** on the same test cases. Gmail is disconnected and email features are **not tested**. Companion to [1-original-openpoke-architecture.md](1-original-openpoke-architecture.md) and [2-problems-and-solutions.md](2-problems-and-solutions.md).

---

## 1. Scope

What's covered:

| Part | Status | Why |
|---|---|---|
| Interaction agent (Poke): chat, routing, delegation | ✅ fully testable | Doesn't need Gmail |
| Execution agents: **triggers** (`createTrigger` / `updateTrigger` / `listTriggers`) | ✅ fully testable | Local SQLite (`data/triggers.db`); **scoped per agent name** |
| Trigger scheduler firing back to the user | ✅ testable | Runs the execution agent; the result flows back through Poke |
| Conversation summarization / compaction | ✅ testable | Runs on the conversation log only |
| Gmail tools, `task_email_search`, important-email watcher | ❌ out of scope | Kept simple; no inbox connected |

**Reminders** become the main way to test real task execution. They have every property the architecture problems depend on: multi-turn follow-ups, ownership by a single agent, recurring state, and results that come back later.

---

## 2. Goals

1. **Correctness:** reminders are created, changed, listed and cancelled correctly: right time, timezone and recurrence.
2. **Routing:** Poke answers chit-chat itself, delegates real tasks, routes follow-ups to the right agent, and doesn't split one goal across several agents.
3. **Efficiency:** latency, LLM calls, tokens, split rate and agents shown to Poke. This is where the fork's changes should show up.
4. **Comparability:** the same scenarios, models and settings on both versions.

---

## 3. How a test run works

The **harness** is the test program (`evals/`). It plays a test case against a running OpenPoke server and records what happens.

**It only uses what both versions have in common.** The two versions differ only in the agent architecture: how agents hand off, route and remember. The API, LLM client, reminder system and data files are shared, and the harness uses only those. It does three things:

1. **Chats like a user.** It sends messages through the same API the web UI uses (`POST /api/v1/chat/send`) and reads the replies (`GET /api/v1/chat/history`).
2. **Records every LLM call.** It wraps the one function every agent uses to call the LLM (`request_chat_completion`), and logs how long each call took, how many tokens it used, and which agent made it.
3. **Reads the data files** after each turn: the reminders (`triggers.db`), the agent list (`roster.json`) and the conversation summary. The fork changes `roster.json` from a list of names to records (problems-and-solutions §3a), so the harness counts entries and works with either format.

**Every run starts the same way:**
- **Clean data:** `server/data/` is wiped first. Each version runs from its own checkout, because these paths are hard-coded.
- **Same timezone:** set at the start (default `America/Los_Angeles`). Expected reminder times are computed in that timezone.
- **Same models:** both versions use identical model settings.
- **No Gmail, watcher off.**

**Practical details:**
- **Firing reminders now.** Instead of waiting until "tomorrow 9am", the harness edits the reminder's time to now, and the scheduler fires it within about 10 seconds.
- **When a turn is finished:** no LLM call is running and nothing new has appeared in the chat for 5 seconds. A turn that takes over 180 seconds fails as a timeout.
- **Repeats:** each case runs 5 times per version, because LLM answers vary from run to run.

---

## 4. Test cases

The full scenario set is in **[4-test-cases.md](4-test-cases.md)**: 21 cases in four groups. They're implemented as YAML files in `evals/scenarios/`; see `evals/README.md` for how to run them.

- **A. Handoff & context (§1),** 4 cases: follow-up edits, clarification answers, earlier-turn context, and a large input (handoff cost and detail preservation).
- **B. Task granularity (§2),** 5 cases: bundled reminders with a follow-up, a mixed message, and three single goals built to tempt splitting (B3–B5).
- **C. Agent sprawl & reuse (§3),** 4 cases: reuse among active and finished agents, recall and prompt growth across many tasks, similar names, and hard follow-ups (synonym, time, recency).
- **R. Regression,** 8 cases: existing features that must not get worse (chit-chat, one-shot and recurring create-and-fire, list, cancel, compaction, invalid time, timezone).

Each case lists an optional `config`, scripted user turns, deterministic `check`s and a `judge` focus. Metrics are recorded for every case automatically.

---

## 5. Evaluators

### 5a. Deterministic checks (pass/fail)

- **Trigger state** (from `triggers.db`):
  - Count, `next_trigger` (within ±1 min of expected), `recurrence_rule`, `status` and payload keywords.
  - Updates change existing rows instead of creating duplicates.
- **Delivery:** a fired trigger produces exactly one user-visible message.
- **Completion:** every turn gets a reply, with no timeouts or crashes.

### 5b. LLM-as-judge (one score, 1–5)

The checks already verify the end state, for example that the trigger is at the right time. The judge covers what they can't: **reply quality**. Were the assistant's messages correct and clear to the user? Examples: confirming the right time, asking when information is missing or ambiguous, explaining a problem.

The judge gets the transcript, the final trigger table and the case's `judge` focus, and returns **one score from 1 to 5**.

Calibration:
- Use a different, stronger model than the agent under test.
- Ask for a justification before each score.
- Hand-label about 30 transcripts and report how often the judge agrees.

### 5c. Efficiency metrics (from the LLM and state traces)

| Metric | Definition |
|---|---|
| **Latency** | From the user message to the last assistant message of that turn, which is usually the result (for example "set for 9am") rather than an acknowledgement |
| **Total turn latency** | From the user message until the turn is done |
| **LLM calls per user turn** | Split by role: interaction / execution / summarizer |
| **Tokens per user turn** | Input and output, split by role, with cost from one shared price table |
| **Split rate** | Share of runs where one goal ended up in more than one agent: agents created > the scenario's `goals:` count (§2). Reusing an agent is not penalized |
| **Roster size over time** | For the sprawl scenarios (§3) |
| **Agents shown to Poke per call** | Distinct agents Poke can see in each of its LLM calls: the original's full agent list, or the fork's `find_agents` results |

---

## 6. Comparison protocol: original vs fork

1. **Only the agent code differs.** The OpenPoke server code (original vs fork) is the one variable. Pin everything else: models, scenarios, timezone, the eval harness (the `evals/` test code that drives and measures both versions) and the judge.
2. **Run** each scenario k = 3 times per version, in alternating order (A, B, A, B), so API latency drift affects both versions equally. Up to 4 runs execute in parallel.
3. **Pair the results by scenario** and report:
   - Deterministic pass rates, with each scenario counting as a pass only if all k runs pass, plus the cases that flipped fail→pass and pass→fail.
   - For every metric (task completion, reply quality, latency, calls, tokens, split rate): the mean per-case value for each version and the paired 95% t-interval of the per-case differences (fork − original). A few large cases (A4, C2) dominate the token and latency differences, so read those intervals with that in mind.
4. **Treat it as a regression gate.** The fork must not do worse on correctness. Efficiency gains count only if quality holds.
5. **Look at the per-case table** to see where each proposal's effect shows: follow-ups for §1, bundled goals for §2, reuse and recall for §3.

### Results template

| Category | Version | Task completion | Reply quality (1–5) | Latency | LLM calls | Tokens (in/out) | Split rate |
|---|---|---|---|---|---|---|---|
| Follow-up refs | original | | | | | | |
| Follow-up refs | fork | | | | | | |
| … | | | | | | | |

Include 2–3 side-by-side transcripts, for example the 3-meds case and the reuse-after-10-reminders case, to make the numbers concrete.

**State the limitation in the write-up:** email features (search, drafting, sending) are not covered.

---

## 7. Repo layout and steps

```
evals/
  harness/      # server launcher, HTTP client, LLM-call recorder, trigger fast-forward, turn-done detection
  scenarios/    # *.yaml
  evaluators/   # trigger-table checks, judge prompts
  run.py        # --version original|fork --scenarios ... --repeats 5
  report.py     # paired comparison → markdown table
```

1. Build the LLM-call recorder and the trigger fast-forward, and confirm both work on the **original** version.
2. Implement a core subset of 4-test-cases.md (R1, R2, A1, B1, C1) with deterministic checks.
3. Record an original-version baseline.
4. Add the judge, calibrate it on about 30 hand-labeled transcripts, then expand to the full set.
5. Run the paired comparison after each rollout step in 2-problems-and-solutions.md.
