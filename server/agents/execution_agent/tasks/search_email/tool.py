"""Email search task implementation."""

from __future__ import annotations

import json
from typing import Any, Callable, Dict, List, Optional, Sequence, Tuple

from server.config import get_settings
from server.jev import filter_search_results
from server.logging_config import logger
from server.openrouter_client import request_chat_completion
from server.services.execution import get_execution_agent_logs
from server.services.gmail import (
    EmailTextCleaner,
    ProcessedEmail,
    execute_gmail_tool,
    get_active_gmail_user_id,
    parse_gmail_fetch_response,
)
from .gmail_internal import GMAIL_FETCH_EMAILS_SCHEMA
from .schemas import (
    GmailSearchEmail,
    EmailSearchToolResult,
    TaskEmailSearchPayload,
    COMPLETE_TOOL_NAME,
    SEARCH_TOOL_NAME,
    TASK_TOOL_NAME,
    get_completion_schema,
)
from .system_prompt import get_system_prompt

# Constants
MAX_LLM_ITERATIONS = 8
ERROR_GMAIL_NOT_CONNECTED = "Gmail not connected. Please connect Gmail in settings first."
ERROR_OPENROUTER_NOT_CONFIGURED = "OpenRouter API key not configured. Set OPENROUTER_API_KEY."
ERROR_EMPTY_QUERY = "search_query must not be empty"
ERROR_QUERY_REQUIRED = "query parameter is required"
ERROR_MESSAGE_IDS_REQUIRED = "message_ids parameter is required"
ERROR_MESSAGE_IDS_MUST_BE_LIST = "message_ids must be provided as a list"
ERROR_TOOL_ARGUMENTS_INVALID = "Tool arguments must be an object"
ERROR_ITERATION_LIMIT = "Email search orchestrator exceeded iteration limit"



_COMPLETION_TOOL_SCHEMA = get_completion_schema()
_LOG_STORE = get_execution_agent_logs()
_EMAIL_CLEANER = EmailTextCleaner(max_url_length=40)


# Create standardized error response for tool calls
def _create_error_response(call_id: str, query: Optional[str], error: str) -> Tuple[str, str]:
    """Create standardized error response for tool calls."""
    result = EmailSearchToolResult(status="error", query=query, error=error)
    return (call_id, _safe_json_dumps(result.model_dump(exclude_none=True)))


# Create standardized success response for tool calls
def _create_success_response(call_id: str, data: Dict[str, Any]) -> Tuple[str, str]:
    """Create standardized success response for tool calls."""
    return (call_id, _safe_json_dumps(data))


def _validate_search_query(search_query: str) -> Optional[str]:
    """Validate search query and return error message if invalid."""
    if not (search_query or "").strip():
        return ERROR_EMPTY_QUERY
    return None


def _validate_gmail_connection() -> Optional[str]:
    """Validate Gmail connection and return user ID or None."""
    return get_active_gmail_user_id()


def _validate_openrouter_config() -> Tuple[Optional[str], Optional[str]]:
    """Validate OpenRouter configuration and return (api_key, model) or (None, error)."""
    settings = get_settings()
    api_key = settings.openrouter_api_key
    if not api_key:
        return None, ERROR_OPENROUTER_NOT_CONFIGURED
    return api_key, settings.execution_agent_search_model


# Return task tool callables
def build_registry(agent_name: str) -> Dict[str, Callable[..., Any]]:  # noqa: ARG001
    """Return task tool callables."""

    return {
        TASK_TOOL_NAME: task_email_search,
    }


# Run an agentic Gmail search for the provided query
async def task_email_search(search_query: str) -> Any:
    """Run an agentic Gmail search for the provided query."""
    logger.info(f"[EMAIL_SEARCH] Starting search for: '{search_query}'")
    
    # Validate inputs
    cleaned_query = (search_query or "").strip()
    if error := _validate_search_query(cleaned_query):
        logger.error(f"[EMAIL_SEARCH] Invalid query: {error}")
        return {"error": error}
    
    composio_user_id = _validate_gmail_connection()
    if not composio_user_id:
        logger.error(f"[EMAIL_SEARCH] Gmail not connected")
        return {"error": ERROR_GMAIL_NOT_CONNECTED}
    
    api_key, model_or_error = _validate_openrouter_config()
    if not api_key:
        logger.error(f"[EMAIL_SEARCH] OpenRouter not configured: {model_or_error}")
        return {"error": model_or_error}
    
    try:
        result = await _run_email_search(
            search_query=cleaned_query,
            composio_user_id=composio_user_id,
            model=model_or_error,
            api_key=api_key,
        )
        logger.info(f"[EMAIL_SEARCH] Found {len(result) if isinstance(result, list) else 0} emails")
        return result
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception(f"[EMAIL_SEARCH] Search failed: {exc}")
        return {"error": f"Email search failed: {exc}"}


