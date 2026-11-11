"""Haiku rewrites of template-generated user messages, with label-preservation checks (scope §1a).

Only ``source == "template"`` cases are rewritten. For multi-dispatch cases the checks also require
every slot's ``@person`` the original message refers to to survive, and the reminder request, if
any, to stay (a rewrite that drops "and remind me…" fails; times are covered by the number and
schedule checks). A rewrite that fails any check is retried once,
then dropped in favour of the original. Infrastructure errors (the call raised) are retried once;
a second failure keeps the original and is recorded in ``ParaphraseReport.errors``.
"""
from __future__ import annotations

import asyncio
import dataclasses
import re
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

from evals.grading import REMINDER_CUE
from evals.pricing import estimate_cost
from evals.schema import Case, validate_cases
from evals.world.roster import World

LLM = Callable[..., Awaitable[dict[str, Any]]]

SYSTEM = (
    "You rewrite one chat message that a user sent to their personal assistant, so the same request "
    "is phrased differently. Rules:\n"
    "- Keep the meaning and every detail: the same task, the same people, the same times, dates and numbers.\n"
    "- Keep every person reference exactly at the level of detail it has now. Never add a surname, email "
    "address or nickname, never turn a pronoun into a name, never add or drop a person.\n"
    "- Keep agent or task names, if any are quoted, word for word.\n"
    "- Write like a real person typing quickly. Do not copy long phrases from the original.\n"
    "- Output only the rewritten message: one line, no quotes, no preamble, no explanation."
)


@dataclass
class ParaphraseReport:
    kept: int = 0
    retried: int = 0
    reverted: int = 0
    prompt_tokens: int = 0
    completion_tokens: int = 0
    errors: list[dict[str, Any]] = field(default_factory=list)
    check_failures: list[dict[str, Any]] = field(default_factory=list)

    def cost(self, model: str) -> float:
        return estimate_cost(model, self.prompt_tokens, self.completion_tokens)


# ------------------------------------------------------------------------------ checks

def _word_in(needle: str, text: str, flags: int = 0) -> bool:
    return re.search(rf"(?<!\w){re.escape(needle)}(?!\w)", text, flags) is not None


def _people(text: str, world: World) -> tuple[set[str], set[str]]:
    """(first names mentioned, people mentioned in full by name or email address)."""
    firsts = {c.display_name.split()[0] for c in world.contacts}
    first_hits = {f for f in firsts if _word_in(f, text)}
    low = text.lower()
    full_hits = {c.display_name for c in world.contacts
                 if len(c.display_name.split()) > 1 and _word_in(c.display_name, text, re.I)}
    full_hits |= {c.display_name for c in world.contacts if c.email.lower() in low}
    return first_hits, full_hits


def _agent_names(text: str, world: World) -> set[str]:
    low = text.lower()
    return {a.name.lower() for a in world.agents.values() if len(a.name) > 3 and a.name.lower() in low}


_DAYS = "monday|tuesday|wednesday|thursday|friday|saturday|sunday"
_SCHEDULE_RE = re.compile(
    rf"\b(?:weekdays?|daily|every day|nightly|weekly|monthly|yearly|annually|once a week|"
    rf"every (?:week|month|year|morning|evening|night|afternoon)|mornings?|evenings?|nights?|afternoons?|"
    rf"noon|midnight|{_DAYS})\b|\b\d{{1,2}}(?::\d{{2}})?\s?(?:am|pm)?\b", re.I)


def _schedule_tokens(text: str) -> set[str]:
    """Cadence words, weekday names and times, lowercased, spaces removed. Compared exactly:
    'every day' and 'daily' are different tokens, so such a rewrite reverts (it could retarget
    the case to a twin trigger on another schedule)."""
    toks = {re.sub(r"\s", "", m.group(0).lower()) for m in _SCHEDULE_RE.finditer(text)}
    return {"weekday" if t == "weekdays" else t for t in toks}


