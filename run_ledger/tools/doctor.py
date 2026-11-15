"""Run Ledger Doctor — Environment, SQLite WAL, and durable execution diagnostics.

Inspects Python runtime, SQLite3 capabilities, optional framework adapters,
and executes an end-to-end ephemeral create -> step -> checkpoint -> resume probe.
"""

from __future__ import annotations

import argparse
import gc
import importlib.util
import json
import platform
import sqlite3
import tempfile
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from run_ledger.core.checkpoint import RunCheckpointManager
from run_ledger.core.ledger import RunLedger
from run_ledger.core.models import RunStatus
from run_ledger.version import __doctrine__, __version__


@dataclass(frozen=True)
class DoctorReport:
    """Structured diagnostic report for Agent Run Ledger."""

    version: str
    doctrine: str
    python_version: str
    platform: str
    sqlite_version: str
    dependencies: dict[str, bool]
    sqlite_probe_ok: bool
    checkpoint_probe_ok: bool
    probe_latency_ms: float
    healthy: bool

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def probe_dependencies() -> dict[str, bool]:
    """Check availability of core and optional runtime dependencies."""
    packages = ("pydantic", "click", "rich", "mcp", "langchain_core", "pytest")
    return {pkg: importlib.util.find_spec(pkg) is not None for pkg in packages}


def run_doctor() -> DoctorReport:
    """Execute environment and durable-execution self-checks."""
    deps = probe_dependencies()
    t0 = time.perf_counter()
    sqlite_ok = False
    checkpoint_ok = False

    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        db_path = str(Path(tmp) / "doctor_probe.db")
        ledger = RunLedger.with_sqlite(db_path)
        run = ledger.create_run(intent="doctor_probe", context={"probe": True})
        with ledger.execute_step(run_id=run.id, name="probe_step", inputs={"x": 1}) as step:
            step.outputs = {"ok": True}
        reloaded = ledger.storage.get_run(run.id)
        sqlite_ok = reloaded is not None and reloaded.status == RunStatus.COMPLETED

        if reloaded is not None:
            cp_path = Path(tmp) / "doctor_checkpoint.json"
            steps = ledger.storage.get_steps_for_run(run.id)
            RunCheckpointManager.save_to_file(reloaded, steps, cp_path)
            restored_run, restored_steps = RunCheckpointManager.restore_from_file(cp_path)
            checkpoint_ok = restored_run.id == reloaded.id and len(restored_steps) == len(steps)
        del ledger
        gc.collect()

    latency_ms = round((time.perf_counter() - t0) * 1000.0, 2)
    healthy = sqlite_ok and checkpoint_ok and all(deps[k] for k in ("pydantic", "click", "rich"))

    return DoctorReport(
        version=__version__,
        doctrine=__doctrine__,
        python_version=platform.python_version(),
        platform=f"{platform.system()} {platform.release()}",
        sqlite_version=sqlite3.sqlite_version,
        dependencies=deps,
        sqlite_probe_ok=sqlite_ok,
        checkpoint_probe_ok=checkpoint_ok,
        probe_latency_ms=latency_ms,
        healthy=healthy,
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Agent Run Ledger environment diagnostics.")
    parser.add_argument("--json", action="store_true", help="Emit JSON report.")
    args = parser.parse_args(argv)

    report = run_doctor()
    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        status = "HEALTHY" if report.healthy else "DEGRADED"
        print(f"Agent Run Ledger Doctor v{report.version} [{status}]")
        print(f"Python: {report.python_version} | SQLite: {report.sqlite_version} | OS: {report.platform}")
        print(f"SQLite Probe: {'OK' if report.sqlite_probe_ok else 'FAIL'} | Checkpoint Seal: {'OK' if report.checkpoint_probe_ok else 'FAIL'} ({report.probe_latency_ms} ms)")
        for pkg, present in report.dependencies.items():
            print(f"  - {pkg}: {'installed' if present else 'missing'}")
    return 0 if report.healthy else 1


if __name__ == "__main__":
    raise SystemExit(main())
