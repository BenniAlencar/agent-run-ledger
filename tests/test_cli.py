"""
Tests for Agent Run Ledger CLI commands.
"""

from click.testing import CliRunner

from run_ledger.cli.main import cli
from run_ledger.core.ledger import RunLedger
from run_ledger.storage.sqlite import SqliteLedgerStorage


def test_cli_info():
    runner = CliRunner()
    result = runner.invoke(cli, ["info"])
    assert result.exit_code == 0
    assert "Agent Run Ledger" in result.output
    assert "Benni Master OS" in result.output


def test_cli_list_inspect_resume_snapshot():
    runner = CliRunner()
    with runner.isolated_filesystem():
        db_path = "test_cli.db"
        ledger = RunLedger(storage=SqliteLedgerStorage(db_path))
        run = ledger.create_run(intent="CLI test mission")

        with ledger.execute_step(run_id=run.id, name="ping_host", inputs={"host": "127.0.0.1"}) as s:
            s.outputs = {"latency_ms": 1.2}

        # 1. list
        res_list = runner.invoke(cli, ["list", "--db", db_path])
        assert res_list.exit_code == 0
        assert "CLI test" in res_list.output
        assert "mission" in res_list.output

        # 2. inspect
        res_inspect = runner.invoke(cli, ["inspect", run.id, "--db", db_path])
        assert res_inspect.exit_code == 0
        assert "ping_host" in res_inspect.output

        # 3. resume
        res_resume = runner.invoke(cli, ["resume", run.id, "--db", db_path])
        assert res_resume.exit_code == 0
        assert "rehydrated successfully" in res_resume.output

        # 4. snapshot
        res_snap = runner.invoke(cli, ["snapshot", run.id, "snap.json", "--db", db_path])
        assert res_snap.exit_code == 0
        assert "Atomic run snapshot created" in res_snap.output
