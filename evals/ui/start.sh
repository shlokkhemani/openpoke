#!/usr/bin/env bash
# One command for the eval UI: builds the React app when needed, then serves API + app on :8765.
#   evals/ui/start.sh            # build if stale, serve, open browser
#   evals/ui/start.sh --dev      # Vite dev server with hot reload (proxies /api to the Python server)
set -euo pipefail
HERE="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
PY="$ROOT/.venv/bin/python"; [ -x "$PY" ] || PY=python3
PORT="${PORT:-8765}"

cd "$HERE"
[ -d node_modules ] || npm install --silent

if [ "${1:-}" = "--dev" ]; then
  "$PY" server.py "$PORT" & API=$!
  trap 'kill $API 2>/dev/null' EXIT
  npm run dev
  exit
fi

# rebuild when any source is newer than the last build
if [ ! -f dist/index.html ] || [ -n "$(find src index.html vite.config.ts -newer dist/index.html -print -quit)" ]; then
  npm run build --silent
fi

( sleep 1; command -v open >/dev/null && open "http://localhost:$PORT" || true ) &
echo "eval UI → http://localhost:$PORT   (ctrl-c to stop)"
exec "$PY" server.py "$PORT"
