"""Predicate vocabulary, canonical values, rendering and the retrieval intent lexicon (deep dive §0.3, §6, §11, §16)."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Set, Tuple


@dataclass(frozen=True)
class PredicateSpec:
    predicate: str
    memory_type: str
    cardinality: str
    value_type: str  # time_window | enum | entity | text | person
    template: str
    keywords: Tuple[str, ...]
    label: str
    keyed: bool = False  # multi slot keyed by an object entity (slot_key gets a third part)


def _kw(s: str) -> Tuple[str, ...]:
    return tuple(s.split())


# §0.3 table.
_SPECS = [
    PredicateSpec("pref.meeting_time", "preference", "single", "time_window", "User prefers meetings {v}.",
                  _kw("meeting meetings schedule calendar call availability time slot book"), "meeting time preference"),
    PredicateSpec("pref.email_style", "preference", "single", "enum", "User prefers {v} emails.",
                  _kw("email draft reply write tone style message"), "email style preference"),
    PredicateSpec("pref.communication_channel", "preference", "single", "enum", "User prefers to be contacted via {v}.",
                  _kw("contact reach message text call"), "contact channel preference"),
    PredicateSpec("pref.favorite_programming_language", "preference", "single", "entity",
                  "User's favorite programming language is {v}.", _kw("programming language code coding favorite"),
                  "favorite programming language"),
    PredicateSpec("pref.likes", "preference", "multi", "text", "User likes {v}.", _kw("like enjoy favorite"), "likes"),
    PredicateSpec("profile.role", "profile", "single", "text", "User works as {v}.", _kw("job role work title"), "role"),
    PredicateSpec("profile.employer", "profile", "single", "entity", "User works at {v}.",
                  _kw("work company job employer"), "employer"),
    PredicateSpec("profile.home_city", "profile", "single", "entity", "User lives in {v}.",
                  _kw("city live home local"), "home city"),
    PredicateSpec("rel.manager", "relationship", "single", "person", "User's manager is {v}.",
                  _kw("manager boss report"), "manager"),
    PredicateSpec("constraint.confirm_before_email", "constraint", "multi", "person",
                  "User wants to approve any email to {obj} before it is sent.", _kw("email send draft reply"),
                  "confirm before emailing", keyed=True),
    PredicateSpec("constraint.avoid", "constraint", "multi", "text", "User does not want {v}.", (), "avoid"),
    PredicateSpec("project.current", "project", "multi", "text", "User is working on {v}.",
                  _kw("project work working"), "current project", keyed=True),
]
VOCAB: Dict[str, PredicateSpec] = {s.predicate: s for s in _SPECS}

# rel.<role> (colleague, partner, ...): relationship, multi, "{v} is the user's {role}."
REL_ROLES = ("colleague", "partner", "assistant", "cofounder", "teammate", "friend", "sister", "brother")


def rel_role_spec(predicate: str) -> Optional[PredicateSpec]:
    role = predicate.split(".", 1)[1] if predicate.startswith("rel.") else ""
    if role in REL_ROLES:
        return PredicateSpec(predicate, "relationship", "multi", "person", "{v} is the user's " + role + ".",
                             (role,), role)
    return None


CUSTOM_SPEC = PredicateSpec("pref.custom", "preference", "single", "text", "{v}", (), "custom preference")

# C4: extractor-only predicates. They exist so policy has something to REJECT. Never in the stored vocabulary.
EXTRACTOR_ONLY: Dict[str, PredicateSpec] = {
    "profile.email": PredicateSpec("profile.email", "profile", "single", "text", "User's email is {v}.", (),
                                   "email address"),
    "profile.api_key": PredicateSpec("profile.api_key", "profile", "single", "text", "User's API key is {v}.", (),
                                     "API key"),
}

# Predicate drift -> canonical predicate (§5 validate).
PREDICATE_ALIASES = {
    "pref.meeting_hours": "pref.meeting_time", "pref.meeting_times": "pref.meeting_time",
    "pref.meeting_preference": "pref.meeting_time", "pref.email_tone": "pref.email_style",
    "pref.favorite_language": "pref.favorite_programming_language",
    "pref.programming_language": "pref.favorite_programming_language",
    "profile.job_title": "profile.role", "profile.company": "profile.employer", "profile.city": "profile.home_city",
    "rel.boss": "rel.manager",
}

ENUM_ALIASES = {"brief": "concise", "short": "concise", "succinct": "concise", "terse": "concise",
                "long": "detailed", "thorough": "detailed", "sms": "text", "texts": "text", "e-mail": "email"}


def spec_for(predicate: str) -> Optional[PredicateSpec]:
    if predicate in VOCAB:
        return VOCAB[predicate]
    if predicate.startswith("pref.custom:"):
        return CUSTOM_SPEC
    return rel_role_spec(predicate) or EXTRACTOR_ONLY.get(predicate)


def is_storable(predicate: str) -> bool:
    return predicate in VOCAB or predicate.startswith("pref.custom:") or rel_role_spec(predicate) is not None


def canonical_predicate(predicate: str) -> Optional[str]:
    if spec_for(predicate):
        return predicate
    return PREDICATE_ALIASES.get(predicate)


def label(predicate: str) -> str:
    spec = spec_for(predicate)
    if predicate.startswith("pref.custom:"):
        return predicate.split(":", 1)[1].replace("_", " ")
    return spec.label if spec else predicate


# ---------------------------------------------------------------------------
# Text normalisation and stemming (shared by grounding, retrieval and forget resolution)
# ---------------------------------------------------------------------------

STOPWORDS = set("""
a an the and or but if then so to of in on at by for with about from as into over after before between is am are was
were be been being do does did have has had i me my mine you your we our it its this that these those what whats which
who whom when where why how can could should would will shall may might must not no yes please just really very
actually also too some any all now there here they them their he she his her him us ok okay thanks thank hi hello
""".split())
# Content words for intent/coverage that are also stopwords would vanish; keep after/before/between in values only.

_TIME_RX = re.compile(r"\b(\d{1,2})(?::(\d{2}))?\s*([ap])\.?\s*m\.?\b", re.I)


def normalise_times(text: str) -> str:
    def sub(m: "re.Match[str]") -> str:
        h, mm, ap = int(m.group(1)), m.group(2) or "00", m.group(3).lower()
        if ap == "p" and h != 12:
            h += 12
        if ap == "a" and h == 12:
            h = 0
        return f"{h:02d}:{mm}"

    return _TIME_RX.sub(sub, text)


def stem(token: str) -> str:
    """Light suffix stripper: consistent for query terms, memory text and lexicon keys (not a full Porter)."""
    t = token.lower()
    if len(t) <= 3 or not t.isalpha():
        return t
    for suf, rep in (("sses", "ss"), ("ies", "i")):
        if t.endswith(suf):
            return t[: -len(suf)] + rep
    if t.endswith("s") and not t.endswith("ss") and not t.endswith("us"):
        t = t[:-1]
    for suf in ("ences", "ence", "ances", "ance", "ing", "ed"):
        if t.endswith(suf) and len(t) - len(suf) >= 3:
            t = t[: -len(suf)]
            if len(t) > 3 and t[-1] == t[-2] and t[-1] not in "lsz":
                t = t[:-1]  # programm -> program
            break
    if t.endswith("e") and len(t) > 4:
        t = t[:-1]
    return t


_TOKEN_RX = re.compile(r"\[[^\]\s]+\]|[A-Za-z0-9][A-Za-z0-9:+#'-]*")


def raw_tokens(text: str) -> List[str]:
    return _TOKEN_RX.findall(text or "")


def is_placeholder(tok: str) -> bool:
    return tok.startswith("[") and tok.endswith("]")


def content_tokens(text: str) -> List[str]:
    out = []
    for tok in raw_tokens(normalise_times(text)):
        if is_placeholder(tok):
            continue
        low = tok.lower().strip("'-")
        low = re.sub(r"'s$", "", low)
        if not low or low in STOPWORDS:
            continue
        out.append(low)
    return out


def stems(text: str) -> List[str]:
    return [stem(t) for t in content_tokens(text)]


def normalise(text: str) -> str:
    """Grounding normal form: times -> HH:MM, lowercase, stemmed tokens (incl. stopwords), placeholders kept."""
    toks = []
    for tok in raw_tokens(normalise_times(text or "")):
        toks.append(tok if is_placeholder(tok) else stem(tok.lower()))
    return " ".join(toks)


def tokens(text: str) -> Set[str]:
    return set(normalise(text).split())


# Intent lexicon: stemmed keyword -> predicate families (same lists as the VOCAB keywords, §16).
INTENT_LEXICON: Dict[str, List[str]] = {}
for _s in _SPECS:
    for _k in _s.keywords:
        INTENT_LEXICON.setdefault(stem(_k), [])
        if _s.predicate not in INTENT_LEXICON[stem(_k)]:
            INTENT_LEXICON[stem(_k)].append(_s.predicate)


def keywords_for(predicate: str) -> List[str]:
    spec = spec_for(predicate)
    if predicate.startswith("pref.custom:"):
        return predicate.split(":", 1)[1].split("_")
    return list(spec.keywords) if spec else []


# ---------------------------------------------------------------------------
# Values: canonicalisation, rendering, display
# ---------------------------------------------------------------------------


def slugify(s: str) -> str:
    return re.sub(r"[^a-z0-9+#]+", "-", s.lower()).strip("-")


def fmt_time(hhmm: str) -> str:
    h, m = (int(x) for x in hhmm.split(":"))
    ap = "AM" if h < 12 else "PM"
    h12 = h % 12 or 12
    return f"{h12} {ap}" if m == 0 else f"{h12}:{m:02d} {ap}"


_PART_OF_DAY = ("morning", "afternoon", "evening")


def parse_time_window(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return value
    text = normalise_times(str(value)).lower()
    m = re.search(r"between\s+(\d{2}:\d{2})\s+(?:and|-)\s+(\d{2}:\d{2})", text)
    if m:
        return {"between": [m.group(1), m.group(2)]}
    m = re.search(r"\b(after|before)\s+(\d{2}:\d{2})", text)
    if m:
        return {m.group(1): m.group(2)}
    for part in _PART_OF_DAY:
        if part in text:
            return {"part_of_day": part}
    return {"text": " ".join(content_tokens(text))}


def time_window_phrase(w: Dict[str, Any]) -> str:
    if "between" in w:
        a, b = w["between"]
        return f"between {fmt_time(a)} and {fmt_time(b)}"
    for k in ("after", "before"):
        if k in w:
            return f"{k} {fmt_time(w[k])}"
    if "part_of_day" in w:
        return f"in the {w['part_of_day']}"
    return str(w.get("text", ""))


def canonical_value(predicate: str, value: Any) -> str:
    """§11: the string that equality, dedupe and the value HMAC are computed over."""
    spec = spec_for(predicate) or CUSTOM_SPEC
    if spec.value_type == "time_window":
        return json.dumps(parse_time_window(value), sort_keys=True)
    if spec.value_type in ("entity", "person"):
        return slugify(str(value))
    if spec.value_type == "enum":
        low = str(value).strip().lower()
        return ENUM_ALIASES.get(low, low)
    return " ".join(stem(t) for t in content_tokens(str(value)))


def value_json(predicate: str, value: Any) -> str:
    """Stored ``value_json``: JSON of the canonical value."""
    spec = spec_for(predicate) or CUSTOM_SPEC
    canon = canonical_value(predicate, value)
    return canon if spec.value_type == "time_window" else json.dumps(canon)


def _pretty_entity(slug: str) -> str:
    return " ".join(p.capitalize() for p in slug.split("-"))


def display_value(predicate: str, stored_value_json: Optional[str]) -> Optional[str]:
    """Short MEMORY_SAFE phrase for the inspector ("Rust", "after 10 AM"). None once purged."""
    if stored_value_json is None:
        return None
    spec = spec_for(predicate) or CUSTOM_SPEC
    try:
        v = json.loads(stored_value_json)
    except ValueError:
        return None
    if spec.value_type == "time_window" and isinstance(v, dict):
        return time_window_phrase(v)
    if spec.value_type in ("entity", "person") and isinstance(v, str):
        return _pretty_entity(v)
    return str(v)


def render(predicate: str, value: Any, obj: Optional[str] = None) -> str:
    """Canonical MEMORY_SAFE sentence from the predicate template."""
    spec = spec_for(predicate) or CUSTOM_SPEC
    if spec.value_type == "time_window":
        v = time_window_phrase(parse_time_window(value))
    elif spec.value_type == "enum":
        v = canonical_value(predicate, value)
    else:
        v = str(value).strip()
    obj_disp = obj.split(":", 1)[-1].replace("-", " ").title() if obj else ""
    text = spec.template.format(v=v, obj=obj_disp)
    return text[:200]


def normalise_entity(name: str) -> str:
    return f"person:{slugify(name)}"
