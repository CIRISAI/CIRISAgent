"""The LLM ladder must tell the user which knob to turn (CIRISAgent#1078 follow-on).

Driven by a real Windows install on 2.9.27 that could not answer a single message.
Its two providers both pointed at Groq and both were broken differently:

    groq_byok                  model=default      -> 404 model does not exist
    openai_compatible_primary  model=gpt-4o-mini  -> 401 Invalid API Key

The user saw "timed out after 110s". Everything needed to fix it was in the log
and nothing was on screen. A wrong model and a rejected key are both "the provider
refused us" and need OPPOSITE actions — pick another model, or paste another key —
so reporting them identically makes the user guess on the one surface where
guessing costs them the whole agent.
"""

from types import SimpleNamespace

import pytest

from ciris_engine.logic.adapters.api.routes.system.health import _llm_breaker_warnings


def _p(name, model, state="closed", err="", recovery=10.0):
    return SimpleNamespace(
        name=name,
        instance=SimpleNamespace(model_name=model, last_error=err),
        circuit_breaker=SimpleNamespace(
            state=SimpleNamespace(value=state), config=SimpleNamespace(recovery_timeout=recovery)
        ),
    )


FRANCESCO = [
    _p("groq_byok", "default", "open", "HTTP 404 The model `default` does not exist or you do not have access to it."),
    _p("openai_compatible_primary", "gpt-4o-mini", "open", "HTTP 401 Invalid API Key"),
]


def _codes(ws):
    return [w.code for w in ws]


def _msg(ws, code):
    return next(w.message for w in ws if w.code == code)


class TestTheRealInstall:
    def test_the_wrong_model_is_named_with_its_provider(self):
        ws = _llm_breaker_warnings(FRANCESCO)
        m = _msg(ws, "llm_model_not_found")
        assert "groq_byok" in m and "default" in m
        assert "LLM Settings" in m, "must point at the screen that fixes it"

    def test_the_rejected_key_gets_a_DIFFERENT_instruction(self):
        # The whole point: same symptom class, opposite remedy.
        ws = _llm_breaker_warnings(FRANCESCO)
        assert "llm_key_rejected" in _codes(ws)
        key_msg = _msg(ws, "llm_key_rejected")
        model_msg = _msg(ws, "llm_model_not_found")
        assert key_msg != model_msg
        assert "key" in key_msg.lower() and "model" in model_msg.lower()

    def test_each_provider_is_named_with_its_role(self):
        ws = _llm_breaker_warnings(FRANCESCO)
        opens = [w.message for w in ws if w.code == "llm_provider_circuit_open"]
        assert any("Primary" in m for m in opens)
        assert any("Secondary" in m for m in opens)

    def test_the_outage_line_says_when_it_retries(self):
        # An outage you know self-heals in 10s is a wait. One you do not know
        # about is a support ticket.
        ws = _llm_breaker_warnings(FRANCESCO)
        m = _msg(ws, "llm_all_providers_failed")
        assert "10" in m
        assert any(w.code == "llm_all_providers_failed" and w.severity == "error" for w in ws)

    def test_every_warning_links_to_the_settings_card(self):
        for w in _llm_breaker_warnings(FRANCESCO):
            assert w.action_url == "/settings/llm", f"{w.code} has no route to the control"


class TestItDoesNotOverreach:
    def test_a_healthy_fleet_says_nothing(self):
        assert _llm_breaker_warnings([_p("groq_byok", "llama3")]) == []

    def test_an_unrecognised_fault_does_not_invent_an_instruction(self):
        # Naming a remedy we are not sure of sends the reader somewhere wrong.
        ws = _llm_breaker_warnings([_p("p", "m", "closed", "HTTP 503 upstream had a bad day")])
        assert "llm_model_not_found" not in _codes(ws)
        assert "llm_key_rejected" not in _codes(ws)
        assert "llm_provider_failed" in _codes(ws)
        assert "bad day" in _msg(ws, "llm_provider_failed"), "repeat the provider's own words instead"

    def test_one_provider_down_is_not_an_outage(self):
        ws = _llm_breaker_warnings(
            [_p("a", "m1", "open", "HTTP 401 Invalid API Key"), _p("b", "m2", "closed")]
        )
        assert "llm_all_providers_failed" not in _codes(ws)

    def test_half_open_is_not_reported_as_lost(self):
        # HALF_OPEN is the breaker testing recovery — warning as things improve
        # is how people learn to ignore warnings.
        ws = _llm_breaker_warnings([_p("a", "m", "half_open")])
        assert "llm_provider_circuit_open" not in _codes(ws)
