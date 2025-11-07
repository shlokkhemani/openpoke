from server.utils.tool_validation import split_known_tools


def test_split_returns_empty_for_single_valid_tool():
    known = {"gmail_send_email"}
    assert split_known_tools("gmail_send_email", known) == []


def test_split_detects_two_concatenated_tools():
    known = {"gmail_send_email", "calendar_create_event"}
    assert split_known_tools("gmail_send_emailcalendar_create_event", known) == [
        "gmail_send_email",
        "calendar_create_event",
    ]


def test_split_detects_tools_separated_by_delimiters():
    known = {"gmail_send_email", "calendar_create_event"}
    for candidate in [
        "gmail_send_email calendar_create_event",
        "gmail_send_email-calendar_create_event",
        "gmail_send_email+calendar_create_event",
        "gmail_send_email_calendar_create_event",
    ]:
        assert split_known_tools(candidate, known) == [
            "gmail_send_email",
            "calendar_create_event",
        ]


def test_split_returns_empty_when_no_match():
    known = {"gmail_send_email"}
    assert split_known_tools("gmailsendemail", known) == []


def test_split_prefers_longest_match_first():
    known = {"send_message_to_agent", "send_message", "send_draft"}
    # Greedy longest-first should pick the longest prefix "send_message_to_agent" then "send_draft"
    assert split_known_tools("send_message_to_agentsend_draft", known) == [
        "send_message_to_agent",
        "send_draft",
    ]


