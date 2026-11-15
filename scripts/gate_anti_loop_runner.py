#!/usr/bin/env python3
"""Anti-Loop & Crash-Resume Gate Runner — fail-closed verification of Skill 90c invariants.

Verifies:
  1. Identical action repetition trips LoopDetectedError.
  2. Alternating A->B->A->B oscillation trips OscillationDetectedError.
  3. Consecutive failures trip ConsecutiveFailureError.
  4. Step budget ceiling trips StepBudgetExceededError.
  5. Crash recovery via resume_run() preserves completed steps without re-execution.
  6. SHA-256 checkpoint save/restore rejects tampered payloads.

Usage:
    python scripts/gate_anti_loop_runner.py
    python scripts/gate_anti_loop_runner.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from run_ledger.core.checkpoint import RunCheckpointManager
from run_ledger.core.circuit_breaker import (
    AntiLoopCircuitBreaker,
    ConsecutiveFailureError,
    LoopDetectedError,
    OscillationDetectedError,
    StepBudgetExceededError,
)
from run_ledger.core.ledger import RunLedger
from run_ledger.core.models import CircuitBreakerConfig, RunStatus


@dataclass(frozen=True)
class GateCheck:
    name: str
    passed: bool
    detail: str


def run_gate() -> dict[str, Any]:
    """Run all fail-closed anti-loop and resumability gates."""
    checks: list[GateCheck] = []

    # 1. Loop detection
    cb_loop = AntiLoopCircuitBreaker(CircuitBreakerConfig(max_repeated_actions=2))
    tripped_loop = False
    try:
        for _ in range(3):
            cb_loop.check_allowed("search_web", {"q": "same"})
            cb_loop.record_action_start("search_web", {"q": "same"})
    except LoopDetectedError:
        tripped_loop = True
    checks.append(GateCheck("loop_detection", tripped_loop, "LoopDetectedError raised on identical repetition"))

    # 2. Oscillation detection
    cb_osc = AntiLoopCircuitBreaker(CircuitBreakerConfig(oscillation_window=4))
    tripped_osc = False
    try:
        for i in range(6):
            name = "tool_a" if i % 2 == 0 else "tool_b"
            payload = {"i": i % 2}
            cb_osc.check_allowed(name, payload)
            cb_osc.record_action_start(name, payload)
    except OscillationDetectedError:
        tripped_osc = True
    checks.append(GateCheck("oscillation_detection", tripped_osc, "OscillationDetectedError raised on A->B->A->B"))

    # 3. Consecutive failures
    cb_fail = AntiLoopCircuitBreaker(CircuitBreakerConfig(max_consecutive_failures=2))
    tripped_fail = False
    try:
        cb_fail.record_failure()
        cb_fail.record_failure()
        cb_fail.check_allowed("step_after_fail", {})
    except ConsecutiveFailureError:
        tripped_fail = True
    checks.append(GateCheck("consecutive_failures", tripped_fail, "ConsecutiveFailureError raised at ceiling"))

    # 4. Step budget ceiling
    cb_budget = AntiLoopCircuitBreaker(CircuitBreakerConfig(max_total_steps=2))
    tripped_budget = False
    try:
        for i in range(3):
            cb_budget.check_allowed(f"s{i}", {"i": i})
            cb_budget.record_action_start(f"s{i}", {"i": i})
    except StepBudgetExceededError:
        tripped_budget = True
    checks.append(GateCheck("step_budget_ceiling", tripped_budget, "StepBudgetExceededError raised at max_total_steps"))

    # 5. Crash recovery + SHA-256 checkpoint integrity
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db = str(Path(tmp) / "gate.db")
        ledger = RunLedger.with_sqlite(db)
        run = ledger.create_run(intent="gate_resume_test")
        with ledger.execute_step(run.id, "step_one", inputs={"k": 1}) as s1:
            s1.outputs = {"v": 1}

        try:
            with ledger.execute_step(run.id, "step_two", inputs={"k": 2}):
                raise RuntimeError("simulated crash")
        except RuntimeError:
            pass

        ledger2 = RunLedger.with_sqlite(db)
        resumed = ledger2.resume_run(run.id)
        with ledger2.execute_step(resumed.id, "step_two", inputs={"k": 2}) as s2:
            s2.outputs = {"v": 2}
        final_run = ledger2.get_run(resumed.id)
        resume_ok = final_run is not None and final_run.status == RunStatus.COMPLETED and final_run.completed_steps >= 2
        checks.append(GateCheck("crash_resume_preservation", resume_ok, "Completed steps preserved across crash"))

        cp_path = Path(tmp) / "cp.json"
        steps = ledger2.storage.get_steps_for_run(final_run.id)
        RunCheckpointManager.save_to_file(final_run, steps, cp_path)
        payload = json.loads(cp_path.read_text(encoding="utf-8"))
        payload["run"]["intent"] = "tampered"
        cp_path.write_text(json.dumps(payload), encoding="utf-8")
        tamper_rejected = False
        try:
            RunCheckpointManager.restore_from_file(cp_path)
        except ValueError:
            tamper_rejected = True
        checks.append(GateCheck("checkpoint_tamper_rejection", tamper_rejected, "Tampered SHA-256 checkpoint rejected"))

    approved = all(c.passed for c in checks)
    return {
        "status": "approved" if approved else "rejected",
        "approved": approved,
        "checks": [asdict(c) for c in checks],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Agent Run Ledger fail-closed gate.")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    args = parser.parse_args(argv)

    result = run_gate()
    if args.json:
        print(json.dumps(result, indent=2))
    else:
        print(f"Gate Status: {result['status'].upper()}")
        for c in result["checks"]:
            mark = "PASS" if c["passed"] else "FAIL"
            print(f"  [{mark}] {c['name']}: {c['detail']}")
    return 0 if result["approved"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
