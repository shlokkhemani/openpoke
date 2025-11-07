"""Enhanced Exa search integration using native Exa Python SDK."""

from __future__ import annotations

import threading
from typing import Any, Dict, List, Optional

from ...config import get_settings
from ...logging_config import logger

_DEFAULT_MAX_RESULTS = 5
_MAX_RESULTS = 20

# Singleton client (thread-safe pattern)
_CLIENT_LOCK = threading.Lock()
_CLIENT: Optional[Any] = None


class ExaError(RuntimeError):
    """Raised when Exa SDK is unavailable or misconfigured."""


def _get_exa_client(settings: Optional[Any] = None):
    """Get or create singleton Exa client."""
    global _CLIENT
    if _CLIENT is not None:
        return _CLIENT

    with _CLIENT_LOCK:
        if _CLIENT is None:
            try:
                from exa_py import Exa  # type: ignore
            except ImportError as exc:
                raise ExaError(
                    "exa_py package not installed; run: pip install exa_py"
                ) from exc

            resolved_settings = settings or get_settings()
            api_key = resolved_settings.exa_api_key

            if not api_key:
                raise ExaError(
                    "EXA_API_KEY environment variable required for Exa SDK"
                )

            try:
                _CLIENT = Exa(api_key=api_key)
                logger.info("Exa SDK client initialized successfully")
            except Exception as exc:
                raise ExaError(f"Failed to initialize Exa client: {exc}") from exc

    return _CLIENT


def get_exa_client(settings: Optional[Any] = None):
    """Public wrapper around the shared Exa client."""

    return _get_exa_client(settings)


