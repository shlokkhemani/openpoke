# Fixed user workload

Send 150 setup messages and observe how many agents the interaction agent creates.
There is no target roster size, early stopping, or reserve pool. The two message
files contain only ordered user strings. Timing schedules and a bootstrapped
inbox define the environment; the application generates agents and histories.

Setup mixes travel, billing, recruiting, customer projects, household tasks,
appointments, subscriptions, events, learning, hobbies, and personal planning.
It includes independent requests, revisions, returns to older topics, and multiple
topics in one request. The separate 20 test messages include explicit references,
contextual shorthand, old topics, a new request, and ambiguity where clarification
is reasonable. Do not shuffle either sequence.

Requests supply their facts. `email_messages.json` bootstraps 20 local emails:
18 supporting context/contact messages and two background messages. It does not
contain execution-agent outputs or future replies. Some topics have no email;
they can still be handled from the user-supplied facts, with placeholders or
clarifying questions when a recipient or other detail is missing. Missing emails
must not be scored as a routing failure automatically.

The inbox keeps initial facts consistent with user requests and all messages
visible at the default initial clock.
Subsequent user updates may supersede initial emails, as in a real conversation.

Drafting still requires configured application tools. Use an isolated tool
environment. The runner does not change the clock; dates in messages are task
details. Local inbox search is a simplified token/alias search, not a complete
Gmail query implementation, and contacts lookup currently returns an empty list.
These limitations apply identically to both comparison modes.

## Validate and preview

Python 3.10+. Message validation and the runner use the standard library; the
server and transport tests use the installed server environment. From repo root:

```bash
python3 -m benchmarks.user_workload
python3 -m unittest benchmarks.user_workload.test_validation -v
python3 -m unittest benchmarks.user_workload.test_email_backend -v
server/venv/bin/python -m unittest discover -s benchmarks -t . -v
python3 -m benchmarks.user_workload.run
```

## Run

Start an isolated OpenPoke server. For comparison, run the same workload from
empty state in both full-roster and shortlist modes, allowing each roster to
grow independently. Both modes are available on `roster-shortlisting`:

- Full roster (default): `OPENPOKE_ROSTER_SHORTLISTING_ENABLED=0`.
- Shortlist: `OPENPOKE_ROSTER_SHORTLISTING_ENABLED=1`.

Set the variable when starting the server, and restart the server when changing
modes. The matcher uses `OPENPOKE_ROSTER_EMBEDDING_MODEL` (default
`openai/text-embedding-3-small`). It selects 5% of the roster, rounded up, with a
minimum of 5 and maximum of 50 agents, capped at the roster size. Configure those
with `OPENPOKE_ROSTER_MATCH_PERCENTAGE`, `OPENPOKE_ROSTER_MATCH_MIN_SIZE`, and
`OPENPOKE_ROSTER_MATCH_MAX_SIZE`. Agent profiles use the latest 5 assigned tasks
(`OPENPOKE_ROSTER_MATCH_RECENT_TASKS`). Small rosters that fit the shortlist skip
embeddings. Both user messages and execution-agent updates use the chosen mode.
Embedding failures stop the interaction instead of silently using the full roster.
Each run's embedding cache lives under its own `OPENPOKE_DATA_DIR`.
Routing mode, embedding model, and matcher settings are saved in the initial/final
snapshots and included in reports; they may differ between comparison modes.
The runner uses `POST /api/v1/chat/send`, `GET /api/v1/benchmark/status`,
`GET /api/v1/benchmark/snapshot` and `GET /api/v1/benchmark/metrics`. It requires
isolated data/tools, a local email backend, and metrics version 1.
Configure the server to use this workload's inbox:

```bash
OPENPOKE_ROSTER_SHORTLISTING_ENABLED=0 \
OPENPOKE_BENCHMARK_MODE=1 \
OPENPOKE_BENCHMARK_TOOLS_ISOLATED=1 \
OPENPOKE_BENCHMARK_EMAIL_FIXTURE="$PWD/benchmarks/user_workload/email_messages.json" \
OPENPOKE_DATA_DIR=/tmp/openpoke-user-workload-fresh \
server/venv/bin/python -m server.server --port 8011
```

