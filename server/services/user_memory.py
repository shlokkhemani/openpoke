"""User Memory service for contextual information about the user (Mem0-like)."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from ..logging_config import logger

# PostgreSQL database imports
try:
    from ..database import SessionLocal
    from ..db_models import UserMemory
    _USE_DATABASE = True
except ImportError:
    _USE_DATABASE = False
    logger.warning("Database not available for user memories")


class UserMemoryService:
    """
    Manages contextual memories about the user (relationships, preferences, habits, etc.).

    Similar to Mem0, but optimized for single-user with PostgreSQL backend.
    Memories are injected into system prompt for personalized interactions.
    """

    def __init__(self, user_id: int = 1):
        """Initialize the user memory service."""
        self.user_id = user_id
        self._use_db = _USE_DATABASE

        if self._use_db:
            logger.info("✅ Using PostgreSQL for user_memories storage")
        else:
            logger.warning("⚠️ Database not available for user_memories")

    def add_memory(
        self,
        category: str,
        key: str,
        value: str,
        context: Optional[str] = None,
        confidence: float = 1.0
    ) -> None:
        """
        Add or update a user memory.

        Args:
            category: Category (relationship, preference, work, habit, project)
            key: Unique key within category (e.g., "colleague_theo")
            value: The memory content (e.g., "Théo is a colleague")
            context: Optional additional context
            confidence: Confidence level 0.0-1.0 (default 1.0)
        """
        if not self._use_db:
            logger.warning("Database not available - cannot add memory")
            return

        try:
            db = SessionLocal()
            try:
                # Check if memory already exists
                existing = db.query(UserMemory).filter(
                    UserMemory.user_id == self.user_id,
                    UserMemory.category == category,
                    UserMemory.key == key
                ).first()

                if existing:
                    # Update existing memory
                    existing.value = value
                    existing.context = context
                    existing.confidence = confidence
                    existing.updated_at = datetime.utcnow()
                    db.commit()
                    logger.info(
                        f"💾 Updated memory: {category}/{key}",
                        extra={"category": category, "key": key}
                    )
                else:
                    # Add new memory
                    new_memory = UserMemory(
                        user_id=self.user_id,
                        category=category,
                        key=key,
                        value=value,
                        context=context,
                        confidence=confidence
                    )
                    db.add(new_memory)
                    db.commit()
                    logger.info(
                        f"💾 New memory added: {category}/{key}",
                        extra={"category": category, "key": key, "value": value[:50]}
                    )
            finally:
                db.close()
        except Exception as exc:
            logger.error(f"❌ Failed to add memory: {exc}", exc_info=True)

    def get_memories(
        self,
        category: Optional[str] = None,
        min_confidence: float = 0.0,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get user memories, optionally filtered by category.

        Args:
            category: Optional category filter
            min_confidence: Minimum confidence threshold
            limit: Maximum number of memories to return

        Returns:
            List of memory dictionaries
        """
        if not self._use_db:
            return []

        try:
            db = SessionLocal()
            try:
                query = db.query(UserMemory).filter(
                    UserMemory.user_id == self.user_id,
                    UserMemory.confidence >= min_confidence
                )

                if category:
                    query = query.filter(UserMemory.category == category)

                # Order by last_accessed (most recent first), then confidence
                query = query.order_by(
                    UserMemory.last_accessed.desc().nullslast(),
                    UserMemory.confidence.desc()
                )

                memories = query.limit(limit).all()
                return [memory.to_dict() for memory in memories]
            finally:
                db.close()
        except Exception as exc:
            logger.error(f"❌ Failed to get memories: {exc}")
            return []

    def delete_memory(self, memory_id: int) -> bool:
        """
        Delete a memory by its ID.

        Args:
            memory_id: The ID of the memory to delete

        Returns:
            True if deleted successfully, False otherwise
        """
        if not self._use_db:
            logger.warning("Database not available - cannot delete memory")
            return False

        try:
            db = SessionLocal()
            try:
                memory = db.query(UserMemory).filter(
                    UserMemory.id == memory_id,
                    UserMemory.user_id == self.user_id
                ).first()

                if not memory:
                    logger.warning(f"⚠️ Memory #{memory_id} not found")
                    return False

                db.delete(memory)
                db.commit()
                logger.info(f"🗑️ Deleted memory #{memory_id}: {memory.category}/{memory.key}")
                return True
            finally:
                db.close()
        except Exception as exc:
            logger.error(f"❌ Failed to delete memory: {exc}")
            return False

    def update_access_time(self, memory_ids: List[int]) -> None:
        """
        Update last_accessed timestamp for given memory IDs.
        Used for prioritization in system prompt.

        Args:
            memory_ids: List of memory IDs to update
        """
        if not self._use_db or not memory_ids:
            return

        try:
            db = SessionLocal()
            try:
                now = datetime.utcnow()
                db.query(UserMemory).filter(
                    UserMemory.id.in_(memory_ids),
                    UserMemory.user_id == self.user_id
                ).update(
                    {"last_accessed": now},
                    synchronize_session=False
                )
                db.commit()
            finally:
                db.close()
        except Exception as exc:
            logger.error(f"❌ Failed to update access time: {exc}")

    def format_memories_for_prompt(self, max_memories: int = 5) -> str:
        """
        Format memories for inclusion in system prompt (condensed format).

        Args:
            max_memories: Maximum number of memories to include (default 5)

        Returns:
            Formatted string ready for prompt injection, or empty string if no memories
        """
        memories = self.get_memories(limit=max_memories)

        if not memories:
            return ""

        # Update access time for these memories (they're being used)
        memory_ids = [m["id"] for m in memories]
        self.update_access_time(memory_ids)

        # Group by category for condensed format
        categories: Dict[str, List[str]] = {}
        for memory in memories:
            cat = memory["category"]
            if cat not in categories:
                categories[cat] = []
            categories[cat].append(memory["value"])

        # Build condensed output
        output = ["## 🧠 USER CONTEXT\n"]
        output.append("Important contextual information about the user:\n")

        # Map category to friendly name
        category_names = {
            "relationship": "Relationships",
            "preference": "Preferences",
            "work": "Work Context",
            "habit": "Habits",
            "project": "Current Projects"
        }

        for cat, values in categories.items():
            friendly_name = category_names.get(cat, cat.title())
            output.append(f"**{friendly_name}:** {', '.join(values)}")

        return "\n".join(output)


# Global singleton
_memory_service: Optional[UserMemoryService] = None


def get_user_memory_service(user_id: int = 1) -> UserMemoryService:
    """Get the global user memory service."""
    global _memory_service
    if _memory_service is None:
        _memory_service = UserMemoryService(user_id=user_id)
    return _memory_service
