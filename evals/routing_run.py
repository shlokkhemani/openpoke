"""The ``routing`` runner: frozen cases through the real IA loop, graded, written to a run folder.

    python -m evals.run routing --modes legacy --sizes 10,300 --split dev --runs 1 \
        [--model <id>] [--cases id1,id2] [--max-cost 35] [--concurrency 4] [--purpose "..."] [--yes]
        [--descriptions regen|world] [--embedder fastembed|hashing]

Plan: every (case, mode, N, run) is one *case-run*, ordered by case id, then mode, size and run as
given. Each case-run calls a mode runner (``MODE_RUNNERS``: ``legacy``, ``legacy_rules``, ``full``, ``hybrid``) with an
LLM wrapper that forces ``--model`` (the IA runtime always asks for ``interaction_agent_model``),
supplies the API key and captures the conversation for the transcript.

- **Infra errors** (``RunRecord.error`` set: transport errors, timeouts, malformed tool calls, the
  iteration limit) are retried once. If the retry errors too, the case-run goes to
  ``errors.jsonl`` and is not graded: it is excluded from every pass rate and counted separately,
  tallied by error kind (``run_store.error_kind``). Any other exception in a case-run (from the
  mode runner, ``roster_for`` or ``grade``) becomes an errored record with the prefix
  ``RunnerError:`` instead of aborting the run.
- **Incremental persistence.** Each case-run's record (or error), grade and transcript are written
  as soon as it completes (``run_store.RunWriter``); the jsonl files are rewritten in plan order at
  the end. ``summary.json``, ``report.md`` and the ``EXPERIMENTS.md`` line come at the end.
- **Cost cap.** Actual spend is summed from the ``usage`` of every attempt; an attempt that got a
  response with no ``usage`` block is also charged its estimate (with a warning). A case-run (or
  a retry) is not started if actual spend + the reservations of case-runs in flight + its own
  reservation (estimate × ``RESERVATION_MARGIN``) would exceed ``max_cost``; from then on every
  remaining case-run is skipped and counted.
- **Counts** of infra errors and skips are of paid case-runs; ``errors.jsonl`` lists each once.
- **Descriptions** (``full`` and ``hybrid``). ``--descriptions regen`` (default) shows the agent cards with
  the regenerated descriptions of ``regen_descriptions.OUT_PATH``, loaded once per run; a missing,
  unparseable or empty file is an error before any estimate or spend, never a fallback.
  ``--descriptions world`` uses each agent's own world description. The source, the file's sha256
  and its coverage of the world's agents go into ``summary.json`` and ``report.md``.
- **Embedder** (``hybrid``). ``--embedder fastembed`` (default, as in production) or ``hashing`` (offline, for
  tests); one ``CachedEmbedder`` is shared by the whole run and recorded in ``summary.json``.
- **Secrets.** Transcripts keep only the system prompt, the message list and the tool names. Every
  persisted object is scrubbed of ``api_key`` / header keys and of the key's value.

Output, in ``<out_root>/<UTC timestamp>-<purpose slug>/``: ``records.jsonl`` (graded records),
``grades.jsonl``, ``errors.jsonl``, ``transcripts/<case>-<mode>-<n>-<run>.json``, ``summary.json``
and ``report.md`` (``evals.report_run``); one line is appended to ``<out_root>/EXPERIMENTS.md``.
"""
from __future__ import annotations

import asyncio
import functools
import json
import re
import subprocess
import warnings
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Awaitable, Callable, Optional

from evals.caseset import load_frozen_cases, read_manifest, sha256_file
from evals.caseset import CASES_DIR
from evals.grading import Grade, RunRecord, grade
from evals.harness import routing
from evals.harness.load_world import CachedEmbedder
from evals.harness.full_roster import description_coverage
from evals.pricing import HAIKU, PRICES, estimate_cost
from evals.report_run import append_experiment, render_report
from evals.run_store import RUNNER_ERROR, RunWriter, error_tables, grade_row, grade_tables, scrub
from evals.schema import Case
from evals.world.roster import World, roster_for

