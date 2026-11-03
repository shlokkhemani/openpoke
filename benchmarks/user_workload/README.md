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

Python 3.10+, standard library only. From the repository root:

```bash
python3 -m benchmarks.user_workload
python3 -m unittest benchmarks.user_workload.test_validation -v
python3 -m unittest benchmarks.user_workload.test_email_backend -v
python3 -m benchmarks.user_workload.run
```

## Run

Start an isolated OpenPoke server, with shortlisting disabled for setup. The runner
uses `POST /api/v1/chat/send` and `GET /api/v1/benchmark/status`. It requires the
status endpoint's benchmark mode, isolated data, and isolated tools markers.
This branch provides that endpoint; the separate matcher repo must expose the
same status contract before using this runner. Matching is configured externally.
Configure the server to use this workload's inbox (the local `.env` also selects it):

```bash
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
`--allow-existing-state`. It records each submission and acceptance, group
completion duration, roster size before/after the group, and final status in ignored
`results/<timestamp>/run.jsonl`. Histories remain in the server's data directory.
Roster changes within a burst are reported for the whole group; they are not
attributed to individual simultaneous messages. The journal includes a copy of
the consumed messages and schedule for reproducibility. Use the same inbox and
initial server clock for both comparison modes as well.
Errors stop the run and preserve partial logs. Requests are never automatically
retried because a lost response could otherwise duplicate a submitted task.
Inspect partial state before restarting: `--allow-existing-state` appends the
entire supplied sequence and is not an automatic resume feature.

After setup, copy the naturally generated state externally for both comparison
modes, then run the same continuous test sequence against each copy:

```bash
python3 -m benchmarks.user_workload.run --live --allow-existing-state \
  --messages benchmarks/user_workload/test_messages.json \
  --base-url http://127.0.0.1:8011/api/v1
```

Freeze inputs before comparison and apply any changes to both modes. Both rosters
can grow. This runner reports roster growth and completion; it does not judge
quality or retrieval correctness. No live run of this workload has been performed.
