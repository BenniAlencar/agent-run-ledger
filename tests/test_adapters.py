"""
Tests for MCP, LangChain, and CrewAI adapters.
"""

from run_ledger.adapters.crewai import RunLedgerCrewWrapper
from run_ledger.adapters.langchain import RunLedgerCallbackHandler
from run_ledger.adapters.mcp_server import McpRunLedgerServer
from run_ledger.core.ledger import RunLedger
from run_ledger.core.models import StepStatus


def test_mcp_run_ledger_server():
    server = McpRunLedgerServer()
    tools = server.get_tool_definitions()
    assert len(tools) == 6

    # 1. Create run
    create_res = server.call_tool("ledger_create_run", {"intent": "Analyze quarterly report"})
    assert create_res["isError"] is False
    run_id = create_res["run_id"]

    # 2. Start step
    start_res = server.call_tool("ledger_step_start", {"run_id": run_id, "name": "fetch_pdf"})
    assert start_res["isError"] is False
    step_id = start_res["step_id"]

    # 3. Complete step
    comp_res = server.call_tool("ledger_step_complete", {"step_id": step_id, "outputs": {"pages": 14}})
    assert comp_res["isError"] is False

    # 4. Check circuit status
    circ_res = server.call_tool("ledger_circuit_status", {})
    assert circ_res["isError"] is False
    assert "HEALTHY" in circ_res["content"][0]["text"]


def test_langchain_callback_handler(memory_ledger: RunLedger):
    handler = RunLedgerCallbackHandler(ledger=memory_ledger)

    handler.on_tool_start({"name": "calculator"}, "2 + 2")
    handler.on_tool_end("4")

    steps = memory_ledger.get_steps(handler.run_id)
    assert len(steps) == 1
    assert steps[0].name == "calculator"
    assert steps[0].outputs["output"] == "4"


def test_crewai_wrapper(memory_ledger: RunLedger):
    run = memory_ledger.create_run(intent="CrewAI search task")
    wrapper = RunLedgerCrewWrapper(ledger=memory_ledger, run_id=run.id)

    def search_web(query: str) -> str:
        return f"Results for: {query}"

    protected_search = wrapper.wrap_tool(search_web, name="search_web")
    output = protected_search("Benni Master OS v9.4")

    assert "Benni Master OS" in output

    steps = memory_ledger.get_steps(run.id)
    assert len(steps) == 1
    assert steps[0].status == StepStatus.COMPLETED
    assert "Benni Master OS" in steps[0].outputs["result"]
