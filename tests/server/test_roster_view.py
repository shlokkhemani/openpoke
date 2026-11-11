"""Task 9: candidate rendering, legacy/ids roster blocks, legacy tool schemas, prompt split."""

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from server.agents.interaction_agent import agent as ia_agent
from server.services.agents.store import AgentRecord, ContactRecord
from server.services.triggers.models import TriggerRecord

IA_DIR = Path("server/agents/interaction_agent")

T_CREATED = datetime(2026, 10, 20, 9, 0, tzinfo=timezone.utc)
T_ACTIVE = datetime(2026, 11, 2, 15, 30, tzinfo=timezone.utc)

# sha256 of json.dumps(TOOL_SCHEMAS, sort_keys=True) at dbb79c8 (computed from
# `git show dbb79c8:server/agents/interaction_agent/tools.py`).
LEGACY_TOOL_SCHEMAS_SHA256 = "3d957311ef46de6c7f5f2fc8eb173c4c213e7d45330c5ddf90f39a720b20b5bc"
# Same source, json.dumps(TOOL_SCHEMAS) WITHOUT sort_keys: pins key and list order too.
LEGACY_TOOL_SCHEMAS_ORDERED_SHA256 = "f4d7dd0edb758224dc49f605aa98fc6cf055e02c1dcad6b496bdd0875afa5e58"
# Names composition (system_prompt.md + prompt_tools_names.md) as pinned at Task F5 (was dbb79c8:
# a0ced981... stripped, fd36a3b1... raw): sha256 after .strip() (P2-R10) and with a trailing newline.
NAMES_PROMPT_STRIPPED_SHA256 = "e92328a1179e65d82c119d8f7d37a8eabd48359aaa91c4454cbebbc2d429694e"
NAMES_PROMPT_RAW_SHA256 = "79d19f1f1f4b1b01cec5b19ab8228b9246652262acb5ba077f385c6ee962bae8"
LEGACY_PROMPT_SHA256 = "d8257b89da9fcb47eaf980b1f9a097c8e147c45196e569e13303c04ec9a1da37"
OLD_REUSE_LINE = "Don't worry if the agent name is unrelated"


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def trigger(tid, payload, rrule=None, start_time=None, status="active"):
    return TriggerRecord(
        id=tid, agent_id="ag_chen0001", payload=payload, start_time=start_time,
        recurrence_rule=rrule, status=status, created_at="2026-10-20T09:00:00Z",
        updated_at="2026-10-20T09:00:00Z",
    )


# --- render_candidate -----------------------------------------------------------------------

def test_candidate_shows_contacts_and_triggers():
    from server.agents.interaction_agent.roster_view import render_candidate

    agent = AgentRecord("ag_chen0001", "Email Alice Chen re offsite",
                        "Drafting the offsite logistics email to Alice Chen.", T_CREATED, T_ACTIVE, T_ACTIVE)
    contacts = [ContactRecord("alice.chen@acme.io", "Alice Chen", "to"),
                ContactRecord("bob.li@acme.io", "Bob Li", "cc")]
    triggers = [
        trigger(1, "Remind Siddharth about the offsite", "RRULE:FREQ=DAILY;BYHOUR=8;BYMINUTE=0"),
        trigger(2, "Old paused nudge", "RRULE:FREQ=DAILY;BYHOUR=9", status="paused"),
        trigger(3, "Send the agenda", start_time="2026-11-05T17:00:00Z"),
    ]
    assert render_candidate(agent, contacts, triggers) == (
        '<agent id="ag_chen0001" name="Email Alice Chen re offsite" last_active="2026-11-02">\n'
        "description: Drafting the offsite logistics email to Alice Chen.\n"
        "contacts: Alice Chen <alice.chen@acme.io>, Bob Li <bob.li@acme.io>\n"
        "trigger: daily at 8am: Remind Siddharth about the offsite (active)\n"
        "trigger: once at 2026-11-05T17:00:00Z: Send the agenda (active)\n"
        "</agent>"
    )


def test_candidate_last_active_falls_back_to_created_and_omits_empty_lines():
    from server.agents.interaction_agent.roster_view import render_candidate

    agent = AgentRecord("ag_new00001", 'Email "Bob" & co', "", T_CREATED, None, None)
    assert render_candidate(agent, [], []) == (
        '<agent id="ag_new00001" name="Email &quot;Bob&quot; &amp; co" last_active="2026-10-20">\n'
        "</agent>"
    )


