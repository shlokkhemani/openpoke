# LTM demo UI

**Live comparison console (default).** One composer sends the same message to two live OpenPoke backends at once
(baseline, LTM off; LTM on) and shows the LTM backend's own trace, memory state and retrieval for that turn.

```bash
cd ~/Documents/openpoke-memory
analysis/lab/live_demo.sh --fresh          # mock model; add --real for OpenRouter (key in env or repo .env)
# UI        http://127.0.0.1:8765/demo_ui/
# baseline  http://127.0.0.1:8020   (LTM OFF)
# LTM       http://127.0.0.1:8021   (LTM ON + debug + test hooks)
```

Pointing the UI at other backends: `?baseline=http://127.0.0.1:8020&ltm=http://127.0.0.1:8021` (the defaults are at the top of
`js/live.js`). The LTM debug routes are loopback-only, so open the UI on the same machine.

Presentation mode: `http://127.0.0.1:8765/demo_ui/?presentation=1` (or the Presentation button, or press P).

**Replay (static traces).** `?mode=replay` renders the gated `analysis/lab/results/ltm_demo/*.json` files as before.

| File | Role |
|---|---|
| `js/main.js` | Picks live (default) or replay |
| `js/live.js` | Backend client (chat, history, debug traces/state/hooks) + session → demo-trace-shaped doc |
| `js/live_app.js` | Live console: OpenPoke-style chats, presets, composer, “What happened?”, drill-down, presentation mode |
| `js/story.js` | Pure summaries of one live turn: state-transition chains, six semantic stages, current memory |
| `js/replay.js` | Static trace viewer (`?mode=replay`) |
| `js/trace.js` | Read-only selectors over the trace schema (shared) |
| `js/components.js` | Renderers shared by both modes |
| `js/presentation.js` | Labels, stage → column mapping, live preset scripts. No outcomes |
