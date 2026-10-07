# Deletion Race Demo (Baseline Proof #4)

Captured 2026-10-07 with the existing analysis lab (`analysis/lab/`), against the unmodified OpenPoke server. It uses the same mechanism as `race_exec` (`analysis/lab/run_experiments.py:317-335`), with marker `DELETE-RACE-9090`. All data is synthetic, and the LLM is the lab's capturing mock with a synthetic key.

## Slide table

Marker `DELETE-RACE-9090` · message `DELEGATE: note DELETE-RACE-9090` · execution agent delayed 4 s · `DELETE` sent 2 s after send.

| Moment | Marker present? | Evidence |
|---|---|---|
| Before delete | Yes | `poke_conversation.log` L1 · `poke_working_memory.log` L3 · `synthetic-lab-agent.log` L1 · `GET /chat/history` (user msg) |
| Immediately after delete | No | 0 hits in `server/data/` · `GET /chat/history` → 0 msgs · cleared by `routes/chat.py:25-45` |
| After in-flight agent finishes | Yes | `poke_conversation.log` L1–2 · `poke_working_memory.log` L3–4 · `synthetic-lab-agent.log` L1 · `GET /chat/history` (assistant msg) · written by `runtime.py:105`, `log.py:140-146` |

Paths: logs under `server/data/conversation/` and `server/data/execution_agents/`. API is `/api/v1/chat/history`. Raw data: `analysis/lab/results/deletion_race_9090.json` (`snapshots[0..2]`).

## Why this happens

| Step | Source | What it does |
|---|---|---|
| 1. Agent started in background | `server/agents/interaction_agent/tools.py:127-141` | `send_message_to_agent` wraps the run in `_execute_async()` and fires it with `loop.create_task(...)` (L141). The task is not stored. |
| 2. Delete clears files only | `server/routes/chat.py:25-45` | Clears conversation log + working memory (L31 → `log.py:194-206`), exec logs (L35), roster (L39), triggers (L43). It does not touch the batch manager or running tasks. |
| 3. Agent finishes; result accepted | `server/agents/execution_agent/batch_manager.py:118-144` | Only guard is the `batch_id` check (L130-132), which delete never resets, so the result is dispatched (L144). |
| 4. Result handed to interaction agent | `batch_manager.py:181-193` | `loop.create_task(runtime.handle_agent_message(payload))` (L193) |
| 5. Written into fresh history | `server/agents/interaction_agent/runtime.py:100-118` → `server/services/conversation/log.py:140-146` | `record_agent_message` (runtime L105) and `record_reply` append to the recreated conversation log and working memory. |
| 6. Exec log recreated | `server/agents/execution_agent/agent.py:114-116` | `record_response` → `record_agent_response` writes `<agent_response>` to `synthetic-lab-agent.log`. |

## Test sequence

Synthetic user message: `DELEGATE: note DELETE-RACE-9090`

The lab mock (`analysis/lab/mock_openrouter.py:77-81`) answers a `DELEGATE:` message by having the interaction agent call `send_message_to_user("On it.")` and `send_message_to_agent("Synthetic Lab Agent", "note DELETE-RACE-9090")`. The execution agent's reply is then delayed by 4 s through the mock's `/__control` endpoint.

| Wall clock (America/Toronto) | Event |
|---|---|
| 12:58:49.057 | Lab stack up: mock OpenRouter on `:18080`, unmodified OpenPoke on `:18001` (`analysis/lab/launch_server.py`) |
| 12:58:49.065 | `POST /__control {"delay": {"execution_agent": 4}}` |
| 12:58:49.074 | `POST /api/v1/chat/send` "DELEGATE: note DELETE-RACE-9090" → 202 |
| 12:58:49.097 / .115 | Interaction-agent LLM calls; execution-agent LLM call starts at .116 (held 4 s by mock) |
| 12:58:51.096 | **Snapshot: before delete** |
| 12:58:51.114 | `DELETE /api/v1/chat/history` → `200 {"ok":true}` |
| 12:58:51.123 | **Snapshot: immediately after delete** |
| ~12:58:53.13 | Delayed execution agent returns. Result is dispatched to the interaction agent (LLM calls 12:58:53.134 / .143) |
| 12:58:56.253 | System idle (no data-file or LLM-capture change for 3 s) |
| 12:58:56.275 | **Snapshot: after in-flight agent finished** |

> **Timestamps inside log entries read `16:58`** because the lab's `fresh_stack()` starts from an empty `server/data/` (no `timezone.txt`), so OpenPoke stamps entries in UTC. 16:58 UTC = 12:58 America/Toronto.

## Storage at each moment

### Before delete (12:58:51.096)