Use a fresh directory for each fresh run; setting a data path does not clear it.

```bash
python3 -m benchmarks.user_workload.run --live \
  --base-url http://127.0.0.1:8011/api/v1
```

Live runs incur model costs. Bundled timing schedules are selected automatically:
`setup_schedule.json` defines ten bursts (22 of 150 messages); `test_schedule.json`
defines three bursts (6 of 20 messages). Bursts include an extra requirement,
a correction, a short contextual revision, and unrelated requests sent rapidly.
Other messages are sent individually after preceding work finishes.

Within a burst, messages are submitted at fixed offsets of 0/2 seconds,
0/3 seconds, or 0/2/4 seconds, without waiting for earlier responses. This sends
corrections while interaction work or execution work may still be in flight.
The runner waits for all submitted user messages to be recorded and all work
to become idle before the next group. HTTP 202 alone is not completion.

The same requested timing applies to both comparison modes regardless of speed.
The journal records actual arrival offsets, active interaction count, pending
execution count, and whether earlier work was still pending. A fast response
may finish before the next arrival; that is recorded as no observed overlap,
not hidden or retried. Scheduling and HTTP overhead can delay actual arrivals.
The runner does not serialize or fix the application's concurrent agent behavior;
any same-agent races are part of what these scenes expose.

Default group completion timeout is 600 seconds after submission. For a smoke
run add `--limit 2`; the limit must not split a burst. Use fresh server state
afterward for the full run. Custom input files are sequential unless supplied
`--schedule path/to/schedule.json` with the same timing schema.

The runner never clears state. It requires empty state unless explicitly passed
`--allow-existing-state`. It records each submission and acceptance, roster size
before/after the group, and final status in ignored `results/<timestamp>/run.jsonl`.
Histories remain in the server's data directory and are copied into final snapshots.
Roster changes within a burst are reported for the whole group; they are not
attributed to individual simultaneous messages. The journal includes a copy of
the consumed messages and schedule for reproducibility. Use the same inbox and
initial server clock for both comparison modes as well.
Errors stop the run and preserve partial logs. Requests are never automatically
retried because a lost response could otherwise duplicate a submitted task.
Inspect partial state before restarting: `--allow-existing-state` appends the
entire supplied sequence and is not an automatic resume feature.

The 150-message workload is itself the comparison sequence. If you also want the
20 extra messages, append them to each mode's own resulting state in separate
output directories. Do not copy one mode's generated state over the other:

```bash
python3 -m benchmarks.user_workload.run --live --allow-existing-state \
  --messages benchmarks/user_workload/test_messages.json \
  --base-url http://127.0.0.1:8011/api/v1
```

Freeze inputs before comparison and apply any changes to both modes. Both rosters
can grow.

## Measurements and saved outcomes

The report measures **full roster size**: initial size, last completed size, and
growth after each completed group, plus **input tokens** in the scope below.
Response quality is not automatically scored.
Inspect the saved requests, replies, and tool actions directly. Fewer agents alone
does not establish better task performance.

Dollar cost, response latency, and roster-context length are not scored. Arrival
offsets and timeouts remain only to drive/verify overlapping input delivery.

The server saves local email-tool evidence to
`<OPENPOKE_DATA_DIR>/benchmark_events.jsonl` in benchmark mode only. The same
ledger records input-token usage for interaction calls and shortlist embeddings.

- **No shortlisting:** sum interaction LLM input tokens across all its calls.
- **Shortlisting:** that same sum plus embedding input tokens for queries and
  agent profiles. Reusing cached embeddings adds no tokens.

