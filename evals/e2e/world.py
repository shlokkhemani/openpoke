"""In-memory Gmail stand-in for end-to-end evals.

Every execution-agent tool eventually calls ``execute_gmail_tool(tool_name, user_id, arguments)``
in ``server.services.gmail.client``. This module provides a fake with the same call shape,
backed by a seeded mailbox, and ``install()`` patches the three modules that import that
function by name. Nothing here talks to the network.

State that success checks read: ``sent``, ``drafts``, ``deleted_drafts``, ``calls``.
"""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

EVAL_USER = "eval-user@example.com"


@dataclass
class Email:
    id: str
    thread_id: str
    sender: str
    to: str
    subject: str
    body: str
    date: str  # ISO 8601
    cc: List[str] = field(default_factory=list)
    labels: List[str] = field(default_factory=lambda: ["INBOX"])

    def as_fetch_payload(self) -> Dict[str, Any]:
        return {
            "messageId": self.id,
            "threadId": self.thread_id,
            "subject": self.subject,
            "sender": self.sender,
            "to": self.to,
            "messageTimestamp": self.date,
            "labelIds": list(self.labels),
            "textBody": self.body,
        }


@dataclass
class Draft:
    id: str
    to: str
    subject: str
    body: str
    cc: List[str] = field(default_factory=list)
    bcc: List[str] = field(default_factory=list)
    thread_id: Optional[str] = None
    created_by_seed: bool = False


@dataclass
class SentMessage:
    id: str
    to: str
    subject: str
    body: str
    cc: List[str] = field(default_factory=list)
    thread_id: Optional[str] = None
    via: str = ""          # which tool produced it
    draft_id: Optional[str] = None


_QUERY_TOKEN = re.compile(r'(-?\w+:"[^"]*"|-?\w+:\S+|"[^"]*"|\S+)')
_IGNORED_PREFIXES = ("newer_than", "older_than", "after", "before", "in", "is", "label", "has", "category")


def _strip_quotes(s: str) -> str:
    s = s.strip()
    if len(s) >= 2 and ((s[0] == '"' and s[-1] == '"') or (s[0] == "(" and s[-1] == ")")):
        s = s[1:-1]
    return s.strip("()")


