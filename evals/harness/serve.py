"""Launch an OpenPoke server copy for evaluation, recording every LLM call.

Run with the OpenPoke virtualenv's python, from nothing in particular:
    python evals/harness/serve.py --root /tmp/run --port 8123 --record /tmp/run/llm_calls.jsonl

`--root` must contain `server/` (a copy of a checkout's server package) and `.env`.
Nothing here imports harness code, so the same launcher works for the original and the fork.
"""

from __future__ import annotations

import argparse
import itertools
import json
import os
import re
import sys
import threading
import time


_AGENT_NAME = re.compile(r'<agent name=\\?"([^"\\]*)')


def _install_llm_recorder(record_path: str) -> None:
    import httpx

    lock = threading.Lock()
    ids = itertools.count(1)
    original_post = httpx.AsyncClient.post

    def write(event: dict) -> None:
        with lock, open(record_path, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(event) + "\n")

    async def recording_post(self, url, *args, **kwargs):
        if not str(url).rstrip("/").endswith("/chat/completions"):
            return await original_post(self, url, *args, **kwargs)

        payload = kwargs.get("json") or {}
        messages = payload.get("messages") or []
        system = next((m.get("content") or "" for m in messages if m.get("role") == "system"), "")
        call_id = next(ids)
        started = time.time()
        # Distinct agents visible in this request: `<agent name="...">` entries, also when JSON-escaped in tool results.
        agent_names = set()
        for message in messages:
            content = message.get("content")
            if isinstance(content, str):
                agent_names.update(_AGENT_NAME.findall(content))
        write({"event": "start", "id": call_id, "t": started, "model": payload.get("model"),
               "system_prefix": str(system)[:300], "n_messages": len(messages),
               "n_tools": len(payload.get("tools") or []), "agents_seen": len(agent_names)})
        try:
            response = await original_post(self, url, *args, **kwargs)
        except BaseException as exc:  # includes asyncio.CancelledError (e.g. an agent timeout cancels the call)
            write({"event": "end", "id": call_id, "t": time.time(), "latency": time.time() - started,
                   "error": f"{type(exc).__name__}: {exc}"})
            raise

        usage, tool_calls, content_len = {}, [], 0
        try:
            data = response.json()
            usage = data.get("usage") or {}
            message = ((data.get("choices") or [{}])[0].get("message")) or {}
            tool_calls = [((c.get("function") or {}).get("name")) for c in (message.get("tool_calls") or [])]
            content_len = len(message.get("content") or "")
        except Exception:
            pass
        ended = time.time()
        write({"event": "end", "id": call_id, "t": ended, "latency": ended - started,
               "status": response.status_code, "usage": usage, "tool_calls": tool_calls,
               "content_len": content_len})
        return response

    httpx.AsyncClient.post = recording_post


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--record", required=True)
    parser.add_argument("--overrides", default="{}", help="JSON object of Settings attributes to override")
    args = parser.parse_args()

    root = os.path.abspath(args.root)
    os.chdir(root)
    sys.path.insert(0, root)

    _install_llm_recorder(os.path.abspath(args.record))

    from server.config import get_settings  # noqa: E402  (loads <root>/.env)

    settings = get_settings()
    for key, value in json.loads(args.overrides).items():
        if not hasattr(settings, key):
            raise SystemExit(f"unknown setting override: {key}")
        setattr(settings, key, value)

    # Gmail stays disconnected: never start the important-email watcher.
    from server.services import get_important_email_watcher  # noqa: E402

    async def _noop() -> None:
        return None

    watcher = get_important_email_watcher()
    watcher.start = _noop  # type: ignore[method-assign]
    watcher.stop = _noop  # type: ignore[method-assign]

    import uvicorn  # noqa: E402
    from server.app import app  # noqa: E402

    uvicorn.run(app, host="127.0.0.1", port=args.port, log_level="warning")


if __name__ == "__main__":
    main()
