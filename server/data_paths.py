"""Resolve runtime data paths, including isolated benchmark runs."""

from __future__ import annotations

import os
from pathlib import Path


DEFAULT_DATA_DIR = Path(__file__).resolve().parent / "data"


def get_data_dir() -> Path:
    """Return the configured runtime data directory."""
    configured = os.getenv("OPENPOKE_DATA_DIR", "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return DEFAULT_DATA_DIR


__all__ = ["DEFAULT_DATA_DIR", "get_data_dir"]