RESULTS_DIR = Path(__file__).parent / "results"
DEFAULT_MAX_COST = 35.0
DEFAULT_CONCURRENCY = 4
SPLITS = ("dev", "test", "all")
ATTEMPT_TIMEOUT_S = 300.0  # one whole IA loop; each HTTP call already has a 60 s timeout

# Prompt tokens per case-run (one whole IA loop, all round trips), piecewise linear in N.
# ``legacy`` is measured: experiment 1 (20261107T095436Z-milestone-a-..., Haiku, 16 dev cases) averaged
# 11,870 prompt tokens per case-run at N=10 and 20,320 at N=300; N=30 / 100 interpolate on roster size.
# ``full`` is measured too: experiment 5 (20261107T234451Z-exp5-full-dev, Haiku, 16 dev cases x 3 runs per N)
# averaged 18,009 / 24,936 / 51,878 / 117,473 prompt tokens per case-run at N=10 / 30 / 100 / 300.
# ``hybrid`` shows at most 20 cards, so it is the ``full`` estimate at min(N, 20) times a search factor.
# Measured in the Task 14 smoke (20261109T194841Z-task-14-smoke-legacy-full-hybrid-on-the, Haiku, dev):
# 18,096 / 22,191 prompt tokens per case-run at N=10 / 30 against ``full``@min(N, 20) of 18,009 / 21,472,
# i.e. x1.00-1.03 (it searched in 1 of 32 case-runs). x1.1 leaves headroom, since searches should be more common
# at N >= 100. PROVISIONAL: recalibrate from the Task 15 dev-check records (N = 100 / 300).
MEASURED_OVER_ESTIMATED = 1.6  # experiment 1: $0.0610 measured / $0.0376 estimated (kept for the pinned test)
_ROUGH_PER_TURN: dict[str, dict[int, int]] = {}  # no mode is estimated from the scope §7 table any more
HYBRID_SEARCH_FACTOR = 1.1
HYBRID_SHOWN = 20
PROMPT_TOKENS_PER_CASE_RUN: dict[str, dict[int, int]] = {
    "legacy": {10: 11900, 300: 20300},
    "full": {10: 18009, 30: 24936, 100: 51878, 300: 117473},  # measured: experiment 5
}
# ``legacy_rules`` = ``legacy`` plus the routing rules (~2.7k characters ≈ 700 tokens per call) over
# ~2.5 round trips (fan-out on broad questions may add one). PROVISIONAL until it has run.
_RULES_EXTRA_TOKENS = 1750
PROMPT_TOKENS_PER_CASE_RUN["legacy_rules"] = {
    n: t + _RULES_EXTRA_TOKENS for n, t in PROMPT_TOKENS_PER_CASE_RUN["legacy"].items()}
COMPLETION_TOKENS_PER_CASE_RUN = 600  # experiment 1: 580 (N=10) and 603 (N=300) per case-run
RESERVATION_MARGIN = 1.2  # the cap reserves this multiple of a case-run's estimate while it is in flight

ModeRunner = Callable[..., Awaitable[RunRecord]]  # (case, world, mode, n, llm, run_idx) -> RunRecord
MODE_RUNNERS: dict[str, ModeRunner] = {"legacy": routing.run_case, "legacy_rules": routing.run_case,
                                       "full": routing.run_case, "hybrid": routing.run_case}
EMBEDDERS = ("fastembed", "hashing")
DESCRIBED_MODES = ("full", "hybrid")  # modes whose cards show descriptions
DESCRIPTION_SOURCES = ("regen", "world")
REGEN_COMMAND = "python -m evals.run regen-descriptions"



def default_llm() -> Callable[..., Awaitable[dict]]:
    """The real chat-completion call (imported lazily so tests never load it by accident)."""
    from server.openrouter_client import request_chat_completion
    return request_chat_completion


def configured_api_key() -> Optional[str]:
    from server.config import get_settings
    return get_settings().openrouter_api_key


def default_model() -> str:
    from server.config import get_settings
    return get_settings().eval_dev_model


