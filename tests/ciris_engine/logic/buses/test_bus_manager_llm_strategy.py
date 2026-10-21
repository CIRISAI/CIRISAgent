"""
Tests for BusManager's LLM distribution-strategy selection logic.

The bus default is LATENCY_BASED, but when replicas > 1 we need LEAST_LOADED
so the bus uses in-flight capacity (not just historical latency) to decide
which replica to send the next call to. CIRIS_LLM_DISTRIBUTION_STRATEGY
lets operators override either default explicitly.

Uses pytest's monkeypatch fixture for env-var manipulation so these tests
are safe to run in parallel (`pytest -n N`). Direct os.environ mutation
leaks across processes/threads when xdist is in play and was the source
of a real flaky-failure on test_initialize_llm_service_real.
"""

from unittest.mock import MagicMock

import pytest

from ciris_engine.logic.buses.bus_manager import BusManager
from ciris_engine.logic.buses.llm_bus import DistributionStrategy


_ENV_KEYS = ("CIRIS_LLM_REPLICAS", "CIRIS_LLM_DISTRIBUTION_STRATEGY")


@pytest.fixture
def mock_deps():
    """Minimal mocks to let BusManager construct without touching the DB."""
    return {
        "service_registry": MagicMock(),
        "time_service": MagicMock(),
        "audit_service": MagicMock(),
        "telemetry_service": MagicMock(),
    }


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    """Ensure these env vars are unset for every test in this module.

    monkeypatch is xdist-safe: each test gets a clean env, and changes are
    reverted automatically on test teardown.
    """
    for key in _ENV_KEYS:
        monkeypatch.delenv(key, raising=False)


def test_default_strategy_is_latency_based(mock_deps):
    """Single-replica (default) bus uses LATENCY_BASED."""
    mgr = BusManager(**mock_deps)
    assert mgr.llm.distribution_strategy == DistributionStrategy.LATENCY_BASED


def test_replicas_gt_one_defaults_to_least_loaded(mock_deps, monkeypatch):
    """With CIRIS_LLM_REPLICAS=2, strategy auto-switches to LEAST_LOADED."""
    monkeypatch.setenv("CIRIS_LLM_REPLICAS", "2")
    mgr = BusManager(**mock_deps)
    assert mgr.llm.distribution_strategy == DistributionStrategy.LEAST_LOADED


def test_explicit_env_strategy_overrides_replica_default(mock_deps, monkeypatch):
    """Explicit CIRIS_LLM_DISTRIBUTION_STRATEGY wins over replica inference."""
    monkeypatch.setenv("CIRIS_LLM_REPLICAS", "3")
    monkeypatch.setenv("CIRIS_LLM_DISTRIBUTION_STRATEGY", "round_robin")
    mgr = BusManager(**mock_deps)
    assert mgr.llm.distribution_strategy == DistributionStrategy.ROUND_ROBIN


def test_invalid_strategy_falls_back_to_latency_based(mock_deps, monkeypatch):
    """Garbage value in the env var doesn't crash — falls back to safe default."""
    monkeypatch.setenv("CIRIS_LLM_DISTRIBUTION_STRATEGY", "not-a-real-strategy")
    mgr = BusManager(**mock_deps)
    assert mgr.llm.distribution_strategy == DistributionStrategy.LATENCY_BASED


def test_invalid_replicas_env_falls_back_to_single(mock_deps, monkeypatch):
    """Non-numeric CIRIS_LLM_REPLICAS doesn't crash — treated as 1."""
    monkeypatch.setenv("CIRIS_LLM_REPLICAS", "not-numeric")
    mgr = BusManager(**mock_deps)
    # 1 replica → default LATENCY_BASED, not LEAST_LOADED
    assert mgr.llm.distribution_strategy == DistributionStrategy.LATENCY_BASED
