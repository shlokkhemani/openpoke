"""Message duplicate detection service with fingerprinting and caching."""

import hashlib
import time
from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Dict, List, Optional

from server.logging_config import logger


@dataclass
class MessageFingerprint:
    """Fingerprint of a message for duplicate detection."""

    content_hash: str
    timestamp: float
    role: str
    normalized_content: str


class DuplicateDetector:
    """
    Efficient duplicate message detector using content hashing and temporal windows.

    Uses an LRU cache of recent messages to avoid loading full transcripts repeatedly.
    Implements message fingerprinting with configurable time windows to detect
    duplicates even when messages arrive in rapid succession.
    """

    def __init__(
        self,
        cache_size: int = 100,
        time_window_seconds: float = 60.0,
        min_content_length: int = 3,
    ) -> None:
        """
        Initialize the duplicate detector.

        Args:
            cache_size: Maximum number of recent messages to cache (LRU eviction)
            time_window_seconds: Time window within which duplicates are detected
            min_content_length: Minimum content length to consider for duplicates
        """
        self.cache_size = cache_size
        self.time_window_seconds = time_window_seconds
        self.min_content_length = min_content_length

        # LRU cache: key = content_hash, value = MessageFingerprint
        self._cache: OrderedDict[str, MessageFingerprint] = OrderedDict()

    def _normalize_content(self, content: str) -> str:
        """
        Normalize message content for comparison.

        Removes leading/trailing whitespace, collapses multiple spaces,
        and converts to lowercase for robust comparison.
        """
        # Strip whitespace and collapse multiple spaces/newlines
        normalized = " ".join(content.strip().split())
        return normalized.lower()

    def _compute_hash(self, content: str) -> str:
        """
        Compute a SHA-256 hash of the normalized message content.

        Uses a fast hash function that's collision-resistant for our use case.
        """
        normalized = self._normalize_content(content)
        return hashlib.sha256(normalized.encode("utf-8")).hexdigest()

    def _extract_message_content(self, message: Any) -> Optional[str]:
        """
        Extract content string from various message formats.

        Handles both dict messages and plain strings.
        """
        if isinstance(message, dict):
            return message.get("content", "")
        elif isinstance(message, str):
            return message
        return None

    def _extract_message_role(self, message: Any) -> str:
        """Extract role from message, defaulting to 'unknown'."""
        if isinstance(message, dict):
            return message.get("role", "unknown")
        return "unknown"

    def _evict_old_entries(self) -> None:
        """Remove cache entries outside the time window."""
        current_time = time.time()
        cutoff_time = current_time - self.time_window_seconds

        # Remove entries older than the time window
        keys_to_remove = [
            key
            for key, fingerprint in self._cache.items()
            if fingerprint.timestamp < cutoff_time
        ]

        for key in keys_to_remove:
            del self._cache[key]

        # Also enforce cache size limit (LRU eviction)
        while len(self._cache) > self.cache_size:
            self._cache.popitem(last=False)  # Remove oldest item

    def _add_to_cache(self, fingerprint: MessageFingerprint) -> None:
        """
        Add a message fingerprint to the cache.

        Updates LRU ordering and evicts old entries.
        """
        # Move to end (most recent) if already exists
        if fingerprint.content_hash in self._cache:
            self._cache.move_to_end(fingerprint.content_hash)
        else:
            self._cache[fingerprint.content_hash] = fingerprint

        # Evict old entries to maintain cache size and time window
        self._evict_old_entries()

    def is_duplicate(
        self,
        message: Any,
        role: Optional[str] = None,
        check_role: bool = True,
    ) -> bool:
        """
        Check if a message is a duplicate of a recent message.

        Args:
            message: Message to check (dict with 'content' or plain string)
            role: Role to match against (if None, extracted from message)
            check_role: Whether to match role in addition to content

        Returns:
            True if message is a duplicate within the time window
        """
        content = self._extract_message_content(message)
        if not content:
            return False

        # Skip very short messages
        if len(content.strip()) < self.min_content_length:
            return False

        content_hash = self._compute_hash(content)
        message_role = role or self._extract_message_role(message)

        # Clean up old entries before checking
        self._evict_old_entries()

        # Check if we have a matching fingerprint in cache
        if content_hash in self._cache:
            cached = self._cache[content_hash]

            # Check role if required
            if check_role and cached.role != message_role:
                return False

            # Check if within time window
            current_time = time.time()
            time_diff = current_time - cached.timestamp

            if time_diff <= self.time_window_seconds:
                logger.warning(
                    "Duplicate message detected",
                    extra={
                        "role": message_role,
                        "content_preview": content[:100],
                        "time_since_original": f"{time_diff:.2f}s",
                        "content_hash": content_hash[:16],
                    },
                )
                return True

        return False

    def mark_as_seen(self, message: Any, role: Optional[str] = None) -> None:
        """
        Mark a message as seen (add to cache).

        Args:
            message: Message to mark as seen
            role: Role to associate with the message
        """
        content = self._extract_message_content(message)
        if not content:
            return

        # Skip very short messages
        if len(content.strip()) < self.min_content_length:
            return

        content_hash = self._compute_hash(content)
        message_role = role or self._extract_message_role(message)
        normalized = self._normalize_content(content)

        fingerprint = MessageFingerprint(
            content_hash=content_hash,
            timestamp=time.time(),
            role=message_role,
            normalized_content=normalized[:200],  # Store preview for debugging
        )

        self._add_to_cache(fingerprint)

        logger.debug(
            "Message marked as seen",
            extra={
                "role": message_role,
                "content_hash": content_hash[:16],
                "cache_size": len(self._cache),
            },
        )

    def check_and_mark(
        self,
        message: Any,
        role: Optional[str] = None,
        check_role: bool = True,
    ) -> bool:
        """
        Check if message is duplicate and mark it as seen if not.

        Convenience method that combines is_duplicate() and mark_as_seen().

        Args:
            message: Message to check and mark
            role: Role to associate with the message
            check_role: Whether to match role in duplicate check

        Returns:
            True if message is a duplicate
        """
        is_dup = self.is_duplicate(message, role=role, check_role=check_role)
        if not is_dup:
            self.mark_as_seen(message, role=role)
        return is_dup

    def load_from_transcript(self, transcript: List[Dict[str, Any]]) -> None:
        """
        Populate cache from a transcript of messages.

        Useful for initializing the detector with conversation history.
        Only loads recent messages within the time window.

        Args:
            transcript: List of message dicts with 'role' and 'content'
        """
        current_time = time.time()

        # Process messages in reverse to get most recent first
        for message in reversed(transcript):
            content = self._extract_message_content(message)
            if not content or len(content.strip()) < self.min_content_length:
                continue

            role = self._extract_message_role(message)
            content_hash = self._compute_hash(content)
            normalized = self._normalize_content(content)

            # Create fingerprint with current time (we don't have original timestamps)
            # This is a conservative approach - all loaded messages get current timestamp
            fingerprint = MessageFingerprint(
                content_hash=content_hash,
                timestamp=current_time,
                role=role,
                normalized_content=normalized[:200],
            )

            self._add_to_cache(fingerprint)

            # Stop if cache is full
            if len(self._cache) >= self.cache_size:
                break

        logger.info(
            "Duplicate detector initialized from transcript",
            extra={"messages_loaded": len(self._cache)},
        )

    def clear(self) -> None:
        """Clear the entire cache."""
        self._cache.clear()
        logger.debug("Duplicate detector cache cleared")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get statistics about the cache state.

        Returns:
            Dictionary with cache statistics
        """
        current_time = time.time()
        if not self._cache:
            return {
                "cache_size": 0,
                "cache_capacity": self.cache_size,
                "time_window_seconds": self.time_window_seconds,
                "oldest_entry_age": None,
                "newest_entry_age": None,
            }

        timestamps = [fp.timestamp for fp in self._cache.values()]
        oldest = min(timestamps)
        newest = max(timestamps)

        return {
            "cache_size": len(self._cache),
            "cache_capacity": self.cache_size,
            "time_window_seconds": self.time_window_seconds,
            "oldest_entry_age": current_time - oldest,
            "newest_entry_age": current_time - newest,
        }


# Global singleton instance
_duplicate_detector: Optional[DuplicateDetector] = None


def get_duplicate_detector(
    cache_size: int = 100,
    time_window_seconds: float = 60.0,
) -> DuplicateDetector:
    """
    Get or create the global duplicate detector instance.

    Args:
        cache_size: Maximum number of messages to cache
        time_window_seconds: Time window for duplicate detection

    Returns:
        Global DuplicateDetector instance
    """
    global _duplicate_detector

    if _duplicate_detector is None:
        _duplicate_detector = DuplicateDetector(
            cache_size=cache_size,
            time_window_seconds=time_window_seconds,
        )
        logger.info(
            "Duplicate detector initialized",
            extra={
                "cache_size": cache_size,
                "time_window_seconds": time_window_seconds,
            },
        )

    return _duplicate_detector
