import asyncio
import hashlib
import json

from evals import run as run_mod
from evals.harness.fake_llm import FakeLLM
from evals.pricing import HAIKU
from evals.schema import load_cases, validate_cases


def test_build_cases_writes_49_files_and_manifest(tmp_path):
    (tmp_path / "stale-001.json").write_text("{}")
    run_mod.build_cases(tmp_path)
    files = sorted(p.name for p in tmp_path.glob("*.json") if p.name != "MANIFEST.json")
    assert len(files) == 49 and "stale-001.json" not in files
    manifest = json.loads((tmp_path / "MANIFEST.json").read_text())
    assert manifest["seed"] == 7
    assert len(manifest["world_sha256"]) == 64
    assert len(manifest["cases"]) == 49
    assert manifest["paraphrase"] is None
    for entry in manifest["cases"]:
        data = (tmp_path / f"{entry['id']}.json").read_bytes()
        assert entry["sha256"] == hashlib.sha256(data).hexdigest()
        assert entry["split"] in ("dev", "test")
    assert {e["split"] for e in manifest["cases"]} == {"dev", "test"}


def test_build_cases_is_reproducible(tmp_path):
    a, b = tmp_path / "a", tmp_path / "b"
    a.mkdir(), b.mkdir()
    run_mod.build_cases(a)
    run_mod.build_cases(b)
    assert (a / "MANIFEST.json").read_bytes() == (b / "MANIFEST.json").read_bytes()


def test_generated_set_validates_after_loading(tmp_path):
    run_mod.build_cases(tmp_path)
    (tmp_path / "MANIFEST.json").unlink()
    assert validate_cases(load_cases(tmp_path)) == []


def test_paraphrase_without_yes_refuses_and_prints_estimate(tmp_path, capsys):
    rc = run_mod.main(["build-cases", "--paraphrase", "--out", str(tmp_path)])
    out = capsys.readouterr().out
    assert rc != 0 and "estimated cost" in out.lower() and "--yes" in out
    assert list(tmp_path.glob("*.json")) == []


def test_paraphrase_with_fake_llm_reports_counts_and_manifest(tmp_path, capsys):
    llm = FakeLLM.text("Could you check on that for me?")  # fails checks for most cases -> reverted
    run_mod.build_cases(tmp_path, paraphrase_cases=True, llm=llm, model=HAIKU)
    out = capsys.readouterr().out
    manifest = json.loads((tmp_path / "MANIFEST.json").read_text())
    stats = manifest["paraphrase"]
    assert stats["kept"] + stats["reverted"] == 38
    assert "kept" in out and "reverted" in out and "retried" in out
    assert stats["prompt_tokens"] == 100 * len(llm.requests)
    (tmp_path / "MANIFEST.json").unlink()
    assert validate_cases(load_cases(tmp_path)) == []


def test_infra_errors_written_only_when_present(tmp_path):
    run_mod.build_cases(tmp_path)
    assert not (tmp_path / "paraphrase_errors.jsonl").exists()
    out2 = tmp_path / "b"
    out2.mkdir()
    run_mod.build_cases(out2, paraphrase_cases=True, llm=FakeLLM.raising(RuntimeError("down")), model=HAIKU)
    lines = (out2 / "paraphrase_errors.jsonl").read_text().strip().splitlines()
    assert len(lines) == 38 and json.loads(lines[0])["case_id"]


def test_load_cases_skips_manifest_in_built_dir(tmp_path):
    run_mod.build_cases(tmp_path)
    assert (tmp_path / "MANIFEST.json").exists()
    assert len(load_cases(tmp_path)) == 49