# Execute the main email search orchestration loop
async def _run_email_search(
    *,
    search_query: str,
    composio_user_id: str,
    model: str,
    api_key: str,
) -> List[Dict[str, Any]]:
    """Execute the main email search orchestration loop."""
    messages: List[Dict[str, Any]] = [
        {"role": "user", "content": _render_user_message(search_query)}
    ]
    queries: List[str] = []
    emails: Dict[str, GmailSearchEmail] = {}
    selected_ids: Optional[List[str]] = None
    
    for iteration in range(MAX_LLM_ITERATIONS):
        logger.debug(
            "[task_email_search] LLM iteration",
            extra={"iteration": iteration + 1, "tool": TASK_TOOL_NAME},
        )
        
        # Get LLM response
        response = await request_chat_completion(
            model=model,
            messages=messages,
            system=get_system_prompt(),
            api_key=api_key,
            tools=[GMAIL_FETCH_EMAILS_SCHEMA, _COMPLETION_TOOL_SCHEMA],
        )
        
        # Process assistant response
        assistant = _extract_assistant_message(response)
        tool_calls = assistant.get("tool_calls") or []
        
        # Add assistant message to conversation
        assistant_entry = {
            "role": "assistant",
            "content": assistant.get("content", "") or "",
        }
        if tool_calls:
            assistant_entry["tool_calls"] = tool_calls
        messages.append(assistant_entry)
        
        # Handle case where LLM doesn't make tool calls
        if not tool_calls:
            logger.info(f"[EMAIL_SEARCH] LLM completed search - no more queries needed")
            selected_ids = []
            break
        
        # Execute tool calls and process responses
        tool_responses, completed_ids = await _execute_tool_calls(
            tool_calls=tool_calls,
            queries=queries,
            emails=emails,
            composio_user_id=composio_user_id,
        )
        
        # Add tool responses to conversation
        for call_id, content in tool_responses:
            messages.append({
                "role": "tool",
                "tool_call_id": call_id,
                "content": content,
            })
        
        # Check if search is complete
        if completed_ids is not None:
            logger.info(f"[EMAIL_SEARCH] Search completed - selected {len(completed_ids)} emails")
            selected_ids = completed_ids
            break
    else:
        logger.error(f"[EMAIL_SEARCH] {ERROR_ITERATION_LIMIT}")
        raise RuntimeError(ERROR_ITERATION_LIMIT)
    
    verified_ids = await _verify_selection(
        search_query=search_query,
        emails=emails,
        selected_ids=selected_ids or [],
    )

    final_result = _build_response(queries, emails, verified_ids)
    unique_queries = list(dict.fromkeys(queries))
    logger.info(f"[EMAIL_SEARCH] Completed - {len(unique_queries)} queries executed, {len(final_result)} emails selected")
    return final_result




# Create user message for the LLM with search context
def _render_user_message(search_query: str) -> str:
    """Create user message for the LLM with search context."""
    return f"Please help me find emails: {search_query}"


