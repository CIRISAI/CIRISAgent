"""LLM failures escalate by what the user can do about it.

One failed call is noise. The same model failing until its breaker opens is a
configuration fact. Every breaker open is an outage. Three sentences, three
responses — the health surface used to collapse them into "all providers
unavailable", which named neither the model nor the provider and so pointed the
reader at nothing they could change.

Every level names MODEL and PROVIDER and links to the card that changes them.
"""

from types import SimpleNamespace

import pytest

from ciris_engine.logic.adapters.api.routes.system.health import _llm_breaker_warnings


def _provider(name, model, state):
    return SimpleNamespace(
        name=name,
        instance=SimpleNamespace(model_name=model),
        circuit_breaker=SimpleNamespace(state=SimpleNamespace(value=state)),
    )


class TestEscalation:
    def test_no_open_breaker_says_nothing(self):
        assert _llm_breaker_warnings([_provider("groq_byok", "llama3", "closed")]) == []

    def test_one_open_breaker_of_several_names_model_and_provider(self):
        ws = _llm_breaker_warnings(
            [_provider("groq_byok", "llama3", "open"), _provider("ciris_primary", "gpt-4o-mini", "closed")]
        )
        assert len(ws) == 1
        w = ws[0]
        assert w.code == "llm_provider_circuit_open"
        assert "llama3" in w.message and "groq_byok" in w.message
        # The agent still has a working route, so this is not an outage.
        assert w.severity == "warning"
        assert w.action_url == "/settings/llm"

    def test_all_open_is_one_outage_not_n_warnings(self):
        ws = _llm_breaker_warnings(
            [_provider("groq_byok", "llama3", "open"), _provider("ciris_primary", "gpt-4o-mini", "open")]
        )
        # N copies of the same sentence is how a warnings array stops being read.
        assert len(ws) == 1
        w = ws[0]
        assert w.code == "llm_all_circuits_open"
        assert w.severity == "error"
        assert "llama3" in w.message and "gpt-4o-mini" in w.message
        assert w.action_url == "/settings/llm"

    def test_half_open_is_not_open(self):
        # HALF_OPEN is the breaker testing recovery — reporting it as an outage
        # would fire a warning at the moment things are getting better.
        assert _llm_breaker_warnings([_provider("p", "m", "half_open")]) == []


class TestItNeverGuesses:
    def test_a_provider_without_a_breaker_is_not_reported_open(self):
        sp = SimpleNamespace(name="p", instance=SimpleNamespace(model_name="m"))
        assert _llm_breaker_warnings([sp]) == []

    def test_an_unknown_model_still_names_the_provider(self):
        sp = SimpleNamespace(
            name="mystery", instance=SimpleNamespace(), circuit_breaker=SimpleNamespace(state="open")
        )
        ws = _llm_breaker_warnings([sp])
        assert len(ws) == 1
        assert "mystery" in ws[0].message
        assert "unknown model" in ws[0].message
