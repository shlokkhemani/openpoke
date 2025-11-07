"""Lessons Learned system for Ariel to improve from mistakes - PostgreSQL with JSON fallback."""

from datetime import datetime
from typing import Any, Dict, List, Optional

from ..logging_config import logger
from .data_manager import get_data_manager

# PostgreSQL database imports
try:
    from ..database import SessionLocal
    from ..db_models import LessonLearned
    _USE_DATABASE = True
except ImportError:
    _USE_DATABASE = False
    logger.warning("Database not available for lessons persistence")

LESSONS_FILENAME = "lessons_learned.json"


class LessonsLearnedService:
    """
    Manages lessons learned from errors and user feedback.

    Uses centralized DataManager for:
    - Automatic backups
    - Atomic writes
    - Data validation
    """

    def __init__(self):
        """Initialize the lessons learned service."""
        self._data_manager = get_data_manager()
        self._use_db = _USE_DATABASE

        if self._use_db:
            logger.info("✅ Using PostgreSQL for lessons_learned storage")
        else:
            logger.warning("⚠️ Using JSON fallback for lessons_learned storage")
            # Initialize file if it doesn't exist
            lessons = self._load_lessons()
            if not lessons:
                self._save_lessons([])

    def _load_lessons(self) -> List[Dict[str, Any]]:
        """Load lessons from PostgreSQL or JSON fallback."""
        if self._use_db:
            try:
                db = SessionLocal()
                try:
                    lessons_db = db.query(LessonLearned).all()
                    return [lesson.to_dict() for lesson in lessons_db]
                finally:
                    db.close()
            except Exception as exc:
                logger.error(f"❌ Failed to load lessons from database: {exc}")
                return []
        else:
            # JSON fallback
            data = self._data_manager.load_json(LESSONS_FILENAME)
            # Support both dict format (with 'lessons' key) and list format
            if isinstance(data, dict):
                return data.get("lessons", [])
            elif isinstance(data, list):
                return data
            return []

    def _save_lessons(self, lessons: List[Dict[str, Any]]) -> None:
        """Save lessons to file."""
        # Wrap in dict for better extensibility
        data = {
            "lessons": lessons,
            "last_updated": datetime.utcnow().isoformat(),
            "total_lessons": len(lessons)
        }
        self._data_manager.save_json(LESSONS_FILENAME, data, backup=True)

    def add_lesson(
        self,
        category: str,
        problem: str,
        solution: str,
        context: Optional[str] = None
    ) -> None:
        """
        Add a new lesson learned.

        Args:
            category: Category of the lesson (e.g., "agent_delegation", "tool_usage")
            problem: Description of the problem encountered
            solution: How to solve or avoid the problem
            context: Optional additional context
        """
        if self._use_db:
            # PostgreSQL mode
            try:
                db = SessionLocal()
                try:
                    # Check if similar lesson exists
                    existing = db.query(LessonLearned).filter(
                        LessonLearned.category == category,
                        LessonLearned.problem == problem
                    ).first()

                    if existing:
                        # Increment occurrences
                        existing.occurrences += 1
                        existing.last_seen = datetime.utcnow()
                        db.commit()
                        logger.info(
                            f"💾 Incremented existing lesson in category '{category}'",
                            extra={"occurrences": existing.occurrences}
                        )
                    else:
                        # Add new lesson
                        new_lesson = LessonLearned(
                            category=category,
                            problem=problem,
                            solution=solution,
                            context=context,
                            occurrences=1
                        )
                        db.add(new_lesson)
                        db.commit()
                        logger.info(
                            f"💾 New lesson learned in category '{category}'",
                            extra={"problem": problem[:100]}
                        )
                finally:
                    db.close()
            except Exception as exc:
                logger.error(f"❌ Failed to add lesson to database: {exc}")
        else:
            # JSON fallback mode
            lessons = self._load_lessons()

            lesson = {
                "category": category,
                "problem": problem,
                "solution": solution,
                "context": context,
                "learned_at": datetime.utcnow().isoformat(),
                "occurrences": 1
            }

            # Check if similar lesson exists
            for existing in lessons:
                if (existing["category"] == category and
                    existing["problem"].lower() == problem.lower()):
                    # Increment occurrences instead of adding duplicate
                    existing["occurrences"] = existing.get("occurrences", 1) + 1
                    existing["last_seen"] = datetime.utcnow().isoformat()
                    logger.info(
                        f"Incremented existing lesson in category '{category}'",
                        extra={"occurrences": existing["occurrences"]}
                    )
                    self._save_lessons(lessons)
                    return

            # Add new lesson
            lessons.append(lesson)
            self._save_lessons(lessons)

            logger.info(
                f"New lesson learned in category '{category}'",
                extra={"problem": problem[:100]}
            )

    def get_lessons(
        self,
        category: Optional[str] = None,
        min_occurrences: int = 1
    ) -> List[Dict[str, Any]]:
        """
        Get lessons, optionally filtered by category.

        Args:
            category: Optional category filter
            min_occurrences: Minimum occurrences to include

        Returns:
            List of lessons matching criteria
        """
        lessons = self._load_lessons()

        filtered = [
            lesson for lesson in lessons
            if lesson.get("occurrences", 1) >= min_occurrences
        ]

        if category:
            filtered = [l for l in filtered if l["category"] == category]

        # Sort by occurrences (most common first)
        filtered.sort(key=lambda x: x.get("occurrences", 1), reverse=True)

        return filtered

    def delete_lesson(self, lesson_id: int) -> bool:
        """
        Delete a lesson by its ID.

        Args:
            lesson_id: The ID of the lesson to delete

        Returns:
            True if deleted successfully, False if lesson not found
        """
        if self._use_db:
            # PostgreSQL mode
            try:
                db = SessionLocal()
                try:
                    lesson = db.query(LessonLearned).filter(LessonLearned.id == lesson_id).first()

                    if not lesson:
                        logger.warning(f"⚠️ Lesson #{lesson_id} not found in database")
                        return False

                    db.delete(lesson)
                    db.commit()
                    logger.info(f"🗑️ Deleted lesson #{lesson_id} from PostgreSQL")
                    return True
                finally:
                    db.close()
            except Exception as exc:
                logger.error(f"❌ Failed to delete lesson from database: {exc}")
                return False
        else:
            # JSON fallback mode
            lessons = self._load_lessons()

            # Find lesson by index (JSON doesn't have IDs, use list index)
            if 0 <= lesson_id < len(lessons):
                deleted_lesson = lessons.pop(lesson_id)
                self._save_lessons(lessons)
                logger.info(f"🗑️ Deleted lesson from JSON: {deleted_lesson.get('problem', '')[:50]}")
                return True
            else:
                logger.warning(f"⚠️ Lesson index {lesson_id} out of range (total: {len(lessons)})")
                return False

    def format_lessons_for_prompt(self, max_lessons: int = 10) -> str:
        """
        Format lessons for inclusion in system prompt.

        Args:
            max_lessons: Maximum number of lessons to include

        Returns:
            Formatted string ready for prompt injection
        """
        lessons = self.get_lessons()

        if not lessons:
            return ""

        # Take top lessons by occurrence
        top_lessons = lessons[:max_lessons]

        output = ["## 📚 LESSONS LEARNED\n"]
        output.append("These are mistakes you've made before. **AVOID REPEATING THEM:**\n")

        for i, lesson in enumerate(top_lessons, 1):
            occurrences = lesson.get("occurrences", 1)
            output.append(f"\n### Lesson {i} ({occurrences}x)")
            output.append(f"**Problem:** {lesson['problem']}")
            output.append(f"**Solution:** {lesson['solution']}")
            if lesson.get("context"):
                output.append(f"**Context:** {lesson['context']}")

        return "\n".join(output)

    def auto_learn_from_error(self, error_type: str, error_message: str) -> None:
        """
        Automatically learn from common error patterns.

        Args:
            error_type: Type of error (e.g., "RuntimeError", "ToolError")
            error_message: Error message
        """
        # Pattern: Tool iteration limit
        if "tool iteration limit" in error_message.lower():
            self.add_lesson(
                category="agent_delegation",
                problem="Atteint la limite d'itérations d'outils sans réponse finale",
                solution="Après la réponse d'un agent, donner IMMÉDIATEMENT une réponse finale en texte plain. Ne PAS rappeler send_message_to_agent.",
                context=f"Error: {error_message[:200]}"
            )

        # Pattern: Duplicate messages
        elif "duplicate" in error_message.lower():
            self.add_lesson(
                category="messaging",
                problem="Envoi de messages dupliqués à l'utilisateur",
                solution="Ne jamais appeler send_message_to_user avec le même texte plusieurs fois. Vérifier si le message a déjà été envoyé.",
                context=f"Error: {error_message[:200]}"
            )

        # Pattern: Agent not responding
        elif "agent" in error_message.lower() and "timeout" in error_message.lower():
            self.add_lesson(
                category="agent_delegation",
                problem="Timeout lors de l'attente d'une réponse d'agent",
                solution="Donner des instructions plus claires et concises aux agents. Si timeout, informer l'utilisateur et continuer.",
                context=f"Error: {error_message[:200]}"
            )


# Global singleton
_lessons_service: Optional[LessonsLearnedService] = None


def get_lessons_service() -> LessonsLearnedService:
    """Get the global lessons learned service."""
    global _lessons_service
    if _lessons_service is None:
        _lessons_service = LessonsLearnedService()
    return _lessons_service
