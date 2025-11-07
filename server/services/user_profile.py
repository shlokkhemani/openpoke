"""
User profile storage - PostgreSQL with JSON fallback.

Automatically uses PostgreSQL if DATABASE_URL is set, otherwise falls back to JSON.
This provides transparent migration path from JSON to database.
"""

import os
from typing import Dict, Optional

from ..logging_config import logger

# Check if DATABASE_URL is available to determine storage backend
_DATABASE_URL = os.getenv("DATABASE_URL")
_use_database = bool(_DATABASE_URL)

if _use_database:
    logger.info("✅ Using PostgreSQL for user profile storage")

    # Import database-backed implementation
    from sqlalchemy.orm import Session

    from ..database import SessionLocal
    from ..db_models import User

    class UserProfile:
        """PostgreSQL-backed user profile storage."""

        def _get_or_create_user(self, db: Session) -> User:
            """Get or create the default user (single-user mode)."""
            user = db.query(User).filter(User.id == 1).first()
            if not user:
                user = User(id=1)
                db.add(user)
                db.commit()
                db.refresh(user)
                logger.info("✅ Created default user in database")
            return user

        def save(self, profile: Dict[str, str]) -> None:
            """Save profile to PostgreSQL."""
            db = SessionLocal()
            try:
                user = self._get_or_create_user(db)
                user.user_name = profile.get("userName", user.user_name)
                user.birth_date = profile.get("birthDate", user.birth_date)
                user.location = profile.get("location", user.location)
                if "timezone" in profile:
                    user.timezone = profile["timezone"]
                db.commit()
                logger.info("💾 Profile saved to PostgreSQL", extra={"user_id": user.id})
            except Exception as exc:
                db.rollback()
                logger.error(f"❌ Failed to save profile: {exc}")
                raise
            finally:
                db.close()

        def load(self) -> Dict[str, str]:
            """Load profile from PostgreSQL."""
            db = SessionLocal()
            try:
                user = self._get_or_create_user(db)
                return {
                    "userName": user.user_name or "",
                    "birthDate": user.birth_date or "",
                    "location": user.location or "",
                    "timezone": user.timezone or "",
                }
            except Exception as exc:
                logger.error(f"❌ Failed to load profile: {exc}")
                return {}
            finally:
                db.close()

        def get_field(self, key: str) -> Optional[str]:
            """Get a single field."""
            profile = self.load()
            return profile.get(key)

        def update_field(self, key: str, value: str) -> None:
            """Update a single field."""
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
                    logger.info("✅ Profile cleared")
            except Exception as exc:
                db.rollback()
                logger.error(f"❌ Failed to clear profile: {exc}")
                raise
            finally:
                db.close()

        def restore_from_backup(self) -> bool:
            """Not applicable with PostgreSQL."""
            logger.warning("restore_from_backup not applicable with PostgreSQL")
            return False

else:
    logger.warning("⚠️ DATABASE_URL not set - using JSON fallback storage")

    # Fallback to JSON-based storage
    from .data_manager import get_data_manager

    PROFILE_FILENAME = "user_profile.json"

    class UserProfile:
        """JSON file-based user profile storage (fallback)."""

        def __init__(self):
            self._data_manager = get_data_manager()

        def save(self, profile: Dict[str, str]) -> None:
            """Save profile to JSON file."""
            self._data_manager.save_json(PROFILE_FILENAME, profile, backup=True)

        def load(self) -> Dict[str, str]:
            """Load profile from JSON file."""
            return self._data_manager.load_json(PROFILE_FILENAME)

        def get_field(self, key: str) -> Optional[str]:
            """Get a single field."""
            profile = self.load()
            return profile.get(key)

        def update_field(self, key: str, value: str) -> None:
            """Update a single field."""
            self._data_manager.update_field(PROFILE_FILENAME, key, value, backup=True)

        def clear(self) -> None:
            """Clear the profile."""
            self._data_manager.delete_file(PROFILE_FILENAME, backup=True)

        def restore_from_backup(self) -> bool:
            """Restore from JSON backup."""
            return self._data_manager.restore_from_backup(PROFILE_FILENAME)


# Singleton instance
_user_profile: Optional[UserProfile] = None


def get_user_profile() -> UserProfile:
    """Get the singleton UserProfile instance."""
    global _user_profile
    if _user_profile is None:
        _user_profile = UserProfile()
    return _user_profile


__all__ = ["UserProfile", "get_user_profile"]