Interaction input includes the entire prompt ingested on each call: instructions,
history, roster, tool definitions and tool results, including cached input tokens
as reported by the provider. Output tokens and execution/search/summarization/
classification calls are excluded, even when they use the same model. Embedding
vectors are not output tokens. Counts come from response `usage.prompt_tokens`
(or `input_tokens`); embedding usage may also use `total_tokens`.
See [OpenRouter usage accounting](https://openrouter.ai/docs/cookbook/administration/usage-accounting).

Missing usage or failed transport attempts are marked unknown, without blocking
the application or making automatic recovery calls. Each record saves response ID,
request outcome, HTTP status when available, exception type, and only returned
input-usage fields. Prompts, response text, output-token counts, and vectors are not
included in token records. Reports expose known counts and missing
usage counts; exact totals/comparisons stay null when coverage is incomplete.
Each interaction request is recorded, including failed transport attempts. Chat
and embedding requests are not automatically retried. Runs without token tracking
are reported as unavailable, not zero; counts cannot be recovered from saved text
alone.

For a successful interaction response with missing usage and a saved response ID,
preview metadata recovery, then explicitly fetch it if wanted:

```bash
server/venv/bin/python -m benchmarks.user_workload.recover_input_tokens RUN_DIRECTORY
server/venv/bin/python -m benchmarks.user_workload.recover_input_tokens RUN_DIRECTORY --fetch
```

This only makes GET requests to OpenRouter's
[`/generation` metadata endpoint](https://openrouter.ai/docs/api/api-reference/generations/get-generation).
It never generates or retries a model response. Only matching generation ID/model
and `native_tokens_prompt` are accepted; normalized `tokens_prompt` is not used as
a substitute. Failed requests, embeddings, missing IDs, unavailable native counts,
or failed lookups remain unknown. A lookup is attempted once per eligible event
per invocation; already recovered counts are reused.

Recovery saves `input-token-recovery.json` separately, leaving original ledgers and
snapshots untouched. Reports validate its link to the exact original event ledger
and show how many counts were recovered. Changed or stale recovery data is rejected.
Responses without a saved response ID cannot be recovered through this command.

Benchmark chat calls allow 180 seconds of response-read inactivity. Override with
`OPENPOKE_BENCHMARK_MODEL_READ_TIMEOUT` (positive seconds) if needed; use the same
setting for both comparison modes. Benchmark execution tasks have a separate
210-second total timeout. Normal application calls retain a 60-second read timeout
and execution tasks retain a 90-second total timeout. A partial run is never
presented as a complete comparison.

Each run saves:

- `initial_snapshot.json` and `final_snapshot.json`: environment, models, full
  conversation, execution histories, local drafts, and reminders.
- `application_events.json`: email actions for this run, updated after each group;
  partial evidence is fetched on ordinary errors when the server is reachable.
- `evidence/<first-message-index>.json`: the requests, prior user-visible
  conversation, current outputs/actions, visible inbox facts, and before/after
  draft/reminder state for one completed group. These omit roster/rankings and
  execution-agent histories.
- `run.jsonl`: input copies, arrival observations, group completion, full-roster
  growth, and hashes tying evidence to the run.

## Reports (offline)

```bash
server/venv/bin/python -m benchmarks.user_workload.report RUN_DIRECTORY
server/venv/bin/python -m benchmarks.user_workload.report FULL_RUN_DIRECTORY --compare SHORTLIST_RUN_DIRECTORY
```

Reports contain full-roster size and scoped input-token counts. They do not call
a model or generate quality scores or pass/fail verdicts.

Roster results include initial size, last completed size, and growth after each
group. `roster_size_change` is the candidate's final size minus the baseline's:
positive means more agents with the candidate, negative means fewer. It is only
calculated when both runs finish. Fewer agents alone does not establish better
performance; inspect the saved outcomes too.

Comparison checks identical user inputs, requested arrival timing, initial inbox,
clock, and application models, and requires both rosters to start empty. Histories
and roster growth may diverge after starting. `input_token_change` is candidate
minus baseline and is only reported when both runs and their usage coverage are
complete. Token completeness is independent of roster-comparison completeness.
