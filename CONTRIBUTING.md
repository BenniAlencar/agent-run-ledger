# Contributing to Agent Run Ledger

Thank you for your interest in contributing to **agent-run-ledger**, the durable execution state machine and anti-loop circuit breaker for AI agents (part of the Benni Master OS ecosystem).

## Philosophy & Reality Lock Doctrine
Every submission must adhere to the **Reality Lock** discipline:
1. **Physical Evidence**: No feature or bugfix is accepted without real pytest evidence.
2. **Deterministic Durability**: Every step state transition must be durable and verifiable.
3. **Loop Safety**: All agent dispatch mechanisms must guard against infinite token exhaustion loops.

## Local Setup
```bash
git clone https://github.com/BenniAlencar/agent-run-ledger.git
cd agent-run-ledger
python -m pip install --upgrade pip setuptools wheel
pip install -e ".[dev]"
```

## Running Tests
All tests must pass 100%:
```bash
pytest tests -v --tb=short
```

## Pull Request Guidelines
- Follow PEP 8 and use type annotations everywhere.
- Maintain multi-version compatibility across Python 3.10, 3.11, and 3.12.
- Include unit tests in `tests/` covering new features or bug fixes.
