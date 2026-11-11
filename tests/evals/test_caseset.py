import json
import shutil

import pytest

from evals import run as run_mod
from evals.caseset import CaseSetError, freeze_case_set, load_frozen_cases, verify_case_set
from evals.world.generate import WORLD_PATH


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    d = tmp_path_factory.mktemp("built")
    run_mod.build_cases(d)
    return d


@pytest.fixture
def case_dir(built, tmp_path):
    d = tmp_path / "v1"
    shutil.copytree(built, d)
    return d


def _manifest(d):
    return json.loads((d / "MANIFEST.json").read_text())


def test_freeze_happy_path_and_idempotent(case_dir):
    assert verify_case_set(case_dir) == []
    before = list(_manifest(case_dir))
    m = freeze_case_set(case_dir)
    assert m["frozen"] is True and m["frozen_on"] == "2026-11-07"
    assert list(_manifest(case_dir))[: len(before)] == before  # existing fields kept in order
    snapshot = (case_dir / "MANIFEST.json").read_bytes()
    freeze_case_set(case_dir)
    assert (case_dir / "MANIFEST.json").read_bytes() == snapshot
    assert len(load_frozen_cases(case_dir)) == 49


def test_unfrozen_set_refused(case_dir):
    with pytest.raises(CaseSetError, match="not frozen"):
        load_frozen_cases(case_dir)


def test_tampered_file_named(case_dir):
    freeze_case_set(case_dir)
    p = case_dir / "followup-001.json"
    p.write_text(p.read_text() + " ")
    with pytest.raises(CaseSetError, match="followup-001.json"):
        load_frozen_cases(case_dir)
    with pytest.raises(CaseSetError, match="followup-001.json"):
        freeze_case_set(case_dir)


def test_extra_file_detected(case_dir):
    freeze_case_set(case_dir)
    (case_dir / "extra-001.json").write_text("{}")
    with pytest.raises(CaseSetError, match="extra-001.json: not listed"):
        load_frozen_cases(case_dir)


def test_paraphrase_errors_file_ignored(case_dir):
    (case_dir / "paraphrase_errors.jsonl").write_text("{}\n")
    assert verify_case_set(case_dir) == []


def test_missing_file_detected(case_dir):
    freeze_case_set(case_dir)
    (case_dir / "trigger-001.json").unlink()
    with pytest.raises(CaseSetError, match="trigger-001.json: listed in MANIFEST but missing"):
        load_frozen_cases(case_dir)


def test_missing_manifest(case_dir):
    (case_dir / "MANIFEST.json").unlink()
    assert "MANIFEST.json is missing" in verify_case_set(case_dir)[0]


def test_world_hash_mismatch(case_dir, tmp_path):
    other = tmp_path / "world.json"
    other.write_text(WORLD_PATH.read_text() + " ")
    assert any("world sha256" in p for p in verify_case_set(case_dir, other))
    with pytest.raises(CaseSetError, match="world sha256"):
        freeze_case_set(case_dir, other)


def test_build_cases_refuses_on_frozen_dir(case_dir, capsys):
    freeze_case_set(case_dir)
    snapshot = (case_dir / "MANIFEST.json").read_bytes()
    assert run_mod.main(["build-cases", "--out", str(case_dir)]) != 0
    assert "frozen" in capsys.readouterr().out
    with pytest.raises(CaseSetError):
        run_mod.build_cases(case_dir)
    assert (case_dir / "MANIFEST.json").read_bytes() == snapshot


def test_force_unfreeze_regenerates(case_dir):
    freeze_case_set(case_dir)
    assert run_mod.main(["build-cases", "--out", str(case_dir), "--force-unfreeze"]) == 0
    assert "frozen" not in _manifest(case_dir)


def test_freeze_cases_cli(case_dir, capsys):
    assert run_mod.main(["freeze-cases", "--dir", str(case_dir)]) == 0
    assert _manifest(case_dir)["frozen"] is True
    (case_dir / "followup-001.json").write_text("{}")
    assert run_mod.main(["freeze-cases", "--dir", str(case_dir)]) == 1