@dataclass
class RoutingConfig:
    modes: list[str]
    sizes: list[int]
    split: str = "dev"
    runs: int = 1
    model: str = HAIKU
    case_ids: Optional[list[str]] = None
    max_cost: float = DEFAULT_MAX_COST
    purpose: str = ""
    concurrency: int = DEFAULT_CONCURRENCY
    command: str = ""
    descriptions: str = "regen"  # ``full`` and ``hybrid`` cards: "regen" or "world"
    embedder: str = "fastembed"  # ``hybrid`` only


@dataclass(frozen=True)
class DescriptionSource:
    """What ``full`` / ``hybrid`` cards show as descriptions: the regenerated map, or ``{}`` (world's own)."""
    source: str
    descriptions: dict[str, str]
    sha256: Optional[str] = None  # of the regen file


def load_descriptions(path: Path) -> dict[str, str]:
    """The ``descriptions`` map of a ``regen-descriptions`` output file; ValueError if unusable."""
    path = Path(path)

    def fail(why: str) -> ValueError:
        return ValueError(f"a run with agent cards needs regenerated descriptions, but {path} {why}. "
                          f"Run `{REGEN_COMMAND}` first, or pass --descriptions world.")

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise fail("does not exist") from None
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise fail(f"cannot be read as JSON ({type(exc).__name__}: {exc})") from None
    descriptions = data.get("descriptions") if isinstance(data, dict) else None
    if not isinstance(descriptions, dict) or not descriptions:
        raise fail("has no descriptions")
    if not all(isinstance(k, str) and isinstance(v, str) for k, v in descriptions.items()):
        raise fail("has a description that is not a string")
    return descriptions


def resolve_descriptions(config: RoutingConfig) -> Optional[DescriptionSource]:
    """The run's descriptions (None when no card mode is among the modes); loads the regen file once."""
    if config.descriptions not in DESCRIPTION_SOURCES:
        raise ValueError(f"unknown descriptions source {config.descriptions!r} "
                         f"(choose from {', '.join(DESCRIPTION_SOURCES)})")
    if not any(m in DESCRIBED_MODES for m in config.modes):
        return None
    if config.descriptions == "world":
        return DescriptionSource("world", {})
    from evals import regen_descriptions

    path = Path(regen_descriptions.OUT_PATH)
    descriptions = load_descriptions(path)
    return DescriptionSource("regen", descriptions, sha256_file(path))


def bind_descriptions(runners: dict[str, ModeRunner], desc: Optional[DescriptionSource]) -> dict[str, ModeRunner]:
    """The run's runners, with the card modes given the run's descriptions."""
    if desc is None:
        return dict(runners)
    return {**runners, **{m: functools.partial(runners[m], descriptions=desc.descriptions)
                          for m in DESCRIBED_MODES if m in runners}}


def make_embedder(name: str) -> CachedEmbedder:
    """One shared, caching embedder: ``fastembed`` (production's) or ``hashing`` (offline)."""
    if name not in EMBEDDERS:
        raise ValueError(f"unknown embedder {name!r} (choose from {', '.join(EMBEDDERS)})")
    from server.services.agents import embeddings

    return CachedEmbedder(embeddings.HashingEmbedder() if name == "hashing" else embeddings.FastEmbedder())


def bind_embedder(runners: dict[str, ModeRunner], embedder: CachedEmbedder) -> dict[str, ModeRunner]:
    """The run's runners, with ``hybrid`` given the run's embedder."""
    if "hybrid" not in runners:
        return dict(runners)
    return {**runners, "hybrid": functools.partial(runners["hybrid"], embedder=embedder)}


def descriptions_summary(desc: DescriptionSource, world: World) -> dict[str, Any]:
    covered, total = description_coverage(world.agents, desc.descriptions)
    return {"source": desc.source, "sha256": desc.sha256,
            "covered": covered if desc.source == "regen" else None, "total": total}


@dataclass(frozen=True)
class CaseRun:
    case: Case
    mode: str
    n: int
    run_idx: int


@dataclass
class Estimate:
    case_runs: int  # paid case-runs
    prompt_tokens: int
    completion_tokens: int
    usd: float


