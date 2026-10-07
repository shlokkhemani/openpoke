"""Run ONE OpenPoke backend for the live side-by-side demo (lab tooling; not production).

The server derives every data path from its own file location (``Path(__file__)/../data``), so two instances started
from the same checkout would share the conversation log and ltm.db. Instead, each instance runs from its own synced
copy of the ``server`` package (``LIVE_ROOT/server``), which gives it a private ``LIVE_ROOT/server/data``. Nothing in the
repo's ``server/`` is modified or written.

Env:
  LIVE_ROOT        instance directory that contains the copied ``server`` package (required)
  LIVE_PORT        port to bind on 127.0.0.1 (required)
  LIVE_MODEL       ``mock`` (default) or ``real``
  LIVE_MOCK_URL    mock OpenRouter URL for mock mode
  LAB_STATE        fake-Composio state dir (synthetic inbox)
  OPENPOKE_LTM_*   feature flags, passed through unchanged
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

LAB = Path(__file__).resolve().parent
REPO = LAB.parent.parent
ROOT = Path(os.environ["LIVE_ROOT"]).resolve()
MODEL = os.environ.get("LIVE_MODEL", "mock")

# The instance copy must win over anything else named ``server``; the lab dir provides fake_composio.
sys.path[:] = [str(ROOT), str(LAB)] + [p for p in sys.path if Path(p or ".").resolve() not in (REPO, LAB)]
os.chdir(ROOT)

if MODEL == "mock":
    # Synthetic credential: never a real key. The mock ignores it.
    os.environ["OPENROUTER_API_KEY"] = "-".join(["sk", "or", "v1", "SYNTHETIC", "LAB", "KEY", "0000"])
else:
    # Real model: the copied config looks for .env next to the copy, so load the repo's .env here (values never printed).
    env = REPO / ".env"
    if env.is_file():
        for line in env.read_text(encoding="utf-8").splitlines():
            s = line.strip()
            if s and not s.startswith("#") and "=" in s:
                k, v = s.split("=", 1)
                k, v = k.strip(), v.strip().strip("'\"")
                if k and v and k not in os.environ:
                    os.environ[k] = v
    if not os.environ.get("OPENROUTER_API_KEY"):
        sys.exit("OPENROUTER_API_KEY is not set (env or repo .env); cannot start in real mode")
os.environ.setdefault("COMPOSIO_GMAIL_AUTH_CONFIG_ID", "ac_SYNTHETIC")

import uvicorn  # noqa: E402

import server  # noqa: E402

assert Path(server.__file__).resolve().is_relative_to(ROOT), f"wrong server package: {server.__file__}"

if MODEL == "mock":
    from server.openrouter_client import client as orc  # noqa: E402

    orc.request_chat_completion.__kwdefaults__["base_url"] = os.environ.get("LIVE_MOCK_URL", "http://127.0.0.1:18120")

# Gmail stays fake in both modes so the demo never touches a real inbox.
from fake_composio import FakeComposio  # noqa: E402
from server.services.gmail import client as gmail_client  # noqa: E402

gmail_client._CLIENT = FakeComposio(Path(os.environ.get("LAB_STATE", ROOT / "lab_state")))

from server.app import app  # noqa: E402

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ["LIVE_PORT"]), log_level="warning")
