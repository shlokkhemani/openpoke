"""Memory policy (deep dive §6-§8, §10, §13, §20). Deterministic: the extractor proposes, this module disposes."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, time, timedelta, timezone
from typing import Callable, Dict, List, Optional, Tuple

from . import vocab
from .models import (
    POLICY_VERSION,
    Candidate,
    Decision,
    NewRecord,
    PolicyDecision,
    PrivacyVerdict,
    SlotInfo,
    from_iso,
    to_iso,
)

# §7 importance
TYPE_BASE = {"constraint": 0.85, "preference": 0.65, "profile": 0.60, "relationship": 0.60, "project": 0.60}
DURABILITY = {"long_term": +0.10, "medium_term": +0.05, "short_term": -0.10, "transient": -0.50}
HABITUAL_RX = r"\b(always|never|usually|prefer|generally|every)\b"
STORE_THRESHOLD = 0.50

# §8 confidence
CERTAINTY = {"explicit": 0.90, "hedged": 0.60, "inferred": 0.45}
SOURCE_TRUST = {"user_message": 1.0}
HALF_LIFE_DAYS = {"profile": 365, "preference": 365, "relationship": 365, "project": 60, "constraint": None}
MERGE_CAP = 0.98

# §13 TTL
TTL = {"project": timedelta(days=90)}
HIGH_SENS_TTL = timedelta(days=180)
HORIZON_GRACE = timedelta(days=7)

ENABLED_TYPES = {"profile", "preference", "constraint", "relationship", "project"}

# §20 poisoning
INJECTION_RX = [r"ignore (all |any )?(previous|prior|above) (instructions|rules)", r"\bsystem prompt\b",
                r"\byou (must|should) (now )?(always|never)\b.*\b(send|forward|share|reveal|exfiltrat)",
                r"\bdisregard\b.*\binstructions\b", r"</?\s*(long_term_memory|system|assistant|tool)\b"]
WIDENING_RX = [r"\b(always|automatically|without asking)\b.*\b(send|forward|cc|bcc|share|pay|transfer|delete)\b",
               r"\b(send|forward|cc|bcc)\b.*\b(to|everything)\b"]
_DESTINATION_RX = re.compile(r"\[(?:EMAIL|PHONE)_\d+\]|https?://|\b[\w.+-]+@[\w-]+\.[\w.-]+\b|\bwww\.", re.I)


def r2(x: float) -> float:
    return round(x + 1e-9, 2)


def clamp(x: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return max(lo, min(hi, x))


# ---------------------------------------------------------------------------
# §6 slot assignment
# ---------------------------------------------------------------------------


def assign_slot(c: Candidate) -> SlotInfo:
    spec = vocab.spec_for(c.predicate) or vocab.CUSTOM_SPEC
    mtype = spec.memory_type  # predicate wins over the extractor's type
    subject = "user" if c.subject in (None, "", "user") else vocab.normalise_entity(c.subject)
    obj = c.object_entity if spec.keyed else None
    if obj and ":" not in obj:
        obj = vocab.normalise_entity(obj)
    slot_key = "|".join(x for x in (subject, c.predicate, obj) if x)
    return SlotInfo(mtype, subject, c.predicate, spec.cardinality, slot_key, spec.value_type, spec.keyed,
                    tuple(vocab.keywords_for(c.predicate)))


# ---------------------------------------------------------------------------
# §7 importance, §8 confidence
# ---------------------------------------------------------------------------


def importance(c: Candidate, slot: SlotInfo) -> Tuple[float, Dict[str, float]]:
    parts: Dict[str, float] = {f"type:{slot.memory_type}": TYPE_BASE[slot.memory_type],
                               f"durability:{c.durability}": DURABILITY[c.durability]}
    if c.explicit_remember:
        parts["explicit_remember"] = 0.20
    if re.search(HABITUAL_RX, c.evidence or "", re.I):
        parts["habitual"] = 0.05
    if slot.subject != "user" and slot.memory_type != "relationship":
        parts["not_about_user"] = -0.30
    return r2(clamp(sum(parts.values()))), {k: r2(v) for k, v in parts.items()}


def initial_confidence(c: Candidate, source_kind: str) -> float:
    return r2(CERTAINTY[c.certainty] * SOURCE_TRUST[source_kind])


def on_merge(old_conf: float, new_conf: float) -> float:
    return r2(min(MERGE_CAP, max(old_conf, new_conf) + 0.05))


def effective_confidence(memory_type: str, confidence: float, last_confirmed_at: str, now: datetime) -> float:
    hl = HALF_LIFE_DAYS[memory_type]
    if hl is None:
        return confidence
    age = (now - from_iso(last_confirmed_at)).days
    return confidence * 0.5 ** (age / hl)


# ---------------------------------------------------------------------------
# §13 TTL
# ---------------------------------------------------------------------------


def _end_of_day(d: date) -> datetime:
    return datetime.combine(d, time(23, 59, 59), tzinfo=timezone.utc)


def ttl(slot: SlotInfo, c: Candidate, observed_at: datetime, sensitivity: str) -> Optional[str]:
    exp: Optional[datetime] = None
    if slot.memory_type in TTL:
        exp = observed_at + TTL[slot.memory_type]
    if c.horizon:
        h = _end_of_day(c.horizon) + HORIZON_GRACE
        exp = h if exp is None else min(exp, h)
    if sensitivity == "high":
        h = observed_at + HIGH_SENS_TTL
        exp = h if exp is None else min(exp, h)
    return to_iso(exp) if exp else None


# ---------------------------------------------------------------------------
# §20 poisoning
# ---------------------------------------------------------------------------


def is_restrictive(c: Candidate) -> bool:
    return c.predicate in {"constraint.confirm_before_email", "constraint.avoid"}


def contains_destination(t: str) -> bool:
    return bool(_DESTINATION_RX.search(t))


def poisoning_check(c: Candidate, memory_type: Optional[str] = None) -> Optional[List[str]]:
    mtype = memory_type or c.memory_type
    t = f"{c.evidence} {c.text} {json.dumps(c.value)}"
    reasons: List[str] = []
    if c.is_instruction_to_assistant and mtype != "constraint":
        reasons.append("INSTRUCTION_LIKE")
    if any(re.search(rx, t, re.I) for rx in INJECTION_RX):
        reasons.append("POISONING_SUSPECTED")
    if any(re.search(rx, t, re.I) for rx in WIDENING_RX):
        reasons.append("CAPABILITY_WIDENING")
    if mtype == "constraint" and not is_restrictive(c) and "CAPABILITY_WIDENING" not in reasons:
        reasons.append("CAPABILITY_WIDENING")
    if mtype == "constraint" and contains_destination(t):
        reasons.append("EXTERNAL_DESTINATION")
    return reasons or None


def canonical_text(c: Candidate, slot: SlotInfo) -> str:
    """LTM_BLOCKERS.md B4 (review M4): for controlled-vocabulary predicates the stored/rendered sentence is ALWAYS the
    deterministic template over (predicate, value); extractor free text is ignored. Custom predicates keep the
    candidate text, which extractor.validate has already required to be grounded in the user's message."""
    if c.predicate.startswith("pref.custom:"):
        return c.text
    obj = slot.slot_key.split("|")[2] if slot.keyed and slot.slot_key.count("|") >= 2 else c.object_entity
    return vocab.render(c.predicate, c.value, obj)


