# OpenPoke: Test Cases

The scenario set for [3-evaluation-plan.md](3-evaluation-plan.md). Gmail is disconnected, so every task uses reminders (triggers). The runnable versions, with concrete messages and structured checks, are in `evals/scenarios/*.yaml`.

Two cases use fixed relative times so results don't depend on what time of day the eval runs: B2 says "tomorrow at 6pm", and C3's card reminder has a time.

| Group | Covers | Cases | Expected original → fork |
|---|---|---|---|
| **A. Handoff & context** | §1 of 2-problems-and-solutions.md | A1–A4 | Same or better quality, lower latency and tokens |
| **B. Task granularity** | §2 | B1–B6 | Lower split rate, fewer calls, same or better quality |
| **C. Agent sprawl & reuse** | §3 | C1–C4 | Correct routing at scale, few agents shown to Poke |
| **R. Regression** | Existing features of the original repo | R1–R8 | **No worse.** These guard against the fork breaking something |

---

## Conventions

```yaml
id: …
config: { … }           # optional; applied before the case starts (e.g. timezone)
turns:                  # run in order; harness waits until each turn is done
  - user: "…"           # send a message
  - fire_triggers: all  # harness action: set next_trigger = now, wait for the scheduler
  - fire_triggers: payload~(a|b)  # same, but only active triggers whose payload matches
check:                  # deterministic, pass/fail (all must pass)
judge:                  # what the judge looks at for reply quality (one score, 1–5)
```

- **Times are relative.** `tomorrow 09:00` is resolved by the harness in the scenario's timezone. A time check passes within ±1 min.
- **Default config:** fresh `data/`, timezone `America/Los_Angeles`, no Gmail, watcher off. A case's `config` overrides these.
- **Metrics** (latency, tokens, LLM calls, agents created, agents shown to Poke) are recorded for every case automatically, so cases don't list them.
- **`goals: N`** in each scenario is the number of separate user goals. A run where more agents were created than that counts as **split**.
- **Trigger checks** read `triggers.db` and filter rows by payload keyword. `active` means `status = active`. A cancelled trigger has `status` ∈ {`paused`, `completed`}.
- **Agent counts** read the roster: the number of entries added during the scenario.
- **Always-on checks** apply to every case and aren't repeated below: every turn gets a reply, with no timeout.

---

## A. Handoff & context (§1)

These test whether the user's intent reaches the execution agent intact, and how much the round trip costs.

### A1. Follow-up edits in place
```yaml
id: A1-follow-up-edit
turns:
  - user: "remind me to call mom tomorrow at 9am"
  - user: "actually make it 10"
  - user: "and do it every sunday"
check:
  - triggers(payload~"mom"): count == 1, active
  - next_trigger == "next sunday 10:00"
  - recurrence_rule contains "FREQ=WEEKLY" and "BYDAY=SU"
judge: each confirmation states the updated time and schedule correctly
```

### A2. Clarification answer
```yaml
id: A2-clarification
turns:
  - user: "remind me about the dentist"
  - user: "4pm tomorrow"          # answer to the expected "when?"
check:
  - after turn 1: no trigger fires immediately (none with next_trigger <= now + 1 min)
  - triggers(payload~"dentist"): exactly one, due between now and tomorrow 16:00
judge: asks for the time instead of guessing; understands the bare answer
```

### A3. Context from earlier turns
```yaml
id: A3-earlier-context
turns:
  - user: "heads up, I'm in Berlin this week"
  - user: "how's your day going"
  - user: "lol fair"
  - user: "remind me tomorrow at 9am to check in for my flight home"
check:
  any_of:
    - triggers(payload~"check in"): 9am Berlin time, tomorrow (counted from the Berlin or the home date)
    - no trigger created AND reply asks which timezone
judge: earlier "Berlin" context used or explicitly clarified, not silently ignored
```
*This is the known `read_conversation` gap (problems-and-solutions §1). The fork may not beat the original here, and that result should be reported either way.*

### A4. Large input: handoff cost and detail preservation

The original has Poke rewrite the request into `instructions`, so a long message means a long, slow handoff, and paraphrasing tends to drop details. In the fork, the handoff is a fixed-size `delegate(name)` and the agent gets the message verbatim.

