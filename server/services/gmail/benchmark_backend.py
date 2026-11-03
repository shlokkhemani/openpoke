"""Deterministic Gmail replacement for isolated benchmark runs."""

from __future__ import annotations

import json
import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional


_TOKEN_PATTERN = re.compile(r"[a-z0-9][a-z0-9_-]*")
_IGNORED_QUERY_WORDS = {
    "after",
    "all",
    "and",
    "before",
    "email",
    "emails",
    "find",
    "from",
    "has",
    "in",
    "is",
    "label",
    "latest",
    "last",
    "mail",
    "message",
    "messages",
    "month",
    "newer",
    "newer_than",
    "of",
    "older",
    "older_than",
    "or",
    "sent",
    "subject",
    "the",
    "them",
    "this",
    "by",
    "check",
    "group",
    "s",
    "summarize",
    "tell",
    "to",
}


def _tokens(value: str) -> set[str]:
    normalized: set[str] = set()
    for token in _TOKEN_PATTERN.findall(value.lower()):
        if token in _IGNORED_QUERY_WORDS or token.isdigit():
            continue
        if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
            token = token[:-1]
        normalized.add(token)
    return normalized


class BenchmarkEmailBackend:
    """Serve fixture emails without contacting Gmail or Composio."""

    def __init__(
        self,
        fixture_path: Path,
        now_provider: Optional[Callable[[], datetime]] = None,
    ) -> None:
        self.fixture_path = fixture_path.resolve()
        payload = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        messages = payload.get("messages") if isinstance(payload, dict) else None
        if not isinstance(messages, list) or not messages:
            raise ValueError("benchmark email fixture must contain a non-empty messages list")
        self.account = payload.get("account", {})
        self.messages = [self._normalize_message(item) for item in messages]
        self._now_provider = now_provider
        self._drafts: list[dict[str, Any]] = []
        self._lock = threading.Lock()

    @staticmethod
    def _normalize_message(item: Any) -> dict[str, Any]:
        if not isinstance(item, dict):
            raise ValueError("benchmark email messages must be JSON objects")
        required = ("id", "thread", "timestamp", "subject", "sender", "to", "body")
        missing = [key for key in required if not str(item.get(key, "")).strip()]
        if missing:
            raise ValueError(f"benchmark email message is missing: {', '.join(missing)}")
        aliases = item.get("aliases", [])
        if not isinstance(aliases, list):
            raise ValueError("benchmark email aliases must be a list")
        return {
            "id": str(item["id"]),
            "thread": str(item["thread"]),
            "timestamp": str(item["timestamp"]),
            "subject": str(item["subject"]),
            "sender": str(item["sender"]),
            "to": str(item["to"]),
            "body": str(item["body"]),
            "aliases": [str(alias) for alias in aliases],
        }

    @staticmethod
    def _raw_message(message: dict[str, Any]) -> dict[str, Any]:
        return {
            "messageId": message["id"],
            "threadId": message["thread"],
            "messageTimestamp": message["timestamp"],
            "subject": message["subject"],
            "sender": message["sender"],
            "to": message["to"],
            "textBody": message["body"],
            "labelIds": ["INBOX"],
            "attachmentList": [],
        }

    def _search(self, arguments: dict[str, Any]) -> dict[str, Any]:
        query = str(arguments.get("query", ""))
        query_tokens = _tokens(query)
        max_results = max(1, min(int(arguments.get("max_results", 10)), 100))
        ranked: list[tuple[int, str, dict[str, Any]]] = []
        if self._now_provider is None:
            from server.benchmark_clock import get_benchmark_clock

            visible_at = get_benchmark_clock().now_utc()
        else:
            visible_at = self._now_provider()

        for message in self.messages:
            message_time = datetime.fromisoformat(
                message["timestamp"].replace("Z", "+00:00")
            )
            if message_time.tzinfo is None:
                message_time = message_time.replace(tzinfo=timezone.utc)
            if message_time.astimezone(timezone.utc) > visible_at:
                continue
            searchable = " ".join(
                [
                    message["subject"],
                    message["sender"],
                    message["body"],
                    *message["aliases"],
                ]
            )
            message_tokens = _tokens(searchable)
            overlap = query_tokens & message_tokens
            alias_hits = sum(
                1 for alias in message["aliases"] if alias.lower() in query.lower()
            )
            score = len(overlap) + (alias_hits * 5)
            if score:
                ranked.append((score, message["timestamp"], message))

        ranked.sort(key=lambda item: (item[0], item[1]), reverse=True)
        selected = [self._raw_message(item[2]) for item in ranked[:max_results]]
        return {"data": {"messages": selected}}

    def execute(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        """Execute the supported Gmail operation against local fixture state."""
        if tool_name == "GMAIL_FETCH_EMAILS":
            return self._search(arguments)
        if tool_name == "GMAIL_GET_PROFILE":
            return {
                "data": {
                    "emailAddress": self.account.get("email", "benchmark@example.test"),
                    "messagesTotal": len(self.messages),
                }
            }
        if tool_name == "GMAIL_CREATE_EMAIL_DRAFT":
            with self._lock:
                draft_id = f"benchmark-draft-{len(self._drafts) + 1:04d}"
                self._drafts.append({"id": draft_id, **arguments})
            return {"successful": True, "data": {"id": draft_id}}
        if tool_name == "GMAIL_LIST_DRAFTS":
            with self._lock:
                return {"data": {"drafts": list(self._drafts)}}
        if tool_name == "GMAIL_DELETE_DRAFT":
            draft_id = str(arguments.get("draft_id", ""))
            with self._lock:
                self._drafts = [draft for draft in self._drafts if draft["id"] != draft_id]
            return {"successful": True, "data": {"id": draft_id}}
        if tool_name in {
            "GMAIL_SEND_DRAFT",
            "GMAIL_FORWARD_MESSAGE",
            "GMAIL_REPLY_TO_THREAD",
        }:
            return {"successful": True, "data": {"simulated": True}}
        if tool_name in {"GMAIL_GET_CONTACTS", "GMAIL_GET_PEOPLE", "GMAIL_SEARCH_PEOPLE"}:
            return {"data": {"people": []}}
        raise ValueError(f"unsupported benchmark Gmail tool: {tool_name}")


_BACKENDS: dict[Path, BenchmarkEmailBackend] = {}
_BACKENDS_LOCK = threading.Lock()


def get_benchmark_email_backend(fixture_path: Path) -> BenchmarkEmailBackend:
    """Return one fixture backend instance for each fixture path."""
    resolved = fixture_path.resolve()
    with _BACKENDS_LOCK:
        backend = _BACKENDS.get(resolved)
        if backend is None:
            backend = BenchmarkEmailBackend(resolved)
            _BACKENDS[resolved] = backend
        return backend


__all__ = ["BenchmarkEmailBackend", "get_benchmark_email_backend"]
