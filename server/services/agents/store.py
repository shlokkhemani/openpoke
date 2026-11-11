from __future__ import annotations

import base64
import re
import secrets
import sqlite3
import threading
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Literal, Optional, Tuple

import numpy as np

from .stopwords import STOPWORDS

_DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
_DEFAULT_DB_PATH = _DATA_DIR / "agents.db"


@dataclass(frozen=True)
class AgentRecord:
    id: str
    name: str
    description: str
    created_at: datetime
    last_user_activity_at: Optional[datetime]
    last_run_at: Optional[datetime]


@dataclass(frozen=True)
class ContactRecord:
    email: str
    display_name: str
    role: str


_SCHEMA = """
CREATE TABLE IF NOT EXISTS agents (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    last_user_activity_at TEXT,
    last_run_at TEXT,
    embedding BLOB
);
CREATE TABLE IF NOT EXISTS agent_contacts (
    agent_id TEXT NOT NULL REFERENCES agents(id),
    email TEXT NOT NULL,
    display_name TEXT NOT NULL DEFAULT '',
    role TEXT NOT NULL DEFAULT 'to',
    PRIMARY KEY (agent_id, email)
);
CREATE INDEX IF NOT EXISTS idx_agent_contacts_email ON agent_contacts(email);
CREATE VIRTUAL TABLE IF NOT EXISTS agents_fts USING fts5(
    agent_id UNINDEXED, search_text, tokenize='unicode61 remove_diacritics 2'
);
"""


def _dt(value: Optional[str]) -> Optional[datetime]:
    return datetime.fromisoformat(value) if value else None


def _iso(value: Optional[datetime]) -> Optional[str]:
    return value.isoformat() if value else None


def _row_to_agent(row: sqlite3.Row) -> AgentRecord:
    return AgentRecord(
        id=row["id"],
        name=row["name"],
        description=row["description"],
        created_at=_dt(row["created_at"]),
        last_user_activity_at=_dt(row["last_user_activity_at"]),
        last_run_at=_dt(row["last_run_at"]),
    )


def _new_id() -> str:
    return "ag_" + base64.b32encode(secrets.token_bytes(5)).decode().lower()


def _fts_query(text: str) -> str:
    """Quote and OR the non-stopword tokens of ``text`` (original case kept); "" if none remain.

    Stopwords are dropped because one makes nearly every agent match, so every agent gets a BM25 rank
    and rare exact matches (a person's name) lose their weight in rank fusion.
    """
    tokens = [t for t in re.findall(r"[^\W_]+", text) if t.lower() not in STOPWORDS]
    return " OR ".join(f'"{t}"' for t in tokens)