| Location | Line | Content |
|---|---|---|
| `server/data/conversation/poke_conversation.log` | L1 | `<user_message timestamp="2026-10-07 16:58:49">DELEGATE: note DELETE-RACE-9090</user_message>` |
| `server/data/conversation/poke_working_memory.log` | L3 | same `<user_message>` |
| `server/data/execution_agents/synthetic-lab-agent.log` | L1 | `<agent_request timestamp="2026-10-07 16:58:49">note DELETE-RACE-9090</agent_request>` |
| `GET /api/v1/chat/history` | — | 2 messages, including `{"role":"user","content":"DELEGATE: note DELETE-RACE-9090"}` |

### Immediately after delete (12:58:51.123)

| Location | Marker |
|---|---|
| `server/data/conversation/poke_conversation.log` | absent (file removed) |
| `server/data/conversation/poke_working_memory.log` | absent |
| `server/data/execution_agents/*.log` | absent |
| `GET /api/v1/chat/history` | absent: **0 messages** |

The marker remained only in the mock's request captures (`LLM:interaction_agent`, `LLM:execution_agent`). That copy is outside OpenPoke, standing in for what the external provider already received.

### After in-flight agent finished (12:58:56.275)

| Location | Line | Content |
|---|---|---|
| `server/data/conversation/poke_conversation.log` | L1 | `<agent_message timestamp="2026-10-07 16:58:53">[SUCCESS] Synthetic Lab Agent: Done: note DELETE-RACE-9090</agent_message>` |
| | L2 | `<poke_reply timestamp="2026-10-07 16:58:53">Update: [SUCCESS] Synthetic Lab Agent: Done: note DELETE-RACE-9090</poke_reply>` |
| `server/data/conversation/poke_working_memory.log` | L3 | same `<agent_message>` |
| | L4 | same `<poke_reply>` |
| `server/data/execution_agents/synthetic-lab-agent.log` | L1 | `<agent_response timestamp="2026-10-07 16:58:53">Done: note DELETE-RACE-9090</agent_response>` |
| `server/data/execution_agents/roster.json` | L1 | `[]` (roster was cleared, but the agent still finished) |
| `GET /api/v1/chat/history` | — | **1 message:** `{"role":"assistant","content":"Update: [SUCCESS] Synthetic Lab Agent: Done: note DELETE-RACE-9090","timestamp":"2026-10-07 16:58:53"}` |

**Result: reproduced.** The deleted marker reappeared in the conversation log, the working memory, the execution-agent log, and the user-facing history API. The user deleted their history and then saw the deleted content come back as a fresh assistant message.

## Exact commands

```bash
cd ~/OpenPoke
# 0. The lab's fresh_stack() runs rmtree on server/data, so the dev backend was stopped and the live data backed up first
pkill -INT -f "server.server"
cp -Rp server/data <scratch>/data_backup
(cd server/data && find . -type f -exec shasum -a 256 {} \; | sort -k2) > <scratch>/data_backup.sha256

# 1-9. Run Proof #4 (reuses run_experiments.py helpers unchanged; marker DELETE-RACE-9090)
.venv-lab/bin/python analysis/lab/race_delete_9090.py "$PWD" analysis/lab/results/deletion_race_9090.json

# 10. Restore the live data and verify it is byte-identical, then restart the dev backend
rm -rf server/data && cp -Rp <scratch>/data_backup server/data
(cd server/data && find . -type f -exec shasum -a 256 {} \; | sort -k2) | diff - <scratch>/data_backup.sha256   # no output = identical
.venv/bin/python -m server.server
```

`analysis/lab/race_delete_9090.py` performs, via the lab helpers:
- `fresh_stack()`
- `control(delay={"execution_agent": 4})`
- `POST /chat/send`
- `sleep(2)`
- snapshot
- `DELETE /chat/history`
- snapshot
- `wait_idle(quiet=3)`
- snapshot

Each snapshot records `scan_locations`, per-file line hits, and `GET /chat/history`.

## Integrity

- **No production code changed:** nothing under `server/` or `web/` was modified. The lab patches seams in memory only (`launch_server.py`).
- **Existing lab not modified:** `run_experiments.py` and `mock_openrouter.py` are unchanged. This run adds `analysis/lab/race_delete_9090.py` (driver) and `analysis/lab/results/deletion_race_9090.json` (raw evidence).
- **Live runtime data preserved:** `server/data/` was backed up before the lab run and restored afterwards. The sha256 of every file matched the pre-run backup.

## Conclusion

**OpenPoke clears the current history, but in-flight background work is not fenced. When the delayed agent finishes, it can write deleted information back into fresh history.**
