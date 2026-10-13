"""
Tests for crash recovery, run resumability, and cryptographic snapshots.
"""

from pathlib import Path
import pytest

from run_ledger.core.checkpoint import RunCheckpointManager
from run_ledger.core.ledger import RunLedger
from run_ledger.core.models import RunStatus, StepStatus, StepType


def test_run_resumability_after_failure(memory_ledger: RunLedger):
    run = memory_ledger.create_run(intent="Process ETL Pipeline", context={"batch_id": "b_100"})

    # Step 1 succeeds
    with memory_ledger.execute_step(run_id=run.id, name="extract_data", inputs={"src": "s3"}) as s1:
        s1.outputs = {"records_extracted": 500}

    # Step 2 fails (e.g. network glitch)
    with pytest.raises(ConnectionError):
        with memory_ledger.execute_step(run_id=run.id, name="transform_data", inputs={"model": "v1"}):
            raise ConnectionError("Transformation cluster offline")

    failed_run = memory_ledger.get_run(run.id)
    assert failed_run.status == RunStatus.FAILED
    assert failed_run.completed_steps == 1

    # Agent system resumes run!
    resumed_run = memory_ledger.resume_run(run.id)
    assert resumed_run.status == RunStatus.RUNNING
    # Context was enriched with step 1 outputs!
    assert resumed_run.context["records_extracted"] == 500

    # Step 2 retry succeeds
    with memory_ledger.execute_step(run_id=run.id, name="transform_data", inputs={"model": "v1"}) as s2_retry:
        s2_retry.outputs = {"transformed": True}

    final_run = memory_ledger.get_run(run.id)
    assert final_run.status == RunStatus.COMPLETED
    assert final_run.completed_steps == 2


def test_checkpoint_roundtrip_and_tamper_detection(temp_dir: Path, memory_ledger: RunLedger):
    run = memory_ledger.create_run(intent="Critical compliance audit")
    step = memory_ledger.add_step(run_id=run.id, name="scan_pii", inputs={"scope": "db"})
    step.status = StepStatus.COMPLETED
    step.outputs = {"pii_found": 0}
    step.seal()
    memory_ledger.storage.save_step(step)

    snapshot_file = temp_dir / "audit_snapshot.json"
    RunCheckpointManager.save_to_file(run, [step], snapshot_file)
    assert snapshot_file.exists()

    # Hydrate back
    hydrated_run, hydrated_steps = RunCheckpointManager.restore_from_file(snapshot_file)
    assert hydrated_run.id == run.id
    assert len(hydrated_steps) == 1
    assert hydrated_steps[0].outputs["pii_found"] == 0

    # Tamper with file
    raw = snapshot_file.read_text(encoding="utf-8")
    tampered_raw = raw.replace('"pii_found": 0', '"pii_found": 99')
    snapshot_file.write_text(tampered_raw, encoding="utf-8")

    with pytest.raises(ValueError) as exc_info:
        RunCheckpointManager.restore_from_file(snapshot_file)

    assert "Snapshot digest mismatch" in str(exc_info.value)
