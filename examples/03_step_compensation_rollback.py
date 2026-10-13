"""
Example 03: Step Compensation & Rollback.

Demonstrates how Agent Run Ledger executes reverse-order compensation handlers
to undo side-effects when a multi-step financial or infrastructure run fails.
"""

import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from run_ledger import RunLedger

if __name__ == "__main__":
    print("--- [AGENT-RUN-LEDGER] Step Compensation & Rollback Demo ---")
    ledger = RunLedger()
    run = ledger.create_run(intent="Provision high-availability cloud database")

    # Step 1: Allocate static IP
    with ledger.execute_step(run_id=run.id, name="allocate_ip", inputs={"region": "us-east-1"}) as s1:
        s1.outputs = {"ip_address": "54.210.12.9"}
        print("   ✔ Step 1: Allocated static IP 54.210.12.9")

    # Step 2: Create EBS storage volume
    with ledger.execute_step(run_id=run.id, name="create_ebs_volume", inputs={"size_gb": 500}) as s2:
        s2.outputs = {"volume_id": "vol-0a1b2c3d"}
        print("   ✔ Step 2: Created EBS volume vol-0a1b2c3d")

    # Step 3 fails
    print("\nSimulating failure during database provisioning step...")
    try:
        with ledger.execute_step(run_id=run.id, name="provision_instance", inputs={"type": "r6g.2xlarge"}):
            raise RuntimeError("Cloud provider quota exceeded for instance type r6g.2xlarge")
    except RuntimeError as err:
        print(f"   ✖ Step 3 failed: {err}")

    # Define compensation handlers for prior completed steps
    handlers = {
        "allocate_ip": lambda step: print(f"   🔄 Rolling back Step 1: Released static IP {step.outputs['ip_address']}"),
        "create_ebs_volume": lambda step: print(f"   🔄 Rolling back Step 2: Deleted EBS volume {step.outputs['volume_id']}"),
    }

    print("\nExecuting run compensation in reverse order...")
    rolled_back_steps = ledger.compensate_run(run.id, handlers)
    print(f"✔ Rollback complete. Compensated {len(rolled_back_steps)} steps.")
