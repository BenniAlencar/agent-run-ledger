"""
Abstract interface for Agent Run Ledger persistence backends.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import List, Optional

from run_ledger.core.models import RunRecord, StepRecord


class BaseLedgerStorage(ABC):
    """Abstract storage provider for durable run and step ledger persistence."""

    @abstractmethod
    def save_run(self, run: RunRecord) -> None:
        """Persists or updates a run record."""
        pass

    @abstractmethod
    def get_run(self, run_id: str) -> Optional[RunRecord]:
        """Retrieves a run record by its unique ID."""
        pass

    @abstractmethod
    def list_runs(self, limit: int = 50) -> List[RunRecord]:
        """Lists recent runs ordered chronologically."""
        pass

    @abstractmethod
    def save_step(self, step: StepRecord) -> None:
        """Persists or updates a discrete step record."""
        pass

    @abstractmethod
    def get_step(self, step_id: str) -> Optional[StepRecord]:
        """Retrieves a step record by its ID."""
        pass

    @abstractmethod
    def get_steps_for_run(self, run_id: str) -> List[StepRecord]:
        """Retrieves all steps belonging to a run, ordered by step_number."""
        pass
