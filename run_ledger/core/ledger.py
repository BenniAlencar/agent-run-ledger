"""
RunLedger Engine — The Durable Multi-Step Execution State Machine.

Derived from Benni Master OS Skill 90c (Run Ledger Protocol):
Guarantees crash-resilient step tracking, zero-cost resume, anti-loop tripwires,
and idempotent execution for autonomous AI agents.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Any, Callable, Dict, Generator, List, Optional, Union

from run_ledger.core.circuit_breaker import AntiLoopCircuitBreaker
from run_ledger.core.models import (
    CircuitBreakerConfig,
    RunRecord,
    RunStatus,
    StepRecord,
    StepStatus,
    StepType,
    _iso_now,
)
from run_ledger.storage.base import BaseLedgerStorage
from run_ledger.storage.memory import InMemoryLedgerStorage
from run_ledger.storage.sqlite import SqliteLedgerStorage


class RunLedger:
    """
    Coordinates and persists multi-step agent runs, enforcing state transitions,
    anti-loop circuit protection, and crash-resilient rehydration.
    """

    def __init__(
        self,
        storage: Optional[BaseLedgerStorage] = None,
        circuit_config: Optional[CircuitBreakerConfig] = None,
    ):
        self.storage: BaseLedgerStorage = storage or InMemoryLedgerStorage()
        self.circuit_breaker = AntiLoopCircuitBreaker(config=circuit_config)

    @classmethod
    def with_sqlite(cls, db_path: str = "agent_runs.db", circuit_config: Optional[CircuitBreakerConfig] = None) -> RunLedger:
        """Convenience constructor using durable SQLite storage."""
        return cls(storage=SqliteLedgerStorage(db_path), circuit_config=circuit_config)

    def create_run(
        self,
        intent: str,
        context: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> RunRecord:
        """Initializes and persists a new agent run."""
        run = RunRecord(
            intent=intent,
            status=RunStatus.PENDING,
            context=context or {},
            metadata=metadata or {},
        )
        self.storage.save_run(run)
        return run

    def add_step(
        self,
        run_id: str,
        name: str,
        step_type: StepType = StepType.TOOL_CALL,
        inputs: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
        max_retries: int = 3,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> StepRecord:
        """Appends an ordered step to a run."""
        run = self.storage.get_run(run_id)
        if not run:
            raise ValueError(f"Run '{run_id}' not found.")

        existing_steps = self.storage.get_steps_for_run(run_id)
        step_number = len(existing_steps) + 1

        step = StepRecord(
            run_id=run_id,
            step_number=step_number,
            name=name,
            step_type=step_type,
            status=StepStatus.PENDING,
            idempotency_key=idempotency_key,
            inputs=inputs or {},
            max_retries=max_retries,
            metadata=metadata or {},
        ).seal()

        self.storage.save_step(step)

        run.total_steps = len(existing_steps) + 1
        run.updated_at = _iso_now()
        self.storage.save_run(run)

        return step

    @contextmanager
    def execute_step(
        self,
        run_id: str,
        name: str,
        step_type: StepType = StepType.TOOL_CALL,
        inputs: Optional[Dict[str, Any]] = None,
        idempotency_key: Optional[str] = None,
        max_retries: int = 3,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Generator[StepRecord, None, None]:
        """
        Guarded execution context manager for a single agent step.
        Enforces circuit breaker check, idempotency check, status transitions,
        timing, and durable error recording.
        """
        # 1. Circuit breaker gate
        self.circuit_breaker.check_allowed(name, inputs)

        run = self.storage.get_run(run_id)
        if not run:
            raise ValueError(f"Run '{run_id}' not found.")

        # 2. Idempotency check: if already completed with identical key in this run, return cached
        if idempotency_key:
            existing = self.storage.get_steps_for_run(run_id)
            for prev in existing:
                if prev.idempotency_key == idempotency_key and prev.status == StepStatus.COMPLETED:
                    # Already executed successfully
                    yield prev
                    return

        # 3. Check if re-attempting an existing failed step in this run
        existing_steps = self.storage.get_steps_for_run(run_id)
        step = None
        for s in existing_steps:
            if s.name == name and s.status == StepStatus.FAILED:
                step = s
                step.attempt += 1
                step.error = None
                break

        if step is None:
            step = self.add_step(
                run_id=run_id,
                name=name,
                step_type=step_type,
                inputs=inputs,
                idempotency_key=idempotency_key,
                max_retries=max_retries,
                metadata=metadata,
            )

        # 4. Refresh run and transition to RUNNING
        run = self.storage.get_run(run_id)
        if run and run.status in (RunStatus.PENDING, RunStatus.FAILED):
            run.status = RunStatus.RUNNING
            self.storage.save_run(run)

        step.status = StepStatus.RUNNING
        step.started_at = _iso_now()
        self.storage.save_step(step)
        self.circuit_breaker.record_action_start(name, inputs)

        start_time = time.perf_counter()
        try:
            yield step
            # Step completed successfully
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            step.status = StepStatus.COMPLETED
            step.completed_at = _iso_now()
            step.duration_ms = round(duration_ms, 2)
            step.seal()
            self.storage.save_step(step)

            # Re-fetch all steps to accurately compute completed_steps and status
            all_steps = self.storage.get_steps_for_run(run_id)
            run = self.storage.get_run(run_id)
            if run:
                run.total_steps = len(all_steps)
                run.completed_steps = sum(1 for s in all_steps if s.status == StepStatus.COMPLETED)
                run.updated_at = _iso_now()
                if run.completed_steps == run.total_steps and run.total_steps > 0:
                    run.status = RunStatus.COMPLETED
                    run.completed_at = _iso_now()
                self.storage.save_run(run)
            self.circuit_breaker.record_success()

        except Exception as exc:
            duration_ms = (time.perf_counter() - start_time) * 1000.0
            step.duration_ms = round(duration_ms, 2)
            step.error = str(exc)
            step.status = StepStatus.FAILED
            step.completed_at = _iso_now()
            step.seal()
            self.storage.save_step(step)

            run = self.storage.get_run(run_id)
            if run:
                run.status = RunStatus.FAILED
                run.updated_at = _iso_now()
                self.storage.save_run(run)
            self.circuit_breaker.record_failure()
            raise

    def resume_run(self, run_id: str) -> RunRecord:
        """
        Rehydrates a failed, paused, or interrupted run to continue execution
        without repeating already completed steps.
        """
        run = self.storage.get_run(run_id)
        if not run:
            raise ValueError(f"Run '{run_id}' not found.")

        steps = self.storage.get_steps_for_run(run_id)
        # Rebuild context from outputs of completed steps
        rebuilt_context: Dict[str, Any] = dict(run.context)
        for s in steps:
            if s.status == StepStatus.COMPLETED and s.outputs:
                rebuilt_context.update(s.outputs)

        run.context = rebuilt_context
        run.status = RunStatus.RUNNING
        run.updated_at = _iso_now()
        self.storage.save_run(run)

        # Reset consecutive failures for the new attempt
        self.circuit_breaker.reset()
        return run

    def compensate_run(
        self,
        run_id: str,
        handlers: Dict[str, Callable[[StepRecord], Any]],
    ) -> List[StepRecord]:
        """
        Executes compensation / rollback handlers in reverse order for all completed steps.
        Useful when a multi-step financial or infrastructure run fails halfway.
        """
        steps = self.storage.get_steps_for_run(run_id)
        completed_steps = [s for s in steps if s.status == StepStatus.COMPLETED]
        rolled_back: List[StepRecord] = []

        for step in reversed(completed_steps):
            if step.name in handlers:
                handler = handlers[step.name]
                try:
                    handler(step)
                    step.status = StepStatus.ROLLED_BACK
                    step.seal()
                    self.storage.save_step(step)
                    rolled_back.append(step)
                except Exception as comp_err:
                    step.error = f"Compensation failed: {comp_err}"
                    self.storage.save_step(step)

        run = self.storage.get_run(run_id)
        if run:
            run.status = RunStatus.ABORTED
            run.updated_at = _iso_now()
            self.storage.save_run(run)

        return rolled_back

    def get_run(self, run_id: str) -> Optional[RunRecord]:
        return self.storage.get_run(run_id)

    def get_steps(self, run_id: str) -> List[StepRecord]:
        return self.storage.get_steps_for_run(run_id)

    def list_runs(self, limit: int = 50) -> List[RunRecord]:
        return self.storage.list_runs(limit=limit)
