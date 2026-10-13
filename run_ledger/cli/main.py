"""
Agent Run Ledger CLI.

Provides command-line run inspection, crash recovery, step tracking,
and anti-loop circuit monitoring with Rich formatting.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

# Ensure UTF-8 console output on Windows
if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import click
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from run_ledger.core.checkpoint import RunCheckpointManager
from run_ledger.core.ledger import RunLedger
from run_ledger.core.models import RunStatus, StepStatus
from run_ledger.storage.sqlite import SqliteLedgerStorage
from run_ledger.version import __author__, __doctrine__, __version__

console = Console(legacy_windows=False)


def _print_branding():
    banner = (
        f"[bold cyan]⚡ Agent Run Ledger[/bold cyan] [bold white]v{__version__}[/bold white]\n"
        f"[dim]The Resumable Multi-Step Execution State Machine & Anti-Loop Circuit Breaker for AI Agents[/dim]\n"
        f"[dim cyan]Doctrine: {__doctrine__} • Maintained by {__author__}[/dim cyan]"
    )
    console.print(Panel(banner, border_style="cyan", expand=False))


@click.group()
@click.version_option(version=__version__, prog_name="run-ledger")
def cli():
    """Agent Run Ledger — Durable multi-step execution and anti-loop circuit breaker."""
    pass


@cli.command("info")
def info():
    """Displays system information, doctrine, and enterprise gateway links."""
    _print_branding()
    rprint("\n[bold]Core Principles:[/bold]")
    rprint("  1. [cyan]Durable State Machine[/cyan]: Every step transition is persisted with deterministic state hashes")
    rprint("  2. [green]Crash Resilience & Resume[/green]: Interrupted or failed runs continue without re-executing steps")
    rprint("  3. [yellow]Anti-Loop Circuit Breaker[/yellow]: Prevents infinite tool hallucinations and runaway token burn\n")
    rprint("[bold]Community & Enterprise Gateway:[/bold]")
    rprint("  • GitHub: [blue]https://github.com/BenniAlencar/agent-run-ledger[/blue]")
    rprint("  • Benni Master OS: [blue]https://bennios.dev[/blue]")
    rprint("  • Operator Hub: [blue]https://hub.bennios.dev[/blue]\n")


@cli.command("list")
@click.option("--db", default="agent_runs.db", help="SQLite database path.")
@click.option("--limit", default=20, help="Maximum runs to display.")
def list_runs(db: str, limit: int):
    """Lists recent runs recorded in the persistent ledger."""
    _print_branding()
    storage = SqliteLedgerStorage(db)
    runs = storage.list_runs(limit=limit)

    if not runs:
        console.print("[yellow]No runs found in ledger database.[/yellow]")
        return

    table = Table(title="Durable Agent Run Ledger", border_style="cyan")
    table.add_column("Run ID", style="cyan", no_wrap=True)
    table.add_column("Intent", style="bold white")
    table.add_column("Status", style="bold")
    table.add_column("Progress", style="green")
    table.add_column("Created At", style="dim")

    for r in runs:
        status_color = "green" if r.status == RunStatus.COMPLETED else ("red" if r.status == RunStatus.FAILED else "yellow")
        status_styled = f"[{status_color}]{r.status.value.upper()}[/{status_color}]"
        progress = f"{r.completed_steps}/{r.total_steps} steps"
        table.add_row(r.id, r.intent[:45], status_styled, progress, r.created_at[:19])

    console.print(table)


@cli.command("inspect")
@click.argument("run_id")
@click.option("--db", default="agent_runs.db", help="SQLite database path.")
def inspect(run_id: str, db: str):
    """Displays detailed execution history and steps for a specific run."""
    _print_branding()
    storage = SqliteLedgerStorage(db)
    run = storage.get_run(run_id)

    if not run:
        console.print(f"[bold red]Error:[/bold red] Run '{run_id}' not found.")
        return

    console.print(f"\n[bold]Run ID:[/bold] [cyan]{run.id}[/cyan]")
    console.print(f"[bold]Intent:[/bold] {run.intent}")
    console.print(f"[bold]Status:[/bold] {run.status.value.upper()}")
    console.print(f"[bold]Context Keys:[/bold] {list(run.context.keys())}\n")

    steps = storage.get_steps_for_run(run_id)
    if not steps:
        console.print("[dim]No steps recorded for this run.[/dim]")
        return

    table = Table(title=f"Step Trace for {run_id}", border_style="cyan")
    table.add_column("#", style="dim", justify="right")
    table.add_column("Step Name", style="bold white")
    table.add_column("Type", style="cyan")
    table.add_column("Status", style="bold")
    table.add_column("Duration", style="yellow", justify="right")
    table.add_column("Details", style="dim")

    for s in steps:
        s_color = "green" if s.status == StepStatus.COMPLETED else ("red" if s.status == StepStatus.FAILED else "yellow")
        s_styled = f"[{s_color}]{s.status.value.upper()}[/{s_color}]"
        details = s.error[:40] if s.error else (f"output keys: {list(s.outputs.keys())}" if s.outputs else "-")
        table.add_row(
            str(s.step_number),
            s.name,
            s.step_type.value,
            s_styled,
            f"{s.duration_ms} ms",
            details,
        )

    console.print(table)


@cli.command("resume")
@click.argument("run_id")
@click.option("--db", default="agent_runs.db", help="SQLite database path.")
def resume(run_id: str, db: str):
    """Rehydrates an interrupted or failed run to continue execution."""
    _print_branding()
    ledger = RunLedger(storage=SqliteLedgerStorage(db))
    try:
        run = ledger.resume_run(run_id)
        steps = ledger.get_steps(run_id)
        completed = sum(1 for s in steps if s.status == StepStatus.COMPLETED)
        console.print(f"[bold green]✔ Run rehydrated successfully![/bold green]")
        console.print(f"  • Run ID: [cyan]{run.id}[/cyan]")
        console.print(f"  • Status: [yellow]{run.status.value.upper()}[/yellow]")
        console.print(f"  • Preserved Steps: [green]{completed}/{len(steps)}[/green]")
        console.print(f"  • Rehydrated Context Keys: {list(run.context.keys())}")
    except Exception as exc:
        console.print(f"[bold red]Failed to resume run:[/bold red] {exc}")


@cli.command("snapshot")
@click.argument("run_id")
@click.argument("output_path", default="run_snapshot.json")
@click.option("--db", default="agent_runs.db", help="SQLite database path.")
def snapshot(run_id: str, output_path: str, db: str):
    """Exports an atomic, SHA-256 sealed checkpoint snapshot of a run."""
    _print_branding()
    storage = SqliteLedgerStorage(db)
    run = storage.get_run(run_id)
    if not run:
        console.print(f"[bold red]Error:[/bold red] Run '{run_id}' not found.")
        return

    steps = storage.get_steps_for_run(run_id)
    saved = RunCheckpointManager.save_to_file(run, steps, output_path)
    console.print(f"[bold green]✔ Atomic run snapshot created at:[/bold green] [cyan]{saved.resolve()}[/cyan]")


if __name__ == "__main__":
    cli()
