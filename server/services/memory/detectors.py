"""Deterministic PII and secret detectors (deep dive §2, §3).

Values are never logged; callers only ever see spans, kinds and classes.
"""

from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from .models import Finding

PROXIMITY_WINDOW = 40
TRAILING_PUNCT = ".,;:!?)]"

# Severity for overlap ties (§2: "most severe class wins").
CLASS_SEVERITY = {"SECRET": 0, "REGULATED_ID": 1, "CONTACT": 2, "PRECISE_LOCATION": 3}
# Within a class and an identical span, the more specific detector names the placeholder
# ("api key is sk-…" is API_KEY, not the generic CREDENTIAL or HIGH_ENTROPY).
KIND_PRIORITY = {k: i for i, k in enumerate((
    "PRIVATE_KEY", "JWT", "API_KEY", "SECRET_URL", "OTP", "CREDENTIAL", "HIGH_ENTROPY",
    "CARD", "GOV_ID", "IBAN", "EMAIL", "PHONE", "ADDRESS",
))}

# Placeholders already in the text (ingress output, P0 output) are not re-detected. This is what makes
# ingress_scrub idempotent: "[SECRET:API_KEY]" would otherwise match the "secret: <value>" credential rule.
PLACEHOLDER_RX = re.compile(r"\[(?:SECRET:[A-Z_]+|[A-Z_]+?(?:_\d+)?)\]")


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------


def luhn_ok(s: str) -> bool:
    digits = [int(c) for c in s if c.isdigit()]
    if not 13 <= len(digits) <= 19:
        return False
    total = 0
    for i, d in enumerate(reversed(digits)):
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def iban_mod97_ok(s: str) -> bool:
    s = s.replace(" ", "").upper()
    if len(s) < 15:
        return False
    rearranged = s[4:] + s[:4]
    try:
        num = "".join(str(int(c, 36)) for c in rearranged)
    except ValueError:
        return False
    return int(num) % 97 == 1


def min_digits(n: int) -> Callable[[str], bool]:
    return lambda s: sum(c.isdigit() for c in s) >= n


def keyword_within(text: str, span: Tuple[int, int], keywords: Sequence[str], window: int = PROXIMITY_WINDOW) -> bool:
    lo, hi = max(0, span[0] - window), min(len(text), span[1] + window)
    around = text[lo:span[0]] + " " + text[span[1]:hi]
    return any(re.search(rf"\b{re.escape(k)}\b", around, re.I) for k in keywords)


# ---------------------------------------------------------------------------
# Detector table
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Detector:
    kind: str
    cls: str
    rx: "re.Pattern[str]"
    validator: Optional[Callable[[str], bool]] = None
    near: Optional[Tuple[str, ...]] = None
    group: int = 0
    strip_trailing: bool = False


def _d(kind, cls, pattern, validator=None, near=None, group=0, strip_trailing=False, flags=0) -> Detector:
    return Detector(kind, cls, re.compile(pattern, flags), validator, near, group, strip_trailing)


# §3, verbatim patterns.
SECRET_DETECTORS: List[Detector] = [
    _d("API_KEY", "SECRET", r"\bsk-(?:or-v1-|test-|live-|proj-)?[A-Za-z0-9_-]{8,}\b"),
    _d("API_KEY", "SECRET", r"\b(?:ghp|gho|ghu|ghs|github_pat)_[A-Za-z0-9_]{20,}\b"),
    _d("API_KEY", "SECRET", r"\bAKIA[0-9A-Z]{16}\b"),
    _d("API_KEY", "SECRET", r"\bxox[abposr]-[A-Za-z0-9-]{10,}\b"),
    _d("API_KEY", "SECRET", r"\bAIza[0-9A-Za-z_-]{35}\b"),
    _d("JWT", "SECRET", r"\beyJ[\w-]{5,}\.[\w-]{5,}\.[\w-]{5,}\b"),
    _d("PRIVATE_KEY", "SECRET", r"-----BEGIN [A-Z ]*PRIVATE KEY-----[\s\S]*?-----END [A-Z ]*PRIVATE KEY-----"),
    _d("CREDENTIAL", "SECRET",
       r"(?i)\b(password|passwd|pwd|passphrase|secret|token|api[ _-]?key)\b\s*(?:is|:|=)\s*(\S+)",
       group=2, strip_trailing=True),
    # 'code'/'pin'/'passcode' are common English words ("the code is in main.py"), so the value must contain a digit
    _d("CREDENTIAL", "SECRET", r"(?i)\b(pin|passcode|code|combination)\b\s*(?:is|:|=)\s*((?=\S*\d)\S{4,})",
       group=2, strip_trailing=True),
    _d("SECRET_URL", "SECRET",
       r"https?://\S+[?&](?:token|key|sig|signature|code|auth|session|access_token)=[^&\s]+"),
    _d("OTP", "SECRET", r"\b\d{4,8}\b",
       near=("code", "otp", "verification", "verify", "passcode", "2fa", "one-time", "login")),
]

