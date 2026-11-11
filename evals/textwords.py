"""One word-splitting rule shared by the stress-paraphrase leak check and the name-overlap baseline."""
from __future__ import annotations

import re

from server.services.agents.stopwords import STOPWORDS

_WORD = re.compile(r"[a-z0-9]+")


def content_words(text: str) -> set[str]:
    """Lowercase, split on non-letters (digits kept), drop stopwords (single characters are kept unless they are one), strip one trailing ``s``."""
    out: set[str] = set()
    for w in _WORD.findall(text.lower()):
        if w in STOPWORDS:
            continue
        if len(w) > 3 and w.endswith("s") and not w.endswith("ss"):
            w = w[:-1]
        out.add(w)
    return out
