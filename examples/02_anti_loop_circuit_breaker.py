"""
Example 02: Anti-Loop Circuit Breaker.

Demonstrates how Agent Run Ledger halts infinite agent loops and hallucinations
before running away with token budgets.
"""

import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from run_ledger import CircuitBreakerConfig, CircuitBreakerTripped, RunLedger

if __name__ == "__main__":
    print("--- [AGENT-RUN-LEDGER] Anti-Loop Circuit Breaker Demo ---")
    config = CircuitBreakerConfig(max_repeated_actions=3)
    ledger = RunLedger(circuit_config=config)
    run = ledger.create_run(intent="Autonomous web research mission")

    print(f"\n1. Run initialized: {run.id}. Breaker configured for max 3 repeated actions.")

    # Simulating an agent hallucinating and calling the same search query repeatedly
    for attempt in range(1, 5):
        try:
            print(f"\nAttempt #{attempt}: Agent calling 'google_search' with identical query...")
            with ledger.execute_step(
                run_id=run.id,
                name="google_search",
                inputs={"query": "benni os autonomous swarms"},
            ) as step:
                step.outputs = {"results": "No new results"}
                print("   ✔ Step executed.")
        except CircuitBreakerTripped as cbt:
            print(f"\n🚨 [CIRCUIT BREAKER ACTIVATED] Loop blocked successfully!")
            print(f"   • Exception: {cbt.__class__.__name__}")
            print(f"   • Reason: {cbt.reason}")
            print(f"   • Details: {cbt.details}")
            break
