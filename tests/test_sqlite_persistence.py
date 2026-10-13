"""
Tests for durable SqliteLedgerStorage.
"""

from run_ledger.core.ledger import RunLedger
from run_ledger.core.models import RunStatus, StepStatus


def test_sqlite_run_and_step_persistence(sqlite_ledger: RunLedger):
    run = sqlite_ledger.create_run(intent="Persistent test mission", context={"env": "prod"})

    with sqlite_ledger.execute_step(run_id=run.id, name="validate_dns", inputs={"domain": "bennios.dev"}) as s:
        s.outputs = {"resolved_ip": "104.21.5.12"}

    # Fetch from storage to verify database rows
    retrieved_run = sqlite_ledger.get_run(run.id)
    assert retrieved_run is not None
    assert retrieved_run.status == RunStatus.COMPLETED
    assert retrieved_run.context["env"] == "prod"

    steps = sqlite_ledger.get_steps(run.id)
    assert len(steps) == 1
    assert steps[0].name == "validate_dns"
    assert steps[0].status == StepStatus.COMPLETED
    assert steps[0].outputs["resolved_ip"] == "104.21.5.12"


def test_sqlite_list_runs(sqlite_ledger: RunLedger):
    for i in range(3):
        sqlite_ledger.create_run(intent=f"Mission {i}")

    runs = sqlite_ledger.list_runs(limit=10)
    assert len(runs) >= 3
