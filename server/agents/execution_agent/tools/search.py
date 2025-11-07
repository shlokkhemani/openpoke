"""Search tool schemas and handlers for the execution agent using Composio/Exa."""

from __future__ import annotations

import re
from typing import Any, Callable, Dict, List, Optional

from server.services.search.exa import ExaSearchError, search_exa
from server.services.search.composio_exa import (
    ExaError,
    generate_answer,
    find_similar,
    get_contents,
    advanced_search,
)
from server.services.execution import get_execution_agent_logs

_LOG_STORE = get_execution_agent_logs()
_SEARCH_AGENT_NAME = "search-execution-agent"

_MAX_SUB_QUERY_SEGMENTS = 3
_QUESTION_SPLIT_THRESHOLD = 180


def _split_complex_question(question: str) -> List[str]:
    """Break large multi-part questions into smaller sub-queries."""

    normalized = " ".join(question.strip().split())
    if not normalized:
        return []

    if len(normalized) <= _QUESTION_SPLIT_THRESHOLD:
        return [normalized]

    segments: List[str] = []
    parts = [segment.strip(" ,;:") for segment in re.split(r"[\?\.!;]+", normalized) if segment.strip()]

    if not parts:
        return [normalized]

    current = ""
    for part in parts:
        candidate = f"{current} {part}".strip() if current else part
        if current and len(candidate) > _QUESTION_SPLIT_THRESHOLD and len(segments) < _MAX_SUB_QUERY_SEGMENTS - 1:
            segments.append(current)
            current = part
        else:
            current = candidate

    if current:
        segments.append(current)

    # Fallback to the original question if splitting failed
    if not segments:
        return [normalized]

    return segments[:_MAX_SUB_QUERY_SEGMENTS]


_SCHEMAS: List[Dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Search the web via the Exa engine using the configured MCP gateway and return curated results.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query to send to Exa. Be specific and detailed for best results.",
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "Maximum number of web results to return (defaults to 5, capped at 20).",
                    },
                    "include_domains": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of domains that should be prioritised in the results.",
                    },
                    "exclude_domains": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of domains that should be filtered out from the results.",
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_news",
            "description": "Search for recent news articles on a specific topic using trusted news sources.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The news topic to search for.",
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "Number of news articles to return (defaults to 10, capped at 20).",
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "research_topic",
            "description": "Conduct comprehensive research on a topic, optionally focusing on specific aspects. Returns diverse perspectives and sources.",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "description": "The main topic to research in depth.",
                    },
                    "focus_areas": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional specific aspects to focus on (e.g., ['history', 'current developments', 'future outlook']).",
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "Number of sources to gather per focus area (defaults to 10, capped at 20).",
                    },
                },
                "required": ["topic"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_company",
            "description": "Search for comprehensive information about a company including news, financials, leadership, products, and public information.",
            "parameters": {
                "type": "object",
                "properties": {
                    "company_name": {
                        "type": "string",
                        "description": "The name of the company to research.",
                    },
                    "aspects": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Specific aspects to research (e.g., ['news', 'financials', 'leadership', 'products']). Defaults to ['news', 'overview'].",
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "Number of results per aspect (defaults to 8, capped at 15).",
                    },
                },
                "required": ["company_name"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_academic",
            "description": "Search for academic papers, research articles, and scholarly sources on a topic from academic databases and journals.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "The research topic or academic question to find sources for.",
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "Number of academic sources to find (defaults to 10, capped at 20).",
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "answer_question",
            "description": "Generate a direct, citation-backed answer to a question using Exa's AI. This is the most powerful search tool - returns a synthesized answer with citations rather than just search results. Perfect for complex questions requiring synthesis from multiple sources.",
            "parameters": {
                "type": "object",
                "properties": {
                    "question": {
                        "type": "string",
                        "description": "Natural language question or topic to answer.",
                    },
                    "num_sources": {
                        "type": "integer",
                        "description": "Number of sources to use for answer generation (defaults to 5, capped at 20).",
                    },
                    "include_domains": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of domains to prioritize for sources.",
                    },
                    "exclude_domains": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of domains to exclude from sources.",
                    },
                },
                "required": ["question"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "find_similar_content",
            "description": "Find web pages semantically similar to a given URL using embeddings-based search. Perfect for finding related articles, similar products, or content exploration.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Reference URL to find similar content for.",
                    },
                    "num_results": {
                        "type": "integer",
                        "description": "Number of similar pages to return (defaults to 10, capped at 20).",
                    },
                    "include_full_content": {
                        "type": "boolean",
                        "description": "Whether to include full text content of similar pages.",
                    },
                },
                "required": ["url"],
                "additionalProperties": False,
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "extract_content",
            "description": "Retrieve full content from a list of URLs. Perfect for deep analysis, content extraction, or reading full articles.",
            "parameters": {
                "type": "object",
                "properties": {
                    "urls": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of URLs to fetch content from (max 10 URLs).",
                    },
                    "include_highlights": {
                        "type": "boolean",
                        "description": "Whether to include highlighted key excerpts.",
                    },
                },
                "required": ["urls"],
                "additionalProperties": False,
            },
        },
    },
]


