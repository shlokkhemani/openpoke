"""Map-reduce digest over long documents (shared by interaction and execution)."""

from __future__ import annotations

import asyncio
import re
from typing import Any, Dict, List, Tuple

from ..config import get_settings
from ..logging_config import logger
from ..openrouter_client import request_chat_completion
from ..utils.tokens import chars_for_tokens
from .overflow import is_context_overflow, terminal_overflow_message

_MAP_SYSTEM = (
    "You are reading one chunk of a long, possibly repetitive document to answer a question. The document may "
    "repeat boilerplate many times while the facts that matter appear only once, as a single sentence. Scan every "
    "message in the chunk. Extract every concrete fact that bears on the question: every amount, percentage, "
    "day count, duration, date, id, name and position statement, quoted verbatim, with who said it. Any specific "
    "figure or term (payment terms, discounts, caps, notice periods, deadlines) is always relevant even if mentioned "
    "once. Reply exactly NOTHING RELEVANT only when the chunk contains no such facts at all. Do not speculate "
    "about other chunks."
)
_REDUCE_SYSTEM = (
    "You are combining notes extracted from consecutive chunks of one long document. Some notes are model "
    "summaries; others are verbatim sentences containing figures, which are authoritative: a term that appears "
    "in a verbatim sentence must appear in your answer even if no summary mentioned it. Produce a single, "
    "compact, faithful answer to the question using only the notes. Keep every figure and identifier exact. "
    "Where the document shows a negotiation, state each side's position. Ignore sentences whose figures are "
    "clearly unrelated to the question. Do not add anything not in the notes."
)
_CROSS_SYSTEM = (
    "You are combining answers produced separately for several documents to one question. Produce one compact, "
    "faithful answer that keeps every document's figures and identifiers exact and clearly attributed to that "
    "document. Do not add anything not in the answers."
)

_FIGURE_RE = re.compile(
    r"(\$\s?\d[\d,]*(?:\.\d+)?\s?[kKmMbB]?|\d+(?:\.\d+)?\s?%|\bnet[- ]\d+\b|\b\d+\s?(?:days?|weeks?|months?|years?|hours?)\b"
    r"|\b(?:19|20)\d\d[-/]\d\d[-/]\d\d\b|\b\d{1,2}[-/]\d{1,2}[-/](?:19|20)?\d\d\b)",
    re.IGNORECASE,
)
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")
_MAX_FIGURE_LINES = 40


def _figure_lines(chunk: str) -> List[str]:
    """Deterministic safety net: keep verbatim every sentence carrying a concrete figure."""
    seen: set = set()
    out: List[str] = []
    for sent in _SENTENCE_SPLIT.split(chunk):
        s2 = " ".join(sent.split())
        if not s2 or len(s2) > 400 or not _FIGURE_RE.search(s2):
            continue
        key = s2.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s2)
        if len(out) >= _MAX_FIGURE_LINES:
            break
    return out


def _chunks(text: str, chunk_tokens: int) -> List[str]:
    size = chars_for_tokens(chunk_tokens)
    if len(text) <= size:
        return [text]
    out: List[str] = []
    i = 0
    while i < len(text):
        j = min(len(text), i + size)
        if j < len(text):
            cut = text.rfind("\n\n", i + int(size * 0.85), j)
            if cut == -1:
                cut = text.rfind("\n", i + int(size * 0.85), j)
            if cut > i:
                j = cut
        out.append(text[i:j])
        i = j
    return out


