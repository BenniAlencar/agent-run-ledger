"""
Tests for RunRecord, StepRecord, state hashing, and cross-version ISO date parsing.
"""

from datetime import datetime, timezone

from run_ledger.core.models import (
    RunRecord,
    RunStatus,
    StepRecord,
    StepStatus,
    StepType,
    _parse_dt,
)


def test_step_record_creation_and_sealing():
    step = StepRecord(
        run_id="run_test_01",
        step_number=1,
        name="web_search",
        step_type=StepType.TOOL_CALL,
        inputs={"query": "benni os autonomous swarms"},
    )

    assert step.status == StepStatus.PENDING
    assert step.state_hash is None

    step.seal()
    assert step.state_hash is not None
    assert len(step.state_hash) == 64  # SHA-256


def test_run_record_hash_determinism():
    run = RunRecord(
        id="run_fixed_01",
        intent="Automated financial audit",
        status=RunStatus.PENDING,
        context={"tenant": "enterprise_01"},
    )
    step1 = StepRecord(
        id="step_01",
        run_id="run_fixed_01",
        step_number=1,
        name="fetch_invoices",
        status=StepStatus.COMPLETED,
    ).seal()

    h1 = run.compute_hash([step1])
    h2 = run.compute_hash([step1])
    assert h1 == h2


def test_parse_dt_cross_version_compatibility():
    """Guarantees Python 3.10, 3.11, 3.12 compatibility for ISO timestamps."""
    # Standard +00:00
    dt1 = _parse_dt("2026-01-01T12:00:00+00:00")
    assert dt1.year == 2026
    assert dt1.tzinfo == timezone.utc

    # Trailing Z (Python 3.10 compatibility check)
    dt2 = _parse_dt("2026-01-01T12:00:00Z")
    assert dt2.year == 2026
    assert dt2.tzinfo == timezone.utc

    # Micros with Z
    dt3 = _parse_dt("2026-06-15T08:30:00.123456Z")
    assert dt3.microsecond == 123456
    assert dt3.tzinfo == timezone.utc
