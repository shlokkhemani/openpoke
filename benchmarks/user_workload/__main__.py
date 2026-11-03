"""Validate message files, or print a message stream without making API calls."""

import argparse
import json
from pathlib import Path
from .schedule import load_groups


ROOT = Path(__file__).parent
FILES = ("setup_messages", "test_messages")


def load_messages(path: Path) -> list[str]:
    messages = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(messages, list) or not messages:
        raise ValueError(f"{path.name}: expected a nonempty list of user messages")
    if any(not isinstance(message, str) or not message.strip() for message in messages):
        raise ValueError(f"{path.name}: every entry must be a nonempty string")
    if len(set(messages)) != len(messages):
        raise ValueError(f"{path.name}: duplicate messages")
    return messages


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--print", dest="stream", choices=FILES,
                        help="Print messages as JSON strings, one per line")
    args = parser.parse_args()
    workloads = {name: load_messages(ROOT / f"{name}.json") for name in FILES}
    all_messages = [message for messages in workloads.values() for message in messages]
    if len(set(all_messages)) != len(all_messages):
        raise ValueError("Duplicate messages across workload files")
    if len(workloads["test_messages"]) != 20:
        raise ValueError("Expected 20 test messages")
    if args.stream:
        for message in workloads[args.stream]:
            print(json.dumps(message, ensure_ascii=False))
    else:
        for name, messages in workloads.items():
            print(f"{name}.json: {len(messages)} user messages")
            schedule_name = "setup_schedule.json" if name == "setup_messages" else "test_schedule.json"
            groups = load_groups(ROOT / schedule_name, len(messages))
            print(f"  {sum(len(offsets) > 1 for _, offsets in groups)} overlapping message groups")
        print("Valid message files. Fixed workload; agent count is measured during execution.")


if __name__ == "__main__":
    main()
