"""Paraphrases of the 48 dense-roster topics (one cheap call per topic), checked for leaks against the agents' words.

    python -m evals.run stress-paraphrase [--yes] [--max-cost X] [--force]

Frozen once written: the file is refused for overwrite without ``--force``. Same retry policy as
``evals.paraphrase``: a leaking or empty paraphrase and an infrastructure error are each retried once.
"""
from __future__ import annotations

import asyncio
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Optional

from evals.paraphrase import _clean
from evals.pricing import estimate_cost
from evals.textwords import content_words
from evals.world.dense import SEED, DenseWorld, build_dense_world
from evals.world.generate import WORLD_PATH
from evals.world.roster import load_world

STRESS_DIR = WORLD_PATH.parent / "stress"
OUT_PATH = STRESS_DIR / "dense_paraphrases.json"
DEFAULT_MAX_COST = 0.25
COMPLETION_TOKENS = 16

SYSTEM = (
    "You help build a retrieval test. Given a topic of an errand a user once gave their assistant, write a short, "
    "casual way the user might refer to that topic later, as a noun phrase of 2 to 6 words. Use none of the "
    "forbidden words (and no plural or singular form of them). Reply with the phrase only: no quotes, no preamble.")
PROMPT = ("Topic: {short} ({phrase}).\nForbidden words: {forbidden}.\n"
          "Write the short casual noun phrase (2-6 words) now.")


def default_llm():
    from evals import regen_descriptions
    return regen_descriptions.default_llm()


def default_model() -> str:
    from server.config import get_settings
    return get_settings().eval_dev_model


def leaks(paraphrase: str, forbidden: Iterable[str]) -> set[str]:
    return content_words(paraphrase) & content_words(" ".join(forbidden))


def forbidden_words(dense: DenseWorld, topic: str) -> set[str]:
    meta = dense.topic_meta[topic]
    text = [meta.short, meta.phrase, meta.reply]
    for p in dense.people:
        a = dense.agents[dense.by_person_topic[(p.email, topic)]]
        text += [a.name, a.description]
    names = content_words(" ".join(p.display_name for p in dense.people))
    return content_words(" ".join(text)) - names


def _prompt(dense: DenseWorld, topic: str) -> str:
    meta = dense.topic_meta[topic]
    return PROMPT.format(short=meta.short, phrase=meta.phrase, forbidden=", ".join(sorted(forbidden_words(dense, topic))))


def prompt_sha256() -> str:
    return hashlib.sha256((SYSTEM + PROMPT).encode("utf-8")).hexdigest()


def _estimate(dense: DenseWorld, model: str) -> tuple[int, int, int, float]:
    prompt = sum((len(SYSTEM) + len(_prompt(dense, t))) // 4 + 1 for t in dense.topics) * 2   # worst case: 2 calls
    completion = COMPLETION_TOKENS * len(dense.topics) * 2
    return len(dense.topics) * 2, prompt, completion, estimate_cost(model, prompt, completion)


async def _generate(dense: DenseWorld, llm, model: str, max_cost: float) -> dict[str, Any]:
    res: dict[str, Any] = {"items": {}, "dropped": [], "errors": [], "skipped_budget": [],
                           "tokens": {"prompt": 0, "completion": 0}, "spent": 0.0}
    for topic in dense.topics:
        base = _prompt(dense, topic)
        prompt, errors, last = base, [], None
        for attempt in (1, 2):
            est = estimate_cost(model, (len(SYSTEM) + len(prompt)) // 4 + 1, COMPLETION_TOKENS)
            if res["spent"] + est > max_cost:
                res["skipped_budget"].append(topic)
                last = "skipped"
                break
            try:
                resp = await llm(model=model, system=SYSTEM, messages=[{"role": "user", "content": prompt}])
                text = _clean(resp["choices"][0]["message"].get("content") or "")
                usage = resp.get("usage") or {}
                pt = int(usage.get("prompt_tokens", (len(SYSTEM) + len(prompt)) // 4 + 1))
                ct = int(usage.get("completion_tokens", COMPLETION_TOKENS))
            except Exception as exc:  # infrastructure error
                errors.append({"topic": topic, "attempt": attempt, "error": f"{type(exc).__name__}: {exc}"})
                last = "error"
                continue
            res["tokens"]["prompt"] += pt
            res["tokens"]["completion"] += ct
            res["spent"] += estimate_cost(model, pt, ct)
            bad = leaks(text, forbidden_words(dense, topic)) if text else set()
            if text and not bad:
                res["items"][topic] = text
                last = "ok"
                break
            last = {"topic": topic, "paraphrase": text, "leaked": sorted(bad)}
            prompt = base + (f"\nYour previous answer {text!r} used forbidden words: {', '.join(sorted(bad))}."
                             if bad else "\nYour previous answer was empty.") + " Try again with other words."
        if last == "error":
            res["errors"] += errors
        elif isinstance(last, dict):
            res["dropped"].append(last)
    return res


def run(out_path: Path = OUT_PATH, yes: bool = False, max_cost: Optional[float] = None, force: bool = False) -> int:
    out_path = Path(out_path)
    cap = DEFAULT_MAX_COST if max_cost is None else max_cost
    dense = build_dense_world(load_world(WORLD_PATH))
    model = default_model()
    calls, prompt, completion, usd = _estimate(dense, model)
    print(f"Estimated cost: ${usd:.4f} for up to {calls} calls (48 topics, one retry each) with {model} "
          f"(~{prompt:,} prompt + ~{completion:,} completion tokens).")
    if out_path.exists() and not force:
        print(f"{out_path} exists and is frozen; refusing to overwrite it (pass --force).")
        return 1
    if not yes:
        print("Refusing to run without --yes.")
        return 2
    if usd > cap:
        print(f"Estimate exceeds --max-cost ${cap:g}; refusing.")
        return 1
    res = asyncio.run(_generate(dense, default_llm(), model, cap))
    data = {"model": model, "generated_on": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
            "prompt_sha256": prompt_sha256(), "seed": SEED, "tokens": res["tokens"],
            "cost_usd": round(res["spent"], 6), "items": res["items"], "dropped": res["dropped"],
            "errors": res["errors"], "skipped_budget": res["skipped_budget"]}
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, indent=1, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {len(data['items'])} paraphrases to {out_path} ({len(data['dropped'])} dropped, "
          f"{len(data['errors'])} errors, {len(data['skipped_budget'])} skipped); spend ${data['cost_usd']:.4f}")
    return 0
