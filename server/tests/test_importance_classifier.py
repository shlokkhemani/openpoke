"""Importance classifier: tool-call parsing and failure tolerance."""

from __future__ import annotations

import json

import pytest

from server.openrouter_client import OpenRouterError
from server.services.gmail import importance_classifier as classifier
from server.services.gmail.processing import ProcessedEmail
from server.tests.conftest import completion, tool_call


def _email(
    *,
    subject: str = "Security alert",
    sender: str = "no-reply@accounts.google.com",
    body: str = "Your verification code is 448213.",
) -> ProcessedEmail:
    from datetime import datetime, timezone

    return ProcessedEmail(
        id="msg-1",
        thread_id="thread-1",
        query="in:inbox",
        subject=subject,
        sender=sender,
        recipient="user@example.com",
        timestamp=datetime(2026, 11, 19, 22, 0, tzinfo=timezone.utc),
        label_ids=["INBOX"],
        clean_text=body,
        has_attachments=False,
        attachment_count=0,
        attachment_filenames=[],
    )


async def test_important_email_returns_summary(scripted_llm) -> None:
    fake = scripted_llm(
        classifier,
        [
            completion(
                tool_calls=[
                    tool_call(
                        classifier._TOOL_NAME,
                        {"important": True, "summary": "Your OTP arrived; use it within 5 minutes."},
                    )
                ]
            )
        ],
    )

    summary = await classifier.classify_email_importance(_email())

    fake.assert_drained()
    assert summary == "Your OTP arrived; use it within 5 minutes."


async def test_unimportant_email_returns_none(scripted_llm) -> None:
    scripted_llm(
        classifier,
        [completion(tool_calls=[tool_call(classifier._TOOL_NAME, {"important": False})])],
    )

    assert await classifier.classify_email_importance(_email()) is None


async def test_important_without_summary_returns_none(scripted_llm) -> None:
    """A blank summary must not become an empty notification."""
    scripted_llm(
        classifier,
        [completion(tool_calls=[tool_call(classifier._TOOL_NAME, {"important": True, "summary": "   "})])],
    )

    assert await classifier.classify_email_importance(_email()) is None


async def test_important_with_missing_summary_returns_none(scripted_llm) -> None:
    scripted_llm(
        classifier,
        [completion(tool_calls=[tool_call(classifier._TOOL_NAME, {"important": True})])],
    )

    assert await classifier.classify_email_importance(_email()) is None


async def test_arguments_as_raw_json_string_are_parsed(scripted_llm) -> None:
    raw = json.dumps({"important": True, "summary": "Interview moved to Friday."})
    scripted_llm(
        classifier,
        [
            completion(
                tool_calls=[
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": classifier._TOOL_NAME, "arguments": raw},
                    }
                ]
            )
        ],
    )

    assert await classifier.classify_email_importance(_email()) == "Interview moved to Friday."


async def test_invalid_json_arguments_return_none(scripted_llm) -> None:
    scripted_llm(
        classifier,
        [
            completion(
                tool_calls=[
                    {
                        "id": "call_1",
                        "type": "function",
                        "function": {"name": classifier._TOOL_NAME, "arguments": "{broken"},
                    }
                ]
            )
        ],
    )

    assert await classifier.classify_email_importance(_email()) is None


async def test_no_tool_call_returns_none(scripted_llm) -> None:
    scripted_llm(classifier, [completion("This email seems important.")])

    assert await classifier.classify_email_importance(_email()) is None


async def test_wrong_tool_name_is_ignored(scripted_llm) -> None:
    scripted_llm(
        classifier,
        [completion(tool_calls=[tool_call("some_other_tool", {"important": True, "summary": "x"})])],
    )

    assert await classifier.classify_email_importance(_email()) is None


async def test_provider_error_is_swallowed(scripted_llm) -> None:
    """A classifier outage must never break the email watcher."""
    scripted_llm(classifier, [OpenRouterError("OpenRouter request failed (429)")])

    assert await classifier.classify_email_importance(_email()) is None


async def test_prompt_payload_carries_email_evidence(scripted_llm) -> None:
    fake = scripted_llm(
        classifier, [completion(tool_calls=[tool_call(classifier._TOOL_NAME, {"important": False})])]
    )

    await classifier.classify_email_importance(
        _email(subject="This week's deals", sender="shop@example.com", body="50% off everything")
    )

    payload = fake.calls[0]["messages"][0]["content"]
    assert "shop@example.com" in payload
    assert "This week's deals" in payload
    assert "50% off everything" in payload


async def test_otp_and_marketing_pair_differ_in_payload(scripted_llm) -> None:
    fake = scripted_llm(
        classifier,
        [
            completion(tool_calls=[tool_call(classifier._TOOL_NAME, {"important": True, "summary": "otp"})]),
            completion(tool_calls=[tool_call(classifier._TOOL_NAME, {"important": False})]),
        ],
    )

    otp = await classifier.classify_email_importance(_email(body="Your verification code is 448213."))
    marketing = await classifier.classify_email_importance(
        _email(subject="This week's deals", sender="shop@example.com", body="50% off everything")
    )

    fake.assert_drained()
    assert otp == "otp"
    assert marketing is None
    assert "448213" in fake.calls[0]["messages"][0]["content"]
    assert "50% off" in fake.calls[1]["messages"][0]["content"]
