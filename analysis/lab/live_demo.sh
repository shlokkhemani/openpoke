#!/usr/bin/env bash
# Live side-by-side LTM demo: baseline backend (LTM OFF) + LTM backend (LTM ON) + demo UI. Lab tooling, not production.
#
#   analysis/lab/live_demo.sh            mock model (no API key needed)
#   analysis/lab/live_demo.sh --fresh    wipe both instances' chat + memory first
#   analysis/lab/live_demo.sh --real     real OpenRouter model (OPENROUTER_API_KEY in env or repo .env)
#   more: --extractor llm | --baseline-port N --ltm-port N --ui-port N --mock-port N   (see live_demo.py --help)
#
# Then open http://127.0.0.1:8765/demo_ui/   Ctrl-C stops every process this started.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
exec "$REPO/.venv-lab/bin/python" "$REPO/analysis/lab/live_demo.py" "$@"