# ---------------------------------------------------------------- planning and estimates

def load_run_cases(config: RoutingConfig, cases_dir: Path = CASES_DIR) -> list[Case]:
    """Frozen cases of ``config.split`` (optionally only ``config.case_ids``), sorted by id."""
    if config.split not in SPLITS:
        raise ValueError(f"unknown split {config.split!r} (choose from {', '.join(SPLITS)})")
    cases = sorted(load_frozen_cases(Path(cases_dir)), key=lambda c: c.id)
    in_split = [c for c in cases if config.split == "all" or c.split == config.split]
    if config.case_ids:
        by_id = {c.id: c for c in in_split}
        missing = [i for i in config.case_ids if i not in by_id]
        if missing:
            raise ValueError(f"case(s) not in split {config.split!r}: {', '.join(missing)}")
        in_split = [c for c in in_split if c.id in set(config.case_ids)]
    return in_split


def check_modes(modes: list[str], runners: dict[str, ModeRunner]) -> None:
    missing = [m for m in modes if m not in runners]
    if missing:
        raise ValueError(f"mode not implemented yet: {', '.join(missing)} (available: {', '.join(runners)})")


def plan(config: RoutingConfig, cases: list[Case]) -> list[CaseRun]:
    return [CaseRun(c, m, n, r) for c in cases for m in config.modes for n in config.sizes
            for r in range(config.runs)]


def prompt_tokens_per_case_run(mode: str, n: int) -> int:
    """Estimated prompt tokens of one case-run of ``mode`` at roster size ``n`` (piecewise linear)."""
    if mode == "hybrid":
        return round(prompt_tokens_per_case_run("full", min(n, HYBRID_SHOWN)) * HYBRID_SEARCH_FACTOR)
    table = PROMPT_TOKENS_PER_CASE_RUN.get(mode, PROMPT_TOKENS_PER_CASE_RUN["full"])  # unknown: the dearest
    if n in table:
        return table[n]
    xs = sorted(table)
    if n < xs[0]:
        x0, x1 = xs[0], xs[1]
    elif n > xs[-1]:
        x0, x1 = xs[-2], xs[-1]
    else:
        x0, x1 = next((a, b) for a, b in zip(xs, xs[1:]) if a <= n <= b)
    y = table[x0] + (table[x1] - table[x0]) * (n - x0) / (x1 - x0)
    return max(int(round(y)), 1)


def _check_priced(model: str) -> None:
    if model not in PRICES:
        raise ValueError(f"no price for model {model!r} in evals/pricing.py (priced: {', '.join(PRICES)})")


def estimate_case_run_cost(model: str, mode: str, n: int) -> float:
    _check_priced(model)
    return estimate_cost(model, prompt_tokens_per_case_run(mode, n), COMPLETION_TOKENS_PER_CASE_RUN)


def reservation_usd(model: str, mode: str, n: int) -> float:
    """What the cost cap holds for one attempt in flight: the estimate with a safety margin."""
    return estimate_case_run_cost(model, mode, n) * RESERVATION_MARGIN


def estimate(config: RoutingConfig, cases: list[Case]) -> Estimate:
    _check_priced(config.model)
    runs = plan(config, cases)
    prompt = sum(prompt_tokens_per_case_run(cr.mode, cr.n) for cr in runs)
    completion = COMPLETION_TOKENS_PER_CASE_RUN * len(runs)
    return Estimate(len(runs), prompt, completion,
                    sum(estimate_case_run_cost(config.model, cr.mode, cr.n) for cr in runs))


# ---------------------------------------------------------------- execution

