# Agent Run Ledger — Architecture Specification

**Doctrine:** Benni Master OS v9.4 — Skill 90c (Run Ledger Protocol) & Skill 83 (Background Execution OS)

---

## 1. System Overview

`agent-run-ledger` provides a deterministic, crash-resilient finite-state machine for multi-step AI agent execution. Every run and step transition is persisted with idempotency semantics, guarded by a real-time anti-loop circuit breaker, and exportable as a SHA-256 sealed checkpoint.

```text
  LangChain / CrewAI / MCP Clients / Python Agents
         │
         ├──► RunLedger.execute_step(run_id, name, inputs)
         └──► McpRunLedgerServer (JSON-RPC 2.0 Tools)
                       │
                       ▼
  ┌─────────────────────────────────────────────────────────────────────┐
  │                        agent-run-ledger                             │
  │                                                                     │
  │  ┌───────────────────┐  ┌───────────────────┐  ┌─────────────────┐  │
  │  │ Anti-Loop Circuit │  │  Durable Step     │  │ Atomic          │  │
  │  │ Breaker           │─►│  State Machine    │─►│ Checkpoint      │  │
  │  │ • Loop Detection  │  │  • PENDING/RUNNING│  │ • SHA-256 Seal  │  │
  │  │ • Oscillation A-B │  │  • COMPLETED/FAIL │  │ • Tamper Guard  │  │
  │  │ • Failure Ceiling │  │  • Compensation   │  │ • File Restore  │  │
  │  └───────────────────┘  └───────────────────┘  └─────────────────┘  │
  │                                                                     │
  │  ┌───────────────────┐  ┌───────────────────┐  ┌─────────────────┐  │
  │  │ Storage Backends  │  │  Framework        │  │ Tools & CLI     │  │
  │  │ • SQLite WAL      │  │  Adapters         │  │ • doctor        │  │
  │  │ • In-Memory       │  │  • LangChain      │  │ • bench_matrix  │  │
  │  │ • BaseLedgerABC   │  │  • CrewAI / MCP   │  │ • inspect/list  │  │
  │  └───────────────────┘  └───────────────────┘  └─────────────────┘  │
  └─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Core Components

| Module | Responsibility |
|---|---|
| `run_ledger/core/models.py` | Pydantic models (`RunRecord`, `StepRecord`, `RunStatus`, `StepStatus`, `CircuitBreakerConfig`) |
| `run_ledger/core/ledger.py` | `RunLedger` orchestrator (`create_run`, `execute_step`, `resume_run`, `complete_run`, `rollback_run`) |
| `run_ledger/core/circuit_breaker.py` | `AntiLoopCircuitBreaker` detecting identical repetition, A-B oscillation, failure streaks, and step ceilings |
| `run_ledger/core/checkpoint.py` | `RunCheckpointManager` producing and verifying SHA-256 `RunSnapshotPayload` archives |
| `run_ledger/storage/sqlite.py` | `SqliteLedgerStorage` with durable run/step tables |
| `run_ledger/storage/memory.py` | `InMemoryLedgerStorage` for zero-I/O unit testing and ephemeral runs |
| `run_ledger/adapters/` | Drop-in integrations for `langchain`, `crewai`, and `mcp_server` |
| `run_ledger/tools/` | `doctor.py` environment/SQLite probe and `bench_matrix.py` throughput matrix |
| `run_ledger/cli/main.py` | Click + Rich terminal CLI (`info`, `list`, `inspect`, `resume`, `doctor`, `matrix`) |

---

## 3. Verification Gates

- `scripts/gate_anti_loop_runner.py`: Fail-closed gate verifying all 4 circuit breaker tripwires, crash-resume step preservation, and SHA-256 checkpoint tamper rejection.
- `scripts/benchmark_ledger_throughput.py`: Multi-backend throughput and checkpoint sealing benchmark.
