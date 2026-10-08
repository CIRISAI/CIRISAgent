"""LLM-mode fixtures for the mock-LLM trace-export guard (CIRISAgent#1244).

The test session runs with ``CIRIS_MOCK_LLM=true`` (tests/conftest.py), and the
guard treats that as "the mock LLM is active": no ship grant, no federation
delivery, ``deployment_type="mock"``. A test of PRODUCTION behaviour has to say
so explicitly with ``real_llm_mode``. A test of the guard itself uses
``mock_llm_mode`` so it does not depend on the session default.
"""

import sys
from typing import Iterator

import pytest


def _clear_mock_signals(monkeypatch: pytest.MonkeyPatch) -> None:
    from ciris_engine.logic.config import env_utils
    from ciris_engine.logic.utils import mock_llm_guard

    monkeypatch.delenv("CIRIS_MOCK_LLM", raising=False)
    monkeypatch.delenv("CIRIS_TRACE_RUN_KIND", raising=False)
    monkeypatch.setattr(sys, "argv", [a for a in sys.argv if a != "--mock-llm"])
    monkeypatch.delitem(env_utils._ENV_VALUES, "CIRIS_MOCK_LLM", raising=False)
    mock_llm_guard._reset_for_tests()


@pytest.fixture
def real_llm_mode(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """No mock-LLM signal anywhere: env, .env values, argv or the latch."""
    from ciris_engine.logic.utils import mock_llm_guard

    _clear_mock_signals(monkeypatch)
    yield
    mock_llm_guard._reset_for_tests()


@pytest.fixture
def mock_llm_mode(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Exactly one mock-LLM signal: the env var, with a fresh latch and log-once set."""
    from ciris_engine.logic.utils import mock_llm_guard

    _clear_mock_signals(monkeypatch)
    monkeypatch.setenv("CIRIS_MOCK_LLM", "true")
    yield
    mock_llm_guard._reset_for_tests()