```yaml
id: A4-large-input                # ~250 words
turns:
  - user: |
      remind me friday at 8pm to pack for the Denver trip. here's everything:

      carry-on: passport, the BLACK phone charger (not the white one, it's broken),
      laptop + laptop charger, headphones, the printed hotel confirmation,
      a pen for the customs form, allergy meds, and the reusable water bottle
      (empty it before security).

      checked bag: 4 pairs of socks, 3 t-shirts, 2 pairs of jeans, the grey hoodie,
      the green rain jacket (NOT the blue one, the zipper is stuck), running shoes,
      hiking boots, toothbrush, toothpaste, contact lens case AND solution,
      sunscreen, and the gift for Sam (wrapped, in the side pocket).

      backpack: trail snacks, the small first-aid kit, sunglasses, a headlamp,
      and the paper trail map.

      if the forecast says below 30°F, also pack the thermal layer and gloves.
      don't pack the camping stove, Sam is bringing one. and skip the umbrella,
      the jacket is enough.
check:
  - triggers: count == 1, next_trigger == "friday 20:00"
  - payload contains all items:
      [passport, black charger, laptop, headphones, hotel confirmation, pen,
       allergy meds, water bottle, socks, t-shirts, jeans, grey hoodie,
       green rain jacket, running shoes, hiking boots, toothbrush, toothpaste,
       lens case, solution, sunscreen, gift for Sam, trail snacks, first-aid kit,
       sunglasses, headlamp, trail map, thermal layer, gloves]
  - payload keeps all constraints:
      [not the white charger, empty the bottle before security, 4 socks / 3 t-shirts / 2 jeans,
       not the blue jacket, thermal + gloves only if below 30°F,
       no camping stove, no umbrella]
  - wait_for_triggers → the reminder is delivered to the user (it may summarize the list)
judge: confirmation and fired reminder are clear and correct (summarizing the list is fine); negations not flipped
```
When reading the cost difference, use Poke's **output** tokens and latency. The user's message adds the same input tokens to both versions.

---

## B. Task granularity (§2)

These test whether one user goal maps to one execution agent.

### B1. Bundled reminders, then a follow-up
```yaml
id: B1-three-meds
turns:
  - user: "set reminders for my 3 meds every day: vitamin D at 8am, metformin at 2pm, and melatonin at 8pm"
  - user: "skip the 2pm one, my doctor dropped it"
check:
  - after turn 1: triggers(payload~"med"): count == 3, all active, daily, at 08:00 / 14:00 / 20:00
  - after turn 1: all 3 triggers share one agent_name
  - after turn 2: exactly 2 active (08:00, 20:00); the 14:00 one paused/completed
judge: one clear confirmation for all three; then confirms which one was dropped
```
*In the original, the three triggers can end up in three separate agents, so the follow-up has to pick the right one by name alone.*

### B2. Unrelated goals in one message
```yaml
id: B2-mixed-message
turns:
  - user: "remind me to call mom tomorrow at 6pm, and how's your week been?"
check:
  - triggers(payload~"mom"): count == 1, next_trigger == "tomorrow 18:00"
  - agents_created == 1
judge: chit-chat answered by Poke naturally alongside the confirmation
```

### B3–B5. Single goals that tempt splitting
These are single goals with independent parts. That's the pattern that made the original split A4 into a packing agent plus a weather agent. Each has `goals: 1`, and the main result is the **split rate**.
- **B3 birthday prep:** cake, card and call reminders on different days.
- **B4 trip prep with forecast:** two reminders plus a "check the forecast" part that no tool can do.
- **B5 gym week:** gym reminders Mon/Wed/Fri at 7am, plus "pack your bag" the night before each at 9pm.

Checks: the reminders exist and all share one `agent_name`. The YAML files are in `evals/scenarios/`.

### B6. Several unrelated tasks in one message
"remind me on the 1st at 9am to pay the internet bill, on friday at 10am to call the pharmacy, and every evening at 7pm to walk the dog". These are three separate goals (`goals: 3`). Checks: each reminder exists exactly once, with 3 active reminders in total, so no agent redid another agent's part.

---

## C. Agent sprawl & reuse (§3)

These test whether the right agent is found and reused as the number of agents grows, and whether Poke's prompt stays bounded.

### C1. Reuse among active and finished agents
```yaml
id: C1-reuse-after-10
turns:
  - user: "remind me to call mom sunday at 6pm"
  - user: "<5 one-shot reminders due within the hour, one per turn: laundry, oven, parking meter, call back Jen, take pills>"
  - fire_triggers: payload~(laundry|oven|parking|Jen|pills)   # these 5 fire and complete
  - user: "<5 more unrelated reminders, one per turn, still active: gym, water plants, rent, dentist, trash>"
  - user: "push the mom one to 7"
check:
  - triggers(payload~"mom"): count == 1, active, next_trigger == "sunday 19:00"
  - the "mom" trigger's agent_name unchanged since turn 1
  - the 5 fired triggers are completed; the 5 other distractors are unchanged
judge: confirms the change to the mom reminder, with no mention of other reminders
```
*There are 10 distractor agents: 5 finished and 5 still active. The original lists all 11 names with no status. The fork has summaries, statuses and ranking.*

