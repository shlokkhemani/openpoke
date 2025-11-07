"""Exa search integration using the native Exa Python SDK."""

from __future__ import annotations

import asyncio
from typing import Any, Dict, Iterable, List, Optional

from ...logging_config import logger
from .composio_exa import ExaError, get_exa_client


_DEFAULT_MAX_RESULTS = 5
_MAX_RESULTS = 20


class ExaSearchError(ExaError):
    """Raised when the Exa search backend is unavailable or misconfigured."""


def _normalise_domains(domains: Optional[Iterable[str]]) -> Optional[List[str]]:
    if not domains:
        return None
    cleaned = [domain.strip() for domain in domains if isinstance(domain, str) and domain.strip()]
    return cleaned or None


def _extract_snippet(item: Any) -> Optional[str]:
    snippet = getattr(item, "snippet", None)
    if snippet:
        return snippet

    text = getattr(item, "text", None)
    if text:
        return text

    highlights = getattr(item, "highlights", None)
    if isinstance(highlights, list) and highlights:
        merged = " ".join(h for h in highlights if isinstance(h, str)).strip()
        return merged or None

    return None


async def search_exa(
    query: str,
    *,
    num_results: int = _DEFAULT_MAX_RESULTS,
    include_domains: Optional[Iterable[str]] = None,
    exclude_domains: Optional[Iterable[str]] = None,
) -> Dict[str, Any]:
    """Asynchronously execute an Exa search request using the native SDK."""

    limit = max(1, min(int(num_results or _DEFAULT_MAX_RESULTS), _MAX_RESULTS))
    include = _normalise_domains(include_domains)
    exclude = _normalise_domains(exclude_domains)

    try:
        client = get_exa_client()
    except ExaError as exc:
        logger.warning("Exa search unavailable: %s", exc)
        raise ExaSearchError(str(exc)) from exc

    kwargs: Dict[str, Any] = {
        "num_results": limit,
    }
    if include:
        kwargs["include_domains"] = include
    if exclude:
        kwargs["exclude_domains"] = exclude

    try:
        # Run the synchronous SDK call in a separate thread to avoid blocking the event loop
        response = await asyncio.to_thread(client.search, query, **kwargs)
    except Exception as exc:
        logger.warning("Exa search request failed: %s", exc)
        raise ExaSearchError(str(exc)) from exc

    raw_results = getattr(response, "results", None)
    if not isinstance(raw_results, list):
        logger.info("Exa search returned no structured results for query='%s'", query)
        return {
            "query": query,
            "results": [],
            "raw": repr(response),
        }

    normalised: List[Dict[str, Any]] = []
    for item in raw_results:
        if item is None:
            continue

        title = getattr(item, "title", None) or getattr(item, "id", None) or "Untitled"
        normalised.append(
            {
                "title": title,
                "url": getattr(item, "url", None),
                "score": getattr(item, "score", None),
                "snippet": _extract_snippet(item),
                "published": getattr(item, "published_date", None) or getattr(item, "published", None),
            }
        )

    return {
        "query": query,
        "results": normalised,
    }


__all__ = [
    "ExaSearchError",
    "search_exa",
]
