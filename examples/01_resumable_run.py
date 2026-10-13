"""
Example 01: Resumable Agent Run & Crash Recovery.

Demonstrates how Agent Run Ledger allows an interrupted or failed agent run
to resume execution without re-executing completed steps.
"""

import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from run_ledger import RunLedger, StepStatus

if __name__ == "__main__":
    print("--- [AGENT-RUN-LEDGER] Resumable Run & Crash Recovery Demo ---")
    ledger = RunLedger()

    # 1. Start a multi-step mission
    run = ledger.create_run(intent="Deploy Production Microservice", context={"env": "production"})
    print(f"\n1. Initialized Run: {run.id} [Status: {run.status.value}]")

    # Step 1: Pre-flight checks
    with ledger.execute_step(run_id=run.id, name="preflight_check", inputs={"target": "k8s"}) as s1:
        s1.outputs = {"cluster_ready": True, "nodes": 10}
        print("   ✔ Step 1: Preflight checks passed.")

    # Step 2: Build container image
    with ledger.execute_step(run_id=run.id, name="build_container", inputs={"tag": "v1.4.0"}) as s2:
        s2.outputs = {"image_digest": "sha256:7f9a8b1c", "size_mb": 142}
        print("   ✔ Step 2: Container image built.")

    # Simulated crash / network failure during Step 3
    print("\n2. Simulating network failure or process restart during Step 3...")
    try:
        with ledger.execute_step(run_id=run.id, name="push_registry", inputs={"registry": "ecr"}):
            raise ConnectionError("Connection reset by peer during image upload")
    except ConnectionError as err:
        print(f"   ✖ Step 3 failed as expected: {err}")

    # Check status
    failed_run = ledger.get_run(run.id)
    print(f"   • Current Run Status: {failed_run.status.value.upper()}")

    # 3. Resume the run
    print("\n3. Calling ledger.resume_run()...")
    resumed_run = ledger.resume_run(run.id)
    print(f"   ✔ Run rehydrated to: {resumed_run.status.value.upper()}")
    print(f"   • Rehydrated Context: {resumed_run.context}")

    # Retry Step 3 (succeeds this time)
    with ledger.execute_step(run_id=run.id, name="push_registry", inputs={"registry": "ecr"}) as s3_retry:
        s3_retry.outputs = {"uploaded": True, "url": "ecr.aws/microservice:v1.4.0"}
        print("   ✔ Step 3: Image successfully pushed to registry.")

    # Step 4: Apply deployment
    with ledger.execute_step(run_id=run.id, name="apply_k8s_manifest", inputs={"replicas": 3}) as s4:
        s4.outputs = {"deployed": True, "service_url": "https://api.bennios.dev"}
        print("   ✔ Step 4: Kubernetes deployment applied.")

    final_run = ledger.get_run(run.id)
    print(f"\n4. Mission Complete! Final Run Status: {final_run.status.value.upper()}")
    print(f"   • Steps Completed: {final_run.completed_steps}/{final_run.total_steps}")
