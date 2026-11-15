"""Matrix Benchmark Suite for Agent Run Ledger.

Runs automated sweeps across step counts and storage backends (in-memory vs SQLite)
to measure step throughput, mean step latency, and checkpoint sealing overhead.
"""

from __future__ import annotations

import argparse
import gc
import json
import statistics
import tempfile
import time
from pathlib import Path
from typing import Any

from run_ledger.core.checkpoint import RunCheckpointManager
from run_ledger.core.ledger import RunLedger
from run_ledger.core.models import CircuitBreakerConfig


class BenchMatrixRunner:
    """Executes a multi-backend, multi-step benchmark matrix on RunLedger."""

    def __init__(
        self,
        step_counts: list[int] | None = None,
        backends: list[str] | None = None,
        reps: int = 2,
    ) -> None:
        self.step_counts = step_counts or [10, 50, 100]
        self.backends = backends or ["memory", "sqlite"]
        self.reps = reps

    def _run_once(self, backend: str, steps: int) -> tuple[float, float]:
        cfg = CircuitBreakerConfig(max_total_steps=max(steps + 10, 100))
        mgr = RunCheckpointManager()
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
            if backend == "sqlite":
                ledger = RunLedger.with_sqlite(str(Path(tmp) / "bench.db"), circuit_config=cfg)
            else:
                ledger = RunLedger(circuit_config=cfg)

            t0 = time.perf_counter()
            run = ledger.create_run(intent=f"bench_{backend}_{steps}")
            for i in range(steps):
                with ledger.execute_step(run_id=run.id, name=f"step_{i}", inputs={"idx": i}) as s:
                    s.outputs = {"result": i * 2}
            exec_elapsed = max(1e-6, time.perf_counter() - t0)

            t_cp = time.perf_counter()
            run_rec = ledger.storage.get_run(run.id)
            steps_rec = ledger.storage.get_steps_for_run(run.id)
            if run_rec is not None:
                cp_path = Path(tmp) / "bench_cp.json"
                mgr.save_to_file(run_rec, steps_rec, cp_path)
                mgr.restore_from_file(cp_path)
            cp_ms = (time.perf_counter() - t_cp) * 1000.0
            del ledger
            gc.collect()
            return exec_elapsed, cp_ms

    def run_matrix(self) -> dict[str, Any]:
        """Execute the full backend x step-count benchmark matrix."""
        rows: list[dict[str, Any]] = []
        for backend in self.backends:
            for steps in self.step_counts:
                elapsed_samples: list[float] = []
                cp_samples: list[float] = []
                for _ in range(self.reps):
                    elapsed, cp_ms = self._run_once(backend, steps)
                    elapsed_samples.append(elapsed)
                    cp_samples.append(cp_ms)

                mean_s = statistics.mean(elapsed_samples)
                rows.append(
                    {
                        "backend": backend,
                        "steps": steps,
                        "mean_total_ms": round(mean_s * 1000.0, 2),
                        "mean_step_ms": round((mean_s * 1000.0) / steps, 3),
                        "steps_per_sec": round(steps / mean_s, 1),
                        "checkpoint_ms": round(statistics.mean(cp_samples), 3),
                    }
                )

        return {
            "backends": self.backends,
            "step_counts": self.step_counts,
            "reps": self.reps,
            "matrix_results": rows,
            "timestamp": int(time.time()),
        }

    @staticmethod
    def format_markdown_table(data: dict[str, Any]) -> str:
        """Render a Markdown summary table from benchmark matrix results."""
        lines = [
            "# Agent Run Ledger Benchmark Matrix",
            "",
            "| Backend | Steps | Total Time (ms) | Mean Step (ms) | Throughput (steps/s) | Checkpoint Seal (ms) |",
            "|---|---:|---:|---:|---:|---:|",
        ]
        for row in data.get("matrix_results", []):
            lines.append(
                f"| {row['backend']} | {row['steps']} | {row['mean_total_ms']} | "
                f"{row['mean_step_ms']} | {row['steps_per_sec']} | {row['checkpoint_ms']} |"
            )
        return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Agent Run Ledger benchmark matrix.")
    parser.add_argument("--steps", type=int, nargs="+", default=[10, 50, 100], help="Step counts to sweep.")
    parser.add_argument("--reps", type=int, default=2, help="Repetitions per cell.")
    parser.add_argument("--json", action="store_true", help="Emit JSON output.")
    args = parser.parse_args(argv)

    runner = BenchMatrixRunner(step_counts=args.steps, reps=args.reps)
    data = runner.run_matrix()
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(runner.format_markdown_table(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
