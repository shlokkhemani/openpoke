"""Semantic shortlisting for the execution-agent roster."""

from __future__ import annotations

import asyncio
import hashlib
import json
import math
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence

from ...config import get_settings
from ...data_paths import get_data_dir
from ...logging_config import logger
from ...openrouter_client import request_embeddings
from .log_store import ExecutionAgentLogStore, get_execution_agent_logs
from .roster import AgentRoster, get_agent_roster


_INDEX_VERSION = 1
_EMBEDDING_BATCH_SIZE = 64
_MAX_EMBEDDING_TEXT_CHARS = 16_000

EmbeddingRequest = Callable[..., Awaitable[Dict[str, Any]]]


@dataclass(frozen=True)
class AgentMatch:
    """An execution agent and its semantic similarity to the current input."""

    name: str
    score: float


class RosterEmbeddingIndex:
    """Small JSON-backed embedding index for execution-agent profiles."""

    def __init__(self, path: Path) -> None:
        self._path = path
        self._lock = threading.Lock()

    def load(self, model: str) -> Dict[str, Dict[str, Any]]:
        with self._lock:
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
            except (FileNotFoundError, json.JSONDecodeError, OSError):
                return {}

        if not isinstance(raw, dict):
            return {}
        if raw.get("version") != _INDEX_VERSION or raw.get("model") != model:
            return {}
        entries = raw.get("entries")
        return entries if isinstance(entries, dict) else {}

    def save(self, model: str, entries: Dict[str, Dict[str, Any]]) -> None:
        payload = {
            "version": _INDEX_VERSION,
            "model": model,
            "entries": entries,
        }
        serialized = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

        with self._lock:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            temp_path = self._path.with_suffix(".tmp")
            try:
                temp_path.write_text(serialized, encoding="utf-8")
                temp_path.replace(self._path)
            finally:
                if temp_path.exists():
                    temp_path.unlink()


