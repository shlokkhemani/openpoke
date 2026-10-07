"""Supervisor for the live side-by-side LTM demo (lab tooling; not production). Use ``live_demo.sh``.

Starts, on 127.0.0.1 only:
  * baseline backend  (LTM flags OFF)                      default :8020
  * LTM backend       (LTM + ingress scrub + debug + hooks) default :8021
  * one mock OpenRouter per backend (mock mode only)        :18120 / :18121
  * the demo UI static server for ``analysis/``             default :8765

Each backend runs from its own copy of ``server/`` under ``analysis/lab/state/live_demo/<name>/`` (gitignored), so the
two never share a conversation log, working memory or ltm.db. The UI server also answers:
  GET  /demo_ui/live-config.json   backend URLs + how they were launched (model mode, extractor, hooks)
  POST /lab/reset                  stop both backends, wipe their data dirs, start them again (lab-only "Reset both")
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

LAB = Path(__file__).resolve().parent
REPO = LAB.parent.parent
ANALYSIS = REPO / "analysis"
BASE_DIR = LAB / "state" / "live_demo"
PY = REPO / ".venv-lab" / "bin" / "python"

LTM_FLAGS = {
    "OPENPOKE_LTM_ENABLED": "true",
    "OPENPOKE_INGRESS_SCRUB": "true",
    "OPENPOKE_LTM_DEBUG": "1",
    "OPENPOKE_LTM_DEBUG_EVENTS": "1",
    "OPENPOKE_LTM_TEST_HOOKS": "1",
}
BASELINE_FLAGS = {k: "false" for k in LTM_FLAGS}
FLAG_PREFIXES = ("OPENPOKE_LTM_", "OPENPOKE_INGRESS_")


def port_busy(port: int) -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", port)) == 0


def log(msg: str) -> None:
    print(f"[live_demo] {msg}", flush=True)


class Instance:
    def __init__(self, name: str, port: int, mock_port: int, flags: dict, args: argparse.Namespace):
        self.name, self.port, self.mock_port, self.flags, self.args = name, port, mock_port, flags, args
        self.root = BASE_DIR / f"{name}-{port}"  # per-port, so two supervisors never share state
        self.procs: list[subprocess.Popen] = []

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def sync_code(self) -> None:
        """Copy the current server package into the instance (keeps the instance's own server/data)."""
        dst = self.root / "server"
        data = dst / "data"
        keep = None
        if data.exists():
            keep = self.root / ".data_keep"
            shutil.rmtree(keep, ignore_errors=True)
            data.rename(keep)
        shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(REPO / "server", dst, ignore=shutil.ignore_patterns("data", "__pycache__", "tests", "*.pyc"))
        if keep:
            keep.rename(data)

    def wipe(self) -> None:
        shutil.rmtree(self.root / "server" / "data", ignore_errors=True)
        shutil.rmtree(self.root / "mock", ignore_errors=True)
        shutil.rmtree(self.root / "lab_state", ignore_errors=True)

    def start(self) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        for d in ("mock", "lab_state"):
            (self.root / d).mkdir(exist_ok=True)
            inbox = self.root / d / "inbox.json"
            if not inbox.exists():
                inbox.write_text("[]")
        logs = self.root / "logs"
        logs.mkdir(exist_ok=True)
        env = {k: v for k, v in os.environ.items() if not k.startswith(FLAG_PREFIXES)}
        env.update(self.flags)
        env.update(
            LIVE_ROOT=str(self.root),
            LIVE_PORT=str(self.port),
            LIVE_MODEL=self.args.model,
            LIVE_MOCK_URL=f"http://127.0.0.1:{self.mock_port}",
            LAB_STATE=str(self.root / "lab_state"),
            OPENPOKE_LTM_EXTRACTOR=self.args.extractor,
            PYTHONDONTWRITEBYTECODE="1",
        )
        if self.args.model == "mock":
            self.procs.append(self._spawn([str(PY), str(LAB / "mock_openrouter.py"), str(self.mock_port), str(self.root / "mock")],
                                          env, logs / "mock.log"))
        self.procs.append(self._spawn([str(PY), str(LAB / "live_instance.py")], env, logs / "server.log"))

    @staticmethod
    def _spawn(cmd, env, logfile: Path) -> subprocess.Popen:
        fh = open(logfile, "ab")
        return subprocess.Popen(cmd, env=env, cwd=str(REPO), stdout=fh, stderr=subprocess.STDOUT, start_new_session=True)

    def wait_healthy(self, timeout: float = 30) -> bool:
        end = time.time() + timeout
        while time.time() < end:
            for p in self.procs:
                if p.poll() is not None:
                    return False
            try:
                with urllib.request.urlopen(self.url + "/api/v1/health", timeout=1) as r:
                    if r.status == 200:
                        return True
            except Exception:
                pass
            time.sleep(0.3)
        return False

    def stop(self) -> None:
        for p in self.procs:
            if p.poll() is None:
                try:
                    os.killpg(p.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
        for p in self.procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                os.killpg(p.pid, signal.SIGKILL)
        self.procs = []
        # wait for the port to be released so a restart can bind it
        end = time.time() + 5
        while port_busy(self.port) and time.time() < end:
            time.sleep(0.1)


class Supervisor:
    def __init__(self, args: argparse.Namespace):
        self.args = args
        self.instances = [
            Instance("baseline", args.baseline_port, args.mock_port, BASELINE_FLAGS, args),
            Instance("ltm", args.ltm_port, args.mock_port + 1, LTM_FLAGS, args),
        ]
        self.lock = threading.Lock()

    def config(self) -> dict:
        b, l = self.instances
        return {
            "source": "live_demo.py",
            "baseline": b.url,
            "ltm": l.url,
            "model_mode": self.args.model,
            "extractor": self.args.extractor,
            "flags": {"baseline": BASELINE_FLAGS, "ltm": LTM_FLAGS},
            "reset_endpoint": "/lab/reset",
        }

    def start_all(self, fresh: bool) -> None:
        for inst in self.instances:
            if fresh:
                inst.wipe()
            inst.sync_code()
            inst.start()
        for inst in self.instances:
            if not inst.wait_healthy():
                raise RuntimeError(f"{inst.name} backend did not become healthy; see {inst.root / 'logs' / 'server.log'}")

    def stop_all(self) -> None:
        for inst in self.instances:
            inst.stop()

    def conversation_kinds(self, path: str) -> dict:
        """Entry kinds of an instance's conversation log, in order. Only ``wait`` entries carry text (the agent's reason):
        /chat/history omits them, so without this a deliberate non-reply looks like a hang."""
        from urllib.parse import parse_qs, urlparse

        side = (parse_qs(urlparse(path).query).get("side") or ["ltm"])[0]
        inst = next((i for i in self.instances if i.name == ("ltm" if side == "ltm" else "baseline")), None)
        logf = inst.root / "server" / "data" / "conversation" / "poke_conversation.log" if inst else None
        if not logf or not logf.exists():
            return {"side": side, "entries": []}
        text = logf.read_text(encoding="utf-8", errors="replace")
        entries = []
        for m in re.finditer(r'<(\w+)(?:\s+timestamp="([^"]*)")?>(.*?)</\1>', text, re.S):
            kind, ts, body = m.group(1), m.group(2), m.group(3)
            entries.append({"kind": kind, "ts": ts, **({"reason": body.strip()[:300]} if kind == "wait" else {})})
        return {"side": side, "entries": entries}

    def reset(self) -> dict:
        with self.lock:
            t0 = time.time()
            self.stop_all()
            self.start_all(fresh=True)
            return {"ok": True, "seconds": round(time.time() - t0, 2)}


def make_handler(sup: Supervisor):
    class Handler(SimpleHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def end_headers(self):
            self.send_header("Cache-Control", "no-store")
            super().end_headers()

        def _json(self, code: int, body: dict) -> None:
            data = json.dumps(body).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):
            if self.path.split("?")[0] == "/demo_ui/live-config.json":
                return self._json(200, sup.config())
            if self.path.split("?")[0] == "/lab/convlog":
                return self._json(200, sup.conversation_kinds(self.path))
            if self.path in ("/", ""):
                self.send_response(302)
                self.send_header("Location", "/demo_ui/")
                return self.end_headers()
            return super().do_GET()

        def do_POST(self):
            if self.path == "/lab/reset":
                if self.client_address[0] not in ("127.0.0.1", "::1"):
                    return self._json(403, {"ok": False})
                try:
                    return self._json(200, sup.reset())
                except Exception as exc:
                    return self._json(500, {"ok": False, "error": str(exc)})
            return self._json(404, {"ok": False})

    return partial(Handler, directory=str(ANALYSIS))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fresh", action="store_true", help="wipe both instances' data before starting")
    ap.add_argument("--real", dest="model", action="store_const", const="real", default="mock",
                    help="use the real OpenRouter model (needs OPENROUTER_API_KEY in env or repo .env)")
    ap.add_argument("--extractor", choices=["rules", "llm"], default="rules")
    ap.add_argument("--baseline-port", type=int, default=int(os.environ.get("LIVE_BASELINE_PORT", 8020)))
    ap.add_argument("--ltm-port", type=int, default=int(os.environ.get("LIVE_LTM_PORT", 8021)))
    ap.add_argument("--ui-port", type=int, default=int(os.environ.get("LIVE_UI_PORT", 8765)))
    ap.add_argument("--mock-port", type=int, default=int(os.environ.get("LIVE_MOCK_PORT", 18120)))
    args = ap.parse_args()

    if not PY.exists():
        sys.exit(f"Missing {PY}. Create it (handoff C17): python3.13 -m venv .venv-lab && .venv-lab/bin/pip install "
                 "'fastapi>=0.115' 'uvicorn>=0.30' 'pydantic>=2.7' 'httpx>=0.27' python-dateutil beautifulsoup4")
    ports = [args.baseline_port, args.ltm_port, args.ui_port] + ([args.mock_port, args.mock_port + 1] if args.model == "mock" else [])
    busy = [p for p in ports if port_busy(p)]
    if busy:
        sys.exit(f"Port(s) already in use: {busy}. Stop the other process or pick ports, e.g. "
                 f"--baseline-port 8030 --ltm-port 8031 --ui-port 8775 --mock-port 18130")
    if args.model == "real" and not os.environ.get("OPENROUTER_API_KEY") and not (REPO / ".env").is_file():
        sys.exit("--real needs OPENROUTER_API_KEY in the environment or in the repo-root .env")

    sup = Supervisor(args)
    httpd = ThreadingHTTPServer(("127.0.0.1", args.ui_port), make_handler(sup))

    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())

    log(f"model={args.model} extractor={args.extractor} fresh={args.fresh}")
    try:
        sup.start_all(fresh=args.fresh)
    except Exception as exc:
        sup.stop_all()
        sys.exit(f"[live_demo] {exc}")

    b, l = sup.instances
    print(f"""
  Live demo UI      http://127.0.0.1:{args.ui_port}/demo_ui/
  Baseline backend  {b.url}   (LTM OFF)   data: {b.root / 'server' / 'data'}
  LTM backend       {l.url}   (LTM ON, debug + test hooks)   data: {l.root / 'server' / 'data'}
  LTM debug         {l.url}/api/v1/memory/debug/state
  Model             {args.model}{' (mock OpenRouter on :%d/:%d)' % (args.mock_port, args.mock_port + 1) if args.model == 'mock' else ''}
  Logs              {BASE_DIR}/<baseline|ltm>/logs/
  Replay (static traces)  http://127.0.0.1:{args.ui_port}/demo_ui/?mode=replay

  Ctrl-C stops everything.
""", flush=True)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    while not stop.wait(0.5):
        pass
    log("stopping…")
    httpd.shutdown()
    httpd.server_close()
    sup.stop_all()
    log("stopped")


if __name__ == "__main__":
    main()