# Common first names that are not world contacts; with the world's first names they identify a
# new person even at the start of a sentence.
_EXTRA_FIRST_NAMES = frozenset(
    "Jordan John Jane Sarah Michael Emily David Jessica James Mary Robert Linda Chris Alex Taylor Sam Mike "
    "Anna Tom Kate Ben Nick Laura Peter Paul Mark Lisa Karen Steve Emma Olivia Noah Ethan Sophia".split())
_REQUEST_VERBS = (
    "tell|email|e-mail|send|ask|write|message|text|dm|check|remind|set|move|push|shift|cancel|turn|follow|look|"
    "search|find|let|give|make|stop|pause|resume|schedule|ping|nudge|draft|forward|reply|call|book|add|update|"
    "get|see|show|confirm|notify|snooze|delete|remove|switch|change|keep|pull|bring|put|note|share|catch|"
    "reschedule|reach|have|drop|shoot|hit|kill|chase|loop|touch|circle|dismiss|mute|disable|enable|rename|"
    "double-check|recheck|verify|find|dig|fetch|grab|help|wake|stand|end|quit|skip|text|fire|run|cut|hold|"
    "mind|mention|inform|update|brief|fill|query|poke|bug|answer|respond|go|try|do|clear|clean")
# Sentence-initial words that are ordinary English (imperatives, auxiliaries, question words), never names.
_COMMON_INITIAL = frozenset(_REQUEST_VERBS.split("|")) | frozenset(
    "are is was were do does did have has had can could would will should shall may might must please pls kindly "
    "any anything anyone anybody what whats where when who how why which if is thanks thank hey hi ok okay just "
    "also and but so sure that this these those it its i we you my your our the a an no not yes maybe once then "
    "there here some every each all both either neither mind".split())
_CAP_RE = re.compile(r"[A-Z][a-z]+(?:'[a-z]+)?")


def _new_name_like(text: str, allowed_lower: str, world: World) -> list[str]:
    """Capitalised words that look like a newly introduced person.

    Conservative on purpose (a false positive only reverts the rewrite). Flagged, when absent
    from the original message, the case history and the world's agent/contact names: any
    capitalised word that is not the first word of a sentence; a sentence-initial word that is
    followed by another capitalised word (a first+last name) or is a known first name.
    """
    known = allowed_lower + " " + " ".join(
        [a.name for a in world.agents.values()] + [c.display_name for c in world.contacts]).lower()
    firsts = {c.display_name.split()[0] for c in world.contacts} | _EXTRA_FIRST_NAMES
    flagged: list[str] = []
    for m in _CAP_RE.finditer(text):
        w = m.group(0).removesuffix("'s")
        if re.search(rf"(?<!\w){re.escape(w.lower())}(?!\w)", known):
            continue
        before = text[: m.start()].rstrip()
        initial = not before or before[-1] in ".!?:"
        if initial and w.lower() in _COMMON_INITIAL and w not in firsts:
            continue
        nxt = re.match(r"\s+[A-Z][a-z]", text[m.end():])
        if not initial or nxt or w in firsts:
            flagged.append(w)
    return flagged


def _person_present(name: str, text: str, world: World) -> bool:
    """The user's message refers to the person by full name, email address or first name."""
    low = text.lower()
    return (_word_in(name, text, re.I) or _word_in(name.split()[0], text)
            or any(c.email.lower() in low for c in world.contacts if c.display_name == name))


def _request_problems(case: Case, orig: str, text: str, world: World) -> list[str]:
    """Multi-dispatch cases: every slot's person survives, and no request ('and remind me…') is dropped."""
    problems: list[str] = []
    slots = [s for o in case.acceptable if o.kind == "dispatch" for s in o.slots]
    if not slots:
        return problems
    for name in dict.fromkeys(p for s in slots for p in s.persons):
        if _person_present(name, orig, world) and not _person_present(name, text, world):
            problems.append(f"slot person dropped: {name}")
    if bool(REMINDER_CUE.search(orig)) != bool(REMINDER_CUE.search(text)):
        problems.append("number of requests changed: the reminder request was dropped or added")
    return problems


