"""
Database models for OpenPoke/Ariel.

SQLAlchemy ORM models for user data, conversation history, etc.
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Column, DateTime, Float, Integer, String, Text
from sqlalchemy.sql import func

from .database import Base


class User(Base):
    """
    User profile model.

    Stores user information for personalization across sessions.
    Single user for now, but extensible to multi-user.
    """

    __tablename__ = "users"

    # Primary key
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # User identifiers
    telegram_chat_id = Column(String(100), unique=True, index=True, nullable=True)
    web_user_id = Column(String(100), unique=True, index=True, nullable=True)

    # Profile information
    user_name = Column(String(200), nullable=True)
    birth_date = Column(String(50), nullable=True)  # Stored as string for flexibility (YYYY-MM-DD)
    location = Column(String(200), nullable=True)
    timezone = Column(String(100), nullable=True)

    # Email connections (from Composio)
    gmail_connected = Column(Boolean, default=False)
    gmail_email = Column(String(255), nullable=True)
    gmail_connection_id = Column(String(255), nullable=True)

    calendar_connected = Column(Boolean, default=False)
    calendar_email = Column(String(255), nullable=True)
    calendar_connection_id = Column(String(255), nullable=True)

    # Metadata
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    last_active_at = Column(DateTime(timezone=True), nullable=True)

    # Preferences (JSON would be better but keeping it simple)
    preferences = Column(Text, nullable=True)  # JSON string for now

    def __repr__(self) -> str:
        return f"<User(id={self.id}, name={self.user_name}, telegram_chat_id={self.telegram_chat_id})>"

    def to_dict(self) -> dict:
        """Convert user model to dictionary."""
        return {
            "id": self.id,
            "telegram_chat_id": self.telegram_chat_id,
            "web_user_id": self.web_user_id,
            "userName": self.user_name,
            "birthDate": self.birth_date,
            "location": self.location,
            "timezone": self.timezone,
            "gmail_connected": self.gmail_connected,
            "gmail_email": self.gmail_email,
            "calendar_connected": self.calendar_connected,
            "calendar_email": self.calendar_email,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_active_at": self.last_active_at.isoformat() if self.last_active_at else None,
        }


class ConversationHistory(Base):
    """
    Conversation history model.

    Stores conversation turns for context and analysis.
    Optional - can be enabled later if needed.
    """

    __tablename__ = "conversation_history"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, index=True, nullable=True)  # Foreign key to users.id

    # Message metadata
    role = Column(String(20), nullable=False)  # "user", "assistant", "system"
    content = Column(Text, nullable=False)

    # Context
    telegram_chat_id = Column(String(100), index=True, nullable=True)
    web_session_id = Column(String(100), index=True, nullable=True)

    # Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<ConversationHistory(id={self.id}, role={self.role}, user_id={self.user_id})>"


class LessonLearned(Base):
    """
    Lessons learned model.

    Stores lessons from errors for continuous improvement.
    Migrated from JSON file to database.
    """

    __tablename__ = "lessons_learned"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)

    # Lesson content
    category = Column(String(100), index=True, nullable=False)
    problem = Column(Text, nullable=False)
    solution = Column(Text, nullable=False)
    context = Column(Text, nullable=True)

    # Tracking
    occurrences = Column(Integer, default=1, nullable=False)
    learned_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self) -> str:
        return f"<LessonLearned(id={self.id}, category={self.category}, occurrences={self.occurrences})>"

    def to_dict(self) -> dict:
        """Convert lesson to dictionary."""
        return {
            "id": self.id,
            "category": self.category,
            "problem": self.problem,
            "solution": self.solution,
            "context": self.context,
            "occurrences": self.occurrences,
            "learned_at": self.learned_at.isoformat() if self.learned_at else None,
            "last_seen": self.last_seen.isoformat() if self.last_seen else None,
        }


class UserMemory(Base):
    """
    User memory model (Mem0-like contextual memory).

    Stores important contextual facts about the user for personalized interactions.
    Examples: relationships, preferences, work context, habits, ongoing projects.
    """

    __tablename__ = "user_memories"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    user_id = Column(Integer, index=True, default=1, nullable=False)  # Foreign key to users.id

    # Memory content
    category = Column(String(50), index=True, nullable=False)  # relationship, preference, work, habit, project
    key = Column(String(200), nullable=False)  # Unique identifier within category (e.g., "colleague_theo")
    value = Column(Text, nullable=False)  # The actual memory content
    context = Column(Text, nullable=True)  # Optional additional context

    # Metadata
    confidence = Column(Float, default=1.0, nullable=False)  # Confidence level (0.0-1.0)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)
    last_accessed = Column(DateTime(timezone=True), nullable=True)  # For prioritization

    def __repr__(self) -> str:
        return f"<UserMemory(id={self.id}, category={self.category}, key={self.key})>"

    def to_dict(self) -> dict:
        """Convert memory to dictionary."""
        return {
            "id": self.id,
            "user_id": self.user_id,
            "category": self.category,
            "key": self.key,
            "value": self.value,
            "context": self.context,
            "confidence": self.confidence,
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_accessed": self.last_accessed.isoformat() if self.last_accessed else None,
        }


__all__ = ["User", "ConversationHistory", "LessonLearned", "UserMemory"]
