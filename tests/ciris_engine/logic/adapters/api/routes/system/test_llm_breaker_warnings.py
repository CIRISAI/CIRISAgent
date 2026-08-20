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

    def test_all_open_emits_exactly_one_outage_line(self):
        ws = _llm_breaker_warnings(
            [_provider("groq_byok", "llama3", "open"), _provider("ciris_primary", "gpt-4o-mini", "open")]
        )
        # The original form of this test asserted len(ws) == 1, guarding against
        # "N copies of the same sentence is how a warnings array stops being
        # read." That concern is still right, but the guard was wrong: the ladder
        # now emits DISTINCT per-provider lines (which model, which fault, which
        # remedy) plus one outage line. Repetition was the problem, not count —
        # so the invariant is that the OUTAGE sentence appears exactly once, not
        # that the array is length one.
        outage = [w for w in ws if w.code == "llm_all_providers_failed"]
        assert len(outage) == 1, "the outage verdict must be stated once, not per provider"
        assert outage[0].severity == "error"
        assert outage[0].action_url == "/settings/llm"
        # And no two warnings may carry the same sentence.
        messages = [w.message for w in ws]
        assert len(messages) == len(set(messages)), f"duplicate warning text: {messages}"

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
        assert ws, "a provider with an open breaker must still be reported"
        joined = " ".join(w.message for w in ws)
        assert "mystery" in joined
        assert "unknown model" in joined
