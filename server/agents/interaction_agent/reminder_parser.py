"""Robust reminder message parsing with regex patterns and structured data."""

import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional


class ReminderMessageType(Enum):
    """Types of reminder-related messages."""

    NOTIFICATION = "notification"  # Triggered reminder being delivered
    CREATION = "creation"  # Confirmation of reminder being created
    GENERAL = "general"  # Other reminder-related messages
    NONE = "none"  # Not a reminder message


@dataclass
class ReminderMessage:
    """Structured representation of a parsed reminder message."""

    message_type: ReminderMessageType
    original_text: str
    reminder_content: Optional[str] = None
    trigger_time: Optional[str] = None
    reminder_title: Optional[str] = None
    is_error: bool = False


class ReminderMessageParser:
    """
    Parser for reminder-related messages using regex patterns.

    Supports both French and English keywords for robust multilingual detection.
    Uses structured patterns instead of hard-coded string matching.
    """

    # Pattern for SUCCESS notification messages - more flexible to match any agent name
    NOTIFICATION_PATTERN = re.compile(
        r'\[SUCCESS\]\s*([^:]+?)\s*:\s*(.+)$',
        re.DOTALL | re.IGNORECASE
    )

    # Keywords for reminder creation detection (case-insensitive)
    CREATION_KEYWORDS = {
        'status': ['créé', 'created', 'programmé', 'programmed', 'actif', 'active', 'scheduled'],
        'entity': ['rappel', 'reminder', 'mémo', 'memo'],
        'identifier': ['#', 'id:', 'id '],
    }

    # Keywords for general reminder detection (case-insensitive)
    GENERAL_KEYWORDS = [
        'rappel', 'reminder', 'remind', 'rappeler', 'mémo', 'memo',
        'alarme', 'alarm', 'notification', 'notifier'
    ]

    # Pattern to extract title/content from structured messages
    TITLE_PATTERN = re.compile(
        r'(?:titre|title|message|content)\s*:\s*["\']?([^"\'\n]+)["\']?',
        re.IGNORECASE
    )

    # Pattern to extract trigger time
    TIME_PATTERN = re.compile(
        r'(?:heure|time).*?(?:déclenchement|trigger)\s*:\s*([^\n]+)',
        re.IGNORECASE
    )

    # Pattern to detect error messages
    ERROR_PATTERN = re.compile(
        r'\b(?:problème|problem|erreur|error|échec|failed?)\b',
        re.IGNORECASE
    )

    def parse(self, message: str) -> ReminderMessage:
        """
        Parse a message and determine its type and content.

        Args:
            message: The raw message text to parse

        Returns:
            ReminderMessage with parsed type and extracted fields
        """
        # Check for notification first (highest priority)
        notification_match = self._check_notification(message)
        if notification_match:
            return notification_match

        # Check for creation confirmation
        creation_match = self._check_creation(message)
        if creation_match:
            return creation_match

        # Check for general reminder-related message
        if self._is_general_reminder(message):
            is_error = self._is_error_message(message)
            return ReminderMessage(
                message_type=ReminderMessageType.GENERAL,
                original_text=message,
                is_error=is_error
            )

        # Not a reminder message
        return ReminderMessage(
            message_type=ReminderMessageType.NONE,
            original_text=message
        )

    def _check_notification(self, message: str) -> Optional[ReminderMessage]:
        """
        Check if message is a reminder notification.

        Args:
            message: The message to check

        Returns:
            ReminderMessage if it's a notification, None otherwise
        """
        match = self.NOTIFICATION_PATTERN.search(message)
        if match:
            agent_name = match.group(1).strip()
            reminder_content = match.group(2).strip()
            # Clean up leading colons or other artifacts
            reminder_content = re.sub(r'^:\s*', '', reminder_content)

            return ReminderMessage(
                message_type=ReminderMessageType.NOTIFICATION,
                original_text=message,
                reminder_content=reminder_content,
                reminder_title=f"Notification from {agent_name}"
            )
        return None

    def _check_creation(self, message: str) -> Optional[ReminderMessage]:
        """
        Check if message is a reminder creation confirmation.

        Args:
            message: The message to check

        Returns:
            ReminderMessage if it's a creation confirmation, None otherwise
        """
        message_lower = message.lower()

        # Must have both entity keyword and status keyword
        has_entity = any(
            keyword in message_lower
            for keyword in self.CREATION_KEYWORDS['entity']
        )
        has_status = any(
            keyword in message_lower
            for keyword in self.CREATION_KEYWORDS['status']
        )
        has_identifier = any(
            keyword in message_lower
            for keyword in self.CREATION_KEYWORDS['identifier']
        )

        if has_entity and has_status and has_identifier:
            # Extract structured information
            title = self._extract_title(message)
            trigger_time = self._extract_time(message)

            return ReminderMessage(
                message_type=ReminderMessageType.CREATION,
                original_text=message,
                reminder_title=title,
                trigger_time=trigger_time
            )

        return None

    def _is_general_reminder(self, message: str) -> bool:
        """
        Check if message is generally related to reminders.

        Args:
            message: The message to check

        Returns:
            True if message contains reminder-related keywords
        """
        message_lower = message.lower()
        return any(
            keyword in message_lower
            for keyword in self.GENERAL_KEYWORDS
        )

    def _is_error_message(self, message: str) -> bool:
        """
        Check if message indicates an error or problem.

        Args:
            message: The message to check

        Returns:
            True if message contains error indicators
        """
        return bool(self.ERROR_PATTERN.search(message))

    def _extract_title(self, message: str) -> Optional[str]:
        """
        Extract reminder title/content from structured message.

        Args:
            message: The message to parse

        Returns:
            Extracted title or None
        """
        # Try to find title/content pattern
        match = self.TITLE_PATTERN.search(message)
        if match:
            title = match.group(1).strip()
            # Only return if it's substantial (avoid very short matches)
            if len(title) > 3:
                return title
        return None

    def _extract_time(self, message: str) -> Optional[str]:
        """
        Extract trigger time from structured message.

        Args:
            message: The message to parse

        Returns:
            Extracted time string or None
        """
        match = self.TIME_PATTERN.search(message)
        if match:
            time_str = match.group(1).strip()
            # Extract just the time portion if it contains extra info
            time_parts = time_str.split()
            if time_parts:
                return time_parts[0]
        return None

    def format_notification(self, parsed: ReminderMessage) -> str:
        """
        Format a notification message for display.

        Args:
            parsed: Parsed reminder message

        Returns:
            Formatted notification text
        """
        if parsed.message_type != ReminderMessageType.NOTIFICATION:
            raise ValueError("Can only format NOTIFICATION type messages")

        return parsed.reminder_content or parsed.original_text

    def format_creation(self, parsed: ReminderMessage) -> str:
        """
        Format a creation confirmation message for display.

        Args:
            parsed: Parsed reminder message

        Returns:
            Formatted creation confirmation text
        """
        if parsed.message_type != ReminderMessageType.CREATION:
            raise ValueError("Can only format CREATION type messages")

        # Build concise confirmation message
        if parsed.reminder_title:
            if parsed.trigger_time:
                return f"✅ Rappel créé : \"{parsed.reminder_title}\" pour {parsed.trigger_time}"
            else:
                return f"✅ Rappel créé : \"{parsed.reminder_title}\""

        # Fallback if we couldn't extract details
        return "✅ Rappel créé avec succès"

    def format_general(self, parsed: ReminderMessage) -> str:
        """
        Format a general reminder-related message for display.

        Args:
            parsed: Parsed reminder message

        Returns:
            Formatted general response text
        """
        if parsed.message_type != ReminderMessageType.GENERAL:
            raise ValueError("Can only format GENERAL type messages")

        # Provide context-appropriate response
        if parsed.is_error:
            return "Le système de rappels rencontre des difficultés. Utilise une alarme téléphone comme alternative."
        else:
            return "Rappel noté."