def test_candidate_weekly_schedule_is_readable():
    from server.agents.interaction_agent.roster_view import render_candidate

    agent = AgentRecord("ag_digest01", "Weekly digest", "Inbox digest.", T_CREATED, T_ACTIVE, None)
    out = render_candidate(agent, [], [trigger(1, "Send digest", "RRULE:FREQ=WEEKLY;BYDAY=MO;BYHOUR=9")])
    assert "trigger: weekly on Monday at 9am: Send digest (active)" in out


# --- roster blocks --------------------------------------------------------------------------

def test_prepare_message_without_roster_block_renders_none():
    out = ia_agent.prepare_message_with_history("hi there ", "<user_message>x</user_message>")
    assert out == [{"role": "user", "content": (
        "<conversation_history>\n<user_message>x</user_message>\n</conversation_history>\n\n"
        "<active_agents>\nNone\n</active_agents>\n\n<new_user_message>\nhi there\n</new_user_message>"
    )}]


def test_prepare_message_uses_given_roster_block():
    out = ia_agent.prepare_message_with_history("done", "", message_type="agent", roster_block="BLOCK")
    assert out[0]["content"] == (
        "<conversation_history>\nNone\n</conversation_history>\n\n"
        "<active_agents>\nBLOCK\n</active_agents>\n\n<new_agent_message>\ndone\n</new_agent_message>"
    )


def test_roster_json_path_is_removed():
    import importlib.util

    import server.services as services
    import server.services.execution as execution
    from server.agents.interaction_agent import runtime as ia_runtime

    assert importlib.util.find_spec("server.services.execution.roster") is None
    # Names are written in pieces so the cleanup grep for the removed names stays empty.
    for module in (services, execution, ia_agent):
        assert not hasattr(module, "get_agent_" + "roster")
    assert not hasattr(ia_agent, "_render_active_" + "agents")
    assert not hasattr(ia_runtime.InteractionAgentRuntime, "_render_" + "roster")


# --- legacy tool schemas --------------------------------------------------------------------

def test_legacy_tool_schemas_pinned_to_dbb79c8():
    from server.agents.interaction_agent.roster_view import legacy_tool_schemas

    assert _sha(json.dumps(legacy_tool_schemas(), sort_keys=True)) == LEGACY_TOOL_SCHEMAS_SHA256
    props = legacy_tool_schemas()[0]["function"]["parameters"]["properties"]
    assert set(props) == {"agent_name", "instructions"}


def test_legacy_tool_schemas_order_pinned_to_dbb79c8():
    from server.agents.interaction_agent.roster_view import legacy_tool_schemas

    assert _sha(json.dumps(legacy_tool_schemas())) == LEGACY_TOOL_SCHEMAS_ORDERED_SHA256


def test_harness_legacy_rules_uses_names_composition():
    # The harness's tools are checked against legacy_tool_schemas() in tests/evals (P2-R9).
    from evals.harness import routing

    assert routing.SYSTEM_PROMPT_RULES == ia_agent.build_system_prompt("names")


# --- prompt split (P2-R5) -------------------------------------------------------------------

def test_names_prompt_is_pinned_at_task_f5():
    names = ia_agent.build_system_prompt("names")
    assert _sha(names) == NAMES_PROMPT_STRIPPED_SHA256
    assert _sha(names + "\n") == NAMES_PROMPT_RAW_SHA256


def test_default_prompt_is_ids():
    assert ia_agent.build_system_prompt() == ia_agent.build_system_prompt("ids")
    assert ia_agent.build_system_prompt("ids") != ia_agent.build_system_prompt("names")


def test_shared_block_identical_in_both_compositions():
    names_block = (IA_DIR / "prompt_tools_names.md").read_text(encoding="utf-8").strip()
    ids_block = (IA_DIR / "prompt_tools_ids.md").read_text(encoding="utf-8").strip()
    names = ia_agent.build_system_prompt("names")
    ids = ia_agent.build_system_prompt("ids")
    assert names.count(names_block) == 1 and ids.count(ids_block) == 1
    assert names_block not in ids and ids_block not in names
    assert names.replace(names_block, "") == ids.replace(ids_block, "")


def test_tool_specific_text_lives_only_in_tool_blocks():
    shared = (IA_DIR / "system_prompt.md").read_text(encoding="utf-8")
    names_block = (IA_DIR / "prompt_tools_names.md").read_text(encoding="utf-8")
    ids_block = (IA_DIR / "prompt_tools_ids.md").read_text(encoding="utf-8")
    assert "`agent_name`" not in shared and "`agent_id`" not in shared
    assert "`agent_name`" in names_block and "`agent_id`" not in names_block
    assert "`agent_name`" not in ids_block


