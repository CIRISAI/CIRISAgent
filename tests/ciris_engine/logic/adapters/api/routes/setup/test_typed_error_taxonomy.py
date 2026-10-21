"""The error a user sees must name their actual remedy.

The live conformance matrix measured a 45% classifier gap: the share of failure
cells whose user-facing message contradicted the real cause. Every test case
here is one of those observed cells — real provider, real status, real body —
not a hypothesised error shape.

The classifier is now typed-first: it reads the provider's structured verdict
through the SAME walker the runtime health surface uses, so setup and the
running agent diagnose a fault identically. Substring matching over str(error)
survives only for transport failures that carry no provider body at all.
"""

import httpx
import pytest

from ciris_engine.logic.adapters.api.routes.setup.llm_validation import (
    _classify_llm_connection_error,
    _validate_llm_connection,
)
from ciris_engine.logic.adapters.api.routes.setup.models import LLMValidationRequest


def _openai_error(status_code: int, body: dict, message: str = ""):
    """A real openai APIStatusError, built the way the SDK builds it."""
    from openai import APIStatusError

    response = httpx.Response(
        status_code=status_code,
        request=httpx.Request("POST", "https://example.invalid/v1/chat/completions"),
        json=body,
    )
    return APIStatusError(message or str(body), response=response, body=body)


class TestObservedCellsNowClassifyCorrectly:
    """Each case is a live-observed provider response from the matrix run."""

    def test_openai_404_missing_model_is_a_model_problem_not_an_endpoint_problem(self) -> None:
        # openai 404: "The model `x` does not exist or you do not have access to it."
        err = _openai_error(
            404, {"error": {"message": "The model `x` does not exist or you do not have access to it.", "code": None}}
        )
        r = _classify_llm_connection_error(err, None)
        assert r.message == "Model not found"
        assert "endpoint" not in (r.error or "").lower(), (
            "this exact cell read 'check your endpoint' before — the user's endpoint was fine"
        )

    def test_groqs_structured_code_is_trusted_verbatim(self) -> None:
        # groq 404 body carries code=model_not_found (2.9.27 field report)
        err = _openai_error(
            404, {"error": {"message": "The model `default` does not exist", "code": "model_not_found"}}
        )
        assert _classify_llm_connection_error(err, None).message == "Model not found"

    def test_openrouters_data_policy_refusal_names_the_policy_not_the_network(self) -> None:
        # THE FRANCESCO CELL. openrouter 404: "No endpoints available matching
        # your guardrail restrictions and data policy."
        err = _openai_error(
            404,
            {"error": {"message": "No endpoints available matching your guardrail restrictions and data policy. Configure: https://openrouter.ai/settings/privacy", "code": 404}},
        )
        r = _classify_llm_connection_error(err, None)
        assert r.message == "Blocked by data policy"
        assert "endpoint url" not in (r.error or "").lower() and "network" not in (r.error or "").lower(), (
            f"the original incident: this was reported as a network problem. got: {r.error}"
        )

    def test_openrouters_routing_refusal_is_the_same_family(self) -> None:
        # observed live: {"provider": {"only": ["Azure"]}} -> 404 "No allowed
        # providers are available for the selected model."
        err = _openai_error(
            404, {"error": {"message": "No allowed providers are available for the selected model.", "code": 404}}
        )
        assert _classify_llm_connection_error(err, None).message == "Blocked by data policy"

    def test_anthropics_out_of_credit_400_does_not_tell_the_user_to_replace_a_working_key(self) -> None:
        # observed live: anthropic reports empty balance as HTTP 400 — the same
        # status google uses for a REJECTED key. Only the body separates them.
        err = _openai_error(
            400,
            {"error": {"message": "Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits.", "code": None}},
        )
        r = _classify_llm_connection_error(err, None)
        assert r.message == "Out of credit"
        assert "replacing the key will not help" in (r.error or "")

    def test_togethers_402_is_billing(self) -> None:
        err = _openai_error(402, {"error": {"message": "Credit limit exceeded, please add credits.", "code": None}})
        assert _classify_llm_connection_error(err, None).message == "Out of credit"

    def test_googles_400_worded_key_rejection_is_authentication(self) -> None:
        # observed live: google 400 "API key not valid. Please pass a valid API
        # key." — no 401, no error.code. Fell to the generic branch before, and
        # the user saw raw JSON.
        err = _openai_error(400, {"error": {"message": "API key not valid. Please pass a valid API key.", "code": None}})
        assert _classify_llm_connection_error(err, None).message == "Authentication failed"

    def test_a_plain_401_is_authentication_whatever_the_body_says(self) -> None:
        err = _openai_error(401, {"error": {"message": "User not found.", "code": None}})
        assert _classify_llm_connection_error(err, None).message == "Authentication failed"

    def test_a_404_with_no_model_in_the_body_is_still_an_endpoint_problem(self) -> None:
        """The inverse must keep working: a typo'd base_url 404s with a body
        that says nothing about models, and sending THAT user to change their
        model would be the same wrong-remedy defect mirrored."""
        err = _openai_error(404, {"error": {"message": "Not Found", "code": None}})
        r = _classify_llm_connection_error(err, "http://localhost:9999/v1")
        assert r.message != "Model not found"


