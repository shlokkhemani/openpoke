from __future__ import annotations

import sqlite3
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional

from ...logging_config import logger
from .models import TriggerRecord
from .utils import to_storage_timestamp, utc_now


class TriggerStore:
    """Low-level persistence for triggers backed by SQLite."""

    def __init__(self, db_path: Path):
        self._db_path = db_path
        self._lock = threading.Lock()
        self._ensure_directory()
        self._ensure_schema()

    def _ensure_directory(self) -> None:
        try:
            self._db_path.parent.mkdir(parents=True, exist_ok=True)
        except Exception as exc:  # pragma: no cover - defensive
            logger.warning(
                "trigger directory creation failed",
                extra={"error": str(exc)},
            )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path, timeout=30, isolation_level=None)
        conn.row_factory = sqlite3.Row
        return conn

    def _ensure_schema(self) -> None:
        schema_sql = """
        CREATE TABLE IF NOT EXISTS triggers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            agent_name TEXT NOT NULL,
            created_by TEXT,
            shared INTEGER NOT NULL DEFAULT 0,
            payload TEXT NOT NULL,
            start_time TEXT,
            next_trigger TEXT,
            recurrence_rule TEXT,
            timezone TEXT,
            status TEXT NOT NULL DEFAULT 'active',
            last_error TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );
        """
        index_sql = """
        CREATE INDEX IF NOT EXISTS idx_triggers_agent_next
        ON triggers (agent_name, next_trigger);
        """
        with self._lock, self._connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute(schema_sql)
            self._migrate_columns(conn)
            conn.execute(index_sql)

    def _migrate_columns(self, conn: sqlite3.Connection) -> None:
        """Add provenance columns to databases created before they existed.

        Existing rows keep NULL ``created_by`` and ``shared = 0``, so their
        visibility stays exactly as it was until a backfill assigns an owner.
        """
        existing = {
            row["name"]
            for row in conn.execute("PRAGMA table_info(triggers)").fetchall()
        }
        if "created_by" not in existing:
            conn.execute("ALTER TABLE triggers ADD COLUMN created_by TEXT")
            logger.info("trigger schema migrated: added created_by")
        if "shared" not in existing:
            conn.execute(
                "ALTER TABLE triggers ADD COLUMN shared INTEGER NOT NULL DEFAULT 0"
            )
            logger.info("trigger schema migrated: added shared")

    def insert(self, payload: Dict[str, Any]) -> int:
        with self._lock, self._connect() as conn:
            columns = ", ".join(payload.keys())
            placeholders = ", ".join([":" + key for key in payload.keys()])
            sql = f"INSERT INTO triggers ({columns}) VALUES ({placeholders})"
            conn.execute(sql, payload)
            trigger_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
            return int(trigger_id)

    def fetch_one(self, trigger_id: int, agent_name: str) -> Optional[TriggerRecord]:
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM triggers WHERE id = ? AND agent_name = ?",
                (trigger_id, agent_name),
            ).fetchone()
        return self._row_to_record(row) if row else None

    def update(self, trigger_id: int, agent_name: str, fields: Dict[str, Any]) -> bool:
        if not fields:
            return False
        assignments = ", ".join(f"{key} = :{key}" for key in fields.keys())
        sql = (
            f"UPDATE triggers SET {assignments}, updated_at = :updated_at"
            " WHERE id = :trigger_id AND agent_name = :agent_name"
        )
        payload = {
            **fields,
            "updated_at": to_storage_timestamp(utc_now()),
            "trigger_id": trigger_id,
            "agent_name": agent_name,
        }
        with self._lock, self._connect() as conn:
            cursor = conn.execute(sql, payload)
            return cursor.rowcount > 0

    def list_for_agent(self, agent_name: str) -> List[TriggerRecord]:
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM triggers WHERE agent_name = ? ORDER BY next_trigger IS NULL, next_trigger",
                (agent_name,),
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def list_visible_to(self, agent_name: str) -> List[TriggerRecord]:
        """Triggers this agent owns plus any shared ones.

        Visibility is by ownership, not by the row's ``agent_name`` alone, so a
        shared reminder store does not leak one agent's reminders to another.
        """
        with self._lock, self._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM triggers WHERE agent_name = ? OR created_by = ? OR shared = 1"
                " ORDER BY next_trigger IS NULL, next_trigger",
                (agent_name, agent_name),
            ).fetchall()
        return [self._row_to_record(row) for row in rows]

    def fetch_visible(self, trigger_id: int, agent_name: str) -> Optional[TriggerRecord]:
        """Return one trigger if this agent may see it, else None."""
        with self._lock, self._connect() as conn:
            row = conn.execute(
                "SELECT * FROM triggers WHERE id = ?"
                " AND (agent_name = ? OR created_by = ? OR shared = 1)",
                (trigger_id, agent_name, agent_name),
            ).fetchone()
        return self._row_to_record(row) if row else None

    def update_visible(
        self, trigger_id: int, agent_name: str, fields: Dict[str, Any]
    ) -> bool:
        """Update a trigger only if this agent is allowed to touch it."""
        if not fields:
            return False
        assignments = ", ".join(f"{key} = :{key}" for key in fields.keys())
        sql = (
            f"UPDATE triggers SET {assignments}, updated_at = :updated_at"
            " WHERE id = :trigger_id"
            " AND (agent_name = :agent_name OR created_by = :agent_name OR shared = 1)"
        )
        payload = {
            **fields,
            "updated_at": to_storage_timestamp(utc_now()),
            "trigger_id": trigger_id,
            "agent_name": agent_name,
        }
        with self._lock, self._connect() as conn:
            cursor = conn.execute(sql, payload)
            return cursor.rowcount > 0

    def assign_owner(
        self, trigger_id: int, *, owner_id: str, created_by: Optional[str] = None
    ) -> bool:
        """Move a trigger to a reserved owner while preserving its creator."""
        fields: Dict[str, Any] = {"agent_name": owner_id}
        if created_by:
            fields["created_by"] = created_by
        with self._lock, self._connect() as conn:
            cursor = conn.execute(
                "UPDATE triggers SET agent_name = :owner_id,"
                " created_by = COALESCE(:created_by, created_by),"
                " updated_at = :updated_at WHERE id = :trigger_id",
                {
                    "owner_id": owner_id,
                    "created_by": created_by,
                    "updated_at": to_storage_timestamp(utc_now()),
                    "trigger_id": trigger_id,
                },
            )
            return cursor.rowcount > 0

    def list_all(self) -> List[TriggerRecord]:
        """Every trigger regardless of owner. Used by migration only."""
        with self._lock, self._connect() as conn:
            rows = conn.execute("SELECT * FROM triggers ORDER BY id").fetchall()
        return [self._row_to_record(row) for row in rows]

    def fetch_due(
        self, agent_name: Optional[str], before_iso: str
    ) -> List[TriggerRecord]:
        sql = (
            "SELECT * FROM triggers WHERE status = 'active' AND next_trigger IS NOT NULL"
            " AND next_trigger <= ?"
        )
        params: List[Any] = [before_iso]
        if agent_name:
            sql += " AND agent_name = ?"
            params.append(agent_name)
        sql += " ORDER BY next_trigger, id"
        with self._lock, self._connect() as conn:
            rows = conn.execute(sql, params).fetchall()
        return [self._row_to_record(row) for row in rows]

    def clear_all(self) -> None:
        with self._lock, self._connect() as conn:
            conn.execute("DELETE FROM triggers")

    def _row_to_record(self, row: sqlite3.Row) -> TriggerRecord:
        data = dict(row)
        # SQLite stores booleans as integers; normalize so the model stays honest.
        data["shared"] = bool(data.get("shared") or 0)
        return TriggerRecord.model_validate(data)


__all__ = ["TriggerStore"]