# Execute tool calls from LLM and process search/completion responses
async def _execute_tool_calls(
    *,
    tool_calls: List[Dict[str, Any]],
    queries: List[str],
    emails: Dict[str, GmailSearchEmail],
    composio_user_id: str,
) -> Tuple[List[Tuple[str, str]], Optional[List[str]]]:
    responses: List[Tuple[str, str]] = []
    completion_ids: Optional[List[str]] = None

    for call in tool_calls:
        call_id = call.get("id") or SEARCH_TOOL_NAME
        function = call.get("function") or {}
        name = function.get("name") or ""
        raw_arguments = function.get("arguments", {})
        arguments, parse_error = _parse_arguments(raw_arguments)

        if parse_error:
            # Handle argument parsing errors
            query = arguments.get("query") if arguments else None
            logger.warning(f"[EMAIL_SEARCH] Tool argument parsing failed: {parse_error}")
            responses.append(_create_error_response(call_id, query, parse_error))

        elif name == COMPLETE_TOOL_NAME:
            # Handle completion tool - signals end of search
            completion_ids_candidate, response_data = _handle_completion_tool(arguments)
            responses.append(_create_success_response(call_id, response_data))
            if completion_ids_candidate is not None:
                logger.info(f"[EMAIL_SEARCH] LLM selected {len(completion_ids_candidate)} emails")
                completion_ids = completion_ids_candidate
                break

        elif name == SEARCH_TOOL_NAME:
            # Handle Gmail search tool
            search_query = arguments.get("query", "<unknown>")
            logger.info(f"[SEARCH_QUERY] LLM generated query: '{search_query}'")
            
            result_model = await _perform_search(
                arguments=arguments,
                queries=queries,
                emails=emails,
                composio_user_id=composio_user_id,
            )
            response_data = result_model.model_dump(exclude_none=True)
            
            if result_model.status == "success":
                count = result_model.result_count or 0
                logger.info(f"[SEARCH_RESULT] Query '{search_query}' → {count} emails found")
            else:
                logger.warning(f"[SEARCH_RESULT] Query '{search_query}' → FAILED: {result_model.error}")
            
            responses.append(_create_success_response(call_id, response_data))

        else:
            # Handle unsupported tools
            query = arguments.get("query")
            error = f"Unsupported tool: {name}"
            logger.warning(f"[EMAIL_SEARCH] Unsupported tool: {name}")
            responses.append(_create_error_response(call_id, query, error))

    return responses, completion_ids


# Perform Gmail search using Composio and process results
async def _perform_search(
    *,
    arguments: Dict[str, Any],
    queries: List[str],
    emails: Dict[str, GmailSearchEmail],
    composio_user_id: str,
) -> EmailSearchToolResult:
    query = (arguments.get("query") or "").strip()
    if not query:
        logger.warning(f"[EMAIL_SEARCH] Search called with empty query")
        return EmailSearchToolResult(
            status="error",
            error=ERROR_QUERY_REQUIRED,
        )

    # Use LLM-provided max_results or default to 10
    max_results = arguments.get("max_results", 10)
    
    composio_arguments = {
        "query": query,
        "max_results": max_results,  # Use LLM-provided value or default 10
        "include_payload": True,  # REQUIRED: Need full email content for text cleaning
        "verbose": True,  # REQUIRED: Need parsed content including messageText
        "include_spam_trash": arguments.get("include_spam_trash", False),  # Default: False
        "format": "full",  # Request full email format
        "metadata_headers": ["From", "To", "Subject", "Date"],  # Ensure we get key headers
    }

    _LOG_STORE.record_action(
        TASK_TOOL_NAME,
        description=f"{TASK_TOOL_NAME} search | query={query} | max_results={max_results}",
    )

    try:
        raw_result = execute_gmail_tool(
            "GMAIL_FETCH_EMAILS",
            composio_user_id,
            arguments=composio_arguments,
        )
    except Exception as exc:
        logger.error(f"[EMAIL_SEARCH] Gmail API failed for '{query}': {exc}")
        return EmailSearchToolResult(
            status="error",
            query=query,
            error=str(exc),
        )

    processed_emails, next_page_token = parse_gmail_fetch_response(
        raw_result,
        query=query,
        cleaner=_EMAIL_CLEANER,
    )
    parsed_emails = [_processed_to_schema(email) for email in processed_emails]

    queries.append(query)
    for email in parsed_emails:
        if email.id not in emails:
            emails[email.id] = email

    return EmailSearchToolResult(
        status="success",
        query=query,
        result_count=len(parsed_emails),
        next_page_token=next_page_token,
        messages=parsed_emails,
    )


