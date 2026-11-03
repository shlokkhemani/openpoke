"""Save user-visible outcomes and tool evidence for inspection."""
import hashlib
import json


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def visible_conversation(snapshot):
    return [entry for entry in snapshot["conversation"]
            if entry["type"] in {"user_message", "poke_reply"}]


def make_evidence(before, after, messages, first_index):
    previous = before["conversation"]
    if after["conversation"][:len(previous)] != previous:
        raise ValueError("Conversation history changed/reset during the run")
    earlier_events = before["metrics_events"]
    if after["metrics_events"][:len(earlier_events)] != earlier_events:
        raise ValueError("Metrics ledger changed/reset during the run")
    new_events = after["metrics_events"][len(earlier_events):]
    return {
        "version": 1, "first_index": first_index,
        "last_index": first_index + len(messages) - 1,
        "requests": messages,
        "prior_conversation": visible_conversation(before),
        "current_conversation": [entry for entry in after["conversation"][len(previous):]
                                 if entry["type"] in {"user_message", "poke_reply"}],
        "inbox": (before.get("email_state") or {}).get("inbox", []),
        "email_actions": [event for event in new_events if event["event"] == "email_action"],
        "before_state": {"triggers": before["triggers"],
                         "drafts": (before.get("email_state") or {}).get("drafts", [])},
        "after_state": {"triggers": after["triggers"],
                        "drafts": (after.get("email_state") or {}).get("drafts", [])},
        "email_action_logging_complete": before.get("email_state") is not None
                                         and after.get("email_state") is not None,
    }
