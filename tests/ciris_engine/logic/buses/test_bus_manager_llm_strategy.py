"""
Tests for BusManager's LLM distribution-strategy selection logic.

The bus default is LATENCY_BASED, but when replicas > 1 we need LEAST_LOADED
so the bus uses in-flight capacity (not just historical latency) to decide
which replica to send the next call to. CIRIS_LLM_DISTRIBUTION_STRATEGY
lets operators override either default explicitly.
"""

import os
from unittest.mock import MagicMock

import pytest

from ciris_engine.logic.buses.bus_manager import BusManager
from ciris_engine.logic.buses.llm_bus import DistributionStrategy


@pytest.fixture
def mock_deps():
    """Minimal mocks to let BusManager construct without touching the DB."""
    return {
        "service_registry": MagicMock(),
        "time_service": MagicMock(),
        "audit_service": MagicMock(),
        "telemetry_service": MagicMock(),
    }


def _clear_env():
    for var in ("CIRIS_LLM_REPLICAS", "CIRIS_LLM_DISTRIBUTION_STRATEGY"):
        os.environ.pop(var, None)


def test_default_strategy_is_latency_based(mock_deps):
    """Single-replica (default) bus uses LATENCY_BASED."""
    _clear_env()
    mgr = BusManager(**mock_deps)
    assert mgr.llm.distribution_strategy == DistributionStrategy.LATENCY_BASED


def test_replicas_gt_one_defaults_to_least_loaded(mock_deps):
    """With CIRIS_LLM_REPLICAS=2, strategy auto-switches to LEAST_LOADED."""
    _clear_env()
    os.environ["CIRIS_LLM_REPLICAS"] = "2"
    try:
        mgr = BusManager(**mock_deps)
        assert mgr.llm.distribution_strategy == DistributionStrategy.LEAST_LOADED
    finally:
        _clear_env()


def test_explicit_env_strategy_overrides_replica_default(mock_deps):
    """Explicit CIRIS_LLM_DISTRIBUTION_STRATEGY wins over replica inference."""
    _clear_env()
    os.environ["CIRIS_LLM_REPLICAS"] = "3"
    os.environ["CIRIS_LLM_DISTRIBUTION_STRATEGY"] = "round_robin"
    try:
        mgr = BusManager(**mock_deps)
        assert mgr.llm.distribution_strategy == DistributionStrategy.ROUND_ROBIN
    finally:
        _clear_env()


def test_invalid_strategy_falls_back_to_latency_based(mock_deps):
    """Garbage value in the env var doesn't crash — falls back to safe default."""
    _clear_env()
    os.environ["CIRIS_LLM_DISTRIBUTION_STRATEGY"] = "not-a-real-strategy"
    try:
        mgr = BusManager(**mock_deps)
        assert mgr.llm.distribution_strategy == DistributionStrategy.LATENCY_BASED
    finally:
        _clear_env()


def test_invalid_replicas_env_falls_back_to_single(mock_deps):
    """Non-numeric CIRIS_LLM_REPLICAS doesn't crash — treated as 1."""
    _clear_env()
    os.environ["CIRIS_LLM_REPLICAS"] = "not-numeric"
    try:
        mgr = BusManager(**mock_deps)
        # 1 replica → default LATENCY_BASED, not LEAST_LOADED
        assert mgr.llm.distribution_strategy == DistributionStrategy.LATENCY_BASED
    finally:
        _clear_env()
