#!/usr/bin/env python3
"""Durable Ledger Throughput & Checkpoint Benchmark.

Measures In-Memory vs SQLite persistence throughput, mean step latency,
and SHA-256 atomic checkpoint sealing overhead across step counts.

Usage:
    python scripts/benchmark_ledger_throughput.py
    python scripts/benchmark_ledger_throughput.py --steps 10 50 100 --reps 2
    python scripts/benchmark_ledger_throughput.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from run_ledger.tools.bench_matrix import BenchMatrixRunner


def run_benchmark(steps: list[int] | None = None, reps: int = 2) -> dict[str, Any]:
    """Execute the ledger throughput matrix benchmark."""
    runner = BenchMatrixRunner(step_counts=steps or [10, 50, 100], reps=reps)
    return runner.run_matrix()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark Agent Run Ledger throughput.")
    parser.add_argument("--steps", type=int, nargs="+", default=[10, 50, 100], help="Step counts to benchmark.")
    parser.add_argument("--reps", type=int, default=2, help="Repetitions per cell.")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    args = parser.parse_args(argv)

    data = run_benchmark(steps=args.steps, reps=args.reps)
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        print(BenchMatrixRunner.format_markdown_table(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
