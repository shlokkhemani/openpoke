"""Integrity of a built case set: verify it against MANIFEST.json, freeze it, load it for grading.

Every grading/run entry point (``routing`` and later layers) must load cases through
``load_frozen_cases`` so results are always graded against the reviewed, unmodified set.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any, Optional

from evals.schema import Case, load_cases, validate_cases
from evals.world.generate import WORLD_PATH

V1_DIR = Path(__file__).parent / "cases" / "v1"
V2_DIR = Path(__file__).parent / "cases" / "v2"
CASES_DIR = V2_DIR  # default case set for runners and graders: v2 since 2026-11-09 (Task 16); v1 kept for regrading old runs
FROZEN_ON = "2026-11-07"
_IGNORED = {"MANIFEST.json"}


class CaseSetError(Exception):
    """The case set is missing, altered, or not frozen."""


def sha256_file(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_manifest(case_dir: Path) -> dict[str, Any] | None:
    path = Path(case_dir) / "MANIFEST.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def is_frozen(case_dir: Path) -> bool:
    m = read_manifest(case_dir)
    return bool(m and m.get("frozen") is True)


def verify_case_set(case_dir: Path, world_path: Path = WORLD_PATH) -> list[str]:
    """Problems between the directory and its MANIFEST (empty list = intact)."""
    case_dir = Path(case_dir)
    manifest = read_manifest(case_dir)
    if manifest is None:
        return [f"{case_dir}: MANIFEST.json is missing"]
    problems: list[str] = []
    listed = set()
    for e in manifest["cases"]:
        listed.add(e["file"])
        path = case_dir / e["file"]
        if not path.exists():
            problems.append(f"{e['file']}: listed in MANIFEST but missing")
        elif sha256_file(path) != e["sha256"]:
            problems.append(f"{e['file']}: sha256 differs from MANIFEST (file was modified)")
    for p in sorted(case_dir.glob("*.json")):
        if p.name not in listed and p.name not in _IGNORED:
            problems.append(f"{p.name}: not listed in MANIFEST")
    if sha256_file(world_path) != manifest.get("world_sha256"):
        problems.append(f"world sha256 differs from MANIFEST ({world_path})")
    return problems


def freeze_case_set(case_dir: Path, world_path: Path = WORLD_PATH, *, frozen_on: Optional[str] = None) -> dict[str, Any]:
    """Mark a verified, valid set as frozen in its MANIFEST (idempotent). Raises CaseSetError otherwise."""
    case_dir = Path(case_dir)
    problems = verify_case_set(case_dir, world_path)
    if not problems:
        problems = validate_cases(load_cases(case_dir))
    if problems:
        raise CaseSetError("cannot freeze:\n" + "\n".join(problems))
    manifest = read_manifest(case_dir)
    manifest["frozen"] = True
    manifest["frozen_on"] = manifest.get("frozen_on", frozen_on or FROZEN_ON)
    (case_dir / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return manifest


def load_frozen_cases(case_dir: Path, world_path: Path = WORLD_PATH) -> list[Case]:
    """The only way graders and runners load cases: refuses a modified or unfrozen set."""
    problems = verify_case_set(case_dir, world_path)
    if not problems and not is_frozen(case_dir):
        problems = [f"{case_dir}: case set is not frozen (run: python -m evals.run freeze-cases)"]
    if problems:
        raise CaseSetError("case set rejected:\n" + "\n".join(problems))
    return load_cases(case_dir)
