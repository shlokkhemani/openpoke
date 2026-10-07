"""Boot the unmodified OpenPoke FastAPI app with test-only seams patched in memory.

Patches (process-local, nothing on disk changes):
  * OpenRouter base_url  -> local capturing mock (LAB_OPENROUTER_URL)
  * Composio client      -> FakeComposio (synthetic inbox)
  * watcher / scheduler  -> shorter poll intervals so tests run in seconds
  * summarisation knobs  -> optional overrides via LAB_SUMMARY_THRESHOLD / LAB_SUMMARY_TAIL
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

LAB = Path(__file__).resolve().parent
REPO = LAB.parent.parent
STATE = Path(os.environ.get("LAB_STATE", LAB / "state"))
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(LAB))

# Synthetic credential: never a real key. The mock records whether a header was sent.
os.environ["OPENROUTER_API_KEY"] = "sk-or-v1-SYNTHETIC-LAB-KEY-0000"
os.environ.setdefault("COMPOSIO_GMAIL_AUTH_CONFIG_ID", "ac_SYNTHETIC")

import uvicorn  # noqa: E402

from server.config import get_settings  # noqa: E402
from server.openrouter_client import client as orc  # noqa: E402

orc.request_chat_completion.__kwdefaults__["base_url"] = os.environ.get(
    "LAB_OPENROUTER_URL", "http://127.0.0.1:18080"
)

settings = get_settings()
if "LAB_SUMMARY_THRESHOLD" in os.environ:
    settings.conversation_summary_threshold = int(os.environ["LAB_SUMMARY_THRESHOLD"])
if "LAB_SUMMARY_TAIL" in os.environ:
    settings.conversation_summary_tail_size = int(os.environ["LAB_SUMMARY_TAIL"])

from fake_composio import FakeComposio  # noqa: E402
from server.services.gmail import client as gmail_client  # noqa: E402
from server.services.gmail import importance_watcher as iw  # noqa: E402
from server.services import trigger_scheduler as ts  # noqa: E402

gmail_client._CLIENT = FakeComposio(STATE)
iw._watcher_instance = iw.ImportantEmailWatcher(
    poll_interval_seconds=float(os.environ.get("LAB_WATCHER_INTERVAL", "3")), lookback_minutes=10
)
ts._scheduler_instance = ts.TriggerScheduler(poll_interval_seconds=1.0)

from server.app import app  # noqa: E402

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("LAB_PORT", "18001")), log_level="info")
