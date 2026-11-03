"""Timing metadata for user messages; never sent to the interaction agent."""
import json
import math
from pathlib import Path


def load_groups(path: Path | None, message_count: int):
    bursts = {} if path is None else json.loads(path.read_text(encoding="utf-8"))
    if path is not None and (not isinstance(bursts, dict) or set(bursts) != {"bursts"}
                             or not isinstance(bursts["bursts"], list)):
        raise ValueError("Schedule must contain a bursts list")
    starts, occupied = {}, set()
    for burst in bursts.get("bursts", []):
        if not isinstance(burst, dict):
            raise ValueError("Each burst must be an object")
        start, offsets = burst.get("start_message"), burst.get("offsets_seconds")
        if not isinstance(start, int) or isinstance(start, bool) or start < 1:
            raise ValueError("Burst start must be a positive 1-based message number")
        if not isinstance(offsets, list) or len(offsets) < 2 or offsets[0] != 0:
            raise ValueError("Burst needs at least two offsets, starting at zero")
        if any(isinstance(v, bool) or not isinstance(v, (int, float))
               or not math.isfinite(v) or v < 0 for v in offsets):
            raise ValueError("Offsets must be finite nonnegative seconds")
        if any(b <= a for a, b in zip(offsets, offsets[1:])):
            raise ValueError("Offsets must increase strictly")
        indices = set(range(start, start + len(offsets)))
        if max(indices) > message_count or indices & occupied:
            raise ValueError("Burst is out of range or overlaps another burst")
        occupied.update(indices)
        starts[start] = offsets
    groups, index = [], 1
    while index <= message_count:
        offsets = starts.get(index, [0])
        groups.append((index, offsets))
        index += len(offsets)
    return groups
