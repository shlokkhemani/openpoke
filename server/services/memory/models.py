"""Core LTM types (deep dive §0.2).

Python 3.10 compatible: enums subclass ``(str, Enum)`` (no 3.11 enum helpers); UTC is ``timezone.utc``.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

EXTRACTOR_VERSION_RULES = "rules-0.1"
EXTRACTOR_VERSION_LLM = "llm-0.1"
POLICY_VERSION = "policy-0.1"


class MemoryType(str, Enum):
    PROFILE = "profile"
    PREFERENCE = "preference"
    CONSTRAINT = "constraint"
    RELATIONSHIP = "relationship"
    PROJECT = "project"


class Status(str, Enum):
    ACTIVE = "active"
    CONTESTED = "contested"
    SUPERSEDED = "superseded"
    EXPIRED = "expired"
    DELETED = "deleted"
    QUARANTINED = "quarantined"


class Durability(str, Enum):
    TRANSIENT = "transient"
    SHORT_TERM = "short_term"
    MEDIUM_TERM = "medium_term"
    LONG_TERM = "long_term"


class Certainty(str, Enum):
    EXPLICIT = "explicit"
    HEDGED = "hedged"
    INFERRED = "inferred"


class Sensitivity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    PROHIBITED = "prohibited"  # never stored


class PolicyDecision(str, Enum):
    STORE = "STORE"
    IGNORE = "IGNORE"
    REJECT = "REJECT"
    QUARANTINE = "QUARANTINE"


class ConsolidationOutcome(str, Enum):
    INSERT = "INSERT"
    MERGE = "MERGE"
    UPDATE = "UPDATE"
    SUPERSEDE = "SUPERSEDE"
    CONTEST = "CONTEST"
    DROP_STALE = "DROP_STALE"
    FENCE_DROP = "FENCE_DROP"


# ---------------------------------------------------------------------------
# Time and ids
# ---------------------------------------------------------------------------


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def to_iso(dt: datetime) -> str:
    """UTC ISO-8601 with milliseconds and a ``Z`` suffix (C10). Lexicographically ordered."""
    dt = dt.astimezone(timezone.utc)
    return dt.strftime("%Y-%m-%dT%H:%M:%S.") + f"{dt.microsecond // 1000:03d}Z"


def from_iso(value: str) -> datetime:
    """Parse ``to_iso`` output. ``fromisoformat`` rejects ``Z`` before Python 3.11."""
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    dt = datetime.fromisoformat(value)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def ulid() -> str:
    """26-char ULID: 48-bit ms timestamp + 80 random bits, Crockford base32."""
    value = (int(time.time() * 1000) << 80) | int.from_bytes(os.urandom(10), "big")
    out = []
    for _ in range(26):
        out.append(_CROCKFORD[value & 31])
        value >>= 5
    return "".join(reversed(out))


def new_id(prefix: str) -> str:
    return f"{prefix}_{ulid()}"


# ---------------------------------------------------------------------------
# Scope and turns
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class MemoryScope:
    """The ONLY way to address the store (§23). Constructed by ``resolve_memory_scope`` and tests."""

    user_id: str


@dataclass(frozen=True)
class TurnRef:
    trace_id: str
    turn_id: str
    scope: MemoryScope
    observed_at: datetime
    epoch: int
    source_kind: str  # 'user_message' | 'agent_message'

    @property
    def observed_iso(self) -> str:
        return to_iso(self.observed_at)


# ---------------------------------------------------------------------------
# Privacy
# ---------------------------------------------------------------------------


@dataclass
class Finding:
    """Deterministic detector hit. NEVER persisted with the value."""

    kind: str
    cls: str
    start: int
    end: int
    placeholder: Optional[str] = None


@dataclass
class ScrubbedText:
    llm_safe: str
    findings: List[Finding]


@dataclass
class PrivacyVerdict:
    sensitivity: str  # 'LOW' | 'MEDIUM' | 'HIGH' | 'PROHIBITED'
    action: str  # 'STORE' | 'REJECT'
    reasons: List[str] = field(default_factory=list)
    categories: List[str] = field(default_factory=list)
    detector_types: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Extraction / policy / consolidation
# ---------------------------------------------------------------------------


@dataclass
class Candidate:
    candidate_id: str
    memory_type: str
    subject: str
    predicate: str
    object_entity: Optional[str]
    value: Any
    text: str
    durability: str
    certainty: str
    is_correction: bool = False
    explicit_remember: bool = False
    is_instruction_to_assistant: bool = False
    sensitivity_category: str = "none"
    evidence: str = ""
    horizon: Optional[date] = None


@dataclass
class IgnoredClause:
    evidence: str
    reason: str


@dataclass
class ExtractionResult:
    candidates: List[Candidate]
    ignored: List[IgnoredClause]
    extractor_version: str
    error: Optional[str] = None  # e.g. 'MALFORMED_JSON': zero candidates, reported as an event


@dataclass(frozen=True)
class SlotInfo:
    memory_type: str
    subject: str
    predicate: str
    cardinality: str
    slot_key: str
    value_type: str
    keyed: bool
    keywords: tuple


@dataclass
class NewRecord:
    """A row ready for consolidation. Contains MEMORY_SAFE text only."""

    slot: SlotInfo
    value_json: str
    value_hmac: str
    canonical_text: str
    importance: float
    confidence: float
    sensitivity: str
    pii_categories: List[str]
    source_kind: str
    source_turn_id: str
    observed_at: str
    expires_at: Optional[str]
    extractor_version: str
    policy_version: str
    candidate_id: Optional[str] = None
    related_id: Optional[str] = None

    @property
    def slot_key(self) -> str:
        return self.slot.slot_key


@dataclass
class Decision:
    kind: PolicyDecision
    reasons: List[str] = field(default_factory=list)
    record: Optional[NewRecord] = None
    importance: Optional[float] = None
    importance_breakdown: Optional[Dict[str, float]] = None
    confidence: Optional[float] = None
    slot: Optional[SlotInfo] = None


@dataclass
class Outcome:
    kind: ConsolidationOutcome
    memory_id: Optional[str] = None
    old_id: Optional[str] = None
    reason_codes: List[str] = field(default_factory=list)
    detail: Dict[str, Any] = field(default_factory=dict)  # LOG_SAFE
    dev_detail: Dict[str, Any] = field(default_factory=dict)  # MEMORY_SAFE, dev-mode events only
