"""
Atomic Checkpoint and Snapshot Protocol for Agent Runs.

Implements Benni Master OS Skill 61 (Snapshot Restore Protocol) applied to multi-step runs:
Provides tamper-evident serialization, state hydration, and SHA-256 verification.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Union

from pydantic import BaseModel, Field

from run_ledger.core.models import RunRecord, StepRecord


class RunSnapshotPayload(BaseModel):
    """Container for a sealed, exportable run snapshot."""
    system: str = "Benni Master OS Run Ledger v1.0.0"
    created_at: str
    run: Dict[str, Any]
    steps: List[Dict[str, Any]]
    snapshot_hash: str


class RunCheckpointManager:
    """Manages serializing and hydrating full agent runs with cryptographic integrity."""

    @staticmethod
    def create_snapshot(run: RunRecord, steps: List[StepRecord]) -> RunSnapshotPayload:
        now_str = datetime.now(timezone.utc).isoformat()
        run_data = run.model_dump()
        steps_data = [s.model_dump() for s in sorted(steps, key=lambda x: x.step_number)]

        digest_input = {
            "created_at": now_str,
            "run": run_data,
            "steps": steps_data,
        }
        encoded = json.dumps(digest_input, sort_keys=True, default=str).encode("utf-8")
        h = hashlib.sha256(encoded).hexdigest()

        return RunSnapshotPayload(
            created_at=now_str,
            run=run_data,
            steps=steps_data,
            snapshot_hash=h,
        )

    @staticmethod
    def save_to_file(run: RunRecord, steps: List[StepRecord], filepath: Union[str, Path]) -> Path:
        p = Path(filepath)
        p.parent.mkdir(parents=True, exist_ok=True)
        snapshot = RunCheckpointManager.create_snapshot(run, steps)
        with open(p, "w", encoding="utf-8") as f:
            f.write(snapshot.model_dump_json(indent=2))
        return p

    @staticmethod
    def restore_from_file(filepath: Union[str, Path]) -> tuple[RunRecord, List[StepRecord]]:
        p = Path(filepath)
        if not p.is_file():
            raise FileNotFoundError(f"Run checkpoint file not found: {p}")

        with open(p, "r", encoding="utf-8") as f:
            raw_data = json.load(f)

        payload = RunSnapshotPayload.model_validate(raw_data)

        # Integrity check
        digest_input = {
            "created_at": payload.created_at,
            "run": payload.run,
            "steps": sorted(payload.steps, key=lambda x: int(x.get("step_number", 0))),
        }
        recomputed = hashlib.sha256(json.dumps(digest_input, sort_keys=True, default=str).encode("utf-8")).hexdigest()

        if recomputed != payload.snapshot_hash:
            raise ValueError(
                f"[RUN-LEDGER INTEGRITY ERROR] Snapshot digest mismatch! "
                f"Expected {payload.snapshot_hash}, recomputed {recomputed}. File has been modified or corrupted."
            )

        run = RunRecord.model_validate(payload.run)
        steps = [StepRecord.model_validate(s) for s in payload.steps]
        return run, steps
