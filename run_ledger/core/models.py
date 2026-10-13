"""
Core data models and state enums for Agent Run Ledger.

Derived from Benni Master OS v9.4 Doctrine:
- Skill 90c (Run Ledger Protocol): typed step state machine with anti-loop enforcement.
- Skill 83 (Background Execution OS): durable checkpointing and idempotent retries.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


def _iso_now() -> str:
    """Returns current UTC timestamp in canonical ISO-8601 format."""
    return datetime.now(timezone.utc).isoformat()


def _parse_dt(iso_str: Any) -> datetime:
    """Parses ISO-8601 strings into timezone-aware UTC datetime across Python 3.10+."""
    if isinstance(iso_str, datetime):
        if iso_str.tzinfo is None:
            return iso_str.replace(tzinfo=timezone.utc)
        return iso_str

    clean = str(iso_str).strip()
    if clean.endswith("Z") or clean.endswith("z"):
        clean = clean[:-1] + "+00:00"

    try:
        dt = datetime.fromisoformat(clean)
        if dt.tzinfo is None:
            return dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime.now(timezone.utc)


class RunStatus(str, Enum):
    """Lifecycle states of an autonomous agent run."""
    PENDING = "pending"
    RUNNING = "running"
    PAUSED = "paused"
    COMPLETED = "completed"
    FAILED = "failed"
    ABORTED = "aborted"


class StepStatus(str, Enum):
    """Lifecycle states of a discrete step in a run."""
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    ROLLED_BACK = "rolled_back"


class StepType(str, Enum):
    """Categorical classification of step activities."""
    INFERENCE = "inference"
    TOOL_CALL = "tool_call"
    CHECKPOINT = "checkpoint"
    VERIFICATION = "verification"
    COMPENSATION = "compensation"


class StepRecord(BaseModel):
    """
    A discrete step within a multi-step agent run.
    Guarantees deterministic execution recording, timing, and SHA-256 state hashing.
    """
    id: str = Field(default_factory=lambda: f"step_{uuid.uuid4().hex[:12]}")
    run_id: str
    step_number: int
    name: str
    step_type: StepType = StepType.TOOL_CALL
    status: StepStatus = StepStatus.PENDING
    idempotency_key: Optional[str] = None
    inputs: Dict[str, Any] = Field(default_factory=dict)
    outputs: Optional[Dict[str, Any]] = None
    error: Optional[str] = None
    attempt: int = 1
    max_retries: int = 3
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    duration_ms: float = 0.0
    state_hash: Optional[str] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    def compute_hash(self) -> str:
        """Computes deterministic SHA-256 state hash for verification."""
        content = {
            "id": self.id,
            "run_id": self.run_id,
            "step_number": self.step_number,
            "name": self.name,
            "status": self.status.value,
            "inputs": self.inputs,
            "outputs": self.outputs,
            "error": self.error,
            "attempt": self.attempt,
        }
        encoded = json.dumps(content, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    def seal(self) -> StepRecord:
        """Seals the step record by generating and storing its state hash."""
        self.state_hash = self.compute_hash()
        return self


class RunRecord(BaseModel):
    """
    The aggregate run ledger governing a complete agent mission.
    Holds execution context, progress counters, and overall lifecycle state.
    """
    id: str = Field(default_factory=lambda: f"run_{uuid.uuid4().hex[:12]}")
    intent: str
    status: RunStatus = RunStatus.PENDING
    context: Dict[str, Any] = Field(default_factory=dict)
    created_at: str = Field(default_factory=_iso_now)
    updated_at: str = Field(default_factory=_iso_now)
    completed_at: Optional[str] = None
    total_steps: int = 0
    completed_steps: int = 0
    metadata: Dict[str, Any] = Field(default_factory=dict)
    run_hash: Optional[str] = None

    def compute_hash(self, steps: List[StepRecord]) -> str:
        """Computes aggregate SHA-256 digest across all steps."""
        step_hashes = [s.state_hash or s.compute_hash() for s in sorted(steps, key=lambda s: s.step_number)]
        content = {
            "id": self.id,
            "intent": self.intent,
            "status": self.status.value,
            "context": self.context,
            "step_hashes": step_hashes,
        }
        encoded = json.dumps(content, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()


class CircuitBreakerConfig(BaseModel):
    """Configuration governing anti-loop circuit breaker trip conditions."""
    max_consecutive_failures: int = 3
    max_repeated_actions: int = 3
    max_total_steps: int = 50
    oscillation_window: int = 4
    token_budget_limit: int = 100_000