def get_schemas() -> List[Dict[str, Any]]:
    """Return search tool schemas."""

    return _SCHEMAS


def build_registry(_: str) -> Dict[str, Callable[..., Any]]:
    """Return callable registry for search tools."""

    return {
        "search_web": search_web,
        "search_news": search_news,
        "research_topic": research_topic,
        "search_company": search_company,
        "search_academic": search_academic,
        "answer_question": answer_question,
        "find_similar_content": find_similar_content,
        "extract_content": extract_content,
    }


def _log_search(tool_name: str, query: str, success: bool, result_count: int = 0, error: Optional[str] = None) -> None:
    """Log search action to execution agent journal."""
    if success:
        _LOG_STORE.record_action(
            _SEARCH_AGENT_NAME,
            description=f"{tool_name} succeeded | query='{query}' | results={result_count}",
        )
    else:
        _LOG_STORE.record_action(
            _SEARCH_AGENT_NAME,
            description=f"{tool_name} failed | query='{query}' | error={error}",
        )


async def search_web(
    query: str,
    num_results: Optional[int] = None,
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Execute a web search via the Exa engine using the configured MCP gateway."""

    try:
        result = await search_exa(
            query,
            num_results=num_results or 5,
            include_domains=include_domains,
            exclude_domains=exclude_domains,
        )
        _log_search("search_web", query, success=True, result_count=len(result.get("results", [])))
        return result
    except ExaSearchError as exc:
        error_msg = str(exc)
        _log_search("search_web", query, success=False, error=error_msg)
        return {
            "query": query,
            "results": [],
            "error": error_msg,
            "error_type": "search_unavailable",
        }
    except Exception as exc:
        error_msg = str(exc)
        _log_search("search_web", query, success=False, error=error_msg)
        return {
            "query": query,
            "results": [],
            "error": f"Unexpected error: {error_msg}",
            "error_type": "unknown",
        }


async def search_news(
    query: str,
    num_results: Optional[int] = None,
) -> Dict[str, Any]:
    """Search for recent news articles using trusted news sources."""

    # Focus on major news domains for news search
    news_domains = [
        "nytimes.com",
        "wsj.com",
        "reuters.com",
        "bloomberg.com",
        "bbc.com",
        "theguardian.com",
        "cnn.com",
        "apnews.com",
        "npr.org",
        "ft.com",
        "economist.com",
        "politico.com",
    ]

    try:
        result = await search_exa(
            query,
            num_results=num_results or 10,
            include_domains=news_domains,
        )
        _log_search("search_news", query, success=True, result_count=len(result.get("results", [])))
        return result
    except ExaSearchError as exc:
        error_msg = str(exc)
        _log_search("search_news", query, success=False, error=error_msg)
        return {
            "query": query,
            "results": [],
            "error": error_msg,
            "error_type": "search_unavailable",
        }
    except Exception as exc:
        error_msg = str(exc)
        _log_search("search_news", query, success=False, error=error_msg)
        return {
            "query": query,
            "results": [],
            "error": f"Unexpected error: {error_msg}",
            "error_type": "unknown",
        }


async def research_topic(
    topic: str,
    focus_areas: Optional[List[str]] = None,
    num_results: Optional[int] = None,
) -> Dict[str, Any]:
    """Conduct comprehensive research on a topic with optional focus areas."""

    if not focus_areas:
        # Single comprehensive search
        return await search_web(topic, num_results=num_results or 10)

    # Search for each focus area
    results_by_area: Dict[str, Any] = {
        "topic": topic,
        "focus_areas": {},
        "total_results": 0,
    }

    results_per_area = max(3, (num_results or 10) // len(focus_areas))

    for area in focus_areas:
        query = f"{topic} {area}"
        try:
            area_results = await search_exa(query, num_results=results_per_area)
            results_by_area["focus_areas"][area] = area_results.get("results", [])
            results_by_area["total_results"] += len(area_results.get("results", []))
        except ExaSearchError as exc:
            results_by_area["focus_areas"][area] = {
                "error": str(exc),
                "results": [],
            }

    _log_search("research_topic", topic, success=True, result_count=results_by_area["total_results"])
    return results_by_area


async def search_company(
    company_name: str,
    aspects: Optional[List[str]] = None,
    num_results: Optional[int] = None,
) -> Dict[str, Any]:
    """Search for comprehensive information about a company."""

    if not aspects:
        aspects = ["news", "overview"]

    company_results: Dict[str, Any] = {
        "company": company_name,
        "aspects": {},
        "total_results": 0,
    }

    results_per_aspect = num_results or 8

    for aspect in aspects:
        query = f"{company_name} {aspect}"
        try:
            aspect_results = await search_exa(query, num_results=results_per_aspect)
            company_results["aspects"][aspect] = aspect_results.get("results", [])
            company_results["total_results"] += len(aspect_results.get("results", []))
        except ExaSearchError as exc:
            company_results["aspects"][aspect] = {
                "error": str(exc),
                "results": [],
            }

    _log_search("search_company", company_name, success=True, result_count=company_results["total_results"])
    return company_results


async def search_academic(
    query: str,
    num_results: Optional[int] = None,
) -> Dict[str, Any]:
    """Search for academic papers and scholarly sources."""

    # Focus on academic and research domains
    academic_domains = [
        "scholar.google.com",
        "arxiv.org",
        "pubmed.ncbi.nlm.nih.gov",
        "jstor.org",
        "sciencedirect.com",
        "springer.com",
        "nature.com",
        "science.org",
        "ieee.org",
        "acm.org",
        "ncbi.nlm.nih.gov",
    ]

    try:
        result = await search_exa(
            query,
            num_results=num_results or 10,
            include_domains=academic_domains,
        )
        _log_search("search_academic", query, success=True, result_count=len(result.get("results", [])))
        return result
    except ExaSearchError as exc:
        error_msg = str(exc)
        _log_search("search_academic", query, success=False, error=error_msg)
        return {
            "query": query,
            "results": [],
            "error": error_msg,
            "error_type": "search_unavailable",
        }
    except Exception as exc:
        error_msg = str(exc)
        _log_search("search_academic", query, success=False, error=error_msg)
        return {
            "query": query,
            "results": [],
            "error": f"Unexpected error: {error_msg}",
            "error_type": "unknown",
        }


def answer_question(
    question: str,
    num_sources: Optional[int] = None,
    include_domains: Optional[List[str]] = None,
    exclude_domains: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Generate a direct, citation-backed answer using Exa's AI with optional segmentation."""

    segmented_queries = _split_complex_question(question)
    if not segmented_queries:
        segmented_queries = [question]

    per_query_sources = max(1, (num_sources or 5) // len(segmented_queries))
    combined_answers: List[str] = []
    combined_citations: List[Dict[str, Any]] = []
    partial_results: List[Dict[str, Any]] = []
    errors: List[str] = []

    try:
        for index, sub_query in enumerate(segmented_queries, start=1):
            result = generate_answer(
                sub_query,
                num_results=per_query_sources,
                include_domains=include_domains,
                exclude_domains=exclude_domains,
            )

            answer_text = result.get("answer") or result.get("text") or ""
            citations = result.get("citations", [])
            error_msg = result.get("error")

            if answer_text:
                combined_answers.append(f"Section {index}: {answer_text.strip()}")

            if citations:
                combined_citations.extend(citations)

            if error_msg:
                errors.append(str(error_msg))

            partial_results.append({
                "question": sub_query,
                "answer": answer_text or None,
                "citations": citations,
                "error": error_msg,
                "raw_result": result,
            })

        success = any(part.get("answer") for part in partial_results)
        total_citations = sum(len(part.get("citations", [])) for part in partial_results)

        if success:
            _log_search("answer_question", question, success=True, result_count=total_citations)
        else:
            _log_search("answer_question", question, success=False, error="No successful sub-query")

        response: Dict[str, Any] = {
            "question": question,
            "answer": "\n\n".join(combined_answers) if combined_answers else None,
            "citations": combined_citations,
            "sub_queries": segmented_queries,
            "partial_answers": partial_results,
        }

        if errors and not success:
            response["error"] = errors[-1]
            response["error_type"] = "composio_unavailable"

        if errors and success:
            response["warnings"] = errors

        return response

    except ExaError as exc:
        error_msg = str(exc)
        _log_search("answer_question", question, success=False, error=error_msg)
        return {
            "question": question,
            "answer": None,
            "citations": [],
            "error": error_msg,
            "error_type": "composio_unavailable",
            "sub_queries": segmented_queries,
            "partial_answers": [],
        }
    except Exception as exc:
        error_msg = str(exc)
        _log_search("answer_question", question, success=False, error=error_msg)
        return {
            "question": question,
            "answer": None,
            "citations": [],
            "error": f"Unexpected error: {error_msg}",
            "error_type": "unknown",
            "sub_queries": segmented_queries,
            "partial_answers": [],
        }


def find_similar_content(
    url: str,
    num_results: Optional[int] = None,
    include_full_content: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Find web pages semantically similar to a given URL.

    Args:
        url: Reference URL to find similar content for
        num_results: Number of similar pages to return
        include_full_content: Whether to include full text

    Returns:
        Dict with 'results' list of similar pages
    """
    try:
        result = find_similar(
            url,
            num_results=num_results or 10,
            include_text=include_full_content or False,
        )
        results = result.get("results", [])
        _log_search("find_similar_content", url, success=True, result_count=len(results))
        return {
            "reference_url": url,
            "results": results,
            "total_results": len(results),
        }
    except ExaError as exc:
        error_msg = str(exc)
        _log_search("find_similar_content", url, success=False, error=error_msg)
        return {
            "reference_url": url,
            "results": [],
            "error": error_msg,
            "error_type": "composio_unavailable",
        }
    except Exception as exc:
        error_msg = str(exc)
        _log_search("find_similar_content", url, success=False, error=error_msg)
        return {
            "reference_url": url,
            "results": [],
            "error": f"Unexpected error: {error_msg}",
            "error_type": "unknown",
        }


def extract_content(
    urls: List[str],
    include_highlights: Optional[bool] = None,
) -> Dict[str, Any]:
    """
    Retrieve full content from a list of URLs.

    Args:
        urls: List of URLs to fetch content from (max 10)
        include_highlights: Whether to include highlighted excerpts

    Returns:
        Dict with 'contents' list of retrieved content
    """
    # Limit to 10 URLs to avoid overwhelming the service
    limited_urls = urls[:10] if len(urls) > 10 else urls

    try:
        result = get_contents(
            limited_urls,
            include_text=True,
            include_highlights=include_highlights or False,
        )
        contents = result.get("contents", []) or result.get("data", [])
        _log_search("extract_content", f"{len(limited_urls)} URLs", success=True, result_count=len(contents))
        return {
            "urls": limited_urls,
            "contents": contents,
            "total_retrieved": len(contents),
        }
    except ExaError as exc:
        error_msg = str(exc)
        _log_search("extract_content", f"{len(limited_urls)} URLs", success=False, error=error_msg)
        return {
            "urls": limited_urls,
            "contents": [],
            "error": error_msg,
            "error_type": "composio_unavailable",
        }
    except Exception as exc:
        error_msg = str(exc)
        _log_search("extract_content", f"{len(limited_urls)} URLs", success=False, error=error_msg)
        return {
            "urls": limited_urls,
            "contents": [],
            "error": f"Unexpected error: {error_msg}",
            "error_type": "unknown",
        }


__all__ = [
    "build_registry",
    "get_schemas",
    "search_web",
    "search_news",
    "research_topic",
    "search_company",
    "search_academic",
    "answer_question",
    "find_similar_content",
    "extract_content",
]
