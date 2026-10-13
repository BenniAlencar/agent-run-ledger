"""
Tests for RunLedger step execution, idempotency, and compensation rollback.
"""

import pytest

from run_ledger.core.ledger import RunLedger
from run_ledger.core.models import RunStatus, StepStatus, StepType


def test_run_creation_and_step_execution(memory_ledger: RunLedger):
    run = memory_ledger.create_run(intent="Deploy API Gateway canary")
    assert run.status == RunStatus.PENDING

    # Execute step 1 successfully
    with memory_ledger.execute_step(
        run_id=run.id,
        name="verify_credentials",
        step_type=StepType.VERIFICATION,
        inputs={"provider": "aws"},
    ) as step:
        step.outputs = {"authenticated": True, "account_id": "123456"}

    updated_run = memory_ledger.get_run(run.id)
    assert updated_run is not None
    assert updated_run.completed_steps == 1
    assert updated_run.status == RunStatus.COMPLETED

    steps = memory_ledger.get_steps(run.id)
    assert len(steps) == 1
    assert steps[0].status == StepStatus.COMPLETED
    assert steps[0].outputs["authenticated"] is True
    assert steps[0].duration_ms >= 0.0


def test_step_idempotency(memory_ledger: RunLedger):
    run = memory_ledger.create_run(intent="Charge customer invoice")

    # First execution with idempotency key
    with memory_ledger.execute_step(
        run_id=run.id,
        name="stripe_charge",
        inputs={"amount_cents": 5000},
        idempotency_key="inv_unique_999",
    ) as step1:
        step1.outputs = {"charge_id": "ch_123", "status": "paid"}

    # Second execution attempt with identical idempotency key
    # Should reuse cached output without creating a duplicate step record!
    with memory_ledger.execute_step(
        run_id=run.id,
        name="stripe_charge",
        inputs={"amount_cents": 5000},
        idempotency_key="inv_unique_999",
    ) as step2:
        pass

    assert step2.outputs["charge_id"] == "ch_123"

    steps = memory_ledger.get_steps(run.id)
    assert len(steps) == 1  # Only 1 step was created!


def test_step_failure_and_run_status(memory_ledger: RunLedger):
    run = memory_ledger.create_run(intent="Run database migration")

    with pytest.raises(RuntimeError) as exc_info:
        with memory_ledger.execute_step(
            run_id=run.id,
            name="apply_migration",
            inputs={"migration_file": "002_add_indexes.sql"},
        ):
            raise RuntimeError("Database locked by another process")

    assert "Database locked" in str(exc_info.value)

    updated_run = memory_ledger.get_run(run.id)
    assert updated_run is not None
    assert updated_run.status == RunStatus.FAILED

    steps = memory_ledger.get_steps(run.id)
    assert len(steps) == 1
    assert steps[0].status == StepStatus.FAILED
    assert "Database locked" in steps[0].error


def test_compensation_rollback(memory_ledger: RunLedger):
    run = memory_ledger.create_run(intent="Provision multi-region cluster")

    # Step 1 succeeds
    with memory_ledger.execute_step(run_id=run.id, name="reserve_ips", inputs={"count": 2}) as s1:
        s1.outputs = {"ips": ["1.1.1.1", "2.2.2.2"]}

    # Step 2 succeeds
    with memory_ledger.execute_step(run_id=run.id, name="create_vpcs", inputs={"region": "us-east-1"}) as s2:
        s2.outputs = {"vpc_id": "vpc_888"}

    compensated_ips = []
    compensated_vpcs = []

    handlers = {
        "reserve_ips": lambda step: compensated_ips.extend(step.outputs["ips"]),
        "create_vpcs": lambda step: compensated_vpcs.append(step.outputs["vpc_id"]),
    }

    rolled_back = memory_ledger.compensate_run(run.id, handlers)
    assert len(rolled_back) == 2
    assert "vpc_888" in compensated_vpcs
    assert "1.1.1.1" in compensated_ips

    updated_run = memory_ledger.get_run(run.id)
    assert updated_run.status == RunStatus.ABORTED
