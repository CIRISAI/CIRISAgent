"""Zero data retention has to be ON THE REQUEST, not in a config object.

The incident this comes from: a user could not configure OpenRouter, and the
provider answered 404 "No endpoints available matching your guardrail
restrictions and data policy." The agent had never sent a data policy. The only
place retention could be constrained was the user's OpenRouter ACCOUNT settings
— out of band, invisible to the client, unverifiable by it — and when those
settings filtered every endpoint, the product blamed the network.

So the requirement is not "add a ZDR field". It is: the promise must be
demonstrably present on the outbound request when the option is on, and
demonstrably absent when it is off. A setting that type-checks, round-trips
through its model, and never reaches the wire is exactly the failure being
fixed — one layer further in.
"""

import inspect

import pytest

from ciris_engine.logic.services.runtime.llm_service.service import (
    OpenAICompatibleClient,
    OpenAIConfig,
    _build_openrouter_provider_config,
)
from ciris_engine.schemas.services.llm import OpenRouterProviderConfig

OPENROUTER = "https://openrouter.ai/api/v1"


def _client(base_url: str, *, zdr: bool) -> OpenAICompatibleClient:
    """A client with only what _build_extra_kwargs reads — no network, no SDK."""
    c = OpenAICompatibleClient.__new__(OpenAICompatibleClient)
    c.openai_config = OpenAIConfig(base_url=base_url, require_zero_data_retention=zdr)
    c.model_name = "meta-llama/llama-4-scout"
    return c


def _extra_body(client: OpenAICompatibleClient) -> dict:
    from ciris_engine.schemas.services.llm import RetryState

    kwargs = client._build_extra_kwargs(None, None, "SomeModel", RetryState())
    return kwargs.get("extra_body") or {}


class TestTheDefaultIsTheSafePosture:
    def test_zdr_is_on_without_anyone_choosing_it(self) -> None:
        """The protective option must be what you get by NOT deciding."""
        assert OpenAIConfig().require_zero_data_retention is True


class TestItIsActuallyOnTheRequest:
    def test_deny_is_present_in_the_outbound_extra_body(self) -> None:
        body = _extra_body(_client(OPENROUTER, zdr=True))
        assert body.get("provider", {}).get("data_collection") == "deny", (
            f"the ZDR promise never reached the request payload; extra_body={body}"
        )

    def test_turning_it_off_removes_it_rather_than_sending_allow_silently(self) -> None:
        body = _extra_body(_client(OPENROUTER, zdr=False))
        assert "data_collection" not in body.get("provider", {}), (
            f"with ZDR off the preference must be omitted, not asserted; extra_body={body}"
        )

    def test_the_value_tracks_configuration_rather_than_a_constant(self) -> None:
        on = _extra_body(_client(OPENROUTER, zdr=True))
        off = _extra_body(_client(OPENROUTER, zdr=False))
        assert on != off, "the flag has no effect on the payload — it is decoration"


class TestTheEmitGuardCannotSwallowIt:
    """The subtlest way this could have shipped broken.

    `provider` is only attached when the config has something worth sending. If
    that condition checks order/ignore alone, then a ZDR-only config — the
    common case, since almost nobody sets a provider order — produces an empty
    condition and the block is dropped. The field would exist, be set from
    config, round-trip through its model, and never appear on the request.
    """

    def test_zdr_alone_with_no_ordering_still_emits_the_provider_block(self) -> None:
        body = _extra_body(_client(OPENROUTER, zdr=True))
        assert "provider" in body, (
            "no order and no ignore is the ordinary case; if the emit guard only tests those, "
            "the data policy is silently discarded"
        )

    def test_the_guard_names_data_collection(self) -> None:
        """Wherever the guard lives, it must name the field.

        It moved from _build_extra_kwargs into the shared builder when setup
        validation started using the same code — so this looks it up rather than
        pinning a location, and would fail if it split back into two.
        """
        from ciris_engine.logic.services.runtime.llm_service.service import build_request_extra_body

        src = inspect.getsource(build_request_extra_body)
        guard = next(l for l in src.splitlines() if "provider_config.order" in l and "if " in l)
        assert "data_collection" in guard, f"emit guard would drop a ZDR-only config: {guard.strip()}"


