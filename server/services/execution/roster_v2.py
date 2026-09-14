"""Worker roster with metadata, for the budgeted context strategy.

Legacy stores a bare list of names in roster.json and renders every name into every interaction-agent
prompt. This module adds, per worker: purpose (from its first request), created/last-used timestamps,
run count, the last task, and identifiers seen in its last report (draft/thread/message ids). It is
kept in a sibling file (roster_meta.json) so the legacy roster.json is untouched.

Rendering follows the same pattern as history: the most recently used workers appear inline with
their metadata; the rest are a count; `find_worker(query)` searches purpose / last task / identifiers.
"""

from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...logging_config import logger
from .roster import get_agent_roster

_ID_RE = re.compile(r"\b(?:draft|thr|thread|msg|message)[-_][A-Za-z0-9]{3,}\b|\b[0-9a-f]{12,}\b", re.IGNORECASE)
_STOP = {"the", "a", "an", "to", "of", "for", "and", "or", "in", "on", "with", "about", "from", "please", "email", "emails",
         "agent", "worker", "task", "reply", "find", "send", "draft", "create", "me", "my", "user", "this", "that", "it"}


def _terms(text: str) -> set:
    return {t.strip(".,;:!?\"'()[]").lower() for t in text.split() if len(t) >= 3} - _STOP


class RosterMeta:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._meta: Dict[str, Dict[str, Any]] = {}
        self.load()

    # ---- persistence -------------------------------------------------
    def load(self) -> None:
        try:
            if self._path.exists():
                data = json.loads(self._path.read_text(encoding="utf-8"))
                self._meta = data if isinstance(data, dict) else {}
            else:
                self._meta = {}
        except Exception as exc:
            logger.warning(f"Failed to load roster_meta.json: {exc}")
            self._meta = {}

    def save(self) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            self._path.write_text(json.dumps(self._meta, indent=1), encoding="utf-8")
        except Exception as exc:
            logger.warning(f"Failed to save roster_meta.json: {exc}")

    # ---- updates -----------------------------------------------------
    def record_request(self, name: str, instructions: str) -> None:
        now = time.time()
        m = self._meta.setdefault(name, {"purpose": "", "created": now, "last_used": now, "runs": 0, "last_task": "", "ids": []})
        if not m.get("purpose"):
            m["purpose"] = " ".join(instructions.split())[:140]
        m["last_task"] = " ".join(instructions.split())[:200]
        m["last_used"] = now
        m["runs"] = int(m.get("runs", 0)) + 1
        self.save()

    def record_report(self, name: str, report: str) -> None:
        m = self._meta.get(name)
        if m is None:
            return
        ids = list(dict.fromkeys(x.group(0) for x in _ID_RE.finditer(report or "")))[:8]
        if ids:
            m["ids"] = ids
        self.save()

    # ---- reads -------------------------------------------------------
    def get(self, name: str) -> Dict[str, Any]:
        return dict(self._meta.get(name) or {})

    def all_names(self) -> List[str]:
        roster = get_agent_roster()
        roster.load()
        return roster.get_agents()

    def recent(self, limit: int) -> List[str]:
        names = self.all_names()
        return sorted(names, key=lambda n: float((self._meta.get(n) or {}).get("last_used", 0)), reverse=True)[:limit]

    def search(self, query: str, limit: int = 5) -> List[Dict[str, Any]]:
        q = _terms(query)
        if not q:
            return []
        scored = []
        for n in self.all_names():
            m = self._meta.get(n) or {}
            ids_text = " ".join(m.get("ids", [])).lower()
            purpose = (m.get("purpose", "") + " " + m.get("last_task", "")).lower()
            name_terms = _terms(n)
            # Identifiers are decisive, purpose/last-task text next, the name last: names are free-form and
            # near-duplicates are common, so a name hit alone should not outrank a worker that did the work.
            score = sum(5 for t in q if t in ids_text) + sum(2 for t in q if t in purpose) + sum(1 for t in q if t in name_terms)
            if score:
                # A worker holding identifiers did real work; prefer it over a name-only match at equal keyword score.
                evidence = 1 if m.get("ids") else 0
                scored.append((score, evidence, float(m.get("last_used", 0)), n))
        scored.sort(key=lambda x: (-x[0], -x[1], -x[2]))
        return [self.describe(n) for _, _, _, n in scored[:limit]]

    def _unused(self):
        scored = []
        return []

    def describe(self, name: str) -> Dict[str, Any]:
        m = self._meta.get(name) or {}
        return {"name": name, "purpose": m.get("purpose", ""), "last_task": m.get("last_task", ""), "runs": m.get("runs", 0),
                "last_used": _ago(m.get("last_used")), "ids": m.get("ids", [])}

    # ---- prompt rendering ---------------------------------------------
    def render(self, *, inline_limit: int) -> str:
        names = self.all_names()
        if not names:
            return "None"
        shown = self.recent(inline_limit)
        lines = []
        for n in shown:
            m = self._meta.get(n) or {}
            bits = [f'name="{_esc(n)}"']
            if m.get("purpose"):
                bits.append(f'purpose="{_esc(m["purpose"][:90])}"')
            if m.get("last_used"):
                bits.append(f'last_used="{_ago(m["last_used"])}"')
            if m.get("ids"):
                bits.append(f'ids="{_esc(", ".join(m["ids"][:4]))}"')
            lines.append(f"<agent {' '.join(bits)} />")
        hidden = len(names) - len(shown)
        if hidden > 0:
            lines.append(f'<more_agents count="{hidden}" note="older workers not listed; call find_worker with a few words '
                         f'about the task or counterpart to look one up before creating a new worker" />')
        return "\n".join(lines)


def _esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace('"', "&quot;").replace("<", "&lt;")


def _ago(ts: Optional[float]) -> str:
    if not ts:
        return "unknown"
    d = max(0, time.time() - float(ts))
    if d < 90:
        return "just now"
    if d < 3600:
        return f"{int(d // 60)}m ago"
    if d < 86400:
        return f"{int(d // 3600)}h ago"
    return f"{int(d // 86400)}d ago"


_roster_meta: Optional[RosterMeta] = None


def get_roster_meta() -> RosterMeta:
    global _roster_meta
    if _roster_meta is None:
        _roster_meta = RosterMeta(get_agent_roster()._roster_path.with_name("roster_meta.json"))
    else:
        # follow the roster path if the harness redirected it
        want = get_agent_roster()._roster_path.with_name("roster_meta.json")
        if _roster_meta._path != want:
            _roster_meta = RosterMeta(want)
    return _roster_meta


__all__ = ["RosterMeta", "get_roster_meta"]
