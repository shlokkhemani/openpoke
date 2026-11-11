"""``evals.inspect_export.export_run``: a run folder -> Inspect AI .eval logs, one per (mode, N)."""
import json
import shutil
import socket
from pathlib import Path

import pytest

from evals import run as run_mod
from evals.inspect_export import export_run
from evals.run_store import read_jsonl
from tests.evals.synthetic_run import write_run

pytest.importorskip("inspect_ai")
from inspect_ai.log import read_eval_log  # noqa: E402

EXP5 = Path("evals/results/20261107T234451Z-exp5-full-dev")
ROWS = [
    ("case-a", "legacy", 10, 0, True, "dispatch", [], None),
    ("case-a", "legacy", 10, 1, False, "none", ["no_dispatch"], None),
    ("case-a", "legacy", 30, 0, True, "dispatch", [], None),
]


@pytest.fixture
def exp5(tmp_path):
    dest = tmp_path / "runs" / EXP5.name
    shutil.copytree(EXP5, dest, ignore=shutil.ignore_patterns("*.v[0-9]*.*"))
    return dest


@pytest.fixture
def synth(tmp_path):
    return write_run(tmp_path / "runs", ROWS)


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    def boom(*args, **kwargs):
        raise AssertionError("export must not touch the network")

    monkeypatch.setattr(socket.socket, "connect", boom)


def samples_of(path):
    return read_eval_log(str(path)).samples


def test_one_eval_file_per_mode_and_n_under_the_run_folder_name(exp5, tmp_path):
    out = tmp_path / "logs"
    paths = export_run(exp5, out)
    assert sorted(p.name for p in paths) == sorted(f"full-N{n}.eval" for n in (10, 30, 100, 300))
    assert all(p.parent == out / exp5.name and p.exists() for p in paths)


def test_sample_count_round_trips_to_grades_rows(exp5, tmp_path):
    grades = read_jsonl(exp5 / "grades.jsonl")
    paths = export_run(exp5, tmp_path / "logs")
    total = 0
    for p in paths:
        n = int(p.stem.split("-N")[1])
        samples = samples_of(p)
        assert len(samples) == sum(1 for g in grades if g["n"] == n)
        total += len(samples)
    assert total == len(grades)


def test_grader_score_matches_passed_and_carries_outcome_and_flags(exp5, tmp_path):
    grades = {(g["case_id"], g["n"], g["run_idx"]): g for g in read_jsonl(exp5 / "grades.jsonl")}
    assert any(not g["passed"] for g in grades.values()) and any(g["flags"] for g in grades.values())
    for p in export_run(exp5, tmp_path / "logs"):
        for s in samples_of(p):
            g = grades[(s.id, s.metadata["N"], s.epoch - 1)]
            sc = s.scores["grader"]
            assert sc.value == ("C" if g["passed"] else "I")
            assert sc.answer == g["outcome_kind"]
            assert sc.explanation == (", ".join(g["flags"]) or None)
            assert sc.metadata["flags"] == g["flags"]
            for k in ("person_ok", "clarify_named_ok", "set_recall", "set_precision", "slots_filled", "slots_total"):
                assert sc.metadata[k] == g[k]
            assert s.metadata["category"] == g["category"] and s.metadata["mode"] == "full"


def test_amb_person_006_is_correct_in_the_regraded_run(exp5, tmp_path):
    p = next(p for p in export_run(exp5, tmp_path / "logs") if p.name == "full-N10.eval")
    mine = [s for s in samples_of(p) if s.id == "amb-person-006"]
    assert sorted(s.epoch for s in mine) == [1, 2, 3]
    assert all(s.scores["grader"].value == "C" for s in mine)


def test_log_spec_and_accuracy_come_from_summary_and_grades(synth, tmp_path):
    log = read_eval_log(str(next(p for p in export_run(synth, tmp_path / "logs") if p.name == "legacy-N10.eval")))
    assert log.eval.task == f"{synth.name}-legacy-N10"
    assert log.eval.model == "test/model-1"
    assert log.eval.created.startswith("2026-11-07T12:00:00")
    assert "synthetic" in json.dumps(log.eval.metadata)
    acc = log.results.scores[0].metrics["accuracy"].value
    assert acc == pytest.approx(1 / 2)


