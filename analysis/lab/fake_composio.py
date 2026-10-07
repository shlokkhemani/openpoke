"""In-process stand-in for the Composio SDK client (synthetic inbox, no network).

Inbox contents come from <state>/inbox.json so the test runner can "deliver" mail
while the server is running. Every call is appended to <state>/composio_calls.jsonl
because Composio is itself an external third-party boundary.
"""

from __future__ import annotations

import base64
import json
import time
from pathlib import Path
from types import SimpleNamespace


class _Recorder:
    def __init__(self, state_dir: Path):
        self.path = state_dir / "composio_calls.jsonl"

    def __call__(self, op: str, **data) -> None:
        with self.path.open("a") as fh:
            fh.write(json.dumps({"t": time.time(), "op": op, **data}, default=str) + "\n")


def _raw_message(mail: dict) -> dict:
    return {
        "messageId": mail["id"],
        "threadId": mail.get("thread", mail["id"]),
        "subject": mail["subject"],
        "sender": mail["sender"],
        "to": mail["to"],
        "messageTimestamp": mail["ts"],
        "labelIds": ["INBOX", "UNREAD"],
        "attachmentList": [{"filename": f} for f in mail.get("attachments", [])],
        "payload": {"body": {"data": base64.urlsafe_b64encode(mail["body"].encode()).decode()}},
    }


class _Tools:
    def __init__(self, state_dir: Path, rec: _Recorder):
        self.state_dir, self.rec = state_dir, rec

    def execute(self, tool_name, user_id=None, arguments=None):
        self.rec("tools.execute", tool=tool_name, user_id=user_id, arguments=arguments)
        if tool_name == "GMAIL_FETCH_EMAILS":
            inbox_path = self.state_dir / "inbox.json"
            inbox = json.loads(inbox_path.read_text()) if inbox_path.exists() else []
            return {"successful": True, "data": {"messages": [_raw_message(m) for m in inbox]}}
        if tool_name == "GMAIL_GET_PROFILE":
            return {"successful": True, "data": {"emailAddress": f"{user_id}@example.test"}}
        return {"successful": True, "data": {"id": "synthetic-draft-1"}}


class _ConnectedAccounts:
    def __init__(self, rec: _Recorder):
        self.rec = rec

    def _acct(self, user_id="lab-user"):
        return SimpleNamespace(id=f"conn-{user_id}", status="ACTIVE", user_id=user_id,
                               email=f"{user_id}@example.test")

    def initiate(self, user_id, auth_config_id):
        self.rec("connected_accounts.initiate", user_id=user_id)
        return SimpleNamespace(id=f"conn-{user_id}", redirect_url="https://example.test/oauth")

    def wait_for_connection(self, conn_id, timeout=2.0):
        return self._acct(conn_id.removeprefix("conn-"))

    def get(self, conn_id):
        return self._acct(conn_id.removeprefix("conn-"))

    def list(self, user_ids=None, **_):
        return {"data": [self._acct(u) for u in (user_ids or [])]}

    def delete(self, conn_id):
        self.rec("connected_accounts.delete", conn_id=conn_id)


class FakeComposio:
    def __init__(self, state_dir: Path):
        rec = _Recorder(state_dir)
        self.connected_accounts = _ConnectedAccounts(rec)
        self.client = SimpleNamespace(tools=_Tools(state_dir, rec))
