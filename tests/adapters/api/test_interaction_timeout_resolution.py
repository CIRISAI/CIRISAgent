"""
Regression tests for `_get_interaction_timeout` resolution:
env var > explicitly configured api_config > LLM budget (#1186).

#791 air-test postgres-leg failure root cause: the server-side interact
response-correlation window defaults to 55s, but the QA runner needed
to bump it to 180s for the --parallel-backends matrix (two agent
stacks share one CI runner, ASPDMA legitimately takes 60-90s under
that load). We set `CIRIS_API_INTERACTION_TIMEOUT=180` in the QA
runner's server spawn, but it had no effect — the adapter's
`_load_config` discards the env-loaded config when an
`APIAdapterConfig` object is passed via `adapter_config` (which is the
runtime's default code path).

`_get_interaction_timeout` now re-checks the env var on each call so
operator overrides take effect regardless of how the
`api_config.interaction_timeout` field was resolved at adapter init.
These tests pin that contract.
"""

import os
from unittest.mock import MagicMock

import pytest

from ciris_engine.logic.adapters.api.routes.agent import _get_interaction_timeout
from ciris_engine.logic.config import llm_budget


@pytest.fixture(autouse=True)
def _budget_reads_process_env_only(monkeypatch):
    """The budget falls back to the home .env; keep a developer's .env out of it."""
    monkeypatch.setattr(llm_budget, "get_env_var", lambda name, default=None: os.environ.get(name, default))
    for var in ("CIRIS_LLM_BUDGET_PROFILE", "CIRIS_LLM_PROVIDER", "LLM_PROVIDER", "OPENAI_API_BASE", "CIRIS_OPENAI_API_BASE"):
        monkeypatch.delenv(var, raising=False)


def _make_request(api_config_timeout):
    """Build a fake Request whose app.state.api_config exposes the
    given interaction_timeout. None means no api_config attribute at
    all (the production-default fallback path)."""
    req = MagicMock()
    if api_config_timeout is None:
        # Attribute absent — hasattr(request.app.state, "api_config")
        # returns False, so the default kicks in.
        delattr_target = MagicMock()
        del delattr_target.api_config
        req.app.state = delattr_target
    else:
        req.app.state.api_config.interaction_timeout = api_config_timeout
    return req


def _make_request_with_none_config():
    req = MagicMock()
    req.app.state.api_config.interaction_timeout = None
    return req


class TestInteractionTimeoutResolution:
    def test_default_when_no_config_no_env(self, monkeypatch):
        """No env, no config: the LLM budget decides (#1186). A hosted
        provider (the default with no base URL) gets the REMOTE deadline."""
        monkeypatch.delenv("CIRIS_API_INTERACTION_TIMEOUT", raising=False)
        assert _get_interaction_timeout(_make_request(None)) == 195.0

    def test_unset_config_uses_budget(self, monkeypatch):
        """interaction_timeout=None is "not configured": the budget applies."""
        monkeypatch.delenv("CIRIS_API_INTERACTION_TIMEOUT", raising=False)
        assert _get_interaction_timeout(_make_request_with_none_config()) == 195.0

    def test_local_provider_gets_local_deadline(self, monkeypatch):
        """A model on the user's own hardware gets the LOCAL deadline."""
        monkeypatch.delenv("CIRIS_API_INTERACTION_TIMEOUT", raising=False)
        monkeypatch.setenv("OPENAI_API_BASE", "http://127.0.0.1:11434/v1")
        assert _get_interaction_timeout(_make_request(None)) == 900.0
        assert _get_interaction_timeout(_make_request_with_none_config()) == 900.0

    def test_explicit_config_beats_budget(self, monkeypatch):
        monkeypatch.delenv("CIRIS_API_INTERACTION_TIMEOUT", raising=False)
        monkeypatch.setenv("CIRIS_LLM_BUDGET_PROFILE", "local")
        assert _get_interaction_timeout(_make_request(90.0)) == 90.0

    def test_non_numeric_or_nonpositive_config_is_ignored(self, monkeypatch):
        monkeypatch.delenv("CIRIS_API_INTERACTION_TIMEOUT", raising=False)
        assert _get_interaction_timeout(_make_request(0)) == 195.0
        assert _get_interaction_timeout(_make_request(True)) == 195.0
        # A bare MagicMock attribute (unconfigured test double) is not a number.
        assert _get_interaction_timeout(MagicMock()) == 195.0

    def test_env_var_beats_budget(self, monkeypatch):
        monkeypatch.setenv("CIRIS_LLM_BUDGET_PROFILE", "local")
        monkeypatch.setenv("CIRIS_API_INTERACTION_TIMEOUT", "42")
        assert _get_interaction_timeout(_make_request(None)) == 42.0

    def test_config_value_when_no_env(self, monkeypatch):
        monkeypatch.delenv("CIRIS_API_INTERACTION_TIMEOUT", raising=False)
        assert _get_interaction_timeout(_make_request(90.0)) == 90.0

    def test_env_var_overrides_default(self, monkeypatch):
        """Without api_config, env var should still take effect."""
        monkeypatch.setenv("CIRIS_API_INTERACTION_TIMEOUT", "180")
        assert _get_interaction_timeout(_make_request(None)) == 180.0

    def test_env_var_overrides_api_config(self, monkeypatch):
        """The load-bearing assertion for #791 fix: env var wins even
        when api_config is set. Without this, the QA runner's bump
        had zero effect because the runtime always passes a stored
        `APIAdapterConfig` and the adapter's `_load_config` discards
        the env-loaded config (adapter.py:_apply_adapter_config)."""
        monkeypatch.setenv("CIRIS_API_INTERACTION_TIMEOUT", "180")
        assert _get_interaction_timeout(_make_request(55.0)) == 180.0

    def test_malformed_env_var_falls_back_to_config(self, monkeypatch):
        """Garbage env var must not crash — fall through to config."""
        monkeypatch.setenv("CIRIS_API_INTERACTION_TIMEOUT", "not-a-number")
        assert _get_interaction_timeout(_make_request(55.0)) == 55.0

    def test_empty_env_var_falls_back_to_config(self, monkeypatch):
        """Empty string is falsy — treat as unset."""
        monkeypatch.setenv("CIRIS_API_INTERACTION_TIMEOUT", "")
        assert _get_interaction_timeout(_make_request(55.0)) == 55.0

    def test_float_env_var(self, monkeypatch):
        """Fractional values are accepted — useful for live-tuning
        without an integer-only constraint."""
        monkeypatch.setenv("CIRIS_API_INTERACTION_TIMEOUT", "120.5")
        assert _get_interaction_timeout(_make_request(55.0)) == 120.5