class FakeGmail:
    def __init__(self, seed: Optional[Dict[str, Any]] = None) -> None:
        self.inbox: List[Email] = []
        self.drafts: Dict[str, Draft] = {}
        self.sent: List[SentMessage] = []
        self.deleted_drafts: List[str] = []
        self.contacts: List[Dict[str, str]] = []
        self.calls: List[Dict[str, Any]] = []
        self._seq = 0
        self.drafts_created = 0
        if seed:
            self.load(seed)

    # ------------------------------------------------------------------ seed
    def load(self, seed: Dict[str, Any]) -> None:
        for e in seed.get("emails", []):
            self.inbox.append(Email(
                id=e["id"], thread_id=e.get("thread_id", e["id"]), sender=e["from"], to=e.get("to", EVAL_USER),
                subject=e["subject"], body=e["body"], date=e["date"], cc=list(e.get("cc", [])),
            ))
        for d in seed.get("drafts", []):
            self.drafts[d["id"]] = Draft(
                id=d["id"], to=d["to"], subject=d["subject"], body=d["body"], cc=list(d.get("cc", [])),
                thread_id=d.get("thread_id"), created_by_seed=True,
            )
        self.contacts = list(seed.get("contacts", []))

    def _next(self, prefix: str) -> str:
        self._seq += 1
        return f"{prefix}-{self._seq:04d}"

    # ------------------------------------------------------------- dispatch
    def execute(self, tool_name: str, user_id: str, arguments: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        args = {k: v for k, v in (arguments or {}).items() if v is not None}
        handler = getattr(self, f"_op_{tool_name.lower()}", None)
        t0 = time.monotonic()
        if handler is None:
            result: Dict[str, Any] = {"successful": False, "error": f"unsupported tool in fake world: {tool_name}"}
        else:
            try:
                result = handler(args)
            except KeyError as exc:
                result = {"successful": False, "error": f"missing argument {exc}"}
        self.calls.append({
            "t": time.monotonic(),
            "tool": tool_name,
            "args": args,
            "ok": bool(result.get("successful", True)) and not result.get("error"),
            "result_brief": _brief(result),
            "wall_ms": round((time.monotonic() - t0) * 1000),
        })
        return result

    # ------------------------------------------------------------- queries
    def _matches(self, email: Email, query: str) -> bool:
        tokens = [t for t in _QUERY_TOKEN.findall(query or "") if t]
        if not tokens:
            return True
        any_mode = any(t.upper() == "OR" for t in tokens)
        tokens = [t for t in tokens if t.upper() != "OR"]
        hay_all = " ".join([email.sender, email.to, email.subject, email.body, " ".join(email.cc)]).lower()
        results: List[bool] = []
        for tok in tokens:
            neg = tok.startswith("-")
            tok = tok[1:] if neg else tok
            if ":" in tok and not tok.startswith('"'):
                prefix, _, value = tok.partition(":")
                value = _strip_quotes(value).lower()
                prefix = prefix.lower()
                if prefix in _IGNORED_PREFIXES:
                    continue
                if prefix == "from":
                    hit = value in email.sender.lower()
                elif prefix == "to":
                    hit = value in email.to.lower() or value in " ".join(email.cc).lower()
                elif prefix == "cc":
                    hit = value in " ".join(email.cc).lower()
                elif prefix == "subject":
                    hit = value in email.subject.lower()
                else:
                    hit = value in hay_all
            else:
                hit = _strip_quotes(tok).lower() in hay_all
            results.append(hit != neg)
        if not results:
            return True
        return any(results) if any_mode else all(results)

    def _op_gmail_fetch_emails(self, a: Dict[str, Any]) -> Dict[str, Any]:
        query = a.get("query", "")
        limit = int(a.get("max_results") or 10)
        hits = [e for e in self.inbox if self._matches(e, query)]
        hits.sort(key=lambda e: e.date, reverse=True)
        return {"successful": True, "data": {"messages": [e.as_fetch_payload() for e in hits[:limit]],
                                              "resultSizeEstimate": len(hits)}}

    def _op_gmail_get_profile(self, a: Dict[str, Any]) -> Dict[str, Any]:
        return {"successful": True, "data": {"response_data": {"emailAddress": EVAL_USER}}}

    # -------------------------------------------------------------- drafts
    def _op_gmail_create_email_draft(self, a: Dict[str, Any]) -> Dict[str, Any]:
        to = a["recipient_email"]
        cc = list(a.get("cc") or []) + list(a.get("extra_recipients") or [])
        draft = Draft(id=self._next("draft"), to=to, subject=a["subject"], body=a["body"], cc=cc,
                      bcc=list(a.get("bcc") or []), thread_id=a.get("thread_id"))
        self.drafts[draft.id] = draft
        self.drafts_created += 1
        return {"successful": True, "data": {"response_data": {
            "id": draft.id, "message": {"id": self._next("msg"), "threadId": draft.thread_id or self._next("thread")},
            "to": to, "cc": cc, "subject": draft.subject}}}

    def _op_gmail_send_draft(self, a: Dict[str, Any]) -> Dict[str, Any]:
        draft = self.drafts.pop(a["draft_id"], None)
        if draft is None:
            return {"successful": False, "error": f"Draft not found: {a['draft_id']}"}
        msg = SentMessage(id=self._next("msg"), to=draft.to, subject=draft.subject, body=draft.body, cc=draft.cc,
                          thread_id=draft.thread_id, via="GMAIL_SEND_DRAFT", draft_id=draft.id)
        self.sent.append(msg)
        return {"successful": True, "data": {"response_data": {"id": msg.id, "threadId": msg.thread_id, "labelIds": ["SENT"]}}}

    def _op_gmail_delete_draft(self, a: Dict[str, Any]) -> Dict[str, Any]:
        if a["draft_id"] not in self.drafts:
            return {"successful": False, "error": f"Draft not found: {a['draft_id']}"}
        self.drafts.pop(a["draft_id"])
        self.deleted_drafts.append(a["draft_id"])
        return {"successful": True, "data": {"response_data": {"deleted": a["draft_id"]}}}

    def _op_gmail_list_drafts(self, a: Dict[str, Any]) -> Dict[str, Any]:
        items = [{"id": d.id, "to": d.to, "subject": d.subject, "threadId": d.thread_id,
                  "snippet": d.body[:120]} for d in self.drafts.values()]
        return {"successful": True, "data": {"drafts": items, "resultSizeEstimate": len(items)}}

    # --------------------------------------------------------------- sends
    def _op_gmail_reply_to_thread(self, a: Dict[str, Any]) -> Dict[str, Any]:
        thread_id = a["thread_id"]
        if not any(e.thread_id == thread_id for e in self.inbox) and not any(s.thread_id == thread_id for s in self.sent):
            return {"successful": False, "error": f"Thread not found: {thread_id}"}
        subject = next((e.subject for e in self.inbox if e.thread_id == thread_id), "")
        cc = list(a.get("cc") or []) + list(a.get("extra_recipients") or [])
        msg = SentMessage(id=self._next("msg"), to=a["recipient_email"], subject=f"Re: {subject}" if subject else "",
                          body=a["message_body"], cc=cc, thread_id=thread_id, via="GMAIL_REPLY_TO_THREAD")
        self.sent.append(msg)
        return {"successful": True, "data": {"response_data": {"id": msg.id, "threadId": thread_id, "labelIds": ["SENT"]}}}

    def _op_gmail_forward_message(self, a: Dict[str, Any]) -> Dict[str, Any]:
        src = next((e for e in self.inbox if e.id == a["message_id"]), None)
        if src is None:
            return {"successful": False, "error": f"Message not found: {a['message_id']}"}
        body = (a.get("additional_text") or "") + "\n\n---- Forwarded message ----\n" + src.body
        msg = SentMessage(id=self._next("msg"), to=a["recipient_email"], subject=f"Fwd: {src.subject}", body=body,
                          thread_id=src.thread_id, via="GMAIL_FORWARD_MESSAGE")
        self.sent.append(msg)
        return {"successful": True, "data": {"response_data": {"id": msg.id, "threadId": src.thread_id}}}

    # ------------------------------------------------------------ contacts
    def _people(self, query: str = "") -> List[Dict[str, Any]]:
        q = query.lower()
        out = []
        for c in self.contacts:
            if not q or q in c.get("name", "").lower() or q in c.get("email", "").lower():
                out.append({"names": [{"displayName": c.get("name", "")}], "emailAddresses": [{"value": c.get("email", "")}]})
        return out

    def _op_gmail_get_contacts(self, a: Dict[str, Any]) -> Dict[str, Any]:
        return {"successful": True, "data": {"connections": self._people()}}

    def _op_gmail_get_people(self, a: Dict[str, Any]) -> Dict[str, Any]:
        return {"successful": True, "data": {"connections": self._people()}}

    def _op_gmail_search_people(self, a: Dict[str, Any]) -> Dict[str, Any]:
        return {"successful": True, "data": {"results": [{"person": p} for p in self._people(a.get("query", ""))]}}

    # -------------------------------------------------------------- export
    def snapshot(self) -> Dict[str, Any]:
        return {
            "sent": [vars(s) for s in self.sent],
            "drafts": [vars(d) for d in self.drafts.values()],
            "deleted_drafts": list(self.deleted_drafts),
            "drafts_created": self.drafts_created,
            "calls": len(self.calls),
        }


def _brief(result: Dict[str, Any]) -> str:
    if result.get("error"):
        return f"error: {result['error']}"
    data = result.get("data") or {}
    if "messages" in data:
        subs = [m.get("subject", "") for m in data["messages"]]
        return f"{len(subs)} message(s): " + "; ".join(subs)[:200]
    rd = data.get("response_data") or data
    keys = ("id", "threadId", "deleted", "to", "subject")
    return ", ".join(f"{k}={rd[k]}" for k in keys if k in rd)[:200] or "ok"


# ---------------------------------------------------------------- patching
_PATCH_TARGETS = (
    "server.agents.execution_agent.tools.gmail",
    "server.agents.execution_agent.tasks.search_email.tool",
    "server.agents.execution_agent.tasks.search_email.gmail_internal",
)


class Installed:
    def __init__(self, world: FakeGmail) -> None:
        self.world = world
        self._saved: List[tuple] = []

    def __enter__(self) -> "Installed":
        import importlib
        for name in _PATCH_TARGETS:
            mod = importlib.import_module(name)
            self._saved.append((mod, mod.execute_gmail_tool, mod.get_active_gmail_user_id))
            mod.execute_gmail_tool = self.world.execute
            mod.get_active_gmail_user_id = lambda: "eval-user"
        return self

    def __exit__(self, *exc) -> None:
        for mod, ex, gu in self._saved:
            mod.execute_gmail_tool = ex
            mod.get_active_gmail_user_id = gu
        self._saved.clear()


def install(world: FakeGmail) -> Installed:
    return Installed(world)


def iso_days_ago(days: int, hour: int = 9) -> str:
    from datetime import timedelta
    dt = datetime.now(timezone.utc) - timedelta(days=days)
    return dt.replace(hour=hour, minute=0, second=0, microsecond=0).isoformat().replace("+00:00", "Z")


__all__ = ["FakeGmail", "install", "Installed", "iso_days_ago", "EVAL_USER"]
