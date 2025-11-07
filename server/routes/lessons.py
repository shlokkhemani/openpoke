"""Lessons learned API routes for testing and management."""

from typing import List, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from ..services.lessons_learned import get_lessons_service

router = APIRouter(prefix="/lessons", tags=["lessons"])


class AddLessonRequest(BaseModel):
    """Request to add a new lesson."""
    category: str
    problem: str
    solution: str
    context: Optional[str] = None


class LessonResponse(BaseModel):
    """Lesson data response."""
    id: Optional[int] = None
    category: str
    problem: str
    solution: str
    context: Optional[str] = None
    occurrences: int
    learned_at: Optional[str] = None
    last_seen: Optional[str] = None


class LessonsListResponse(BaseModel):
    """Response with list of lessons."""
    ok: bool
    lessons: List[LessonResponse]
    total: int


class LessonAddedResponse(BaseModel):
    """Response after adding a lesson."""
    ok: bool
    message: str


@router.get("/", response_model=LessonsListResponse)
def get_all_lessons(
    category: Optional[str] = None,
    min_occurrences: int = 1
) -> LessonsListResponse:
    """
    Get all lessons learned.

    Query params:
    - category: Filter by category (optional)
    - min_occurrences: Minimum occurrences to include (default: 1)
    """
    service = get_lessons_service()
    lessons = service.get_lessons(category=category, min_occurrences=min_occurrences)

    return LessonsListResponse(
        ok=True,
        lessons=[
            LessonResponse(
                id=lesson.get("id"),
                category=lesson["category"],
                problem=lesson["problem"],
                solution=lesson["solution"],
                context=lesson.get("context"),
                occurrences=lesson.get("occurrences", 1),
                learned_at=lesson.get("learned_at"),
                last_seen=lesson.get("last_seen")
            )
            for lesson in lessons
        ],
        total=len(lessons)
    )


@router.post("/test", response_model=LessonAddedResponse)
def add_test_lesson() -> LessonAddedResponse:
    """
    Add a test lesson to verify PostgreSQL is working.

    This endpoint adds a sample lesson that you can verify in the database.
    """
    service = get_lessons_service()

    service.add_lesson(
        category="test",
        problem="Test de persistance PostgreSQL",
        solution="Vérifier que les lessons sont sauvegardées dans la base de données",
        context="Lesson créée via l'endpoint /api/lessons/test pour tester le système"
    )

    return LessonAddedResponse(
        ok=True,
        message="Test lesson added successfully! Check the lessons_learned table in PostgreSQL."
    )


@router.post("/add", response_model=LessonAddedResponse)
def add_custom_lesson(payload: AddLessonRequest) -> LessonAddedResponse:
    """
    Add a custom lesson manually.

    Use this to add lessons for testing or manual documentation.
    """
    service = get_lessons_service()

    try:
        service.add_lesson(
            category=payload.category,
            problem=payload.problem,
            solution=payload.solution,
            context=payload.context
        )

        return LessonAddedResponse(
            ok=True,
            message=f"Lesson added in category '{payload.category}'"
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


__all__ = ["router"]
