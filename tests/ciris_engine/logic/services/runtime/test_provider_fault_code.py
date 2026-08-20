"""Diagnose the provider's fault from ITS code, not from our reading of its prose.

The health surface turns this into an instruction — "choose a different model" vs
"update your key" — and those are opposite actions. Deriving them from substrings
makes every vendor's wording, in every locale, load-bearing, and the first vendor
to write "unknown model" instead of "does not exist" silently stops being
diagnosed.

The trap this pins: a 404 from an OpenAI-compatible endpoint means "we could not
find that". That is a missing MODEL if the body says so, and a WRONG BASE URL if
it does not. Telling a user with a typo'd endpoint to go change their model is
confidently wrong, which is worse than saying nothing.
"""

import httpx
import openai
import pytest

from ciris_engine.logic.services.runtime.llm_service.service import _root_provider_fault


def _api_error(status: int, body: dict | None):
    req = httpx.Request("POST", "https://api.groq.com/openai/v1/chat/completions")
    resp = httpx.Response(status, request=req, json=body or {})
    return openai.APIStatusError("boom", response=resp, body=body)


class TestStructuredSignal:
    def test_groqs_real_model_not_found_body(self):
        # Verbatim shape from the 2.9.27 Windows field report.
        e = _api_error(404, {"error": {"message": "The model `default` does not exist or you do not "
                                                  "have access to it.",
                                       "type": "invalid_request_error", "code": "model_not_found"}})
        assert _root_provider_fault(e) == "model_not_found"

    def test_a_401_is_a_bad_key_without_needing_a_body(self):
        assert _root_provider_fault(_api_error(401, None)) == "invalid_api_key"

    def test_429_is_rate_limited(self):
        assert _root_provider_fault(_api_error(429, None)) == "rate_limited"

    def test_it_digs_through_a_wrapper(self):
        # Instructor wraps; the provider's truth is one or two links down.
        inner = _api_error(404, {"error": {"code": "model_not_found", "message": "no such model"}})
        try:
            try:
                raise inner
            except Exception as ie:
                raise RuntimeError("InstructorRetryException-ish") from ie
        except RuntimeError as outer:
            assert _root_provider_fault(outer) == "model_not_found"


class TestTheFourOhFourTrap:
    def test_a_bare_404_is_NOT_diagnosed_as_a_missing_model(self):
        # Very likely a wrong base_url. Sending this user to change their model
        # is confidently wrong.
        assert _root_provider_fault(_api_error(404, None)) == ""

    def test_a_404_about_something_else_is_not_a_missing_model(self):
        e = _api_error(404, {"error": {"message": "The requested endpoint was not found",
                                       "type": "invalid_request_error"}})
        assert _root_provider_fault(e) == ""

    def test_a_404_whose_message_names_the_model_does_count(self):
        # No `code` field, but the body says what was missing.
        e = _api_error(404, {"error": {"message": "The model `llama-99` does not exist"}})
        assert _root_provider_fault(e) == "model_not_found"


class TestItStaysQuietWhenUnsure:
    def test_an_unknown_fault_returns_empty(self):
        assert _root_provider_fault(_api_error(503, {"error": {"message": "upstream unavailable"}})) == ""

    def test_a_plain_exception_returns_empty(self):
        assert _root_provider_fault(RuntimeError("something went wrong")) == ""
