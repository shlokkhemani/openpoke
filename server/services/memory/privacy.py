"""Privacy gateway: ingress scrub (§4.1), P0 scrub (§4), P1 classify (§9), P2 egress (§18)."""

from __future__ import annotations

import json
import re
from collections import Counter
from typing import Callable, Dict, List, Optional, Tuple

from .detectors import PLACEHOLDER_RX, detect, detect_all, high_entropy_tokens, resolve_overlaps
from .models import Candidate, Finding, PrivacyVerdict, ScrubbedText

INGRESS_CLASSES = {"SECRET", "REGULATED_ID"}

# ---------------------------------------------------------------------------
# Ingress-persistence scrub (§4.1): prohibited classes only, irreversible
# ---------------------------------------------------------------------------


def _placeholder_for(f: Finding) -> str:
    return f"[SECRET:{f.kind}]" if f.cls == "SECRET" else f"[{f.kind}]"


def ingress_scrub(text: str) -> Tuple[str, List[Finding]]:
    """Replace SECRET / REGULATED_ID spans with typed placeholders. NO raw map: irreversible by design.

    Idempotent: placeholders are never re-detected (detectors.PLACEHOLDER_RX), so I1 + I2 is safe.
    The ``ingress.scrub`` event is emitted by the caller that owns the trace (``MemoryService.prepare_turn``).
    """
    if not text:
        return text, []
    findings = [f for f in detect_all(text) if f.cls in INGRESS_CLASSES]
    if not findings:
        return text, []
    out, cursor = [], 0
    for f in sorted(findings, key=lambda f: f.start):
        f.placeholder = _placeholder_for(f)
        out.append(text[cursor:f.start])
        out.append(f.placeholder)
        cursor = f.end
    out.append(text[cursor:])
    return "".join(out), findings


def prohibited_findings(text: str) -> List[Finding]:
    """Leak-guard primitive: any SECRET / REGULATED_ID pattern left in ``text``."""
    return [f for f in detect_all(text) if f.cls in INGRESS_CLASSES]


# ---------------------------------------------------------------------------
# P0 scrub (§4): LLM_SAFE representation
# ---------------------------------------------------------------------------


def _escape_user_brackets(text: str) -> str:
    """'[' -> '［' unless it opens a real placeholder (ingress output must stay recognisable to P1)."""
    keep = {m.start() for m in PLACEHOLDER_RX.finditer(text) if _is_real_placeholder(m.group())}
    return "".join("［" if ch == "[" and i not in keep else ch for i, ch in enumerate(text))


# Only what ingress_scrub can emit; a user-typed "[EMAIL_1]" is a collision and gets escaped (§4).
_REAL_PLACEHOLDER = re.compile(r"\[(?:SECRET:[A-Z_]+|CARD|GOV_ID|IBAN)\]")


def _is_real_placeholder(s: str) -> bool:
    return bool(_REAL_PLACEHOLDER.fullmatch(s))


def scrub(text: str) -> Tuple[ScrubbedText, Dict[str, str]]:
    """Typed placeholders for every detector class. The placeholder->value map covers only reversible classes
    (CONTACT, PRECISE_LOCATION) and must stay in the caller's local scope."""
    text = _escape_user_brackets(text or "")
    findings = detect_all(text)
    counters: Counter = Counter()
    out: List[str] = []
    raw_map: Dict[str, str] = {}
    cursor = 0
    for f in sorted(findings, key=lambda f: f.start):
        counters[f.kind] += 1
        if f.cls == "SECRET":
            f.placeholder = f"[SECRET:{f.kind}]"
        elif f.cls == "REGULATED_ID":
            f.placeholder = f"[{f.kind}]"
        else:
            f.placeholder = f"[{f.kind}_{counters[f.kind]}]"
        out.append(text[cursor:f.start])
        out.append(f.placeholder)
        cursor = f.end
        if f.cls in ("CONTACT", "PRECISE_LOCATION"):
            raw_map[f.placeholder] = text[f.start:f.end]  # SECRET / REGULATED never mapped
    out.append(text[cursor:])
    return ScrubbedText("".join(out), findings), raw_map


# ---------------------------------------------------------------------------
# P1 classify (§9)
# ---------------------------------------------------------------------------