def generate_answer_sync(
    query: str,
    *,
    num_results: int = 5,
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """
    Generate a direct, citation-backed answer using Exa's AI.

    This is the most powerful search tool - it returns a synthesized answer
    with citations rather than just search results.

    Args:
        query: Natural language question or topic
        num_results: Number of sources to use for answer generation
        include_domains: Optional list of domains to prioritize
        exclude_domains: Optional list of domains to exclude

    Returns:
        Dict with 'answer' (text), 'citations' (list of sources), and metadata
    """
    try:
        client = _get_exa_client()

        result = client.search_and_contents(
            query,
            num_results=min(num_results, _MAX_RESULTS),
            include_domains=include_domains,
            exclude_domains=exclude_domains,
            text=True,
        )

        # Extract answer and citations
        answer_text = result.answer if hasattr(result, 'answer') else None
        citations = []

        if hasattr(result, 'results'):
            for item in result.results:
                citations.append({
                    'url': item.url if hasattr(item, 'url') else None,
                    'title': item.title if hasattr(item, 'title') else None,
                    'text': item.text if hasattr(item, 'text') else None,
                    'score': item.score if hasattr(item, 'score') else None,
                })

        logger.info(
            f"generate_answer succeeded | query='{query}' | citations={len(citations)}"
        )

        return {
            "query": query,
            "answer": answer_text,
            "citations": citations,
        }

    except ExaError as exc:
        logger.warning(f"generate_answer failed: {exc}")
        return {
            "query": query,
            "answer": None,
            "citations": [],
            "error": str(exc),
        }
    except Exception as exc:
        logger.exception("generate_answer unexpected error")
        return {
            "query": query,
            "answer": None,
            "citations": [],
            "error": f"Unexpected error: {exc}",
        }


def find_similar(
    url: str,
    *,
    num_results: int = 10,
    include_text: bool = False,
    include_highlights: bool = False,
) -> Dict[str, Any]:
    """
    Find web pages semantically similar to a given URL using Exa SDK.

    Uses embeddings-based search to find content similar to the reference URL.

    Args:
        url: Reference URL to find similar content for
        num_results: Number of similar pages to return
        include_text: Whether to include full text content
        include_highlights: Whether to include highlighted excerpts

    Returns:
        Dict with 'results' (list of similar pages) and metadata
    """
    try:
        client = _get_exa_client()

        if include_text:
            result = client.find_similar_and_contents(
                url,
                num_results=min(num_results, _MAX_RESULTS),
                text=True,
                highlights=include_highlights,
            )
        else:
            result = client.find_similar(
                url,
                num_results=min(num_results, _MAX_RESULTS),
            )

        # Extract results
        results = []
        if hasattr(result, 'results'):
            for item in result.results:
                result_dict = {
                    'url': item.url if hasattr(item, 'url') else None,
                    'title': item.title if hasattr(item, 'title') else None,
                    'score': item.score if hasattr(item, 'score') else None,
                }

                if include_text and hasattr(item, 'text'):
                    result_dict['text'] = item.text

                if include_highlights and hasattr(item, 'highlights'):
                    result_dict['highlights'] = item.highlights

                results.append(result_dict)

        logger.info(
            f"find_similar succeeded | url='{url}' | results={len(results)}"
        )

        return {
            "url": url,
            "results": results,
            "total_results": len(results),
        }

    except ExaError as exc:
        logger.warning(f"find_similar failed: {exc}")
        return {
            "url": url,
            "results": [],
            "error": str(exc),
        }
    except Exception as exc:
        logger.exception("find_similar unexpected error")
        return {
            "url": url,
            "results": [],
            "error": f"Unexpected error: {exc}",
        }


def get_contents(
    urls: List[str],
    *,
    include_text: bool = True,
    include_highlights: bool = False,
) -> Dict[str, Any]:
    """
    Retrieve full content from a list of URLs using Exa SDK.

    Args:
        urls: List of URLs to fetch content from
        include_text: Whether to include full text content
        include_highlights: Whether to include highlighted excerpts

    Returns:
        Dict with 'contents' (list of retrieved content) and metadata
    """
    try:
        client = _get_exa_client()

        result = client.get_contents(
            urls,
            text=include_text,
            highlights=include_highlights,
        )

        # Extract contents
        contents = []
        if hasattr(result, 'results'):
            for item in result.results:
                content_dict = {
                    'url': item.url if hasattr(item, 'url') else None,
                    'title': item.title if hasattr(item, 'title') else None,
                }

                if include_text and hasattr(item, 'text'):
                    content_dict['text'] = item.text

                if include_highlights and hasattr(item, 'highlights'):
                    content_dict['highlights'] = item.highlights

                contents.append(content_dict)

        logger.info(
            f"get_contents succeeded | urls={len(urls)} | retrieved={len(contents)}"
        )

        return {
            "urls": urls,
            "contents": contents,
            "total_retrieved": len(contents),
        }

    except ExaError as exc:
        logger.warning(f"get_contents failed: {exc}")
        return {
            "urls": urls,
            "contents": [],
            "error": str(exc),
        }
    except Exception as exc:
        logger.exception("get_contents unexpected error")
        return {
            "urls": urls,
            "contents": [],
            "error": f"Unexpected error: {exc}",
        }


def advanced_search(
    query: str,
    *,
    num_results: int = 10,
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None,
    start_published_date: Optional[str] = None,
    end_published_date: Optional[str] = None,
    category: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Advanced search with date filtering and categorization using Exa SDK.

    Args:
        query: Search query
        num_results: Number of results
        include_domains: Domains to prioritize
        exclude_domains: Domains to exclude
        start_published_date: Start date filter (ISO format)
        end_published_date: End date filter (ISO format)
        category: Content category filter

    Returns:
        Dict with search results and metadata
    """
    try:
        client = _get_exa_client()

        kwargs: Dict[str, Any] = {
            "num_results": min(num_results, _MAX_RESULTS),
        }

        if include_domains:
            kwargs["include_domains"] = include_domains
        if exclude_domains:
            kwargs["exclude_domains"] = exclude_domains
        if start_published_date:
            kwargs["start_published_date"] = start_published_date
        if end_published_date:
            kwargs["end_published_date"] = end_published_date
        if category:
            kwargs["category"] = category

        result = client.search(query, **kwargs)

        # Extract results
        results = []
        if hasattr(result, 'results'):
            for item in result.results:
                results.append({
                    'url': item.url if hasattr(item, 'url') else None,
                    'title': item.title if hasattr(item, 'title') else None,
                    'score': item.score if hasattr(item, 'score') else None,
                    'published_date': item.published_date if hasattr(item, 'published_date') else None,
                })

        logger.info(
            f"advanced_search succeeded | query='{query}' | results={len(results)}"
        )

        return {
            "query": query,
            "results": results,
            "total_results": len(results),
        }

    except ExaError as exc:
        logger.warning(f"advanced_search failed: {exc}")
        return {
            "query": query,
            "results": [],
            "error": str(exc),
        }
    except Exception as exc:
        logger.exception("advanced_search unexpected error")
        return {
            "query": query,
            "results": [],
            "error": f"Unexpected error: {exc}",
        }


# Keep the original function name for backwards compatibility
def generate_answer(query: str, **kwargs: Any) -> Dict[str, Any]:
    """Alias for generate_answer_sync."""
    return generate_answer_sync(query, **kwargs)


__all__ = [
    "ExaError",
    "get_exa_client",
    "generate_answer",
    "generate_answer_sync",
    "find_similar",
    "get_contents",
    "advanced_search",
]
