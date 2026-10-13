"""
In-Memory Storage Implementation for Agent Run Ledger.
"""

from __future__ import annotations

from typing import Dict, List, Optional

from run_ledger.core.models import RunRecord, StepRecord
from run_ledger.storage.base import BaseLedgerStorage


class InMemoryLedgerStorage(BaseLedgerStorage):
    """Volatile, high-speed in-memory storage for ephemeral agent runs and unit tests."""

    def __init__(self):
        self._runs: Dict[str, RunRecord] = {}
        self._steps: Dict[str, StepRecord] = {}

    def save_run(self, run: RunRecord) -> None:
        self._runs[run.id] = run

    def get_run(self, run_id: str) -> Optional[RunRecord]:
        return self._runs.get(run_id)

    def list_runs(self, limit: int = 50) -> List[RunRecord]:
        ordered = sorted(self._runs.values(), key=lambda r: r.created_at, reverse=True)
        return ordered[:limit]

    def save_step(self, step: StepRecord) -> None:
        self._steps[step.id] = step

    def get_step(self, step_id: str) -> Optional[StepRecord]:
        return self._steps.get(step_id)

    def get_steps_for_run(self, run_id: str) -> List[StepRecord]:
        matching = [s for s in self._steps.values() if s.run_id == run_id]
        return sorted(matching, key=lambda s: s.step_number)
