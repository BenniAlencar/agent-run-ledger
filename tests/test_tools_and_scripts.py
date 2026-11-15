"""Tests for run_ledger.tools and scripts/."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from click.testing import CliRunner

from run_ledger.cli.main import cli
from run_ledger.tools.bench_matrix import BenchMatrixRunner
from run_ledger.tools.doctor import run_doctor

ROOT = Path(__file__).resolve().parent.parent


def test_doctor_healthy() -> None:
    report = run_doctor()
    assert report.healthy is True
    assert report.sqlite_probe_ok is True
    assert report.checkpoint_probe_ok is True
    assert report.probe_latency_ms >= 0.0


def test_bench_matrix_runner() -> None:
    runner = BenchMatrixRunner(step_counts=[5, 10], backends=["memory", "sqlite"], reps=1)
    data = runner.run_matrix()
    assert len(data["matrix_results"]) == 4
    md = BenchMatrixRunner.format_markdown_table(data)
    assert "| memory | 5 |" in md
    assert "| sqlite | 10 |" in md


def test_cli_doctor_and_matrix() -> None:
    runner = CliRunner()
    res_doc = runner.invoke(cli, ["doctor", "--json"])
    assert res_doc.exit_code == 0
    payload = json.loads(res_doc.output)
    assert payload["healthy"] is True

    res_mat = runner.invoke(cli, ["matrix", "--steps", "5", "--reps", "1", "--json"])
    assert res_mat.exit_code == 0
    mat_payload = json.loads(res_mat.output)
    assert len(mat_payload["matrix_results"]) == 2


def test_scripts_run_cleanly() -> None:
    bench = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "benchmark_ledger_throughput.py"), "--steps", "5", "--reps", "1", "--json"],
        capture_output=True,
        text=True,
        check=True,
    )
    bench_data = json.loads(bench.stdout)
    assert len(bench_data["matrix_results"]) == 2

    gate = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "gate_anti_loop_runner.py"), "--json"],
        capture_output=True,
        text=True,
        check=True,
    )
    gate_data = json.loads(gate.stdout)
    assert gate_data["approved"] is True
    assert all(c["passed"] for c in gate_data["checks"])
