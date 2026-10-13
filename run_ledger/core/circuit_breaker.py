"""
Anti-Loop Circuit Breaker for Autonomous AI Agents.

Implements Benni Master OS Skill 90c (Run Ledger Protocol):
Guards against infinite loops, recursive tool hallucinations, oscillating agent ping-pong,
and unbounded token/step expenditure.
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Dict, List, Optional

from run_ledger.core.models import CircuitBreakerConfig


class CircuitBreakerTripped(Exception):
    """Base exception raised when anti-loop circuit breaker trips to protect agent execution."""
    def __init__(self, message: str, reason: str, details: Optional[Dict[str, Any]] = None):
        super().__init__(message)
        self.reason = reason
        self.details = details or {}


class LoopDetectedError(CircuitBreakerTripped):
    """Raised when an identical action or input is repeated beyond the safe threshold."""
    pass


class OscillationDetectedError(CircuitBreakerTripped):
    """Raised when agent ping-pongs between alternating states without forward progress."""
    pass


class ConsecutiveFailureError(CircuitBreakerTripped):
    """Raised when consecutive step failures exceed the tolerance threshold."""
    pass


class StepBudgetExceededError(CircuitBreakerTripped):
    """Raised when the aggregate step count exceeds the safety ceiling."""
    pass


class AntiLoopCircuitBreaker:
    """
    Monitors execution history in real-time, detecting pathological loop patterns
    and tripping the circuit before runaway resource consumption occurs.
    """

    def __init__(self, config: Optional[CircuitBreakerConfig] = None):
        self.config = config or CircuitBreakerConfig()
        self.action_history: List[str] = []
        self.input_hash_history: List[str] = []
        self.consecutive_failures: int = 0
        self.total_steps_recorded: int = 0
        self._tripped: bool = False
        self._trip_reason: Optional[str] = None

    @property
    def is_tripped(self) -> bool:
        return self._tripped

    @property
    def trip_reason(self) -> Optional[str]:
        return self._trip_reason

    def _hash_inputs(self, inputs: Dict[str, Any]) -> str:
        """Deterministic hash of step inputs."""
        encoded = json.dumps(inputs, sort_keys=True, default=str).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()[:16]

    def check_allowed(self, step_name: str, inputs: Optional[Dict[str, Any]] = None) -> None:
        """
        Evaluates whether a planned step is safe to execute.
        Throws a specific CircuitBreakerTripped subclass if a loop is detected.
        """
        if self._tripped:
            raise CircuitBreakerTripped(
                f"[CIRCUIT-BREAKER TRIPPED] Run halted: {self._trip_reason}",
                reason=self._trip_reason or "already_tripped",
            )

        # 1. Total step budget ceiling
        if self.total_steps_recorded >= self.config.max_total_steps:
            self._trip(f"Maximum step budget exceeded ({self.config.max_total_steps} steps)")
            raise StepBudgetExceededError(
                f"[CIRCUIT-BREAKER] Total step budget of {self.config.max_total_steps} exceeded.",
                reason="max_total_steps_exceeded",
                details={"total_steps": self.total_steps_recorded},
            )

        # 2. Consecutive failure ceiling
        if self.consecutive_failures >= self.config.max_consecutive_failures:
            self._trip(f"Consecutive failures exceeded ({self.consecutive_failures} failures)")
            raise ConsecutiveFailureError(
                f"[CIRCUIT-BREAKER] Consecutive step failures reached {self.consecutive_failures}.",
                reason="consecutive_failures_exceeded",
                details={"failures": self.consecutive_failures},
            )

        # 3. Identical repeated action detection
        inp_hash = self._hash_inputs(inputs or {})
        combined_key = f"{step_name}:{inp_hash}"

        recent_actions = self.action_history[-self.config.max_repeated_actions :]
        if len(recent_actions) == self.config.max_repeated_actions:
            if all(a == combined_key for a in recent_actions):
                self._trip(f"Repeated identical action '{step_name}' ({self.config.max_repeated_actions} times)")
                raise LoopDetectedError(
                    f"[CIRCUIT-BREAKER LOOP DETECTED] Repeated identical action '{step_name}' with identical payload "
                    f"invoked {self.config.max_repeated_actions} times consecutively.",
                    reason="identical_action_loop",
                    details={"action": step_name, "repetitions": self.config.max_repeated_actions},
                )

        # 4. Oscillation pattern detection (e.g. A -> B -> A -> B)
        if len(self.action_history) >= self.config.oscillation_window:
            window = self.action_history[-self.config.oscillation_window :]
            # Pattern A, B, A, B
            if window[0] == window[2] and window[1] == window[3] and window[0] != window[1]:
                self._trip(f"Oscillating loop detected between '{window[0]}' and '{window[1]}'")
                raise OscillationDetectedError(
                    f"[CIRCUIT-BREAKER OSCILLATION] Agent is oscillating between '{window[0]}' and '{window[1]}'.",
                    reason="state_oscillation",
                    details={"sequence": window},
                )

    def record_action_start(self, step_name: str, inputs: Optional[Dict[str, Any]] = None) -> None:
        """Records the initiation of a step for loop tracking."""
        inp_hash = self._hash_inputs(inputs or {})
        combined_key = f"{step_name}:{inp_hash}"
        self.action_history.append(combined_key)
        self.input_hash_history.append(inp_hash)
        self.total_steps_recorded += 1

    def record_success(self) -> None:
        """Resets the consecutive failure counter upon a successful step."""
        self.consecutive_failures = 0

    def record_failure(self) -> None:
        """Increments consecutive failure counter."""
        self.consecutive_failures += 1

    def _trip(self, reason: str) -> None:
        """Internally locks the breaker into tripped state."""
        self._tripped = True
        self._trip_reason = reason

    def reset(self) -> None:
        """Resets circuit breaker state for a resumed or re-calibrated run."""
        self._tripped = False
        self._trip_reason = None
        self.consecutive_failures = 0