class RosterMatcher:
    """Return the execution agents most relevant to an incoming message."""

    def __init__(
        self,
        *,
        roster: AgentRoster,
        logs: ExecutionAgentLogStore,
        model: str,
        percentage: float = 5.0,
        min_size: int = 5,
        max_size: int = 50,
        recent_task_limit: int = 5,
        index_path: Optional[Path] = None,
        embedding_request: EmbeddingRequest = request_embeddings,
    ) -> None:
        if not math.isfinite(percentage) or not 0 < percentage <= 100:
            raise ValueError("Shortlist percentage must be greater than 0 and at most 100")
        if min_size < 1 or max_size < min_size:
            raise ValueError("Shortlist sizes must satisfy 1 <= min_size <= max_size")

        self._roster = roster
        self._logs = logs
        self._model = model
        self._percentage = percentage
        self._min_size = min_size
        self._max_size = max_size
        self._recent_task_limit = max(1, recent_task_limit)
        self._index = RosterEmbeddingIndex(
            index_path if index_path is not None
            else get_data_dir() / "execution_agents" / "roster_embeddings.json"
        )
        self._embedding_request = embedding_request
        self._operation_lock = asyncio.Lock()

    async def shortlist(self, query_text: str) -> List[str]:
        """Return a percentage of roster names ordered by semantic relevance.

        Round the percentage up, apply the configured minimum and maximum, and
        never select more agents than exist in the roster.
        A small roster is returned unchanged because shortlisting it would add an
        external request without reducing the interaction agent's context.
        Matching errors propagate to the caller instead of using the full roster.
        """

        self._roster.load()
        agent_names = self._roster.get_agents()
        shortlist_size = min(
            len(agent_names),
            self._max_size,
            max(self._min_size, math.ceil(len(agent_names) * self._percentage / 100)),
        )
        if len(agent_names) <= shortlist_size or not query_text.strip():
            return agent_names

        async with self._operation_lock:
            matches = await self._rank(
                _bounded_embedding_text(query_text),
                agent_names,
                shortlist_size,
            )

        logger.info(
            "execution-agent roster shortlisted",
            extra={
                "roster_size": len(agent_names),
                "shortlist_size": len(matches),
                "agents": [match.name for match in matches],
            },
        )
        return [match.name for match in matches]

    async def _rank(
        self, query_text: str, agent_names: Sequence[str], shortlist_size: int
    ) -> List[AgentMatch]:
        profiles = {name: self._build_agent_profile(name) for name in agent_names}
        fingerprints = {
            name: hashlib.sha256(profile.encode("utf-8")).hexdigest()
            for name, profile in profiles.items()
        }

        query_vector = (await self._embed_texts([query_text]))[0]
        entries = self._index.load(self._model)
        valid_entries: Dict[str, Dict[str, Any]] = {}
        stale_names: List[str] = []

        for name in agent_names:
            entry = entries.get(name)
            if self._is_valid_entry(
                entry,
                fingerprints[name],
                expected_dimensions=len(query_vector),
            ):
                valid_entries[name] = entry
            else:
                stale_names.append(name)

        for start in range(0, len(stale_names), _EMBEDDING_BATCH_SIZE):
            batch_names = stale_names[start : start + _EMBEDDING_BATCH_SIZE]
            batch_vectors = await self._embed_texts(
                [profiles[name] for name in batch_names]
            )
            for name, vector in zip(batch_names, batch_vectors):
                valid_entries[name] = {
                    "fingerprint": fingerprints[name],
                    "embedding": vector,
                }

        # Remove agents no longer in the roster while persisting refreshed entries.
        self._index.save(self._model, valid_entries)

        scored = [
            AgentMatch(
                name=name,
                score=_cosine_similarity(
                    query_vector, valid_entries[name]["embedding"]
                ),
            )
            for name in agent_names
        ]
        roster_order = {name: index for index, name in enumerate(agent_names)}
        scored.sort(key=lambda match: (-match.score, roster_order[match.name]))
        return scored[:shortlist_size]

    def _build_agent_profile(self, agent_name: str) -> str:
        requests = [
            payload.strip()
            for tag, _timestamp, payload in self._logs.iter_entries(agent_name)
            if tag == "agent_request" and payload.strip()
        ]
        recent_requests = requests[-self._recent_task_limit :]

        lines = [f"Agent name: {agent_name}"]
        if recent_requests:
            lines.append("Recent assigned tasks (newest first):")
            lines.extend(f"- {request}" for request in reversed(recent_requests))
        return _bounded_embedding_text("\n".join(lines))

    @staticmethod
    def _is_valid_entry(
        entry: Any,
        fingerprint: str,
        *,
        expected_dimensions: int,
    ) -> bool:
        if not isinstance(entry, dict) or entry.get("fingerprint") != fingerprint:
            return False
        embedding = entry.get("embedding")
        return (
            isinstance(embedding, list)
            and bool(embedding)
            and len(embedding) == expected_dimensions
            and all(
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(float(value))
                for value in embedding
            )
        )

    async def _embed_texts(self, texts: Sequence[str]) -> List[List[float]]:
        response = await self._embedding_request(model=self._model, input=list(texts))
        raw_data = response.get("data")
        if not isinstance(raw_data, list) or len(raw_data) != len(texts):
            raise ValueError("Embedding response count did not match input count")

        ordered: List[Optional[List[float]]] = [None] * len(texts)
        for fallback_index, item in enumerate(raw_data):
            if not isinstance(item, dict):
                raise ValueError("Embedding response contained an invalid item")
            index = item.get("index", fallback_index)
            embedding = item.get("embedding")
            if not isinstance(index, int) or not 0 <= index < len(texts):
                raise ValueError("Embedding response contained an invalid index")
            if (
                not isinstance(embedding, list)
                or not embedding
                or not all(
                    isinstance(value, (int, float))
                    and not isinstance(value, bool)
                    and math.isfinite(float(value))
                    for value in embedding
                )
            ):
                raise ValueError("Embedding response contained an invalid vector")
            ordered[index] = [float(value) for value in embedding]

        if any(vector is None for vector in ordered):
            raise ValueError("Embedding response omitted an input")
        return [vector for vector in ordered if vector is not None]


def _cosine_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if len(left) != len(right) or not left:
        raise ValueError("Embedding vectors must have the same non-zero dimensions")

    dot_product = sum(a * b for a, b in zip(left, right))
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return dot_product / (left_norm * right_norm)


def _bounded_embedding_text(text: str) -> str:
    """Keep embedding inputs comfortably below common model context limits."""

    return text.strip()[:_MAX_EMBEDDING_TEXT_CHARS]


_roster_matcher: Optional[RosterMatcher] = None
_roster_matcher_lock = threading.Lock()


def get_roster_matcher() -> RosterMatcher:
    """Return the process-wide roster matcher."""

    global _roster_matcher
    if _roster_matcher is None:
        with _roster_matcher_lock:
            if _roster_matcher is None:
                settings = get_settings()
                _roster_matcher = RosterMatcher(
                    roster=get_agent_roster(),
                    logs=get_execution_agent_logs(),
                    model=settings.roster_embedding_model,
                    percentage=settings.roster_match_percentage,
                    min_size=settings.roster_match_min_size,
                    max_size=settings.roster_match_max_size,
                    recent_task_limit=settings.roster_match_recent_tasks,
                )
    return _roster_matcher


__all__ = ["AgentMatch", "RosterMatcher", "get_roster_matcher"]
