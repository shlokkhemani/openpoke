"""Capture an agent's contacts (and their names) from successful Gmail and email-search tool calls."""

from __future__ import annotations

from email.utils import getaddresses
from typing import Any, Dict, List, Optional, Tuple

from ...logging_config import logger
from .store import ContactRecord

# tool name -> ((argument, role), ...). bcc is deliberately ignored.
# Known limit (documented, not fixed, Siddharth 2026-11-08): contacts are added only when an agent
# sends. An agent that only searches or reads mail ("Find emails from Helena about ...") gets no
# contact rows (``record_contact_names_from_tool_call`` fills names, never adds contacts), so the
# retrieval contact boost and person expansion skip it; it is found only by its name/description
# text. The eval world writes contacts for every agent, so evals don't measure this gap.
_RECIPIENT_FIELDS: Dict[str, Tuple[Tuple[str, str], ...]] = {
    "gmail_create_draft": (("recipient_email", "to"), ("extra_recipients", "to"), ("cc", "cc")),
    "gmail_reply_to_thread": (("recipient_email", "to"), ("extra_recipients", "to"), ("cc", "cc")),
    "gmail_forward_email": (("recipient_email", "to"),),
    # gmail_execute_draft only carries a draft id: nothing to capture (known gap, scope §2).
}


def _is_failed(result: Any) -> bool:
    if isinstance(result, dict):
        return bool(result.get("error")) or result.get("successful") is False
    return False


def _addresses(value: Any) -> List[Tuple[str, str]]:
    """(lowercased address, display name) pairs from ``"Name <addr>"`` / bare strings; no-@ entries skipped."""
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, (list, tuple)):
        return []
    found: List[Tuple[str, str]] = []
    for raw in value:
        if not isinstance(raw, str) or not raw.strip():
            continue
        for name, addr in getaddresses([raw]):
            addr = addr.strip().lower()
            if "@" not in addr:
                logger.debug(f"skipping recipient without an address: {raw!r}")
                continue
            found.append((addr, " ".join(name.split())))
    return found


def contacts_from_tool_call(tool_name: str, args: Optional[Dict[str, Any]], result: Any) -> List[ContactRecord]:
    """Recipients of a successful Gmail send-type call (empty otherwise)."""
    fields = _RECIPIENT_FIELDS.get(tool_name)
    if not fields or not isinstance(args, dict) or _is_failed(result):
        return []
    return [
        ContactRecord(email=email, display_name=name, role=role)
        for arg, role in fields
        for email, name in _addresses(args.get(arg))
    ]


def record_contacts_from_tool_call(
    store: Any, agent_id: str, tool_name: str, args: Optional[Dict[str, Any]], result: Any
) -> None:
    """Record recipients of a successful Gmail send-type call. Never raises."""
    try:
        contacts = contacts_from_tool_call(tool_name, args, result)
        if contacts:
            store.add_contacts(agent_id, contacts)
    except Exception as exc:
        logger.warning(f"[{agent_id}] contact capture failed for {tool_name}: {exc}")


_SEARCH_TOOL = "task_email_search"
_HEADER_KEYS = ("sender", "recipient")


def _reads_mail(tool_name: str) -> bool:
    return tool_name == _SEARCH_TOOL or tool_name.startswith("gmail_")


def _plain(node: Any) -> Any:
    return node.model_dump() if hasattr(node, "model_dump") else node


def _header_names(node: Any, found: Dict[str, str], depth: int = 0) -> None:
    node = _plain(node)
    if depth > 8:
        return
    if isinstance(node, dict):
        for key, value in node.items():
            if key in _HEADER_KEYS and isinstance(value, str):
                for email, name in _addresses(value):
                    if name:
                        found.setdefault(email, name)
            else:
                _header_names(value, found, depth + 1)
    elif isinstance(node, (list, tuple)):
        for item in node:
            _header_names(item, found, depth + 1)


def record_contact_names_from_tool_call(store: Any, agent_id: str, tool_name: str, result: Any) -> None:
    """Fill empty names of already-recorded contacts from sender/recipient headers. Never adds contacts or raises."""
    try:
        if not _reads_mail(tool_name) or _is_failed(result):
            return
        names: Dict[str, str] = {}
        _header_names(result, names)
        if names:
            store.fill_contact_names(agent_id, names)
    except Exception as exc:
        logger.warning(f"[{agent_id}] contact name fill failed for {tool_name}: {exc}")


_SUBJECT_ARG_TOOLS = {"gmail_create_draft", "gmail_reply_to_thread", "gmail_forward_email"}


def _subjects_in(node: Any, found: List[str], depth: int = 0) -> None:
    node = _plain(node)
    if depth > 8:
        return
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "subject" and isinstance(value, str):
                if value.strip():
                    found.append(value.strip())
            else:
                _subjects_in(value, found, depth + 1)
    elif isinstance(node, (list, tuple)):
        for item in node:
            _subjects_in(item, found, depth + 1)


def extract_subjects(tool_name: str, args: Any, result: Any) -> List[str]:
    """Email subjects of a successful Gmail or email-search call: the ``subject`` argument of sends, else any in the result."""
    try:
        if not _reads_mail(tool_name) or _is_failed(result):
            return []
        if tool_name in _SUBJECT_ARG_TOOLS:
            subject = args.get("subject") if isinstance(args, dict) else None
            return [subject.strip()] if isinstance(subject, str) and subject.strip() else []
        found: List[str] = []
        _subjects_in(result, found)
        return found
    except Exception as exc:
        logger.warning(f"subject extraction failed for {tool_name}: {exc}")
        return []


__all__ = ["extract_subjects", "record_contact_names_from_tool_call", "record_contacts_from_tool_call"]
