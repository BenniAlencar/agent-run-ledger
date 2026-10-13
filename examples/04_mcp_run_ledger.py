"""
Example 04: Model Context Protocol (MCP) Server for Agent Run Ledger.

Demonstrates running the native MCP tool interface for LLM agent integration.
"""

import json
import sys
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from run_ledger import McpRunLedgerServer

if __name__ == "__main__":
    print("--- [AGENT-RUN-LEDGER] MCP Server Tool Suite Demo ---")
    server = McpRunLedgerServer()
    tools = server.get_tool_definitions()

    print(f"\n1. Registered {len(tools)} MCP tools for LLM agent consumption:")
    for t in tools:
        print(f"   • {t['name']}: {t['description']}")

    # 1. MCP tool: ledger_create_run
    res_run = server.call_tool("ledger_create_run", {"intent": "Autonomous Code Refactoring"})
    run_id = res_run["run_id"]
    print(f"\n2. Tool call 'ledger_create_run' -> {res_run['content'][0]['text']}")

    # 2. MCP tool: ledger_step_start
    res_step = server.call_tool("ledger_step_start", {"run_id": run_id, "name": "ast_parse"})
    step_id = res_step["step_id"]
    print(f"3. Tool call 'ledger_step_start' -> {res_step['content'][0]['text']}")

    # 3. MCP tool: ledger_step_complete
    res_comp = server.call_tool("ledger_step_complete", {"step_id": step_id, "outputs": {"classes_parsed": 8}})
    print(f"4. Tool call 'ledger_step_complete' -> {res_comp['content'][0]['text']}")

    # 4. MCP tool: ledger_circuit_status
    res_circ = server.call_tool("ledger_circuit_status", {})
    print(f"\n5. Tool call 'ledger_circuit_status':\n{res_circ['content'][0]['text']}")
