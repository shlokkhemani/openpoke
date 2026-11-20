"""LLM-powered classifier for determining important Gmail emails."""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from .processing import ProcessedEmail
from ...config import get_settings
from ...logging_config import logger
from ...llm_client import LLMError, request_chat_completion


_TOOL_NAME = "mark_email_importance"
_TOOL_SCHEMA: Dict[str, Any] = {
    "type": "function",
    "function": {
        "name": _TOOL_NAME,
        "description": (
            "Decide whether an email should be proactively surfaced to the user and, "
            "if so, provide a natural-language summary explaining why."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "important": {
                    "type": "boolean",
                    "description": (
                        "Set to true only when the email requires timely attention, a decision, "
                        "coordination, or contains critical security information (e.g. OTPs)."
                    ),
                },
                "summary": {
                    "type": "string",
                    "description": (
                        "Concise 2-3 sentence summary highlighting sender, topic, and the "
                        "specific action or urgency for the user. Only include when important=true."
                    ),
                },
            },
            "required": ["important"],
            "additionalProperties": False,
        },
    },
}

_SYSTEM_PROMPT = (
    "You review incoming Gmail messages and decide whether they warrant an immediate proactive "
    "notification to the user. Only mark an email as important if it materially affects the "
    "user's plans, requires a prompt decision or action, is a security-sensitive OTP or login "
    "notice, or contains high-priority updates (e.g. interviews, meeting changes). Ignore "
    "order confirmations, routine marketing, newsletters, generic receipts, and low-impact "
    "status notifications. When important, craft a brief summary that will be forwarded to the "
    "user describing what happened and why it matters."
)


def _format_email_payload(email: ProcessedEmail) -> str:
    attachments = ", ".join(email.attachment_filenames) if email.attachment_filenames else "None"
    labels = ", ".join(email.label_ids) if email.label_ids else "None"
    header_lines = [
        f"Sender: {email.sender}",
        f"Recipient: {email.recipient}",
        f"Subject: {email.subject}",
        f"Received (user timezone): {email.timestamp.isoformat()}",
        f"Thread ID: {email.thread_id or 'None'}",
        f"Labels: {labels}",
        f"Has attachments: {'Yes' if email.has_attachments else 'No'}",
        f"Attachment filenames: {attachments}",
    ]

    return (
        "Email Metadata:\n"
        + "\n".join(header_lines)
        + "\n\nCleaned Body:\n"
        + (email.clean_text or "(empty body)")
    )


async def classify_email_importance(email: ProcessedEmail) -> Optional[str]:
    """Return summary text when email should be surfaced; otherwise None."""

    settings = get_settings()
    base_url = (settings.llm_base_url or "").strip()
    model = settings.email_classifier_model

    if not base_url:
        logger.warning("Skipping importance check; LLM_BASE_URL is not configured")
        return None

    user_payload = _format_email_payload(email)
    messages = [{"role": "user", "content": user_payload}]

    try:
        response = await request_chat_completion(
            model=model,
            messages=messages,
            system=_SYSTEM_PROMPT,
            base_url=base_url,
            tools=[_TOOL_SCHEMA],
        )
    except LLMError as exc:
        logger.error(
            "Importance classification failed",
            extra={"message_id": email.id, "error": str(exc)},
        )
        return None
    except Exception as exc:  # pragma: no cover - defensive
        logger.exception(
            "Unexpected error during importance classification",
            extra={"message_id": email.id},
        )
        return None

    choice = (response.get("choices") or [{}])[0]
    message = choice.get("message") or {}
    tool_calls = message.get("tool_calls") or []

    for tool_call in tool_calls:
        function_block = tool_call.get("function") or {}
        if function_block.get("name") != _TOOL_NAME:
            continue

        raw_arguments = function_block.get("arguments")
        arguments = _coerce_arguments(raw_arguments)
        if arguments is None:
            logger.warning(
                "Importance tool returned invalid arguments",
                extra={"message_id": email.id},
            )
            return None

        important = bool(arguments.get("important"))
        summary = arguments.get("summary")

        if not important:
            return None

        if not isinstance(summary, str) or not summary.strip():
            logger.warning(
                "Importance tool marked email important without summary",
                extra={"message_id": email.id},
            )
            return None

        return summary.strip()

    logger.debug(
        "Importance classification produced no tool call",
        extra={"message_id": email.id},
    )
    return None


def _coerce_arguments(raw: Any) -> Optional[Dict[str, Any]]:
    if raw is None:
        return {}
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        if not raw.strip():
            return {}
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return None
    return None


__all__ = ["classify_email_importance"]
