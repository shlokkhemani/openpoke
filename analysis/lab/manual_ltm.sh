#!/usr/bin/env bash
# Browser manual-test mode for the OpenPoke LTM prototype (lab tooling; not production).
#
# Starts the FastAPI backend (LTM + ingress scrub + debug events + test hooks ON) AND the normal web chat UI,
# with the UI proxying to that backend. Ctrl-C stops everything this script started.
#
#   analysis/lab/manual_ltm.sh            mock LLM: no API keys needed; the assistant always replies "Noted."
#   analysis/lab/manual_ltm.sh real       real OpenRouter model: needs OPENROUTER_API_KEY in the repo-root .env
#   ... --fresh                           first delete LTM memories + chat history (server/data/memory, conversation)
#   ... --no-ui                           backend only
#
# Ports: MANUAL_LTM_PORT (backend, default 8001), MANUAL_UI_PORT (chat UI, default 3000).
#
# Debug endpoints are loopback-only and exist only while this is running (OPENPOKE_LTM_DEBUG=1).
set -euo pipefail

REPO="$(cd "$(dirname "$0")/../.." && pwd)"
PY="$REPO/.venv-lab/bin/python"
MODE=mock
FRESH=0
UI=1
PORT="${MANUAL_LTM_PORT:-8001}"
UI_PORT="${MANUAL_UI_PORT:-3000}"
for arg in "$@"; do
  case "$arg" in
    mock) MODE=mock ;;
    real) MODE=real ;;
    --fresh) FRESH=1 ;;
    --no-ui) UI=0 ;;
    *) echo "usage: $0 [mock|real] [--fresh] [--no-ui]" >&2; exit 2 ;;
  esac
done

if [ ! -x "$PY" ]; then
  echo "Missing $PY. Create it first (handoff C17):" >&2
  echo "  python3.13 -m venv .venv-lab && .venv-lab/bin/pip install 'fastapi>=0.115' 'uvicorn>=0.30' 'pydantic>=2.7' 'httpx>=0.27' python-dateutil beautifulsoup4" >&2
  exit 1
fi

export OPENPOKE_LTM_ENABLED=true
export OPENPOKE_INGRESS_SCRUB=true
export OPENPOKE_LTM_DEBUG=1
export OPENPOKE_LTM_DEBUG_EVENTS=1
export OPENPOKE_LTM_TEST_HOOKS=1
export OPENPOKE_LTM_EXTRACTOR=rules

cd "$REPO"
mkdir -p "$REPO/analysis/lab/state"
if [ "$FRESH" = 1 ]; then
  rm -rf "$REPO/server/data/memory" "$REPO/server/data/conversation"
  echo "[manual_ltm] wiped server/data/memory and server/data/conversation"
fi

for p in "$PORT" "$UI_PORT"; do
  if lsof -nP -iTCP:"$p" -sTCP:LISTEN >/dev/null 2>&1; then
    echo "Port $p is already in use (another OpenPoke?). Stop it, or pick free ports, e.g.:" >&2
    echo "  MANUAL_LTM_PORT=8011 MANUAL_UI_PORT=3011 $0 $*" >&2
    exit 1
  fi
done

PIDS=()
kill_tree() { local c; for c in $(pgrep -P "$1" 2>/dev/null); do kill_tree "$c"; done; kill "$1" 2>/dev/null || true; }
cleanup() { for p in "${PIDS[@]:-}"; do [ -n "$p" ] && kill_tree "$p"; done; }
trap cleanup EXIT INT TERM

if [ "$UI" = 1 ]; then
  if [ ! -d "$REPO/web/node_modules" ]; then
    echo "Installing web dependencies (npm ci keeps web/package-lock.json unchanged)..."
    npm ci --prefix "$REPO/web" --no-audit --no-fund >/dev/null
  fi
  PY_SERVER_URL="http://localhost:$PORT" npm run dev --prefix "$REPO/web" -- -p "$UI_PORT" > "$REPO/analysis/lab/state/manual_ui.log" 2>&1 &
  PIDS+=($!)
fi

echo ""
echo "  Chat UI:       http://localhost:$UI_PORT"
echo "  Memory state:  http://localhost:$PORT/api/v1/memory/debug/state"
echo "  Trace list:    http://localhost:$PORT/api/v1/memory/debug/traces?limit=10"
echo "  Trace detail:  http://localhost:$PORT/api/v1/memory/debug/trace/<trace_id>"
echo "  Test hooks:    http://localhost:$PORT/docs  (memory-debug section)"
echo ""

if [ "$MODE" = mock ]; then
  STATE="$REPO/analysis/lab/state/manual"
  mkdir -p "$STATE"
  [ -f "$STATE/inbox.json" ] || echo '[]' > "$STATE/inbox.json"
  "$PY" "$REPO/analysis/lab/mock_openrouter.py" 18080 "$STATE" > "$STATE/mock.out" 2>&1 &
  PIDS+=($!)
  # launch_server.py: unmodified app + lab seams (OpenRouter -> local mock, Composio -> fake inbox)
  LAB_STATE="$STATE" LAB_PORT="$PORT" "$PY" "$REPO/analysis/lab/launch_server.py"
else
  # Bind to loopback: the debug routes are loopback-only anyway, and the server has no auth (F-1).
  "$PY" -m server.server --host 127.0.0.1 --port "$PORT"
fi
