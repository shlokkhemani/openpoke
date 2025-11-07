"""Telegram service for sending messages asynchronously."""

import asyncio
import os
from typing import Optional

import httpx

from ..logging_config import logger


class TelegramService:
    """Service for sending messages to Telegram users asynchronously."""

    def __init__(self):
        """Initialize Telegram service with bot token from environment."""
        self.bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
        if not self.bot_token:
            logger.warning("TELEGRAM_BOT_TOKEN not set - Telegram notifications disabled")

        self.base_url = f"https://api.telegram.org/bot{self.bot_token}"
        self._client: Optional[httpx.AsyncClient] = None

    async def _get_client(self) -> httpx.AsyncClient:
        """Get or create async HTTP client."""
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=10.0)
        return self._client

    async def send_typing_action(self, chat_id: str) -> bool:
        """
        Send typing action to show the bot is processing.

        Args:
            chat_id: Telegram chat ID

        Returns:
            True if action was sent successfully, False otherwise
        """
        if not self.bot_token:
            return False

        try:
            client = await self._get_client()
            response = await client.post(
                f"{self.base_url}/sendChatAction",
                json={
                    "chat_id": chat_id,
                    "action": "typing",
                }
            )
            return response.status_code == 200
        except Exception:
            # Typing action is not critical, don't log errors
            return False

    async def send_message(
        self,
        chat_id: str,
        text: str,
        parse_mode: str = "Markdown"
    ) -> bool:
        """
        Send a message to a Telegram chat. Splits long messages into multiple shorter ones.

        Args:
            chat_id: Telegram chat ID
            text: Message text to send
            parse_mode: Message formatting (Markdown or HTML)

        Returns:
            True if all messages were sent successfully, False otherwise
        """
        if not self.bot_token:
            logger.error("Cannot send Telegram message - bot token not configured")
            return False

        # Split long messages into chunks of max 250 chars for better UX
        # User prefers 2-3 short messages instead of one long message
        MAX_CHUNK_SIZE = 250

        if len(text) <= MAX_CHUNK_SIZE:
            # Short message - send as is
            return await self._send_single_message(chat_id, text, parse_mode)

        # Long message - split into multiple messages
        chunks = self._split_message(text, MAX_CHUNK_SIZE)
        logger.info(
            f"Splitting long message into {len(chunks)} chunks",
            extra={"chat_id": chat_id, "total_length": len(text)}
        )

        all_success = True
        for i, chunk in enumerate(chunks):
            if i > 0:
                # Small delay between messages to avoid rate limiting
                await asyncio.sleep(0.5)

            success = await self._send_single_message(chat_id, chunk, parse_mode)
            if not success:
                all_success = False

        return all_success

    def _split_message(self, text: str, max_size: int) -> list[str]:
        """Split a message into chunks, trying to break at paragraph or sentence boundaries."""
        if len(text) <= max_size:
            return [text]

        chunks = []
        remaining = text

        while remaining:
            if len(remaining) <= max_size:
                chunks.append(remaining)
                break

            # Try to split at natural boundaries (most natural to least)
            # 1. Paragraph boundary
            split_at = remaining.rfind('\n\n', 0, max_size)
            if split_at == -1:
                # 2. Line break
                split_at = remaining.rfind('\n', 0, max_size)
            if split_at == -1:
                # 3. Sentence ending with period
                split_at = remaining.rfind('. ', 0, max_size)
            if split_at == -1:
                # 4. Question mark
                split_at = remaining.rfind('? ', 0, max_size)
            if split_at == -1:
                # 5. Exclamation mark
                split_at = remaining.rfind('! ', 0, max_size)
            if split_at == -1:
                # 6. Semicolon or colon
                for punct in ['; ', ': ']:
                    split_at = remaining.rfind(punct, 0, max_size)
                    if split_at != -1:
                        break
            if split_at == -1:
                # 7. Comma (less ideal but still a pause)
                split_at = remaining.rfind(', ', 0, max_size)
            if split_at == -1:
                # 8. Any space
                split_at = remaining.rfind(' ', 0, max_size)
            if split_at == -1:
                # 9. Force split at max_size (last resort)
                split_at = max_size

            chunk = remaining[:split_at].strip()
            if chunk:
                chunks.append(chunk)
            remaining = remaining[split_at:].strip()

        return chunks

    async def _send_single_message(
        self,
        chat_id: str,
        text: str,
        parse_mode: str
    ) -> bool:
        """Send a single message to Telegram."""
        try:
            client = await self._get_client()
            response = await client.post(
                f"{self.base_url}/sendMessage",
                json={
                    "chat_id": chat_id,
                    "text": text,
                    "parse_mode": parse_mode,
                }
            )

            if response.status_code == 200:
                logger.info(
                    "Telegram message sent",
                    extra={
                        "chat_id": chat_id,
                        "text_length": len(text),
                    }
                )
                return True
            else:
                logger.error(
                    "Telegram API error",
                    extra={
                        "status_code": response.status_code,
                        "response": response.text[:200],
                    }
                )
                return False

        except Exception as exc:
            logger.error(
                "Failed to send Telegram message",
                extra={
                    "error": str(exc),
                    "chat_id": chat_id,
                }
            )
            return False

    async def close(self):
        """Close the HTTP client."""
        if self._client:
            await self._client.aclose()
            self._client = None


# Global singleton instance
_telegram_service: Optional[TelegramService] = None


def get_telegram_service() -> TelegramService:
    """Get the global Telegram service instance."""
    global _telegram_service
    if _telegram_service is None:
        _telegram_service = TelegramService()
    return _telegram_service