### C2. Recall across many tasks, and prompt growth
```yaml
id: C2-list-tomorrow
turns:
  - user: "<20 reminders over the next 7 days, one per turn, 4 of them tomorrow>"
  - user: "what reminders do I have tomorrow?"
check:
  - all 20 triggers created and active
  - reply lists exactly the 4 tomorrow reminders (keyword match), no extras
judge: complete, correct, concise
```
*`listTriggers` only returns the calling agent's own triggers, so no single agent can answer the last question. Poke has to work from what it knows about its agents. The report also plots **Poke's prompt tokens over the 20 setup turns** and the final roster size. The slope shows whether the prompt stays bounded.*

### C3. Similar names
```yaml
id: C3-disambiguation
turns:
  - user: "remind me to call mom sunday 6pm"
  - user: "remind me to call mom's doctor monday 10am"
  - user: "remind me to buy mom a birthday card friday at 5pm"
  - user: "cancel the doctor one"
check:
  - triggers(payload~"doctor"): paused/completed
  - the other two "mom" triggers still active
judge: picks the right one, or asks if it's genuinely unclear
```

### C4. Hard follow-ups: synonym, time, recency
Ten reminders, one per turn. Then three follow-ups that share no keywords with the request they refer to, so the agent search (`find_agents`) has to work for them:
- **"move the pills one to 9pm"** → the meds reminder. A synonym: "pills" vs "meds".
- **"cancel the 3pm one"** → the vet reminder. Only the time identifies it.
- **"push the last one I set back by a day"** → the library books reminder. Only recency identifies it.

Checks: each change lands on the right reminder, through the agent that created it, and nothing else changes. The YAML is in `evals/scenarios/C4-hard-routing.yaml`.

---

## R. Regression: existing functionality

These must pass on the original repo, and the fork must not do worse on them.

### R1. Chit-chat only
```yaml
id: R1-chit-chat
turns:
  - user: "hey, how's it going"
check:
  - agents_created == 0, no LLM calls with role = execution
judge: replies naturally to the greeting
```
*This is the control case: latency should be equal across versions.*

### R2. One-shot reminder: create and fire
```yaml
id: R2-one-shot
turns:
  - user: "remind me to take the laundry out in 30 minutes"
  - fire_triggers: all
check:
  - after turn 1: triggers: count == 1, active, next_trigger == "now + 30 min", recurrence_rule empty
  - exactly 1 new user-visible message after the firing, mentioning "laundry"
  - trigger status == completed
judge: confirms the time clearly; the reminder message is clear
```

### R3. Recurring reminder: create and fire
```yaml
id: R3-recurring
turns:
  - user: "remind me to take meds every weekday at 8am"
  - fire_triggers: all
check:
  - after turn 1: recurrence_rule contains "FREQ=WEEKLY" and "BYDAY=MO,TU,WE,TH,FR" (any order)
  - after turn 1: next_trigger == next weekday 08:00
  - exactly 1 user-visible message after the firing, mentioning "meds"
  - trigger still active; next_trigger moved to the next weekday 08:00 after the firing
```

### R4. List reminders
```yaml
id: R4-list
turns:
  - user: "remind me to water plants tomorrow 9am"
  - user: "what reminders do I have?"
check:
  - reply mentions "water plants" and "9"
```
*This is the basic listing guard. C2 tests listing at scale.*

### R5. Cancel a reminder
```yaml
id: R5-cancel
turns:
  - user: "remind me to call the bank tomorrow at noon"
  - user: "never mind, cancel that"
check:
  - triggers(payload~"bank"): status in (paused, completed)
  - fire_triggers: all → no "bank" message shown to the user
```

### R6. Compaction keeps facts
```yaml
id: R6-compaction
config: { conversation_summary_threshold: 20, conversation_summary_tail_size: 5 }   # same in both versions, to keep the run short
turns:
  - user: "fyi my sister's name is Ana"
  - user: "<~15 chit-chat turns, enough to cross the threshold>"
  - user: "remind me to call my sister tomorrow at 7pm"
check:
  - working memory contains a conversation_summary (compaction ran)
  - triggers: payload contains "Ana"
judge: uses the remembered name naturally
```

### R7. Invalid time
```yaml
id: R7-past-time
turns:
  - user: "remind me yesterday at 5pm to call Joe"
check:
  - no trigger with next_trigger in the past or within 1 min of now
judge: points out the problem and offers an alternative
```

### R8. Timezone respected
```yaml
id: R8-timezone
config: { timezone: Asia/Tokyo }
turns:
  - user: "remind me at 8am tomorrow to call the office"
check:
  - next_trigger == "tomorrow 08:00 Asia/Tokyo"
```

---

## Coverage summary

| Group | Cases | Where the fork should differ |
|---|---|---|
| A | 4 | Latency and LLM calls; details preserved (A4) |
| B | 5 | Split rate, LLM calls, tokens |
| C | 4 | Routing of follow-ups (C1, C3, C4), agents shown to Poke |
| R | 8 | Should not differ: no regressions; R1 is the latency control |
| **Total** | **22** | |

Add a regression case for every bug found.
