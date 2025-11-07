"""
User profile storage using PostgreSQL.

Replaces JSON-based storage with database persistence.
"""

from typing import Dict, Optional

from sqlalchemy.orm import Session

from ..database import SessionLocal
from ..logging_config import logger
from ..db_models import User


class UserProfileDB:
    """
    User profile storage using PostgreSQL.

    Features:
    - True database persistence (survives all deployments)
    - Multi-user ready (telegram_chat_id or web_user_id)
    - ACID transactions
    - Automatic timestamps
    """

    def __init__(self):
        """Initialize UserProfile service."""
        pass

    def _get_or_create_user(self, db: Session, identifier: Optional[str] = None) -> User:
        """
        Get or create the default user.

        For now, we support single-user mode. Later this can be extended
        to multi-user by passing telegram_chat_id or web_user_id.

        Args:
            db: Database session
            identifier: Optional identifier (telegram_chat_id or web_user_id)

        Returns:
            User: The user object
        """
        # For single-user mode, just get or create user with ID=1
        user = db.query(User).filter(User.id == 1).first()

        if not user:
            user = User(id=1)
            db.add(user)
            db.commit()
            db.refresh(user)
            logger.info("✅ Created default user profile in database")

        return user

    def save(self, profile: Dict[str, str]) -> None:
        """
        Save user profile to database.

        Args:
            profile: Dictionary containing user profile data
                Expected keys: userName, birthDate, location, timezone (optional)
        """
        db = SessionLocal()
        try:
            user = self._get_or_create_user(db)

            # Update fields
            user.user_name = profile.get("userName", user.user_name)
            user.birth_date = profile.get("birthDate", user.birth_date)
            user.location = profile.get("location", user.location)

            # Optional timezone
            if "timezone" in profile:
                user.timezone = profile["timezone"]

            db.commit()
            db.refresh(user)

            logger.info(
                "💾 Profile saved to database",
                extra={
                    "user_id": user.id,
                    "user_name": user.user_name,
                    "location": user.location
                }
            )

        except Exception as exc:
            db.rollback()
            logger.error(f"❌ Failed to save profile to database: {exc}")
            raise
        finally:
            db.close()

    def load(self) -> Dict[str, str]:
        """
        Load user profile from database.

        Returns:
            Dictionary with profile data, or empty dict if not found
        """
        db = SessionLocal()
        try:
            user = self._get_or_create_user(db)

            profile = {
                "userName": user.user_name or "",
                "birthDate": user.birth_date or "",
                "location": user.location or "",
                "timezone": user.timezone or "",
            }

            logger.info(
                "📖 Profile loaded from database",
                extra={
                    "user_id": user.id,
                    "has_name": bool(user.user_name),
                    "has_location": bool(user.location)
                }
            )

            return profile

        except Exception as exc:
            logger.error(f"❌ Failed to load profile from database: {exc}")
            return {}
        finally:
            db.close()

    def get_field(self, key: str) -> Optional[str]:
        """
        Get a single field from the profile.

        Args:
            key: Field name to retrieve

        Returns:
            Field value or None if not found
        """
        profile = self.load()
        return profile.get(key)

    def update_field(self, key: str, value: str) -> None:
        """
        Update a single field in the profile.

        Args:
            key: Field name to update
            value: New value
        """
        profile = self.load()
        profile[key] = value
        self.save(profile)

    def clear(self) -> None:
        """Clear the profile."""
        db = SessionLocal()
        try:
            user = db.query(User).filter(User.id == 1).first()
            if user:
                user.user_name = None
                user.birth_date = None
                user.location = None
                user.timezone = None
                db.commit()
                logger.info("✅ Profile cleared from database")
        except Exception as exc:
            db.rollback()
            logger.error(f"❌ Failed to clear profile: {exc}")
            raise
        finally:
            db.close()

    def restore_from_backup(self) -> bool:
        """
        Restore profile from backup.

        Note: With PostgreSQL, we don't need file backups.
        Database has its own backup/restore mechanisms.

        Returns:
            bool: Always returns False (not applicable)
        """
        logger.warning("restore_from_backup called but not applicable with PostgreSQL")
        return False


# Singleton instance
_user_profile: Optional[UserProfileDB] = None


def get_user_profile() -> UserProfileDB:
    """Get the singleton UserProfile instance."""
    global _user_profile
    if _user_profile is None:
        _user_profile = UserProfileDB()
    return _user_profile


__all__ = ["UserProfileDB", "get_user_profile"]