_CLAUSE_START = r"(?:^|[.!?;:,\u2014-]\s*|\b(?:and|then|also|but)\s+)"
_REQUEST_RE = re.compile(
    rf"{_CLAUSE_START}(?:(?:please|pls|kindly)\s+)?(?:{_REQUEST_VERBS})\b"
    r"|\b(?:can|could|would|will)\s+you\b|\byou\s+(?:can|could|would)\b|\bmind\s+\w+ing\b"
    r"|\b(?:for|need|want|like|love) you to\b|\bi\s+(?:want|need)\s+(?!to\b)\w"
    r"|\bi(?:'d| would)\s+(?:like|love|appreciate)\b|\bi\s+(?:don't|do not|no longer)\s+want\b"
    r"|^\s*no more\b|\bremind me\b|\bany chance\b",
    re.I)
_PRONOUN_CLASSES = {
    "she": {"she", "her", "hers", "herself"},
    "he": {"he", "him", "his", "himself"},
    "they": {"they", "them", "their", "theirs", "themselves"},
}


def _is_request(text: str) -> bool:
    """The message asks the assistant to do something (imperative, 'can you', 'please', 'I want')."""
    return _REQUEST_RE.search(text.strip()) is not None


def _asks_for_something(text: str) -> bool:
    return _is_request(text) or "?" in text


def _pronoun_classes(text: str) -> set[str]:
    words = set(re.findall(r"[a-z]+", text.lower().replace("'", " ")))
    return {k for k, forms in _PRONOUN_CLASSES.items() if words & forms}


def _ask_and_pronoun_problems(case: Case, orig: str, text: str, relies_on_pronoun: bool) -> list[str]:
    problems: list[str] = []
    dispatches = any(o.kind in ("dispatch", "create", "reuse") for o in case.acceptable)
    if _is_request(orig) and not (_is_request(text) or "?" in text):
        problems.append("request dropped: the original asks the assistant to do something, the rewrite does not")
    elif dispatches and not _asks_for_something(text):
        problems.append("request dropped: the label dispatches but the rewrite asks for nothing")
    o_pro, r_pro = _pronoun_classes(orig), _pronoun_classes(text)
    if relies_on_pronoun and o_pro != r_pro:
        problems.append(f"pronoun changed or dropped: {sorted(o_pro)} -> {sorted(r_pro)}")
    elif o_pro and r_pro - o_pro:
        problems.append(f"pronoun changed: {sorted(o_pro)} -> {sorted(r_pro)}")
    return problems


def check_paraphrase(case: Case, rewritten: str, world: World) -> list[str]:
    """Problems that make ``rewritten`` unsafe to substitute for ``case.message`` (empty = fine)."""
    problems: list[str] = []
    text = rewritten.strip()
    if not text:
        return ["empty rewrite"]
    if "\n" in text:
        problems.append("rewrite spans several lines")
    orig = case.message

    o_first, o_full = _people(orig, world)
    r_first, r_full = _people(text, world)
    # First names matter on their own only for people not named in full (a full name or an email
    # address, which has no first-name token, already identifies the person).
    o_alone = o_first - {n.split()[0] for n in o_full}
    r_alone = r_first - {n.split()[0] for n in r_full}
    if o_alone != r_alone:
        problems.append(f"first names changed: {sorted(o_alone)} -> {sorted(r_alone)}")
    for name in sorted(o_full - r_full):
        problems.append(f"full name or email of {name} dropped")
    for name in sorted(r_full - o_full):
        problems.append(f"full name or email of {name} added")

    if _agent_names(orig, world) != _agent_names(text, world):
        problems.append("agent names changed")
    if set(re.findall(r"\d+", orig)) != set(re.findall(r"\d+", text)):
        problems.append("numbers changed")
    o_sched, r_sched = _schedule_tokens(orig), _schedule_tokens(text)
    if o_sched != r_sched:
        problems.append(f"cadence/schedule wording changed: {sorted(o_sched)} -> {sorted(r_sched)}")
    problems += _request_problems(case, orig, text, world)
    problems += _ask_and_pronoun_problems(case, orig, text, relies_on_pronoun=not (o_first or o_full))
    allowed = " ".join([orig, *(t.text for t in case.ia_history)]).lower()
    new_names = _new_name_like(text, allowed, world)
    if new_names:
        problems.append(f"name-like words not in the original or history: {new_names}")

    # Surname / email of a colliding contact, and copied description wording, use the same rules
    # as the case-set validator.
    problems += [p.split(": ", 1)[1] for p in validate_cases([dataclasses.replace(case, message=text)])]
    return problems