def test_ids_block_states_the_plan_rules():
    ids_block = (IA_DIR / "prompt_tools_ids.md").read_text(encoding="utf-8")
    for phrase in ("`agent_id`", "`name`", "never both", "the same task, or the same person and"):
        assert phrase in ids_block, phrase


# The ids block after Task F3 (deliberate prompt change): the three earlier lines, the reworded "never write an
# email yourself" line and the pronoun line (F2 pinned 54a87503...; R-F1-5 pinned the three-line block at 0e55f9ab...).
IDS_BLOCK_SHA256 = "9f1bfa15579ebc4b0f7e5cd310fa78fef887e58fb671bea5cdced9ea537203ad"
NEVER_WRITE_EMAIL_LINE = (
    "- Never write an email yourself. `send_draft` only shows the user a draft that an agent wrote. To reply to or follow up on an email an agent already handled, send the instructions to that agent's `agent_id`; it writes the reply in that thread. A new email on a new topic needs a new agent, even when an existing agent already emails the same person. Contact addresses on the agent cards are there to help you pick the right agent, not for emailing people directly.\n"
)
PRONOUN_LINE = (
    '- When the user\'s message comes right after an agent\'s message and refers to it with "this", "that" or "it" (e.g. "push this back an hour"), it means that agent: send the request to its `agent_id` without asking which one.\n'
)
OLD_REPLY_PHRASE = "To reply to or follow up on an email, send"


def test_ids_block_drops_the_answer_from_descriptions_line():
    raw = (IA_DIR / "prompt_tools_ids.md").read_bytes()
    text = raw.decode("utf-8")
    assert "answer broad status questions" not in text
    assert "When the active agents come with descriptions" not in text
    assert "answer broad status questions" not in ia_agent.build_system_prompt("ids")
    assert text.endswith(NEVER_WRITE_EMAIL_LINE + PRONOUN_LINE) and len(text.splitlines()) == 5
    assert text.count("\n- ") == 4 and text.startswith("- ")
    for phrase in ("A new email on a new topic needs a new agent", "without asking which one"):
        assert phrase in text and phrase in ia_agent.build_system_prompt("ids")
        assert phrase in ia_agent.build_system_prompt("names")
    assert OLD_REPLY_PHRASE not in text
    assert NEVER_WRITE_EMAIL_LINE.strip() in ia_agent.build_system_prompt("ids")
    assert NEVER_WRITE_EMAIL_LINE.strip() not in ia_agent.build_system_prompt("names")
    assert hashlib.sha256(raw).hexdigest() == IDS_BLOCK_SHA256


def _names_block_from_ids_block(ids_text: str) -> str:
    """Mechanical transform: drop the interface-only line and the agent-cards sentence, then use `agent_name`."""
    lines = ids_text.splitlines(keepends=True)
    assert lines[1].startswith("- Send by `agent_id` to reuse an agent, or by `name` to create one, never both.")
    del lines[1]
    text = "".join(lines)
    cards = " Contact addresses on the agent cards are there to help you pick the right agent, not for emailing people directly."
    assert text.count(cards) == 1
    text = text.replace(cards, "")
    return text.replace("`agent_id`", "`agent_name`").replace("`name`", "`agent_name`")


def test_names_block_is_the_ids_block_with_only_tool_wording_changed():
    ids_text = (IA_DIR / "prompt_tools_ids.md").read_text(encoding="utf-8")
    names_text = (IA_DIR / "prompt_tools_names.md").read_text(encoding="utf-8")
    assert names_text == _names_block_from_ids_block(ids_text)


def test_shared_routing_rules_in_both_compositions():
    for style in ("names", "ids"):
        p = ia_agent.build_system_prompt(style)
        for heading in ("One operation per agent", "People who share a first name", "Broad questions",
                        "Unclear requests", "Never assume and proceed"):
            assert heading in p, (style, heading)


def test_old_reuse_line_absent_from_compositions_present_in_legacy():
    assert OLD_REUSE_LINE not in ia_agent.build_system_prompt("names")
    assert OLD_REUSE_LINE not in ia_agent.build_system_prompt("ids")
    assert OLD_REUSE_LINE in (IA_DIR / "system_prompt_legacy.md").read_text(encoding="utf-8")


def test_system_prompt_legacy_pinned_unchanged():
    # Pin: passes before Task 9 (the file is not touched).
    assert hashlib.sha256((IA_DIR / "system_prompt_legacy.md").read_bytes()).hexdigest() == LEGACY_PROMPT_SHA256