class CapturingLLM:
    """Forces the model, supplies the API key, and keeps the conversation for the transcript."""

    def __init__(self, inner: Callable[..., Awaitable[dict]], model: str, api_key: Optional[str]) -> None:
        self.inner, self.model, self.api_key = inner, model, api_key
        self.system: Optional[str] = None
        self.messages: list[dict[str, Any]] = []  # the runtime's own list: grows with the loop
        self.tools: list[str] = []
        self.prompt_tokens = self.completion_tokens = 0  # from every response's usage block
        self.unmetered = 0  # responses with no usage block

    async def __call__(self, **kwargs: Any) -> dict:
        kwargs["model"] = self.model
        if self.api_key is not None:
            kwargs["api_key"] = self.api_key
        self.system = kwargs.get("system")
        self.messages = kwargs.get("messages") or []
        self.tools = [t.get("function", {}).get("name", "") for t in kwargs.get("tools") or []]
        response = await self.inner(**kwargs)
        usage = response.get("usage") if isinstance(response, dict) else None
        if isinstance(usage, dict):
            self.prompt_tokens += int(usage.get("prompt_tokens") or 0)
            self.completion_tokens += int(usage.get("completion_tokens") or 0)
        else:
            self.unmetered += 1
        return response

    def transcript(self) -> list[dict[str, Any]]:
        head = [{"role": "system", "content": self.system}] if self.system else []
        return head + json.loads(json.dumps(self.messages))


@dataclass
class CaseRunResult:
    case_run: CaseRun
    record: Optional[RunRecord] = None     # None when skipped
    transcript: list[dict[str, Any]] = field(default_factory=list)
    tools: list[str] = field(default_factory=list)
    attempts: int = 0
    attempt_errors: list[str] = field(default_factory=list)
    skipped: bool = False
    grade: Optional[Grade] = None          # set once graded (no error)

    @property
    def errored(self) -> bool:
        return self.record is not None and self.record.error is not None


class _Ledger:
    def __init__(self, model: str, max_cost: float) -> None:
        self.model, self.max_cost = model, max_cost
        self.spent = self.reserved = 0.0
        self.prompt_tokens = self.completion_tokens = 0
        self.unmetered_attempts, self.unmetered_usd = 0, 0.0
        self.stopped = False

    def try_reserve(self, est: float) -> bool:
        if self.stopped or self.spent + self.reserved + est > self.max_cost:
            self.stopped = True
            return False
        self.reserved += est
        return True

    def settle(self, reserved: float, prompt_tokens: int, completion_tokens: int,
               unmetered_charge: float = 0.0) -> None:
        """Release ``reserved`` and charge the measured tokens, plus ``unmetered_charge`` (the
        attempt's estimate) when a response carried no usage block."""
        self.reserved -= reserved
        self.prompt_tokens += prompt_tokens
        self.completion_tokens += completion_tokens
        self.spent += estimate_cost(self.model, prompt_tokens, completion_tokens) + unmetered_charge
        if unmetered_charge:
            self.unmetered_attempts += 1
            self.unmetered_usd += unmetered_charge


def _error_record(cr: CaseRun, mode: str, error: str, cap: Optional[CapturingLLM] = None) -> RunRecord:
    return RunRecord(cr.case.id, mode, cr.n, cr.run_idx, [], [], "", cap.prompt_tokens if cap else 0,
                     cap.completion_tokens if cap else 0, 0.0, 0, error)


def _runner_error(exc: BaseException, what: str = "") -> str:
    return f"{RUNNER_ERROR}: {what}{type(exc).__name__}: {exc}"


