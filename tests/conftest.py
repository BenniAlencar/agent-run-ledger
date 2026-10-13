"""
Pytest fixtures for Agent Run Ledger test suite.
"""

from pathlib import Path
import pytest

from run_ledger.core.ledger import RunLedger
from run_ledger.storage.memory import InMemoryLedgerStorage
from run_ledger.storage.sqlite import SqliteLedgerStorage


@pytest.fixture
def temp_dir(tmp_path: Path) -> Path:
    return tmp_path


@pytest.fixture
def memory_ledger() -> RunLedger:
    return RunLedger(storage=InMemoryLedgerStorage())


@pytest.fixture
def sqlite_ledger(temp_dir: Path) -> RunLedger:
    db_path = temp_dir / "test_runs.db"
    return RunLedger(storage=SqliteLedgerStorage(db_path))
