"""
LangChain and LangGraph callback integration for Agent Run Ledger.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional
from uuid import UUID

from run_ledger.core.ledger import RunLedger
from run_ledger.core.models import StepStatus, StepType


class RunLedgerCallbackHandler:
    """
    Hooks into LangChain agent execution cycles to track tool calls as durable ledger steps.
    """

    def __init__(self, ledger: RunLedger, run_id: Optional[str] = None):
        self.ledger = ledger
        self.run_id = run_id or self.ledger.create_run(intent="LangChain Agent Execution").id
        self._active_steps: Dict[str, str] = {}  # run_step_key -> step_id

    def on_tool_start(
        self,
        serialized: Dict[str, Any],
        input_str: str,
        *,
        run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Called when a tool execution starts."""
        tool_name = serialized.get("name", "unknown_tool")
        key = str(run_id) if run_id else tool_name

        self.ledger.circuit_breaker.check_allowed(tool_name, {"input": input_str})

        step = self.ledger.add_step(
            run_id=self.run_id,
            name=tool_name,
            step_type=StepType.TOOL_CALL,
            inputs={"input": input_str},
        )
        self._active_steps[key] = step.id
        self.ledger.circuit_breaker.record_action_start(tool_name, {"input": input_str})

    def on_tool_end(
        self,
        output: str,
        *,
        run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Called when a tool execution succeeds."""
        step_id = None
        if run_id and str(run_id) in self._active_steps:
            step_id = self._active_steps.pop(str(run_id))
        elif self._active_steps:
            _, step_id = self._active_steps.popitem()

        if step_id:
            step = self.ledger.storage.get_step(step_id)
            if step:
                step.outputs = {"output": output}
                step.status = StepStatus.COMPLETED
                self.ledger.storage.save_step(step)
                self.ledger.circuit_breaker.record_success()

    def on_tool_error(
        self,
        error: BaseException,
        *,
        run_id: Optional[UUID] = None,
        **kwargs: Any,
    ) -> None:
        """Called when a tool execution fails."""
        step_id = None
        if run_id and str(run_id) in self._active_steps:
            step_id = self._active_steps.pop(str(run_id))
        elif self._active_steps:
            _, step_id = self._active_steps.popitem()

        if step_id:
            step = self.ledger.storage.get_step(step_id)
            if step:
                step.error = str(error)
                step.status = StepStatus.FAILED
                self.ledger.storage.save_step(step)
                self.ledger.circuit_breaker.record_failure()
