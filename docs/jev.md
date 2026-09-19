# Typed decisions with Jev

Configuration, failure behaviour, and — more importantly — what this layer has
and has not been measured to do.

## Configuration

Everything is optional. Without `TYPESAFE_API_KEY` the layer is inert.

| Variable | Default | What it does |
| --- | --- | --- |
| `TYPESAFE_API_KEY` | unset | Turns the layer on. |
| `TYPESAFE_BASE_URL` | unset | Route through a gateway. Origin only: the SDK appends `/v1/systemone`. |
| `JEV_MODEL` | `jev-1.13.0` | Pinned, not an alias. |
| `JEV_DEADLINE_SECONDS` | `6.0` | Hard wall-clock ceiling per decision. |
| `JEV_GUARDRAIL_DEADLINE_SECONDS` | `3.0` | Tighter ceiling on the agent's hot path. |
| `JEV_TIMEOUT_SECONDS` | `3.0` | Per-HTTP-request timeout. |
| `JEV_MAX_RETRIES` | `1` | SDK retries. |
| `JEV_STATE_CHAR_BUDGET` | `24000` | Body clipping. |
| `JEV_SEARCH_MAX_CANDIDATES` | `20` | Cap on search results scored per call. |
| `JEV_QUARANTINE_INJECTIONS` | `1` | Withhold a flagged body but tell the user. `0` drops it silently. |
| `JEV_EMAIL_SCREENING` | `1` | Per-decision off switch. |
| `JEV_TOOL_GUARDRAIL` | `1` | Per-decision off switch. |
| `JEV_SEARCH_FILTER` | `1` | Per-decision off switch. |
| `JEV_DECISION_LOG` | `1` | Write probabilities to `server/data/jev_decisions.jsonl`. |
| `JEV_DECISION_LOG_MAX_ENTRIES` | `2000` | Bound on that file. |

## Why the model is pinned

An alias moves when a release ships, and the thresholds in
`server/jev/thresholds.py` are calibrated against one model. Upgrading is a
deliberate act that should be followed by re-checking the thresholds.

## Failure policy: open, and bounded

Outages, rate limits, malformed responses and timeouts all degrade to the
pre-existing behaviour rather than blocking the assistant. TypeSafe publishes no
guidance either way; this is a choice.

Every call also carries a hard `asyncio.wait_for` deadline, because the SDK's
retry budget does not bound wall time: it decides whether to sleep again before
sleeping, so the final attempt still gets a full request timeout on top of the
budget. Measured against a blackholed endpoint, a 12-second budget took 16
seconds. The guardrail runs before every tool call inside a run the batch
manager caps at 90 seconds, so roughly five dead calls would have turned a
fail-open guardrail into a user-visible timeout.

## The decision log

Each decision writes its probabilities, verdict and reason — never the email
body — to a bounded JSON-lines file. Thresholds are only re-tunable offline if
the numbers were stored: a sweep over the log costs nothing, while a sweep that
has to re-ask the model costs a run of the whole mailbox.

## Notes on the thresholds

- **They are defaults, not truths.** Jev is calibrated across a population of
  answers rather than per answer, so the right cut points depend on the
  operator's mail. TypeSafe's own guidance for finding them is "test thresholds
  by plotting confidence against accuracy on your data".
- **`noul` answers carry no `confidence` field.** The probability is the signal
  and values near 0.5 are the uncertain region, which is why each gate here is a
  two-sided band. The three-tier confidence-routing pattern in TypeSafe's docs is
  defined on Choice and Score, not on Noul.
- **No dates are sent to Jev.** jev-1.13 reads dates as text rather than as
  ordered quantities, so email age and schedule reasoning stays in Python.
- **The guardrail has three rungs and only one stops a call.** Off-task steers
  and never holds, following pi-warden's replay over 17,160 guarded tool calls,
  which found off-task the weakest of four signals against user regret (AUC 0.51
  against 0.74 for "does this mutate state") and the cause of 56 of 139 holds
  with no user complaints. A `mutates` question is asked and logged but nothing
  gates on it yet.

## What has been measured

`docs/injection-findings.md` reports 43,776 requests against attacker-authored
email bodies. In short: nothing could force an email to be surfaced, but
*silencing* one was easy, and the injection question wired to a silent drop was
the easiest route of all. That is why a flagged body is quarantined rather than
dropped.

## What has not

- **There are no accuracy numbers.** No labelled set exists, and the 90 tests
  verify routing logic, not judgement quality. The contamination experiment
  measures robustness, not accuracy.
- **The cost story only holds on the skip path.** On the surface path the layer
  makes a Jev call *and* a summarisation call, and falls through to the original
  classifier if the summary comes back empty.
- **The gate may be looser than the boolean it replaced.** Security codes
  surface at 0.60 while general importance needs 0.75, and the uncertain band
  still reaches the original classifier, so the set of surfaced mail may be a
  superset of today's.
- **`IRREVERSIBLE_TOOLS` is an enumeration**, and enumerations go stale. Names
  are matched ignoring case and separators so a rename does not silently disarm
  the rung, and the model's own `irreversible` answer is an independent second
  route, but an allow-list of this shape has been publicly bypassed elsewhere.