class TestTheBuilderIsToldRatherThanDeciding:
    def test_it_takes_the_policy_as_a_parameter(self) -> None:
        """Hardcoding the policy inside the builder is how this started."""
        params = inspect.signature(_build_openrouter_provider_config).parameters
        assert "require_zero_data_retention" in params

    def test_the_call_site_passes_configuration_through(self) -> None:
        src = inspect.getsource(OpenAICompatibleClient._build_extra_kwargs)
        assert "self.openai_config.require_zero_data_retention" in src, (
            "the request must carry the USER's policy, not a literal chosen here"
        )

    @pytest.mark.parametrize("zdr,expected", [(True, "deny"), (False, None)])
    def test_builder_output(self, zdr: bool, expected) -> None:
        assert _build_openrouter_provider_config(require_zero_data_retention=zdr).data_collection == expected


class TestTheBuiltKwargsAreTheRequest:
    """_build_extra_kwargs' output is splatted into the SDK call, so asserting
    on it is asserting on the request rather than on an intermediate."""

    def test_extra_kwargs_is_splatted_into_the_completion_call(self) -> None:
        src = inspect.getsource(OpenAICompatibleClient)
        assert "**extra_kwargs" in src, (
            "if the built kwargs stop being passed through, every assertion above becomes "
            "a statement about a dictionary nobody sends"
        )


class TestNonOpenRouterProvidersAreUnaffected:
    def test_no_provider_block_is_invented_for_other_endpoints(self) -> None:
        """data_collection is an OpenRouter routing preference. Sending it
        elsewhere risks a 422 — other providers express retention differently,
        which is why the catalogue records it per endpoint."""
        body = _extra_body(_client("https://api.groq.com/openai/v1", zdr=True))
        assert "provider" not in body


class TestSetupAndPipelineAskTheProviderTheSameQuestion:
    """The divergence that let setup bless what the pipeline refused.

    Setup validation used to build a bare AsyncOpenAI and send a plain
    completion — no reasoning-off extras, no data policy. So "Connection
    successful!" was an answer to a different question than the one the agent
    would go on to ask.

    With ZDR that gap inverts the guarantee. Omitting the policy makes
    validation MORE likely to succeed, so a user who asked for zero retention
    would be told their configuration works precisely because the check dropped
    the constraint they requested.
    """

    def test_both_paths_produce_the_same_extra_body(self) -> None:
        from ciris_engine.logic.services.runtime.llm_service.service import build_request_extra_body

        pipeline = _extra_body(_client(OPENROUTER, zdr=True))
        setup = build_request_extra_body(OPENROUTER, "meta-llama/llama-4-scout", require_zero_data_retention=True)
        assert pipeline == setup, (
            "setup validation and the pipeline must send the same request shaping, or setup can "
            f"pass on a configuration the pipeline refuses.\n  pipeline={pipeline}\n  setup={setup}"
        )

    def test_validation_actually_attaches_it_to_the_call(self) -> None:
        """Building the body and forgetting to send it is the same bug again."""
        import inspect

        from ciris_engine.logic.adapters.api.routes.setup import llm_validation

        src = inspect.getsource(llm_validation._validate_openai_compatible)
        assert "build_request_extra_body" in src, "validation must use the shared builder"
        assert src.count("extra_body=extra_body") >= 2, (
            "both the max_tokens attempt AND the max_completion_tokens retry must carry it — "
            "a reasoning model would otherwise validate without the policy"
        )

    def test_the_validation_request_carries_the_users_choice(self) -> None:
        from ciris_engine.logic.adapters.api.routes.setup.models import LLMValidationRequest

        assert "require_zero_data_retention" in LLMValidationRequest.model_fields
        req = LLMValidationRequest(provider="openrouter", api_key="k")
        assert req.require_zero_data_retention is True, (
            "a caller that omits the field must get the protective posture, not the permissive one"
        )