class _Executor:
    def __init__(self, config: RoutingConfig, world: World, llm: Callable[..., Awaitable[dict]],
                 api_key: Optional[str], runners: dict[str, ModeRunner], writer: RunWriter) -> None:
        self.config, self.world, self.llm, self.api_key, self.runners = config, world, llm, api_key, runners
        self.writer = writer
        self.ledger = _Ledger(config.model, config.max_cost)
        self.sem = asyncio.Semaphore(max(1, config.concurrency))
        self.paid: dict[tuple, asyncio.Task] = {}

    async def _attempt(self, cr: CaseRun, mode: str) -> tuple[RunRecord, CapturingLLM]:
        cap = CapturingLLM(self.llm, self.config.model, self.api_key)
        try:
            rec = await asyncio.wait_for(
                self.runners[mode](cr.case, self.world, mode, cr.n, cap, cr.run_idx), ATTEMPT_TIMEOUT_S)
            rec = replace(rec, mode=mode)  # the plan labels the record, whatever the runner wrote
        except asyncio.TimeoutError:
            rec = replace(_error_record(cr, mode, f"TimeoutError: no final response within {ATTEMPT_TIMEOUT_S:.0f}s",
                                        cap), latency_s=ATTEMPT_TIMEOUT_S)
        except Exception as exc:  # noqa: BLE001 - any runner bug is an errored record, never an abort
            rec = _error_record(cr, mode, _runner_error(exc), cap)
        return rec, cap

    async def _run_paid(self, cr: CaseRun, mode: str) -> CaseRunResult:
        out = CaseRunResult(replace(cr, mode=mode))
        est = estimate_case_run_cost(self.config.model, mode, cr.n)
        hold = reservation_usd(self.config.model, mode, cr.n)
        async with self.sem:
            for _ in range(2):  # first try + one retry on an infra error
                if not self.ledger.try_reserve(hold):
                    if out.attempts == 0:
                        out.skipped = True
                    else:
                        out.attempt_errors.append("retry skipped: max-cost reached")
                    return out
                rec, cap = await self._attempt(cr, mode)
                if cap.unmetered:
                    warnings.warn(f"{cr.case.id} {mode} N={cr.n}: {cap.unmetered} response(s) with no usage "
                                  f"block; charging the attempt's estimate ${est:.4f}", RuntimeWarning, stacklevel=2)
                self.ledger.settle(hold, cap.prompt_tokens, cap.completion_tokens, est if cap.unmetered else 0.0)
                out.attempts += 1
                out.record, out.transcript, out.tools = rec, cap.transcript(), cap.tools
                if rec.error is None:
                    return out
                out.attempt_errors.append(rec.error)
        return out

    def _paid_task(self, cr: CaseRun, mode: str) -> asyncio.Task:
        key = (cr.case.id, mode, cr.n, cr.run_idx)
        if key not in self.paid:
            self.paid[key] = asyncio.ensure_future(self._run_paid(cr, mode))
        return self.paid[key]

    async def _result(self, cr: CaseRun) -> CaseRunResult:
        return await self._paid_task(cr, cr.mode)

    async def run_one(self, cr: CaseRun) -> CaseRunResult:
        """Run, grade and persist one case-run; an exception makes it a RunnerError record."""
        try:
            out = await self._result(cr)
        except Exception as exc:  # noqa: BLE001
            out = CaseRunResult(cr, record=_error_record(cr, cr.mode, _runner_error(exc)))
        if out.record is not None and out.record.error is None:
            try:
                out.grade = grade(cr.case, out.record, roster_for(cr.case, self.world, cr.n),
                                  cr.mode)
            except Exception as exc:  # noqa: BLE001 - one bad record must not lose the run
                out.record = replace(out.record, error=_runner_error(exc, "grading failed: "))
        self._persist(out)
        return out

    def _persist(self, o: CaseRunResult) -> None:
        if o.record is None:
            return
        model = self.config.model
        if o.grade is not None:
            self.writer.append("records", _record_row(o, model))
            self.writer.append("grades", _grade_row(o))
        else:
            self.writer.append("errors", _record_row(o, model))
        self.writer.transcript(_transcript_name(o.case_run), _transcript_doc(o, model))

    async def run_all(self, runs: list[CaseRun]) -> list[CaseRunResult]:
        return list(await asyncio.gather(*(self.run_one(cr) for cr in runs)))


# ---------------------------------------------------------------- persistence

def slugify(text: str, limit: int = 40) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:limit].strip("-")
    return slug or "routing"


def _run_dir(out_root: Path, now: datetime, purpose: str) -> Path:
    base = f"{now.strftime('%Y%m%dT%H%M%SZ')}-{slugify(purpose)}"
    path, i = out_root / base, 2
    while path.exists():
        path, i = out_root / f"{base}-{i}", i + 1
    return path


