"""The LLM fault ladder, driven by the REAL registry types.

test_llm_fault_ladder.py builds providers out of SimpleNamespace. That is fine
for the message logic and useless for the question that actually sank the
timer-race guard: does this code read attributes that EXIST on the object
production hands it?

A guard whose accessors miss returns "" everywhere, produces no warnings, and
looks exactly like a healthy system. So these tests use
`registries.base.ServiceProvider` and `registries.circuit_breaker.CircuitBreaker`
themselves, and assert that the real LLM service class declares the two fields
the ladder reads.
"""

import inspect

import pytest

from ciris_engine.logic.adapters.api.routes.system.health import (
    _breaker_state,
    _llm_breaker_warnings,
    _provider_last_error,
    _provider_model,
    _retry_seconds,
)
from ciris_engine.logic.registries.base import Priority, ServiceProvider
from ciris_engine.logic.registries.circuit_breaker import CircuitBreaker, CircuitBreakerConfig


class _LLMStandIn:
    """Carries exactly the attributes the real client sets — asserted below."""

    def __init__(self, model: str, err: str = "", fault: str = "") -> None:
        self.model_name = model
        self.last_error = err
        self.last_fault_code = fault


def _real_provider(
    name: str, model: str, err: str = "", fault: str = "", open_: bool = False, recovery: float = 45.0
):
    # NOT the default 45 != CircuitBreakerConfig().recovery_timeout (10.0).
    # _retry_seconds falls back to a hardcoded 10 when it cannot read the
    # config, which is the SAME number as the default — so a test using the
    # default cannot tell "read the breaker" from "returned the fallback",
    # and passes even when the accessor is broken. Mutation testing caught
    # exactly that here.
    breaker = CircuitBreaker(name, CircuitBreakerConfig(recovery_timeout=recovery))
    if open_:
        breaker.force_open(reason="test")
    return ServiceProvider(
        name=name,
        priority=Priority.NORMAL,
        instance=_LLMStandIn(model, err, fault),
        capabilities=["call_llm_structured"],
        circuit_breaker=breaker,
    )


class TestTheAccessorsMatchProduction:
    def test_the_real_client_declares_both_fields_the_ladder_reads(self) -> None:
        from ciris_engine.logic.services.runtime.llm_service.service import OpenAICompatibleClient

        src = inspect.getsource(OpenAICompatibleClient.__init__)
        assert "self.last_error" in src
        assert "self.last_fault_code" in src, (
            "the ladder prefers the structured slug over substring-matching the text; if the "
            "client stops setting it, every fault falls back to guessing from prose"
        )

    def test_service_provider_really_has_the_fields_the_ladder_walks(self) -> None:
        for field in ("name", "instance", "circuit_breaker"):
            assert field in ServiceProvider.__annotations__, field

    def test_accessors_resolve_against_a_real_provider(self) -> None:
        sp = _real_provider("groq_byok", "default", err="HTTP 404 model missing", fault="model_not_found")
        assert _provider_model(sp) == "default"
        assert _provider_last_error(sp) == "HTTP 404 model missing"
        assert _breaker_state(sp) == "closed"

    def test_retry_seconds_comes_from_the_real_breaker_config(self) -> None:
        sp = _real_provider("p", "m", open_=True, recovery=45.0)
        assert _retry_seconds(sp) == 45, "must READ the breaker, not return its fallback"

    def test_the_fallback_is_distinguishable_from_a_real_read(self) -> None:
        """Guards the test above: if the fallback ever equals what we configure,
        that assertion goes blind and this one says so."""
        sp_no_breaker = _real_provider("p", "m")
        sp_no_breaker.circuit_breaker = None
        assert _retry_seconds(sp_no_breaker) == 10
        assert _retry_seconds(sp_no_breaker) != 45


class TestTheLadderFiresOnRealObjects:
    def test_a_wrong_model_is_named_with_its_remedy(self) -> None:
        sp = _real_provider("groq_byok", "default", err="HTTP 404 the model does not exist", fault="model_not_found")
        codes = [w.code for w in _llm_breaker_warnings([sp])]
        assert "llm_model_not_found" in codes, codes

    def test_all_providers_open_reports_the_retry_interval(self) -> None:
        providers = [
            _real_provider("groq_byok", "default", err="HTTP 404 no such model", fault="model_not_found", open_=True),
            _real_provider("openai_primary", "gpt-4o-mini", err="HTTP 401 Invalid API Key", fault="invalid_api_key", open_=True),
        ]
        warnings = _llm_breaker_warnings(providers)
        codes = [w.code for w in warnings]
        assert "llm_all_providers_failed" in codes, codes
        message = next(w.message for w in warnings if w.code == "llm_all_providers_failed")
        assert "45" in message, (
            f"the user was promised the ACTUAL retry interval, not a constant; got {message!r}"
        )

    def test_a_healthy_provider_produces_no_warnings(self) -> None:
        assert _llm_breaker_warnings([_real_provider("ok", "gpt-4o-mini")]) == []

    def test_an_observer_is_given_no_link_on_real_objects(self) -> None:
        providers = [
            _real_provider("groq_byok", "default", err="HTTP 404 no such model", fault="model_not_found", open_=True)
        ]
        for warning in _llm_breaker_warnings(providers, can_manage=False):
            assert warning.action_url is None, (
                f"{warning.code} handed an observer a settings link they cannot open"
            )