async def digest_text(text: str, question: str, *, model: str, api_key: str, label: str = "document") -> Dict[str, Any]:
    settings = get_settings()
    chunk_tokens = settings.digest_chunk_tokens
    parts = _chunks(text, chunk_tokens)
    sem = asyncio.Semaphore(settings.digest_concurrency)

    async def _call(prompt: str, system: str, *, max_tokens: int) -> str:
        for attempt in range(2):
            try:
                resp = await asyncio.wait_for(
                    request_chat_completion(
                        model=model,
                        messages=[{"role": "user", "content": prompt}],
                        system=system,
                        api_key=api_key,
                        max_tokens=max_tokens,
                        reasoning={"enabled": False},
                    ),
                    timeout=settings.digest_call_timeout_s,
                )
            except asyncio.TimeoutError:
                logger.warning("digest call timed out", extra={"attempt": attempt, "label": label})
                continue
            content = ((resp.get("choices") or [{}])[0].get("message", {}) or {}).get("content") or ""
            if content.strip():
                return content
        return ""

    async def _map(i: int, part: str) -> str:
        prompt = f"QUESTION: {question}\n\nCHUNK {i} of {len(parts)} of {label}:\n\n{part}"
        async with sem:
            return await _call(prompt, _MAP_SYSTEM, max_tokens=2000)

    try:
        contents = await asyncio.gather(*(_map(i, part) for i, part in enumerate(parts, start=1)))
    except Exception as exc:
        if is_context_overflow(exc):
            return {"error": terminal_overflow_message("digest chunk", "Lower digest_chunk_tokens.")}
        raise
    calls = len(parts)
    notes: List[str] = []
    for i, (part, content) in enumerate(zip(parts, contents), start=1):
        if content.strip() and "NOTHING RELEVANT" not in content.upper():
            notes.append(f"[chunk {i}/{len(parts)}] {content.strip()}")
        figures = _figure_lines(part)
        if figures:
            notes.append(f"[chunk {i}/{len(parts)} verbatim sentences containing figures]\n- " + "\n- ".join(figures))
    if not notes:
        return {
            "message_id": label,
            "chunks": len(parts),
            "llm_calls": calls,
            "answer": "No relevant content found for the question.",
        }
    if len(parts) == 1:
        return {"chunks": 1, "llm_calls": calls, "answer": notes[0].split("] ", 1)[-1]}
    reduce_prompt = f"QUESTION: {question}\n\nNOTES:\n" + "\n\n".join(notes)
    answer = await _call(reduce_prompt, _REDUCE_SYSTEM, max_tokens=3000)
    calls += 1
    if not answer.strip():
        answer = "Reduce step failed; raw notes follow.\n\n" + "\n\n".join(notes)
    return {"chunks": len(parts), "llm_calls": calls, "answer": answer.strip()}


async def digest_many(items: List[Tuple[str, str]], question: str, *, model: str, api_key: str) -> Dict[str, Any]:
    """Hierarchical digest: digest each (label, text) separately, then reduce across per-document answers."""
    settings = get_settings()
    sem = asyncio.Semaphore(max(1, settings.digest_concurrency // 2))

    async def _one(label: str, text: str) -> Tuple[str, Dict[str, Any]]:
        async with sem:
            return label, await digest_text(text, question, model=model, api_key=api_key, label=label)

    results = await asyncio.gather(*(_one(lbl, txt) for lbl, txt in items))
    per_doc = []
    calls = 0
    for label, out in results:
        calls += int(out.get("llm_calls") or 0)
        if out.get("error"):
            per_doc.append({"label": label, "error": out["error"]})
        else:
            per_doc.append({"label": label, "answer": out.get("answer", "")})
    if len(per_doc) == 1:
        return {
            "documents": per_doc,
            "llm_calls": calls,
            "answer": per_doc[0].get("answer") or per_doc[0].get("error", ""),
        }
    notes = "\n\n".join(f"[{d['label']}]\n{d.get('answer') or d.get('error')}" for d in per_doc)
    prompt = f"QUESTION: {question}\n\nANSWERS PER DOCUMENT:\n{notes}"
    try:
        resp = await asyncio.wait_for(
            request_chat_completion(
                model=model,
                messages=[{"role": "user", "content": prompt}],
                system=_CROSS_SYSTEM,
                api_key=api_key,
                max_tokens=3000,
                reasoning={"enabled": False},
            ),
            timeout=settings.digest_call_timeout_s,
        )
        answer = ((resp.get("choices") or [{}])[0].get("message", {}) or {}).get("content") or ""
        calls += 1
    except Exception:
        answer = ""
    if not answer.strip():
        answer = "Cross-document reduce failed; per-document answers follow.\n\n" + notes
    return {"documents": per_doc, "llm_calls": calls, "answer": answer.strip()}


__all__ = ["digest_text", "digest_many"]
