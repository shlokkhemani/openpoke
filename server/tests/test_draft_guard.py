"""Draft guard: an email cannot be sent without creation and explicit approval."""

from __future__ import annotations

import pytest

from server.services.gmail import draft_guard


@pytest.fixture(autouse=True)
def clean_guard():
    draft_guard.reset()
    yield
    draft_guard.reset()


def test_unknown_draft_cannot_be_sent() -> None:
    error = draft_guard.check_send_allowed("never-created")

    assert error is not None
    assert "not created in this session" in error


def test_created_draft_still_needs_approval() -> None:
    draft_guard.register_created_draft({"draft_id": "d-1"})

    error = draft_guard.check_send_allowed("d-1")

    assert error is not None
    assert "not approved" in error


def test_approved_draft_may_be_sent() -> None:
    draft_guard.register_created_draft({"draft_id": "d-1"})
    assert draft_guard.approve_draft("d-1") is True

    assert draft_guard.check_send_allowed("d-1") is None


def test_cannot_approve_a_draft_that_was_never_created() -> None:
    assert draft_guard.approve_draft("ghost") is False
    assert draft_guard.check_send_allowed("ghost") is not None


def test_a_second_creation_of_the_same_id_clears_approval() -> None:
    """Re-creating a draft invalidates any earlier approval."""
    draft_guard.register_created_draft({"draft_id": "d-1"})
    draft_guard.approve_draft("d-1")
    assert draft_guard.check_send_allowed("d-1") is None

    draft_guard.register_created_draft({"draft_id": "d-1"})

    assert draft_guard.check_send_allowed("d-1") is not None


def test_empty_draft_id_is_rejected() -> None:
    assert draft_guard.check_send_allowed("") is not None
    assert draft_guard.check_send_allowed("   ") is not None


@pytest.mark.parametrize(
    "payload",
    [
        {"draft_id": "a"},
        {"draftId": "a"},
        {"id": "a"},
        {"data": {"id": "a"}},
        {"data": {"draft": {"id": "a"}}},
        [{"id": "a"}],
    ],
)
def test_draft_id_is_found_across_response_shapes(payload) -> None:
    assert draft_guard.register_created_draft(payload) == "a"


def test_response_without_an_id_registers_nothing() -> None:
    assert draft_guard.register_created_draft({"status": "ok"}) is None
    assert draft_guard.was_created("") is False


def test_approval_is_per_draft() -> None:
    draft_guard.register_created_draft({"draft_id": "d-1"})
    draft_guard.register_created_draft({"draft_id": "d-2"})
    draft_guard.approve_draft("d-1")

    assert draft_guard.check_send_allowed("d-1") is None
    assert draft_guard.check_send_allowed("d-2") is not None


def test_reset_clears_everything() -> None:
    draft_guard.register_created_draft({"draft_id": "d-1"})
    draft_guard.approve_draft("d-1")

    draft_guard.reset()

    assert draft_guard.was_created("d-1") is False
    assert draft_guard.check_send_allowed("d-1") is not None
