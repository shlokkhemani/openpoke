"""Context-window monitoring and compression notices."""

from __future__ import annotations

import pytest

from server.services import context_monitor as cm


@pytest.fixture(autouse=True)
def clean_state(monkeypatch):
    cm.reset()
    monkeypatch.delenv("OPENPOKE_DEBUG_CONTEXT", raising=False)
    monkeypatch.delenv("LLM_CONTEXT_TOKENS", raising=False)
    yield
    cm.reset()


# --------------------------------------------------------------------------
# Thresholds
# --------------------------------------------------------------------------

def test_usage_below_eighty_percent_is_ok() -> None:
    report = cm.measure("agent:a", 100_000)  # 76% of 131072

    assert report.level == "ok"
    assert cm.observe(report) is None


def test_eighty_percent_crossing_warns() -> None:
    report = cm.measure("agent:a", 104_858)  # just over 80% of 131072

    assert report.level == "warn"
    notice = cm.observe(report)
    assert notice is not None
    assert "80% full" in notice


def test_exactly_eighty_percent_warns() -> None:
    """The boundary itself must warn, not only values above it."""
    window = cm.context_window_tokens()
    exact = (window * 80 + 99) // 100  # smallest int that reaches 80%

    report = cm.measure("agent:a", exact)

    assert report.used_tokens * 100 >= report.window_tokens * 80
    assert report.level == "warn"


def test_ninety_five_percent_is_critical() -> None:
    report = cm.measure("agent:a", int(131_072 * 0.96))

    assert report.level == "critical"
    notice = cm.observe(report)
    assert "tokens remain" in notice
    assert "may fail" in notice


def test_window_comes_from_env(monkeypatch) -> None:
    monkeypatch.setenv("LLM_CONTEXT_TOKENS", "8192")

    report = cm.measure("agent:a", 7000)

    assert report.window_tokens == 8192
    assert report.level == "warn", "7000/8192 is 85%"


def test_invalid_env_falls_back_to_default(monkeypatch) -> None:
    monkeypatch.setenv("LLM_CONTEXT_TOKENS", "not-a-number")

    assert cm.context_window_tokens() == 131072


# --------------------------------------------------------------------------
# Notify once per level
# --------------------------------------------------------------------------

def test_warning_is_emitted_only_once_per_level() -> None:
    report = cm.measure("agent:a", int(131_072 * 0.82))

    assert cm.observe(report) is not None
    assert cm.observe(report) is None, "must not repeat every turn"


def test_escalating_to_critical_emits_again() -> None:
    cm.observe(cm.measure("agent:a", int(131_072 * 0.82)))
    notice = cm.observe(cm.measure("agent:a", int(131_072 * 0.97)))

    assert notice is not None
    assert "may fail" in notice


def test_labels_are_tracked_separately() -> None:
    assert cm.observe(cm.measure("agent:a", int(131_072 * 0.82))) is not None
    assert cm.observe(cm.measure("agent:b", int(131_072 * 0.82))) is not None


# --------------------------------------------------------------------------
# Usage extraction
# --------------------------------------------------------------------------

def test_report_from_usage_counts_prompt_and_completion() -> None:
    report = cm.report_from_usage(
        "agent:a", {"prompt_tokens": 100, "completion_tokens": 50}
    )

    assert report is not None
    assert report.used_tokens == 150


def test_report_from_usage_handles_missing_usage() -> None:
    assert cm.report_from_usage("agent:a", None) is None
    assert cm.report_from_usage("agent:a", {}) is None
    assert cm.report_from_usage("agent:a", {"prompt_tokens": "bad"}) is None


# --------------------------------------------------------------------------
# Debug flag
# --------------------------------------------------------------------------

def test_debug_flag_off_by_default() -> None:
    assert cm.debug_enabled() is False


@pytest.mark.parametrize("value", ["1", "true", "YES", "on"])
def test_debug_flag_accepts_common_values(monkeypatch, value) -> None:
    monkeypatch.setenv("OPENPOKE_DEBUG_CONTEXT", value)

    assert cm.debug_enabled() is True


def test_debug_flag_rejects_other_values(monkeypatch) -> None:
    monkeypatch.setenv("OPENPOKE_DEBUG_CONTEXT", "0")

    assert cm.debug_enabled() is False


# --------------------------------------------------------------------------
# Describe
# --------------------------------------------------------------------------

def test_describe_reports_percentage_and_remaining() -> None:
    report = cm.measure("agent:Email", int(131_072 * 0.85))

    text = cm.describe(report)

    assert "85% full" in text
    assert "agent:Email" in text
    assert "131,072 tokens" in text