SPECIAL = {"health", "sexuality", "religion", "politics", "immigration", "criminal", "minor", "biometric"}
MEDIUM = {"finance", "family", "location_coarse"}
LEXICON = {
    "health": r"\b(diagnos\w*|therapy|therapist|medication|adhd|depress\w*|pregnan\w*|hiv|cancer|surgery)\b",
    "finance": r"\b(debt|loan|salary|rent|overdraft|bankrupt\w*|credit score)\b",
    "religion": r"\b(church|mosque|synagogue|temple|religio\w*|pray\w*|atheis\w*)\b",
    "sexuality": r"\b(gay|lesbian|bisexual|transgender|queer|sexual orientation)\b",
    "politics": r"\b(democrat\w*|republican\w*|political party|vote[sd]? for)\b",
    "immigration": r"\b(visa status|green card|asylum|undocumented|deport\w*|work permit)\b",
    "criminal": r"\b(arrest\w*|convict\w*|felony|criminal record|parole|probation)\b",
    "minor": r"\b(my (?:son|daughter|kid|child) is \d{1,2})\b",
    "biometric": r"\b(fingerprint|face ?id|retina|biometric\w*)\b",
    "family": r"\b(my (?:wife|husband|partner|son|daughter|kids?|children|mom|mother|dad|father|sister|brother))\b",
}

_PLACEHOLDER_KINDS = re.compile(r"\[(SECRET:[A-Z_]+|[A-Z_]+?)(?:_\d+)?\]")
_PLACEHOLDER_CLASS = {"EMAIL": "CONTACT", "PHONE": "CONTACT", "ADDRESS": "PRECISE_LOCATION",
                      "CARD": "REGULATED_ID", "GOV_ID": "REGULATED_ID", "IBAN": "REGULATED_ID"}
_CONTACT_CLASSES = {"CONTACT", "PRECISE_LOCATION"}


def _typed_labels(hits: List[Finding], placeholders: List[str]) -> List[str]:
    labels = {f"{h.cls}:{h.kind}" for h in hits}
    for p in placeholders:
        if p.startswith("SECRET:"):
            labels.add(p)
        elif p in _PLACEHOLDER_CLASS:
            labels.add(f"{_PLACEHOLDER_CLASS[p]}:{p}")
    return sorted(labels)


def _contact_in(text: str) -> bool:
    hits = detect(text)
    kinds = _PLACEHOLDER_KINDS.findall(text)
    return any(h.cls in _CONTACT_CLASSES for h in hits) or any(_PLACEHOLDER_CLASS.get(k) in _CONTACT_CLASSES for k in kinds)


def classify(c: Candidate, rerender: Optional[Callable[[Candidate], str]] = None) -> PrivacyVerdict:
    """Combine re-run detectors, placeholders and category signals; take the most sensitive."""
    value_text = json.dumps(c.value)
    text = f"{c.text} {value_text}"
    hits = resolve_overlaps(detect(text) + high_entropy_tokens(text))
    placeholders = _PLACEHOLDER_KINDS.findall(text)
    labels = _typed_labels(hits, placeholders)
    cats = {c.sensitivity_category or "none"} | {k for k, rx in LEXICON.items() if re.search(rx, text, re.I)}
    cats.discard("none")

    secret_kinds = [h.kind for h in hits if h.cls == "SECRET"] + [p.split(":", 1)[1] for p in placeholders if p.startswith("SECRET:")]
    if secret_kinds:
        return PrivacyVerdict("PROHIBITED", "REJECT", ["SECRET_" + secret_kinds[0]], detector_types=labels)
    if any(h.cls == "REGULATED_ID" for h in hits) or any(p in ("CARD", "GOV_ID", "IBAN") for p in placeholders):
        return PrivacyVerdict("PROHIBITED", "REJECT", ["REGULATED_ID"], detector_types=labels)
    if _contact_in(value_text):
        return PrivacyVerdict("PROHIBITED", "REJECT", ["CONTACT_IDENTIFIER_NOT_NEEDED"], detector_types=labels)
    reasons: List[str] = []
    if _contact_in(c.text):
        # REDACT: rebuild the text from the (clean) structured value.
        c.text = rerender(c) if rerender else PLACEHOLDER_RX.sub("", c.text).strip()
        reasons = ["REDACTED_IDENTIFIER"]
    if cats & SPECIAL:
        if not c.explicit_remember:
            return PrivacyVerdict("PROHIBITED", "REJECT",
                                  ["SPECIAL_CATEGORY_NO_CONSENT", *sorted(cats & SPECIAL)], detector_types=labels)
        return PrivacyVerdict("HIGH", "STORE", reasons + ["SPECIAL_CATEGORY_EXPLICIT"], sorted(cats), labels)
    if cats & MEDIUM or c.predicate == "profile.home_city":
        return PrivacyVerdict("MEDIUM", "STORE", reasons, sorted(cats), labels)
    return PrivacyVerdict("LOW", "STORE", reasons, sorted(cats), labels)


# ---------------------------------------------------------------------------
# P2 egress (§18)
# ---------------------------------------------------------------------------


def egress_findings(text: str) -> List[Finding]:
    """Any detector hit in text bound for a prompt. Placeholders do not count (they are not values)."""
    return resolve_overlaps(detect(text) + high_entropy_tokens(text))