# ---------------------------------------------------------------------------
# §10 decide
# ---------------------------------------------------------------------------


def decide(
    c: Candidate,
    v: PrivacyVerdict,
    source_kind: str,
    *,
    value_hmac: Callable[[str, str], str],
    source_turn_id: str,
    observed_at: datetime,
    extractor_version: str,
) -> Decision:
    """First match wins (privacy and poisoning before worthiness). ``value_hmac(slot_key, canonical)`` is the
    store's keyed hash for the caller's scope."""
    if source_kind != "user_message":
        return Decision(PolicyDecision.IGNORE, ["SOURCE_NOT_ALLOWED"])
    if v.action == "REJECT":
        return Decision(PolicyDecision.REJECT, list(v.reasons))
    slot = assign_slot(c)
    poison = poisoning_check(c, slot.memory_type)
    if poison:
        return Decision(PolicyDecision.REJECT, poison, slot=slot)  # prod: QUARANTINE
    if not vocab.is_storable(c.predicate):
        return Decision(PolicyDecision.IGNORE, ["PREDICATE_NOT_STORABLE"], slot=slot)
    imp, breakdown = importance(c, slot)
    conf = initial_confidence(c, source_kind)
    if slot.memory_type not in ENABLED_TYPES:
        return Decision(PolicyDecision.IGNORE, ["TYPE_DISABLED"], slot=slot)
    if c.durability == "transient":
        return Decision(PolicyDecision.IGNORE, ["TRANSIENT"], importance=imp, importance_breakdown=breakdown, slot=slot)
    if slot.subject != "user" and slot.memory_type != "relationship" and not slot.keyed:
        return Decision(PolicyDecision.IGNORE, ["NOT_ABOUT_USER"], importance=imp, importance_breakdown=breakdown,
                        slot=slot)
    if imp < STORE_THRESHOLD:
        return Decision(PolicyDecision.IGNORE, ["LOW_IMPORTANCE"], importance=imp, importance_breakdown=breakdown,
                        slot=slot)
    sensitivity = v.sensitivity.lower()
    canon = vocab.canonical_value(c.predicate, c.value)
    rec = NewRecord(
        slot=slot,
        value_json=vocab.value_json(c.predicate, c.value),
        value_hmac=value_hmac(slot.slot_key, canon),
        canonical_text=canonical_text(c, slot),
        importance=imp,
        confidence=conf,
        sensitivity=sensitivity,
        pii_categories=list(v.categories),
        source_kind=source_kind,
        source_turn_id=source_turn_id,
        observed_at=to_iso(observed_at),
        expires_at=ttl(slot, c, observed_at, sensitivity),
        extractor_version=extractor_version,
        policy_version=POLICY_VERSION,
        candidate_id=c.candidate_id,
    )
    return Decision(PolicyDecision.STORE, list(v.reasons), record=rec, importance=imp,
                    importance_breakdown=breakdown, confidence=conf, slot=slot)
