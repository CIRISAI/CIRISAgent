"""Health names each provider spending limit with its own remedy (#1366 item 20 F8).

OpenRouter refuses for four reasons, named in ``limit_source``: a transient
in-flight budget, one request too large for it, the key's own limit, and a
guardrail/workspace budget. Before, all four fell through to the generic
"provider failed" line, and a retried in-flight refusal stayed on the health
page after the provider had answered again.
"""

import time
from types import SimpleNamespace

import pytest

from ciris_engine.logic.adapters.api.routes.system.health import _llm_breaker_warnings


def _p(code: str, err: str = "OpenRouter refused", live: bool = True):
    instance = SimpleNamespace(
        model_name="google/gemma-4-31B-it",
        last_error=err,
        last_fault_code=code,
        live_fault_code=lambda: code if live else "",
    )
    return SimpleNamespace(
        name="openrouter",
        instance=instance,
        circuit_breaker=SimpleNamespace(
            state=SimpleNamespace(value="closed"), config=SimpleNamespace(recovery_timeout=10.0)
        ),
    )


@pytest.mark.parametrize(
    "fault,code,severity",
    [
        ("in_flight_budget", "llm_in_flight_budget", "warning"),
        ("request_too_large", "llm_request_too_large", "error"),
        ("key_limit", "llm_key_limit", "error"),
        ("budget_limit", "llm_budget_limit", "error"),
    ],
)
@pytest.mark.parametrize("can_manage", [True, False])
def test_each_limit_has_its_own_warning(fault, code, severity, can_manage):
    ws = _llm_breaker_warnings([_p(fault)], can_manage=can_manage)
    assert [w.code for w in ws] == [code]
    w = ws[0]
    assert w.severity == severity
    assert "openrouter" in w.message and "gemma-4-31B-it" in w.message
    assert not w.message.startswith("status."), "the string must exist in en.json"
    assert (w.action_url is not None) == can_manage


@pytest.mark.parametrize("can_manage", [True, False])
def test_key_limit_says_key_limit_never_add_credits(can_manage):
    m = _llm_breaker_warnings([_p("key_limit")], can_manage=can_manage)[0].message.lower()
    assert "key limit" in m and "credit" not in m


def test_request_too_large_names_its_remedies():
    m = _llm_breaker_warnings([_p("request_too_large")])[0].message
    assert "lower max_tokens or the prompt, or add credits" in m


def test_a_retried_in_flight_refusal_is_not_left_on_the_page():
    # The provider answered after the refusal: nothing to report, not even
    # the generic "provider failed" line.
    assert _llm_breaker_warnings([_p("in_flight_budget", live=False)]) == []


def test_a_terminal_limit_stays_after_unrelated_successes():
    assert [w.code for w in _llm_breaker_warnings([_p("key_limit", live=False)])] == ["llm_key_limit"]