class AgentStore:
    def __init__(self, db_path: Path):
        self._path = Path(db_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        return conn

    def _run(self, sql: str, params: tuple = ()) -> None:
        with self._lock, closing(self._connect()) as conn, conn:
            conn.execute(sql, params)

    def _query(self, sql: str, params: tuple = ()) -> List[sqlite3.Row]:
        with closing(self._connect()) as conn:
            return conn.execute(sql, params).fetchall()

    def create_agent(self, name: str, description: str = "") -> AgentRecord:
        now = datetime.now().astimezone()
        for _ in range(10):
            record = AgentRecord(_new_id(), name, description, now, None, None)
            try:
                self.insert_agent(record)
                return record
            except sqlite3.IntegrityError:
                continue
        raise RuntimeError("could not allocate a unique agent id")

    def insert_agent(self, record: AgentRecord) -> None:
        self._run(
            "INSERT INTO agents (id, name, description, created_at, last_user_activity_at, last_run_at)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (record.id, record.name, record.description, _iso(record.created_at),
             _iso(record.last_user_activity_at), _iso(record.last_run_at)),
        )

    def get(self, agent_id: str) -> Optional[AgentRecord]:
        rows = self._query("SELECT * FROM agents WHERE id = ?", (agent_id,))
        return _row_to_agent(rows[0]) if rows else None

    def list_agents(self) -> List[AgentRecord]:
        return [_row_to_agent(r) for r in self._query("SELECT * FROM agents ORDER BY created_at, id")]

    def update_description(self, agent_id: str, text: str) -> None:
        self._run("UPDATE agents SET description = ? WHERE id = ?", (text, agent_id))

    def add_contacts(self, agent_id: str, contacts: List[ContactRecord]) -> None:
        with self._lock, closing(self._connect()) as conn, conn:
            for c in contacts:
                # A later record only fills an empty display_name; the first role is kept.
                conn.execute(
                    "INSERT INTO agent_contacts (agent_id, email, display_name, role)"
                    " VALUES (?, ?, ?, ?)"
                    " ON CONFLICT(agent_id, email) DO UPDATE SET display_name = excluded.display_name"
                    " WHERE agent_contacts.display_name = '' AND excluded.display_name != ''",
                    (agent_id, c.email.strip().lower(), c.display_name, c.role),
                )

    def fill_contact_names(self, agent_id: str, names: Dict[str, str]) -> None:
        """Set display names of this agent's existing contacts whose name is empty; never adds rows."""
        with self._lock, closing(self._connect()) as conn, conn:
            for email, name in names.items():
                if name and name.strip():
                    conn.execute(
                        "UPDATE agent_contacts SET display_name = ?"
                        " WHERE agent_id = ? AND email = ? AND display_name = ''",
                        (name.strip(), agent_id, email.strip().lower()),
                    )

    def contacts_for(self, agent_id: str) -> List[ContactRecord]:
        rows = self._query(
            "SELECT email, display_name, role FROM agent_contacts WHERE agent_id = ? ORDER BY rowid",
            (agent_id,),
        )
        return [ContactRecord(r["email"], r["display_name"], r["role"]) for r in rows]

    def agents_for_email(self, email: str) -> List[str]:
        rows = self._query(
            "SELECT agent_id FROM agent_contacts WHERE email = ? ORDER BY rowid",
            (email.strip().lower(),),
        )
        return [r["agent_id"] for r in rows]

    def find_contacts_by_name(self, name: str) -> List[ContactRecord]:
        """Case-insensitive match on full name or first name; one result per email."""
        wanted = " ".join(name.split()).casefold()
        if not wanted:
            return []
        found: dict = {}
        for r in self._query("SELECT email, display_name, role FROM agent_contacts ORDER BY rowid"):
            full = " ".join(r["display_name"].split()).casefold()
            if not full:
                continue
            if wanted == full or wanted == full.split(" ")[0]:
                found.setdefault(r["email"], ContactRecord(r["email"], r["display_name"], r["role"]))
        return sorted(found.values(), key=lambda c: c.email)

    def record_use(self, agent_id: str, source: Literal["user", "trigger", "agent"], at: datetime) -> None:
        if source == "user":
            self._run(
                "UPDATE agents SET last_run_at = ?, last_user_activity_at = ? WHERE id = ?",
                (_iso(at), _iso(at), agent_id),
            )
        else:
            self._run("UPDATE agents SET last_run_at = ? WHERE id = ?", (_iso(at), agent_id))

    def set_search_text(self, agent_id: str, text: str) -> None:
        with self._lock, closing(self._connect()) as conn, conn:
            conn.execute("DELETE FROM agents_fts WHERE agent_id = ?", (agent_id,))
            conn.execute("INSERT INTO agents_fts (agent_id, search_text) VALUES (?, ?)", (agent_id, text))

    def set_embedding(self, agent_id: str, vec: np.ndarray) -> None:
        blob = np.asarray(vec, dtype=np.float32).tobytes()
        self._run("UPDATE agents SET embedding = ? WHERE id = ?", (blob, agent_id))

    def embeddings(self, dim: Optional[int] = None) -> Tuple[List[str], np.ndarray]:
        """Ids and a float32 matrix (n, D) of rows whose vector length is ``dim``.

        With ``dim=None`` the most common length wins (ties go to the smaller length). Never raises on
        mixed lengths; an empty result is a 2-D array of shape (0, dim or 0).
        """
        rows = self._query("SELECT id, embedding FROM agents WHERE embedding IS NOT NULL ORDER BY id")
        vecs = [(r["id"], np.frombuffer(r["embedding"], dtype=np.float32)) for r in rows]
        if dim is None and vecs:
            counts: dict = {}
            for _, v in vecs:
                counts[len(v)] = counts.get(len(v), 0) + 1
            dim = min(counts, key=lambda n: (-counts[n], n))
        vecs = [(i, v) for i, v in vecs if len(v) == dim]
        if not vecs:
            return [], np.zeros((0, dim or 0), dtype=np.float32)
        return [i for i, _ in vecs], np.stack([v for _, v in vecs])

    def fts_search(self, query: str, limit: int) -> List[Tuple[str, float]]:
        """BM25 search; score is -bm25() so higher is better. Never raises on odd input."""
        match = _fts_query(query)
        if not match:
            return []
        rows = self._query(
            "SELECT agent_id, bm25(agents_fts) AS score FROM agents_fts"
            " WHERE agents_fts MATCH ? AND agent_id IN (SELECT id FROM agents)"
            " ORDER BY score LIMIT ?",
            (match, limit),
        )
        return [(r["agent_id"], -float(r["score"])) for r in rows]

    def ids_needing_embedding(self, dim: int) -> List[str]:
        rows = self._query(
            "SELECT id FROM agents WHERE embedding IS NULL OR length(embedding) != ? ORDER BY id", (dim * 4,)
        )
        return [r["id"] for r in rows]

    def clear(self) -> None:
        with self._lock, closing(self._connect()) as conn, conn:
            for table in ("agents_fts", "agent_contacts", "agents"):
                conn.execute(f"DELETE FROM {table}")


_store: Optional[AgentStore] = None
_store_lock = threading.Lock()


def get_agent_store() -> AgentStore:
    global _store
    if _store is None:
        with _store_lock:
            if _store is None:
                _store = AgentStore(_DEFAULT_DB_PATH)
    return _store
