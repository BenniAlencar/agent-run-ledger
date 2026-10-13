"""
Durable SQLite Storage Implementation for Agent Run Ledger.

Provides crash-resilient local persistence, ACID transaction guarantees,
and WAL indexing for high-concurrency multi-agent runs.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from run_ledger.core.models import RunRecord, RunStatus, StepRecord, StepStatus, StepType
from run_ledger.storage.base import BaseLedgerStorage


class SqliteLedgerStorage(BaseLedgerStorage):
    """ACID-compliant SQLite storage backend for durable agent run tracking."""

    def __init__(self, db_path: Union[str, Path] = "agent_runs.db"):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _get_conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=30.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

    def _init_schema(self) -> None:
        with self._get_conn() as conn:
            conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    intent TEXT NOT NULL,
                    status TEXT NOT NULL,
                    context TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    completed_at TEXT,
                    total_steps INTEGER NOT NULL,
                    completed_steps INTEGER NOT NULL,
                    metadata TEXT NOT NULL,
                    run_hash TEXT
                );

                CREATE TABLE IF NOT EXISTS steps (
                    id TEXT PRIMARY KEY,
                    run_id TEXT NOT NULL,
                    step_number INTEGER NOT NULL,
                    name TEXT NOT NULL,
                    step_type TEXT NOT NULL,
                    status TEXT NOT NULL,
                    idempotency_key TEXT,
                    inputs TEXT NOT NULL,
                    outputs TEXT,
                    error TEXT,
                    attempt INTEGER NOT NULL,
                    max_retries INTEGER NOT NULL,
                    started_at TEXT,
                    completed_at TEXT,
                    duration_ms REAL NOT NULL,
                    state_hash TEXT,
                    metadata TEXT NOT NULL,
                    FOREIGN KEY (run_id) REFERENCES runs(id)
                );

                CREATE INDEX IF NOT EXISTS idx_runs_status ON runs(status);
                CREATE INDEX IF NOT EXISTS idx_steps_run_id ON steps(run_id);
                CREATE INDEX IF NOT EXISTS idx_steps_status ON steps(status);
                CREATE INDEX IF NOT EXISTS idx_steps_idempotency ON steps(idempotency_key);
                """
            )

    def save_run(self, run: RunRecord) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO runs (
                    id, intent, status, context, created_at, updated_at,
                    completed_at, total_steps, completed_steps, metadata, run_hash
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    intent = excluded.intent,
                    status = excluded.status,
                    context = excluded.context,
                    updated_at = excluded.updated_at,
                    completed_at = excluded.completed_at,
                    total_steps = excluded.total_steps,
                    completed_steps = excluded.completed_steps,
                    metadata = excluded.metadata,
                    run_hash = excluded.run_hash
                """,
                (
                    run.id,
                    run.intent,
                    run.status.value,
                    json.dumps(run.context, default=str),
                    run.created_at,
                    run.updated_at,
                    run.completed_at,
                    run.total_steps,
                    run.completed_steps,
                    json.dumps(run.metadata, default=str),
                    run.run_hash,
                ),
            )

    def _row_to_run(self, row: sqlite3.Row) -> RunRecord:
        return RunRecord(
            id=row["id"],
            intent=row["intent"],
            status=RunStatus(row["status"]),
            context=json.loads(row["context"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            completed_at=row["completed_at"],
            total_steps=row["total_steps"],
            completed_steps=row["completed_steps"],
            metadata=json.loads(row["metadata"]),
            run_hash=row["run_hash"],
        )

    def get_run(self, run_id: str) -> Optional[RunRecord]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM runs WHERE id = ?", (run_id,)).fetchone()
            if row:
                return self._row_to_run(row)
        return None

    def list_runs(self, limit: int = 50) -> List[RunRecord]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,)
            ).fetchall()
            return [self._row_to_run(r) for r in rows]

    def save_step(self, step: StepRecord) -> None:
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT INTO steps (
                    id, run_id, step_number, name, step_type, status,
                    idempotency_key, inputs, outputs, error, attempt,
                    max_retries, started_at, completed_at, duration_ms,
                    state_hash, metadata
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status = excluded.status,
                    outputs = excluded.outputs,
                    error = excluded.error,
                    attempt = excluded.attempt,
                    completed_at = excluded.completed_at,
                    duration_ms = excluded.duration_ms,
                    state_hash = excluded.state_hash,
                    metadata = excluded.metadata
                """,
                (
                    step.id,
                    step.run_id,
                    step.step_number,
                    step.name,
                    step.step_type.value,
                    step.status.value,
                    step.idempotency_key,
                    json.dumps(step.inputs, default=str),
                    json.dumps(step.outputs, default=str) if step.outputs is not None else None,
                    step.error,
                    step.attempt,
                    step.max_retries,
                    step.started_at,
                    step.completed_at,
                    step.duration_ms,
                    step.state_hash,
                    json.dumps(step.metadata, default=str),
                ),
            )

    def _row_to_step(self, row: sqlite3.Row) -> StepRecord:
        return StepRecord(
            id=row["id"],
            run_id=row["run_id"],
            step_number=row["step_number"],
            name=row["name"],
            step_type=StepType(row["step_type"]),
            status=StepStatus(row["status"]),
            idempotency_key=row["idempotency_key"],
            inputs=json.loads(row["inputs"]),
            outputs=json.loads(row["outputs"]) if row["outputs"] is not None else None,
            error=row["error"],
            attempt=row["attempt"],
            max_retries=row["max_retries"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            duration_ms=row["duration_ms"],
            state_hash=row["state_hash"],
            metadata=json.loads(row["metadata"]),
        )

    def get_step(self, step_id: str) -> Optional[StepRecord]:
        with self._get_conn() as conn:
            row = conn.execute("SELECT * FROM steps WHERE id = ?", (step_id,)).fetchone()
            if row:
                return self._row_to_step(row)
        return None

    def get_steps_for_run(self, run_id: str) -> List[StepRecord]:
        with self._get_conn() as conn:
            rows = conn.execute(
                "SELECT * FROM steps WHERE run_id = ? ORDER BY step_number ASC",
                (run_id,),
            ).fetchall()
            return [self._row_to_step(r) for r in rows]
