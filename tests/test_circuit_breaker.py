"""
Tests for AntiLoopCircuitBreaker detection patterns.
"""

import pytest

from run_ledger.core.circuit_breaker import (
    AntiLoopCircuitBreaker,
    CircuitBreakerConfig,
    ConsecutiveFailureError,
    LoopDetectedError,
    OscillationDetectedError,
    StepBudgetExceededError,
)


def test_repeated_identical_action_trips():
    config = CircuitBreakerConfig(max_repeated_actions=3)
    cb = AntiLoopCircuitBreaker(config=config)

    # 1st call
    cb.check_allowed("search_docs", {"query": "vector index"})
    cb.record_action_start("search_docs", {"query": "vector index"})

    # 2nd call
    cb.check_allowed("search_docs", {"query": "vector index"})
    cb.record_action_start("search_docs", {"query": "vector index"})

    # 3rd call
    cb.check_allowed("search_docs", {"query": "vector index"})
    cb.record_action_start("search_docs", {"query": "vector index"})

    # 4th call must trip LoopDetectedError!
    with pytest.raises(LoopDetectedError) as exc_info:
        cb.check_allowed("search_docs", {"query": "vector index"})

    assert "Repeated identical action" in str(exc_info.value)
    assert cb.is_tripped is True


def test_consecutive_failure_trips():
    config = CircuitBreakerConfig(max_consecutive_failures=2)
    cb = AntiLoopCircuitBreaker(config=config)

    cb.record_failure()
    assert cb.consecutive_failures == 1

    cb.record_failure()
    assert cb.consecutive_failures == 2

    # Next attempt should be blocked
    with pytest.raises(ConsecutiveFailureError) as exc_info:
        cb.check_allowed("retry_step", {})

    assert "Consecutive step failures" in str(exc_info.value)
    assert cb.is_tripped is True


def test_step_budget_exceeded():
    config = CircuitBreakerConfig(max_total_steps=5)
    cb = AntiLoopCircuitBreaker(config=config)

    for i in range(5):
        cb.check_allowed(f"step_{i}", {"val": i})
        cb.record_action_start(f"step_{i}", {"val": i})

    with pytest.raises(StepBudgetExceededError) as exc_info:
        cb.check_allowed("step_6", {"val": 6})

    assert "Total step budget of 5 exceeded" in str(exc_info.value)
    assert cb.is_tripped is True


def test_oscillation_trips():
    config = CircuitBreakerConfig(oscillation_window=4)
    cb = AntiLoopCircuitBreaker(config=config)

    # Pattern: A -> B -> A -> B
    cb.record_action_start("agent_researcher", {"task": "find_bug"})
    cb.record_action_start("agent_coder", {"task": "fix_bug"})
    cb.record_action_start("agent_researcher", {"task": "find_bug"})
    cb.record_action_start("agent_coder", {"task": "fix_bug"})

    with pytest.raises(OscillationDetectedError) as exc_info:
        cb.check_allowed("agent_researcher", {"task": "find_bug"})

    assert "Agent is oscillating" in str(exc_info.value)
    assert cb.is_tripped is True


def test_circuit_breaker_reset():
    config = CircuitBreakerConfig(max_consecutive_failures=2)
    cb = AntiLoopCircuitBreaker(config=config)

    cb.record_failure()
    cb.record_failure()
    assert cb.consecutive_failures == 2

    # Reset
    cb.reset()
    assert cb.is_tripped is False
    assert cb.consecutive_failures == 0
    # Should now be allowed
    cb.check_allowed("healthy_action", {})
