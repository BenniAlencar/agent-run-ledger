"""
Native Model Context Protocol (MCP) Server for Agent Run Ledger.

Allows Claude Desktop, Cursor, Antigravity, and Project Benjamin to govern
durable multi-step runs, inspect circuit breaker state, and resume interrupted missions.
"""

from __future__ import annotations

import json
from typing import Any, Dict, List, Optional

from run_ledger.core.checkpoint import RunCheckpointManager
from run_ledger.core.circuit_breaker import CircuitBreakerTripped
from run_ledger.core.ledger import RunLedger
from run_ledger.core.models import StepStatus, StepType, _iso_now


class McpRunLedgerServer:
    """
    Exposes Run Ledger execution controls as standard Model Context Protocol tools.
    """

    def __init__(self, ledger: Optional[RunLedger] = None):
        self.ledger = ledger or RunLedger()

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Returns MCP tool definitions conforming to the JSON-RPC spec."""
        return [
            {
                "name": "ledger_create_run",
                "description": "Initializes a durable multi-step agent run ledger with intent and initial context.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "intent": {"type": "string", "description": "Goal or mission intent of the run."},
                        "context": {"type": "object", "description": "Initial input context parameters."},
                    },
                    "required": ["intent"],
                },
            },
            {
                "name": "ledger_step_start",
                "description": "Registers and starts a new step in a run, evaluated through the anti-loop circuit breaker.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string", "description": "Active run ID."},
                        "name": {"type": "string", "description": "Step or tool name."},
                        "inputs": {"type": "object", "description": "Step input arguments."},
                        "step_type": {"type": "string", "enum": ["tool_call", "inference", "verification"], "default": "tool_call"},
                        "idempotency_key": {"type": "string", "description": "Optional idempotency key."},
                    },
                    "required": ["run_id", "name"],
                },
            },
            {
                "name": "ledger_step_complete",
                "description": "Marks a step as successfully completed and persists its output.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "step_id": {"type": "string", "description": "ID of the step to complete."},
                        "outputs": {"type": "object", "description": "Output payload produced by the step."},
                    },
                    "required": ["step_id"],
                },
            },
            {
                "name": "ledger_step_fail",
                "description": "Records an error and marks a step as failed.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "step_id": {"type": "string", "description": "ID of the step that failed."},
                        "error_message": {"type": "string", "description": "Detailed failure or exception message."},
                    },
                    "required": ["step_id", "error_message"],
                },
            },
            {
                "name": "ledger_run_resume",
                "description": "Rehydrates a failed or interrupted run, preparing it to resume from the last pending step.",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "run_id": {"type": "string", "description": "ID of the run to resume."},
                    },
                    "required": ["run_id"],
                },
            },
            {
                "name": "ledger_circuit_status",
                "description": "Inspects the active state of the Anti-Loop Circuit Breaker.",
                "inputSchema": {
                    "type": "object",
                    "properties": {},
                },
            },
        ]

    def call_tool(self, name: str, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Dispatches an MCP tool call to the RunLedger engine."""
        try:
            if name == "ledger_create_run":
                intent = arguments["intent"]
                context = arguments.get("context", {})
                run = self.ledger.create_run(intent=intent, context=context)
                return {
                    "content": [{"type": "text", "text": f"Created run '{run.id}' with intent: {intent}"}],
                    "isError": False,
                    "run_id": run.id,
                }

            elif name == "ledger_step_start":
                run_id = arguments["run_id"]
                step_name = arguments["name"]
                inputs = arguments.get("inputs", {})
                idempotency_key = arguments.get("idempotency_key")
                raw_type = arguments.get("step_type", "tool_call")
                step_type = StepType(raw_type)

                # Check circuit breaker
                self.ledger.circuit_breaker.check_allowed(step_name, inputs)

                step = self.ledger.add_step(
                    run_id=run_id,
                    name=step_name,
                    step_type=step_type,
                    inputs=inputs,
                    idempotency_key=idempotency_key,
                )
                step.status = StepStatus.RUNNING
                step.started_at = _iso_now()
                self.ledger.storage.save_step(step)
                self.ledger.circuit_breaker.record_action_start(step_name, inputs)

                return {
                    "content": [{"type": "text", "text": f"Started step '{step.id}' ({step_name})"}],
                    "isError": False,
                    "step_id": step.id,
                }

            elif name == "ledger_step_complete":
                step_id = arguments["step_id"]
                outputs = arguments.get("outputs", {})
                step = self.ledger.storage.get_step(step_id)
                if not step:
                    return {"content": [{"type": "text", "text": f"Step '{step_id}' not found"}], "isError": True}

                step.status = StepStatus.COMPLETED
                step.outputs = outputs
                step.completed_at = _iso_now()
                step.seal()
                self.ledger.storage.save_step(step)

                run = self.ledger.storage.get_run(step.run_id)
                if run:
                    run.completed_steps += 1
                    run.updated_at = _iso_now()
                    self.ledger.storage.save_run(run)

                self.ledger.circuit_breaker.record_success()
                return {
                    "content": [{"type": "text", "text": f"Step '{step_id}' marked COMPLETED"}],
                    "isError": False,
                }

            elif name == "ledger_step_fail":
                step_id = arguments["step_id"]
                err = arguments["error_message"]
                step = self.ledger.storage.get_step(step_id)
                if not step:
                    return {"content": [{"type": "text", "text": f"Step '{step_id}' not found"}], "isError": True}

                step.status = StepStatus.FAILED
                step.error = err
                step.completed_at = _iso_now()
                step.seal()
                self.ledger.storage.save_step(step)

                self.ledger.circuit_breaker.record_failure()
                return {
                    "content": [{"type": "text", "text": f"Step '{step_id}' recorded as FAILED: {err}"}],
                    "isError": False,
                }

            elif name == "ledger_run_resume":
                run_id = arguments["run_id"]
                run = self.ledger.resume_run(run_id)
                steps = self.ledger.get_steps(run_id)
                completed = sum(1 for s in steps if s.status == StepStatus.COMPLETED)
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": f"Run '{run_id}' rehydrated to RUNNING. {completed}/{len(steps)} steps preserved.",
                        }
                    ],
                    "isError": False,
                }

            elif name == "ledger_circuit_status":
                tripped = self.ledger.circuit_breaker.is_tripped
                reason = self.ledger.circuit_breaker.trip_reason
                actions = len(self.ledger.circuit_breaker.action_history)
                return {
                    "content": [
                        {
                            "type": "text",
                            "text": (
                                f"Circuit Breaker Status: {'TRIPPED' if tripped else 'CLOSED (HEALTHY)'}\n"
                                f"Trip Reason: {reason or 'None'}\n"
                                f"Recorded Actions: {actions}\n"
                                f"Consecutive Failures: {self.ledger.circuit_breaker.consecutive_failures}"
                            ),
                        }
                    ],
                    "isError": False,
                }

            else:
                return {
                    "content": [{"type": "text", "text": f"Unknown tool: {name}"}],
                    "isError": True,
                }

        except CircuitBreakerTripped as cbt:
            return {
                "content": [{"type": "text", "text": f"[CIRCUIT BREAKER BLOCKED] {cbt}"}],
                "isError": True,
            }
        except Exception as exc:
            return {
                "content": [{"type": "text", "text": f"[RUN LEDGER ERROR] {str(exc)}"}],
                "isError": True,
            }