class TestTransportFailuresUseTheExceptionType:
    def test_a_connection_error_names_the_url_not_a_fault(self) -> None:
        from openai import APIConnectionError

        err = APIConnectionError(request=httpx.Request("POST", "http://localhost:1234/v1/chat/completions"))
        r = _classify_llm_connection_error(err, "http://localhost:1234/v1")
        assert r.message == "Connection failed"
        assert "localhost:1234" in (r.error or "")


class TestValidationRefusesWithoutAModel:
    """The three per-provider fabrications are deleted, not just bypassed.

    On providers that served the guessed model (openai, openrouter) the wizard
    said "Connection successful!" for a model the user never chose — a silent
    wrong SUCCESS, which cost more than the 404s did.
    """

    @pytest.mark.asyncio
    @pytest.mark.parametrize("provider", ["openai", "openrouter", "anthropic", "google", "groq", "together"])
    async def test_no_model_is_refused_before_any_network(self, provider: str) -> None:
        r = await _validate_llm_connection(LLMValidationRequest(provider=provider, api_key="sk-test", model=None))
        assert r.valid is False
        assert r.message == "No model selected"

    @pytest.mark.asyncio
    async def test_mobile_local_keeps_its_short_circuit(self) -> None:
        r = await _validate_llm_connection(LLMValidationRequest(provider="mobile_local", api_key="", model=None))
        assert r.valid is True

    def test_the_fabricated_defaults_are_gone_from_the_source(self) -> None:
        import inspect

        from ciris_engine.logic.adapters.api.routes.setup import llm_validation

        src = inspect.getsource(llm_validation)
        for fabricated in ('"gpt-3.5-turbo"', '"claude-haiku-4-5-20251001"', '"gemini-2.0-flash"'):
            assert fabricated not in src, (
                f"{fabricated} is back in llm_validation.py — the wizard is substituting a model "
                "the user never chose again (CIRISAgent#1078-class)"
            )


class TestUncataloguedProvidersAreNotErrors:
    @pytest.mark.asyncio
    async def test_deepinfra_answers_normally_and_points_at_live_discovery(self) -> None:
        from ciris_engine.logic.adapters.api.routes.setup.llm_routes import get_provider_models

        resp = await get_provider_models("deepinfra")
        data = resp.data
        assert data["curated"] is False
        assert data["compatible_models"] == []
        assert "live discovery" in data["note"].lower() or "list-models" in data["note"]

    @pytest.mark.asyncio
    async def test_a_catalogued_provider_still_serves_curated_data(self) -> None:
        from ciris_engine.logic.adapters.api.routes.setup.llm_routes import get_provider_models

        resp = await get_provider_models("openai")
        assert len(resp.data["compatible_models"]) > 0


class TestTheSdkUnwrapsTheBodyAndSoMustWe:
    """Verified live: openai's SDK stores `.body` as the INNER error object.

    A real NotFoundError carries {"message": ..., "code": "model_not_found"}
    directly — no {"error": ...} envelope. The first version of these tests
    built the wrapped shape because that is how I imagined the SDK stores it;
    they passed while every live 404 fell through to the endpoint branch. The
    live matrix caught it within the hour. Both shapes must classify, and the
    UNWRAPPED one is the shape production actually sees.
    """

    def test_the_unwrapped_openai_body_classifies(self) -> None:
        # byte-for-byte the body observed live on 2026-08-21
        err = _openai_error(404, {})
        err.body = {
            "message": "The model `ciris-qa-does-not-exist` does not exist or you do not have access to it.",
            "type": "invalid_request_error",
            "param": None,
            "code": "model_not_found",
        }
        assert _classify_llm_connection_error(err, None).message == "Model not found"

    def test_googles_list_wrapped_body_classifies(self) -> None:
        # observed live: google wraps its error in a LIST
        err = _openai_error(400, {})
        err.body = [{"error": {"code": 400, "message": "API key not valid. Please pass a valid API key.", "status": "INVALID_ARGUMENT"}}]
        assert _classify_llm_connection_error(err, None).message == "Authentication failed"

    def test_openrouters_invalid_model_id_wording(self) -> None:
        err = _openai_error(400, {"error": {"message": "meta-llama/nope is not a valid model ID", "code": 400}})
        assert _classify_llm_connection_error(err, None).message == "Model not found"

    def test_a_whitespace_key_is_named_at_the_gate(self) -> None:
        from ciris_engine.logic.adapters.api.routes.setup.llm_validation import (
            _validate_api_key_for_provider,
        )

        r = _validate_api_key_for_provider(
            LLMValidationRequest(provider="openrouter", api_key="sk-or-v1-abc\n", model="m")
        )
        assert r is not None and "whitespace" in (r.error or "").lower()
