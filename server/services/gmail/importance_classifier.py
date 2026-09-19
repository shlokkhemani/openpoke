"""Classifier for determining important Gmail emails.

Two stages. A Jev typed decision screens every email first: confidently
unimportant mail never reaches an LLM, and confidently important mail skips
straight to summarisation. Only the uncertain middle band pays for the full
LLM judgement, which is also the whole behaviour when Jev is not configured.
"""

from __future__ import annotations

import json
from typing import Any, Dict, Optional

from .processing import ProcessedEmail
from ...config import get_settings
from ...jev import QUARANTINE, SKIP, SURFACE, record_screening, screen_email
from ...logging_config import logger
from ...openrouter_client import OpenRouterError, request_chat_completion


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


_SUMMARY_SYSTEM_PROMPT = (
    "You write the one-notification summary of an email that has already been judged "
    "worth surfacing to the user. Reply with 2-3 sentences naming the sender, the topic, "
    "and the specific action or urgency for the user. Do not add a preamble, a greeting, "
    "or any commentary about the email's importance."
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

    screening = await screen_email(
        sender=email.sender,
        recipient=email.recipient,
        subject=email.subject,
        body=email.clean_text,
        labels=email.label_ids,
        has_attachments=email.has_attachments,
        attachment_filenames=email.attachment_filenames,
    )

    record_screening(
        screening,
        message_id=email.id,
        sender=email.sender,
        subject=email.subject,
    )

    if screening.verdict == QUARANTINE:
        logger.warning(
            "Email quarantined by typed screening",
            extra={
                "message_id": email.id,
                "reason": screening.reason,
                "probabilities": screening.probabilities,
            },
        )
        return _quarantine_notice(email)

    if screening.verdict == SKIP:
        logger.debug(
            "Email skipped by typed screening",
            extra={
                "message_id": email.id,
                "reason": screening.reason,
                "probabilities": screening.probabilities,
            },
        )
        return None

    if screening.verdict == SURFACE:
        logger.debug(
            "Email surfaced by typed screening",
            extra={
                "message_id": email.id,
                "reason": screening.reason,
                "probabilities": screening.probabilities,
            },
        )
        summary = await _summarize_email(email)
        if summary:
            return summary
        # Summarisation failed; fall through to the full LLM judgement rather
        # than dropping an email the screen already flagged as important.

    return await _classify_with_llm(email)


def _quarantine_notice(email: ProcessedEmail) -> str:
    """Return the fixed notice shown when a body is withheld.

    Assembled in code, never by a model, and it carries no body. Sender and
    subject are attacker-controlled for external mail, so both are clipped and
    labelled as unverified; the point is that the user learns a message exists
    rather than that they learn what it says.
    """

    sender = (email.sender or "unknown sender")[:120]
    subject = (email.subject or "(no subject)")[:120]
    return (
        "A message was withheld because its body reads as an attempt to give "
        "instructions to an assistant rather than to you. Its contents have not "
        f"been read to me. Unverified sender: {sender}. Unverified subject: "
        f"{subject}. Open it yourself if you were expecting it."
    )


async def _summarize_email(email: ProcessedEmail) -> Optional[str]:
    """Return a notification summary for an email already judged important."""

    settings = get_settings()
    api_key = settings.openrouter_api_key
    if not api_key:
        logger.warning("Skipping importance summary; OpenRouter API key missing")
        return None

    try:
        response = await request_chat_completion(
            model=settings.email_classifier_model,
            messages=[{"role": "user", "content": _format_email_payload(email)}],
            system=_SUMMARY_SYSTEM_PROMPT,
            api_key=api_key,
        )
    except OpenRouterError as exc:
        logger.error(
            "Importance summary failed",
            extra={"message_id": email.id, "error": str(exc)},
        )
        return None
    except Exception:  # pragma: no cover - defensive
        logger.exception(
            "Unexpected error while summarizing an important email",
            extra={"message_id": email.id},
        )
        return None

    message = (response.get("choices") or [{}])[0].get("message") or {}
    content = message.get("content")
    if isinstance(content, str) and content.strip():
        return content.strip()

    logger.warning(
        "Importance summary returned no content",
        extra={"message_id": email.id},
    )
    return None


async def _classify_with_llm(email: ProcessedEmail) -> Optional[str]:
    """Decide importance and write a summary in a single tool-calling LLM call."""

    settings = get_settings()
    api_key = settings.openrouter_api_key
    model = settings.email_classifier_model

    if not api_key:
        logger.warning("Skipping importance check; OpenRouter API key missing")
        return None

    user_payload = _format_email_payload(email)
    messages = [{"role": "user", "content": user_payload}]

    try:
        response = await request_chat_completion(
            model=model,
            messages=messages,
            system=_SYSTEM_PROMPT,
            api_key=api_key,
            tools=[_TOOL_SCHEMA],
        )
    except OpenRouterError as exc:
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