# Drop selected emails a typed decision is confident do not answer the request
async def _verify_selection(
    *,
    search_query: str,
    emails: Dict[str, GmailSearchEmail],
    selected_ids: Sequence[str],
) -> List[str]:
    """Return the selection after the Jev relevance filter, if it is available."""

    candidates = {
        message_id: {
            "from": email.sender,
            "subject": email.subject,
            "body": email.clean_text,
        }
        for message_id, email in emails.items()
    }

    outcome = await filter_search_results(
        request=search_query,
        selected_ids=list(selected_ids),
        candidates=candidates,
    )
    if outcome.dropped:
        logger.info(
            f"[EMAIL_SEARCH] Relevance filter dropped {len(outcome.dropped)} of "
            f"{len(selected_ids)} selected emails"
        )
    return outcome.kept


# Build final response with selected emails and logging
def _build_response(
    queries: List[str],
    emails: Dict[str, GmailSearchEmail],
    selected_ids: Sequence[str],
) -> List[Dict[str, Any]]:
    # Deduplicate queries while preserving order
    unique_queries = list(dict.fromkeys(queries))
    
    # Deduplicate and filter valid email IDs efficiently
    valid_ids = [id.strip() for id in selected_ids if id and id.strip()]
    unique_ids = list(dict.fromkeys(valid_ids))
    selected_emails = [emails[id] for id in unique_ids if id in emails]
    
    # Log any missing email IDs
    missing_ids = [id for id in unique_ids if id not in emails]
    if missing_ids:
        logger.warning(f"[EMAIL_SEARCH] {len(missing_ids)} selected email IDs not found")
    
    payload = TaskEmailSearchPayload(emails=selected_emails)
    
    _LOG_STORE.record_action(
        TASK_TOOL_NAME,
        description=(
            f"{TASK_TOOL_NAME} completed | queries={len(unique_queries)} "
            f"| emails={len(selected_emails)}"
        ),
    )
    
    return [email.model_dump(exclude_none=True) for email in payload.emails]


def _extract_assistant_message(response: Dict[str, Any]) -> Dict[str, Any]:
    """Extract assistant message from OpenRouter API response."""
    return response.get("choices", [{}])[0].get("message", {})


def _parse_arguments(raw_arguments: Any) -> Tuple[Dict[str, Any], Optional[str]]:
    """Parse tool arguments with proper error handling."""
    if isinstance(raw_arguments, dict):
        return raw_arguments, None
    if isinstance(raw_arguments, str):
        if not raw_arguments.strip():
            return {}, None
        try:
            return json.loads(raw_arguments), None
        except json.JSONDecodeError as exc:
            return {}, f"Failed to parse tool arguments: {exc}"
    return {}, ERROR_TOOL_ARGUMENTS_INVALID



def _handle_completion_tool(arguments: Dict[str, Any]) -> Tuple[Optional[List[str]], Dict[str, Any]]:
    """Handle completion tool call, parsing message IDs and returning response."""
    raw_ids = arguments.get("message_ids")
    if raw_ids is None:
        return None, {"status": "error", "error": ERROR_MESSAGE_IDS_REQUIRED}
    if not isinstance(raw_ids, list):
        return None, {"status": "error", "error": ERROR_MESSAGE_IDS_MUST_BE_LIST}
    
    # Filter out empty/invalid IDs efficiently
    message_ids = [str(value).strip() for value in raw_ids if str(value).strip()]
    
    return message_ids, {"status": "success", "message_ids": message_ids}


def _safe_json_dumps(payload: Any) -> str:
    """Safely serialize payload to JSON string."""
    try:
        return json.dumps(payload, ensure_ascii=False)
    except (TypeError, ValueError):
        return json.dumps({"repr": repr(payload)})





def _processed_to_schema(email: ProcessedEmail) -> GmailSearchEmail:
    """Convert shared processed email into GmailSearchEmail schema."""

    return GmailSearchEmail(
        id=email.id,
        thread_id=email.thread_id,
        query=email.query,
        subject=email.subject,
        sender=email.sender,
        recipient=email.recipient,
        timestamp=email.timestamp,
        label_ids=list(email.label_ids),
        clean_text=email.clean_text,
        has_attachments=email.has_attachments,
        attachment_count=email.attachment_count,
        attachment_filenames=list(email.attachment_filenames),
    )


__all__ = [
    "GmailSearchEmail",
    "EmailSearchToolResult",
    "build_registry",
    "task_email_search",
]