def test_tool_call_name_and_arguments_survive_the_round_trip(synth, tmp_path):
    p = next(p for p in export_run(synth, tmp_path / "logs") if p.name == "legacy-N30.eval")
    s = samples_of(p)[0]
    calls = [tc for m in s.messages if m.role == "assistant" for tc in (m.tool_calls or [])]
    assert len(calls) == 1
    assert calls[0].function == "send_message_to_agent"
    assert calls[0].arguments == {"agent_name": "Mailer", "instructions": "case-a-legacy"}
    assert [m.role for m in s.messages] == ["system", "user", "assistant", "tool", "assistant"]
    assert s.messages[3].tool_call_id == calls[0].id
    assert s.metadata["latency_s"] == 1.5 and s.metadata["round_trips"] == 2
    assert s.metadata["calls"] == [{"name": "send_message_to_agent"}] and s.metadata["error"] is None


def test_real_run_tool_calls_round_trip(exp5, tmp_path):
    seen = 0
    for p in export_run(exp5, tmp_path / "logs"):
        for s in samples_of(p):
            for m in s.messages:
                if m.role == "assistant" and m.tool_calls:
                    for tc in m.tool_calls:
                        assert tc.function and isinstance(tc.arguments, dict)
                        seen += 1
    assert seen > 0


def test_missing_transcript_gives_empty_messages_not_a_crash(tmp_path):
    run = write_run(tmp_path / "runs", ROWS, missing={("case-a", "legacy", 10, 1)})
    p = next(p for p in export_run(run, tmp_path / "logs") if p.name == "legacy-N10.eval")
    by_epoch = {s.epoch: s for s in samples_of(p)}
    assert by_epoch[2].messages == [] and by_epoch[2].metadata["transcript_missing"] is True
    assert by_epoch[2].scores["grader"].value == "I"
    assert len(by_epoch[1].messages) == 5 and not by_epoch[1].metadata.get("transcript_missing")


def test_infra_errors_are_not_samples_and_are_counted_in_log_metadata(tmp_path):
    err = {"case_id": "case-b", "mode": "legacy", "n": 10, "run_idx": 0, "error": "boom"}
    run = write_run(tmp_path / "runs", ROWS, errors=[err, {**err, "run_idx": 1}])
    p = next(p for p in export_run(run, tmp_path / "logs") if p.name == "legacy-N10.eval")
    log = read_eval_log(str(p))
    assert len(log.samples) == 2 and all(s.id == "case-a" for s in log.samples)
    assert "infra_errors" in log.eval.metadata and log.eval.metadata["infra_errors"] == 2


def test_export_does_not_modify_the_run_folder(synth, tmp_path):
    before = {f: f.read_bytes() for f in synth.rglob("*") if f.is_file()}
    export_run(synth, tmp_path / "logs")
    assert {f: f.read_bytes() for f in synth.rglob("*") if f.is_file()} == before


def test_cli_inspect_prints_paths_and_the_view_command(synth, tmp_path, capsys):
    out = tmp_path / "logs"
    assert run_mod.main(["inspect", str(synth), "--out", str(out)]) == 0
    text = capsys.readouterr().out
    assert str(out / synth.name / "legacy-N10.eval") in text
    assert f"inspect view --log-dir {out}" in text


def test_cli_inspect_without_inspect_ai_exits_1_with_the_pip_hint(synth, tmp_path, capsys, monkeypatch):
    import builtins

    real = builtins.__import__

    def fake(name, *a, **kw):
        if name == "inspect_ai" or name.startswith("inspect_ai."):
            raise ImportError("No module named 'inspect_ai'")
        return real(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake)
    assert run_mod.main(["inspect", str(synth), "--out", str(tmp_path / "logs")]) == 1
    assert "pip install inspect_ai==0.3.288" in capsys.readouterr().out
    assert not (tmp_path / "logs").exists() or not list((tmp_path / "logs").rglob("*.eval"))
