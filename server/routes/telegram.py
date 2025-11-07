"""Telegram-specific routes for handling bot messages."""

import asyncio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..agents.interaction_agent import InteractionAgentRuntime
from ..services.telegram_service import get_telegram_service
from ..logging_config import logger

router = APIRouter(prefix="/telegram", tags=["telegram"])


class TelegramMessageRequest(BaseModel):
    """Request model for Telegram messages."""
    message: str
    chat_id: str


class TelegramMessageResponse(BaseModel):
    """Response model for Telegram messages."""
    status: str
    message: str


async def _process_telegram_message_background(chat_id: str, message: str) -> None:
    """
    Background task to process Telegram message asynchronously.

    This runs independently and pushes responses to Telegram as they become available.
    """
    telegram_service = get_telegram_service()

    try:
        # Send typing indicator immediately
        await telegram_service.send_typing_action(chat_id)

        logger.info(
            "Background processing started",
            extra={
                "chat_id": chat_id,
                "message_preview": message[:100]
            }
        )

        runtime = InteractionAgentRuntime()
        result = await runtime.execute(
            user_message=message,
            telegram_chat_id=chat_id  # Enable async push notifications
        )

        # If the runtime returns a final response (cases without send_message_to_user calls)
        # we need to send it to Telegram
        if result.response and result.response.strip():
            logger.info(
                f"📤 SENDING FINAL RESPONSE TO TELEGRAM (chat_id={chat_id})",
                extra={
                    "chat_id": chat_id,
                    "response_length": len(result.response),
                    "response_preview": result.response[:200]
                }
            )
            await telegram_service.send_message(chat_id, result.response)
            logger.info(
                "✅ Final response sent to Telegram",
                extra={"chat_id": chat_id, "success": result.success}
            )
        else:
            logger.info(
                "ℹ️ No final response to send (messages sent via send_message_to_user tools)",
                extra={"chat_id": chat_id}
            )

        logger.info(
            "Background processing completed",
            extra={
                "chat_id": chat_id,
                "success": result.success,
                "agents_used": result.execution_agents_used
            }
        )

    except Exception as exc:
        logger.exception(
            "Error in background message processing",
            extra={"chat_id": chat_id, "error": str(exc)}
        )

        # Send SIMPLE, user-friendly error message
        error_type = type(exc).__name__

        if "RuntimeError" in error_type and "iteration limit" in str(exc):
            error_msg = "Désolé, j'ai eu trop d'étapes à faire. Reformule ta question plus simplement ?"
        elif "timeout" in str(exc).lower():
            error_msg = "Ça prend trop de temps. Réessaie avec une question plus précise ?"
        else:
            error_msg = "Une erreur inattendue s'est produite. Réessaie ou demande autre chose ?"

        try:
            await telegram_service.send_message(chat_id, error_msg)
            logger.info(f"Error message sent to Telegram chat {chat_id}")
        except Exception as send_exc:
            logger.error(
                "Failed to send error message to Telegram",
                extra={"chat_id": chat_id, "error": str(send_exc)}
            )


@router.post("/message", response_model=TelegramMessageResponse, status_code=202)
async def handle_telegram_message(request: TelegramMessageRequest) -> TelegramMessageResponse:
    """
    Handle incoming Telegram messages asynchronously.

    This endpoint returns immediately with a 202 Accepted status.
    The actual processing happens in the background, and responses are pushed
    to Telegram as they become available through the Telegram API.
    """
    try:
        logger.info(
            "Telegram message received - launching background task",
            extra={
                "chat_id": request.chat_id,
                "message_length": len(request.message),
                "message_preview": request.message[:100]
            }
        )

        # Launch background task without awaiting
        asyncio.create_task(
            _process_telegram_message_background(request.chat_id, request.message)
        )

        # Return immediately
        return TelegramMessageResponse(
            status="processing",
            message="Message received and being processed"
        )

    except Exception as e:
        logger.exception("Error launching background task", extra={"error": str(e)})
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )
