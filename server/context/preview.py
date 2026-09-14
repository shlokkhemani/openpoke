"""Head/tail text previews for bounded prompts."""

from __future__ import annotations

from ..utils.tokens import chars_for_tokens


def preview_text(text: str, max_tokens: int, *, note: str = "") -> str:
    max_chars = chars_for_tokens(max_tokens)
    if len(text) <= max_chars:
        return text
    head = max(200, int(max_chars * 0.8))
    tail = max(80, max_chars - head)
    omitted = len(text) - head - tail
    return f"{text[:head]}\n[... {omitted:,} characters omitted{(': ' + note) if note else ''} ...]\n{text[-tail:]}"


__all__ = ["preview_text"]
