"""
CrewAI task and tool execution wrapper for Agent Run Ledger.
"""

from __future__ import annotations

from typing import Any, Callable, Dict, Optional

from run_ledger.core.ledger import RunLedger
from run_ledger.core.models import StepType


class RunLedgerCrewWrapper:
    """
    Wraps CrewAI tools and agent tasks with durable step execution and loop tripwires.
    """

    def __init__(self, ledger: RunLedger, run_id: str):
        self.ledger = ledger
        self.run_id = run_id

    def wrap_tool(self, tool_fn: Callable[..., Any], name: Optional[str] = None) -> Callable[..., Any]:
        """Decorates a function/tool so every execution is recorded in the run ledger."""
        tool_name = name or getattr(tool_fn, "__name__", "crewai_tool")

        def wrapped(*args: Any, **kwargs: Any) -> Any:
            inputs = {"args": args, "kwargs": kwargs}
            with self.ledger.execute_step(
                run_id=self.run_id,
                name=tool_name,
                step_type=StepType.TOOL_CALL,
                inputs=inputs,
            ) as step:
                result = tool_fn(*args, **kwargs)
                step.outputs = {"result": result}
                return result

        return wrapped