# ------------------------------------------------------------------------------ prompt

def build_prompt(case: Case, world: World) -> str:
    first, full = _people(case.message, world)
    lines = [f"Message to rewrite:\n{case.message}", ""]
    if full:
        lines.append(f"It names {', '.join(sorted(full))} in full: keep the full name (or the email address) in the rewrite.")
    only_first = sorted(first - {n.split()[0] for n in full})
    if only_first:
        lines.append(f"It refers to {', '.join(only_first)} by first name only: keep it that way, with no surname or email.")
    if not first and re.search(r"\b(her|him|them|she|he|they)\b", case.message, re.I):
        lines.append("It refers to someone by pronoun only: keep that same pronoun, do not name anyone.")
    if _is_request(case.message):
        lines.append("It is a request to the assistant to do something: the rewrite must still ask for it "
                     "(not thank, not state).")
    slots = [s for o in case.acceptable if o.kind == "dispatch" for s in o.slots]
    if len(slots) > 1:
        lines.append(f"It asks for {len(slots)} separate things: keep every one of them.")
    lines.append("Rewrite it now. Output only the rewritten message.")
    return "\n".join(lines)


def _clean(s: str) -> str:
    s = s.strip()
    if len(s) > 1 and s[0] == s[-1] and s[0] in "\"'":
        s = s[1:-1].strip()
    return s


# ------------------------------------------------------------------------------ driver

async def _rewrite_one(case: Case, model: str, llm: LLM, world: World, report: ParaphraseReport) -> Case:
    needed_retry = False
    first_error: Optional[dict[str, Any]] = None
    for attempt in (1, 2):
        try:
            resp = await llm(model=model, system=SYSTEM,
                             messages=[{"role": "user", "content": build_prompt(case, world)}])
            text = _clean(resp["choices"][0]["message"].get("content") or "")
            usage = resp.get("usage") or {}
            report.prompt_tokens += int(usage.get("prompt_tokens", 0))
            report.completion_tokens += int(usage.get("completion_tokens", 0))
        except Exception as exc:  # infrastructure error
            problems = None
            err = {"case_id": case.id, "attempt": attempt, "error": f"{type(exc).__name__}: {exc}"}
        else:
            problems, err = check_paraphrase(case, text, world), None
            if not problems:
                report.kept += 1
                report.retried += needed_retry
                return dataclasses.replace(case, message=text, original_message=case.message,
                                           source="paraphrased")
            report.check_failures.append({"case_id": case.id, "attempt": attempt, "problems": problems,
                                          "rewrite": text})
        if err is not None and first_error is None:
            first_error = err
        if attempt == 1:
            needed_retry = True
    if first_error is not None:  # reverted after at least one infrastructure error: record it
        report.errors.append(first_error)
    report.retried += needed_retry
    report.reverted += 1
    return case


async def paraphrase(cases: list[Case], model: str, llm: LLM, *, world: World,
                     report: Optional[ParaphraseReport] = None, concurrency: int = 8) -> list[Case]:
    """Rewrite the message of every ``source == "template"`` case; other cases pass through."""
    report = report if report is not None else ParaphraseReport()
    sem = asyncio.Semaphore(concurrency)

    async def one(c: Case) -> Case:
        if c.source != "template":
            return c
        async with sem:
            return await _rewrite_one(c, model, llm, world, report)

    return list(await asyncio.gather(*(one(c) for c in cases)))