# §2, verbatim patterns.
DETECTORS: List[Detector] = [
    _d("EMAIL", "CONTACT", r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    _d("PHONE", "CONTACT", r"(?:\+?\d{1,3}[\s.-]?)?(?:\(?\d{3}\)?[\s.-]?)\d{3}[\s.-]?\d{4}\b", min_digits(10)),
    _d("CARD", "REGULATED_ID", r"\b(?:\d[ -]?){13,19}\b", luhn_ok),
    _d("GOV_ID", "REGULATED_ID", r"\b\d{3}-\d{2}-\d{4}\b"),  # SSN-like
    _d("GOV_ID", "REGULATED_ID", r"\b\d{3}[ -]\d{3}[ -]\d{3}\b", near=("sin", "ssn", "social", "insurance")),
    _d("IBAN", "REGULATED_ID", r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b", iban_mod97_ok),
    _d("ADDRESS", "PRECISE_LOCATION",
       r"\b\d{1,5}\s+(?:[A-Z][a-z]+\s){1,3}(?:St|Street|Ave|Avenue|Rd|Road|Lane|Ln|Blvd|Dr|Drive|Way|Ct)\b"),
    *SECRET_DETECTORS,
]


# LTM_BLOCKERS.md B2: the bare typed labels the spec prescribes for traces and events ("SECRET:API_KEY", handoff §7
# canary labels; design §25 "SECRET -> REJECT" detector labels) are labels, not values. Only exact class:kind labels
# from this module's own detector kinds are protected.
_SECRET_KINDS = ("API_KEY", "JWT", "PRIVATE_KEY", "CREDENTIAL", "SECRET_URL", "OTP", "HIGH_ENTROPY")
TYPED_LABEL_RX = re.compile(r"\bSECRET:(?:" + "|".join(_SECRET_KINDS) + r")\b")


def _placeholder_spans(text: str) -> List[Tuple[int, int]]:
    return [m.span() for m in PLACEHOLDER_RX.finditer(text)] + [m.span() for m in TYPED_LABEL_RX.finditer(text)]


def _inside_protected(text: str, start: int, end: int, spans: Iterable[Tuple[int, int]]) -> bool:
    """True only when the finding's core (trimmed of surrounding punctuation/quotes) lies entirely inside one
    placeholder/label span. Mere overlap is not enough: "[X]hunter2pass" or "SECRET:API_KEY=hunter2pass99" must still
    be detected (review M3)."""
    while start < end and not text[start].isalnum():
        start += 1
    while end > start and not text[end - 1].isalnum():
        end -= 1
    return any(s <= start and end <= e for s, e in spans)


def detect(text: str) -> List[Finding]:
    """All §2/§3 detector hits, overlaps resolved."""
    if not text:
        return []
    protected = _placeholder_spans(text)
    hits: List[Finding] = []
    for det in DETECTORS:
        for m in det.rx.finditer(text):
            start, end = m.span(det.group)
            value = text[start:end]
            if det.strip_trailing:
                stripped = value.rstrip(TRAILING_PUNCT)
                end -= len(value) - len(stripped)
                value = stripped
            if det.kind == "CARD":  # the repeated "\d[ -]?" can swallow a trailing separator
                trimmed = value.rstrip(" -")
                end -= len(value) - len(trimmed)
                value = trimmed
            if end <= start:
                continue
            if det.validator and not det.validator(value):
                continue
            if det.near and not keyword_within(text, (start, end), det.near):
                continue
            if _inside_protected(text, start, end, protected):
                continue
            hits.append(Finding(det.kind, det.cls, start, end))
    return resolve_overlaps(hits)


# ---------------------------------------------------------------------------
# High-entropy fallback (§3)
# ---------------------------------------------------------------------------

_ENTROPY_TOKEN = re.compile(r"[A-Za-z0-9_\-+/=]{20,}")


def char_classes(s: str) -> int:
    return sum((
        any(c.islower() for c in s),
        any(c.isupper() for c in s),
        any(c.isdigit() for c in s),
        any(not c.isalnum() for c in s),
    ))


def shannon_bits_per_char(s: str) -> float:
    counts = Counter(s)
    n = len(s)
    return -sum((c / n) * math.log2(c / n) for c in counts.values())


def looks_like_url_path(s: str) -> bool:
    parts = [p for p in s.split("/") if p]
    return s.count("/") >= 2 and all(p.replace("-", "").replace("_", "").isalpha() for p in parts)


# LTM_BLOCKERS.md B1: the system's own ULID-based ids ('mem_' + ULID, §0.1) would otherwise be flagged as secrets.
_SYSTEM_ID = re.compile(r"(?:mem|evt|trc|run)_[0-9A-HJKMNP-TV-Z]{20,26}")


def is_system_id(s: str) -> bool:
    return bool(_SYSTEM_ID.fullmatch(s))


def high_entropy_tokens(text: str) -> List[Finding]:
    protected = _placeholder_spans(text)
    out = []
    for tok in _ENTROPY_TOKEN.finditer(text or ""):
        s = tok.group()
        if (char_classes(s) >= 3 and shannon_bits_per_char(s) >= 3.5 and not looks_like_url_path(s)
                and not is_system_id(s)):
            if not _inside_protected(text, tok.start(), tok.end(), protected):
                out.append(Finding("HIGH_ENTROPY", "SECRET", tok.start(), tok.end()))
    return out


# ---------------------------------------------------------------------------
# Overlaps and helpers
# ---------------------------------------------------------------------------


def resolve_overlaps(hits: List[Finding]) -> List[Finding]:
    """Longest span wins; on tie the most severe class, then the most specific kind."""
    ranked = sorted(
        hits,
        key=lambda f: (-(f.end - f.start), CLASS_SEVERITY.get(f.cls, 9), KIND_PRIORITY.get(f.kind, 99), f.start),
    )
    kept: List[Finding] = []
    for f in ranked:
        if not any(f.start < k.end and k.start < f.end for k in kept):
            kept.append(f)
    return sorted(kept, key=lambda f: f.start)


def detect_all(text: str) -> List[Finding]:
    """§4: ``detect`` plus the high-entropy fallback, overlaps resolved."""
    return resolve_overlaps(detect(text) + high_entropy_tokens(text))


def counts(findings: Iterable[Finding]) -> List[Dict[str, object]]:
    """LOG_SAFE summary: ``[{type, count}]`` sorted by type. No values, lengths or offsets."""
    c = Counter(f.kind for f in findings)
    return [{"type": k, "count": c[k]} for k in sorted(c)]