def git_note() -> str:
    try:
        root = Path(__file__).resolve().parent.parent
        head = subprocess.run(["git", "rev-parse", "--short", "HEAD"], cwd=root, capture_output=True,
                              text=True, timeout=10, check=True).stdout.strip()
        dirty = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True,
                               text=True, timeout=10, check=True).stdout.strip()
    except Exception:  # noqa: BLE001 - informational only
        return "git status unavailable"
    return f"uncommitted working tree on HEAD {head}" if dirty else f"clean working tree at HEAD {head}"


def _record_row(o: CaseRunResult, model: str) -> dict[str, Any]:
    row = asdict(o.record)
    row.update(model=model, category=o.case_run.case.category, attempts=o.attempts,
               attempt_errors=list(o.attempt_errors))
    return row


def _grade_row(o: CaseRunResult) -> dict[str, Any]:
    return grade_row(o.case_run.case, o.record, o.grade, o.case_run.mode)


def _transcript_name(cr: CaseRun) -> str:
    return f"{cr.case.id}-{cr.mode}-{cr.n}-{cr.run_idx}.json"


def _transcript_doc(o: CaseRunResult, model: str) -> dict[str, Any]:
    cr = o.case_run
    return {"case_id": cr.case.id, "mode": cr.mode, "n": cr.n, "run_idx": cr.run_idx, "model": model,
            "attempts": o.attempts, "error": o.record.error,
            "tools": o.tools, "messages": o.transcript}


def _display_path(path: Path) -> str:
    """``path`` relative to the repo root when it is inside it."""
    try:
        return str(Path(path).resolve().relative_to(Path(__file__).resolve().parent.parent))
    except ValueError:
        return str(path)


def search_tables(modes: list[str], sizes: list[int], graded: list[tuple[Case, RunRecord]],
                  world: World) -> dict[str, Any]:
    """Per hybrid mode x N: case-runs graded, that searched, search errors, and whether the case's target
    agents (``expected_for``) were all in the initial cards or only reached by search."""
    from evals.retrieval_eval import expected_for

    out: dict[str, Any] = {}
    for m in modes:
        if m != "hybrid":
            continue
        out[m] = {str(n): {"graded": 0, "searched": 0, "search_errors": 0,
                           "target_in_initial": 0, "target_found_by_search": 0} for n in sizes}
    for case, rec in graded:
        if rec.mode not in out:
            continue
        cell = out[rec.mode][str(rec.n)]
        cell["graded"] += 1
        cell["searched"] += bool(rec.searches)
        cell["search_errors"] += sum(1 for s in rec.searches if s["error"])
        target = expected_for(case, world)[1]
        if not target:
            continue
        if target <= set(rec.initial_ids):
            cell["target_in_initial"] += 1
        elif target <= set(rec.initial_ids) | {i for s in rec.searches for i in s["ids"]}:
            cell["target_found_by_search"] += 1
    return out


def summarize(config: RoutingConfig, cases: list[Case], outcomes: list[CaseRunResult], ledger: _Ledger,
              est: Estimate, *, cases_dir: Path, run_dir: Path, now: datetime,
              descriptions: Optional[dict[str, Any]] = None, world: Optional[World] = None) -> dict[str, Any]:
    modes, sizes = config.modes, config.sizes
    graded = [o for o in outcomes if o.grade is not None]
    tables = grade_tables(modes, sizes, cases, [(o.case_run.case, o.record, o.grade) for o in graded])
    infra = {m: {str(n): 0 for n in sizes} for m in modes}
    skipped = {m: {str(n): 0 for n in sizes} for m in modes}
    errored = [o for o in outcomes if o.errored]
    skips = [o for o in outcomes if o.skipped]
    for o in errored:
        infra[o.case_run.mode][str(o.case_run.n)] += 1
    for o in skips:
        skipped[o.case_run.mode][str(o.case_run.n)] += 1
    error_kinds, loops = error_tables([asdict(o.record) for o in errored])
    paid = graded
    manifest = read_manifest(cases_dir) or {}
    extra = {} if descriptions is None else {"descriptions": descriptions}  # only runs with card modes
    if "hybrid" in modes:
        extra["embedder"] = config.embedder
        extra["search"] = search_tables(modes, sizes, [(o.case_run.case, o.record) for o in graded], world)
    return {
        "purpose": config.purpose,
        "command": config.command,
        "date_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "run_folder": run_dir.name,
        "model": config.model,
        "git": git_note(),
        "case_set": {"dir": _display_path(cases_dir), "version": manifest.get("version"),
                     "manifest_sha256": sha256_file(Path(cases_dir) / "MANIFEST.json"),
                     "frozen_on": manifest.get("frozen_on"), "world_sha256": manifest.get("world_sha256")},
        "split": config.split,
        "case_ids": [c.id for c in cases],
        "n_cases": len(cases),
        "modes": modes, "sizes": sizes, "runs": config.runs,
        "max_cost": config.max_cost, "concurrency": config.concurrency,
        **extra,
        "counts": {
            "planned": len(outcomes),
            "completed": len(graded),
            "graded": len(graded),
            "infra_errors": len(errored),
            "retried": sum(o.attempts > 1 for o in outcomes),
            "skipped_max_cost": len(skips),
        },
        "cost": {"actual_usd": round(ledger.spent, 6), "estimated_usd": round(est.usd, 6),
                 "prompt_tokens": ledger.prompt_tokens, "completion_tokens": ledger.completion_tokens,
                 "reservation_margin": RESERVATION_MARGIN, "unmetered_attempts": ledger.unmetered_attempts,
                 "unmetered_usd": round(ledger.unmetered_usd, 6)},
        "latency": {
            "mean_latency_s": round(sum(o.record.latency_s for o in paid) / len(paid), 3) if paid else None,
            "mean_round_trips": round(sum(o.record.round_trips for o in paid) / len(paid), 3) if paid else None,
        },
        **{k: tables[k] for k in ("pass_rate", "by_category", "flags", "structural")},
        "infra_errors": infra,
        "skipped": skipped,
        "error_kinds": error_kinds,
        "iteration_limit": loops,
        "failing": tables["failing"],
    }


async def execute_routing(config: RoutingConfig, cases: list[Case], world: World,
                          llm: Callable[..., Awaitable[dict]], out_root: Path = RESULTS_DIR, *,
                          api_key: Optional[str] = None, runners: Optional[dict[str, ModeRunner]] = None,
                          cases_dir: Path = CASES_DIR, now: Optional[datetime] = None,
                          descriptions: Optional[DescriptionSource] = None) -> Path:
    """Run, grade and write every output file; returns the run folder.

    ``descriptions`` is the run's already-loaded source (the CLI loads it before its estimate);
    without it, a run with ``full`` loads it here, before anything is written or spent."""
    runners = MODE_RUNNERS if runners is None else runners
    check_modes(config.modes, runners)
    if descriptions is None:
        descriptions = resolve_descriptions(config)
    runners = bind_descriptions(runners, descriptions)
    if "hybrid" in config.modes:
        runners = bind_embedder(runners, make_embedder(config.embedder))
    est = estimate(config, cases)
    now = now or datetime.now(timezone.utc)
    runs = plan(config, cases)
    out_root = Path(out_root)
    run_dir = _run_dir(out_root, now, config.purpose)
    writer = RunWriter(run_dir, [s for s in [api_key, configured_api_key()] if s])
    ex = _Executor(config, world, llm, api_key, runners, writer)
    outcomes = await ex.run_all(runs)

    # The files were appended in completion order; rewrite them in plan order.
    model = config.model
    graded = [o for o in outcomes if o.grade is not None]
    writer.rewrite("records", [_record_row(o, model) for o in graded])
    writer.rewrite("grades", [_grade_row(o) for o in graded])
    writer.rewrite("errors", [_record_row(o, model) for o in outcomes if o.errored])
    desc_summary = descriptions_summary(descriptions, world) if descriptions is not None else None
    summary = scrub(summarize(config, cases, outcomes, ex.ledger, est, cases_dir=Path(cases_dir),
                              run_dir=run_dir, now=now, descriptions=desc_summary, world=world), writer.secrets)
    writer.text("summary.json", json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    writer.text("report.md", render_report(summary))
    append_experiment(out_root / "EXPERIMENTS.md", summary)
    return run_dir
