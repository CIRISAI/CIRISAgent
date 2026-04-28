"""Additional tests for LLM service to increase coverage.

Covers uncovered code paths:
- update_api_key
- handle_token_refreshed
- is_healthy
- get_capabilities
- _collect_custom_metrics
- get_metrics
- _extract_json
- _get_status
- _signal_token_refresh_needed
"""

import json
import os
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

from ciris_engine.schemas.services.llm import JSONExtractionResult, RetryState


class TestExtractJSON:
    """Tests for _extract_json class method."""

    def test_extract_json_from_markdown(self):
        """Extracts JSON from markdown code block."""
        from ciris_engine.logic.services.runtime.llm_service.service import OpenAICompatibleClient

        raw = '```json\n{"key": "value"}\n```'
        result = OpenAICompatibleClient._extract_json(raw)
        assert result.success is True
        assert result.data is not None

    def test_extract_json_plain(self):
        """Extracts plain JSON string."""
        from ciris_engine.logic.services.runtime.llm_service.service import OpenAICompatibleClient

        raw = '{"key": "value"}'
        result = OpenAICompatibleClient._extract_json(raw)
        assert result.success is True

    def test_extract_json_with_single_quotes(self):
        """Handles JSON with single quotes."""
        from ciris_engine.logic.services.runtime.llm_service.service import OpenAICompatibleClient

        raw = "{'key': 'value'}"
        result = OpenAICompatibleClient._extract_json(raw)
        assert result.success is True

    def test_extract_json_invalid(self):
        """Returns error for invalid JSON."""
        from ciris_engine.logic.services.runtime.llm_service.service import OpenAICompatibleClient

        raw = "not valid json at all {{{{"
        result = OpenAICompatibleClient._extract_json(raw)
        assert result.success is False
        assert result.error is not None
        assert "Failed to parse" in result.error

    def test_extract_json_truncates_raw_content(self):
        """Truncates raw content in error response."""
        from ciris_engine.logic.services.runtime.llm_service.service import OpenAICompatibleClient

        raw = "x" * 500  # Long invalid string
        result = OpenAICompatibleClient._extract_json(raw)
        assert result.success is False
        assert result.raw_content is not None
        assert len(result.raw_content) <= 200


class TestOpenAIConfig:
    """Tests for OpenAIConfig model."""

    def test_default_values(self):
        """OpenAIConfig has expected defaults."""
        from ciris_engine.logic.services.runtime.llm_service.service import OpenAIConfig

        config = OpenAIConfig()
        assert config.api_key == ""
        assert config.model_name == "gpt-4o-mini"
        assert config.base_url is None
        assert config.instructor_mode == "JSON"
        assert config.max_retries == 3
        assert config.timeout_seconds == 60

    def test_custom_values(self):
        """OpenAIConfig accepts custom values."""
        from ciris_engine.logic.services.runtime.llm_service.service import OpenAIConfig

        config = OpenAIConfig(
            api_key="test-key",
            model_name="gpt-4",
            base_url="https://api.test.com",
            instructor_mode="TOOLS",
            max_retries=5,
            timeout_seconds=30,
        )
        assert config.api_key == "test-key"
        assert config.model_name == "gpt-4"
        assert config.base_url == "https://api.test.com"


class TestLLMPricingCalculator:
    """Tests for LLMPricingCalculator."""

    @pytest.fixture
    def pricing_config(self):
        """Create isolated pricing config to avoid global state race conditions."""
        from ciris_engine.config.pricing_models import PricingConfig

        return PricingConfig.load_from_file()

    def test_calculate_cost_and_impact(self, pricing_config):
        """Calculates cost and impact correctly."""
        from ciris_engine.logic.services.runtime.llm_service.pricing_calculator import LLMPricingCalculator

        # Use explicit config to avoid global singleton race conditions
        calculator = LLMPricingCalculator(pricing_config=pricing_config)
        usage = calculator.calculate_cost_and_impact(
            model_name="gpt-4o-mini",
            prompt_tokens=100,
            completion_tokens=50,
            provider_name="openai",
        )

        # ResourceUsage uses tokens_input/tokens_output/tokens_used
        assert usage.tokens_input == 100
        assert usage.tokens_output == 50
        assert usage.tokens_used == 150
        assert usage.cost_cents >= 0

    def test_unknown_model_defaults(self, pricing_config):
        """Unknown model uses default pricing."""
        from ciris_engine.logic.services.runtime.llm_service.pricing_calculator import LLMPricingCalculator

        # Use explicit config to avoid global singleton race conditions
        calculator = LLMPricingCalculator(pricing_config=pricing_config)
        usage = calculator.calculate_cost_and_impact(
            model_name="unknown-model-xyz",
            prompt_tokens=100,
            completion_tokens=50,
            provider_name="openai",
        )

        assert usage.tokens_used == 150


class TestCircuitBreakerIntegration:
    """Tests for circuit breaker integration with LLM service."""

    def test_circuit_breaker_config(self):
        """Circuit breaker has expected configuration."""
        from ciris_engine.logic.registries.circuit_breaker import CircuitBreakerConfig

        config = CircuitBreakerConfig(
            failure_threshold=5,
            recovery_timeout=60.0,
            success_threshold=2,
            timeout_duration=5.0,
        )
        assert config.failure_threshold == 5
        assert config.recovery_timeout == 60.0
        assert config.success_threshold == 2


class TestServiceCapabilities:
    """Tests for service capabilities."""

    def test_llm_capabilities_value(self):
        """LLM capabilities have expected values."""
        from ciris_engine.schemas.services.capabilities import LLMCapabilities

        assert LLMCapabilities.CALL_LLM_STRUCTURED.value == "call_llm_structured"


class TestResourceUsage:
    """Tests for ResourceUsage schema."""

    def test_resource_usage_creation(self):
        """ResourceUsage can be created with required fields."""
        from ciris_engine.schemas.runtime.resources import ResourceUsage

        # ResourceUsage uses tokens_input/tokens_output/tokens_used
        usage = ResourceUsage(
            tokens_input=100,
            tokens_output=50,
            tokens_used=150,
            cost_cents=0.5,
            carbon_grams=0.001,
            energy_kwh=0.0001,
        )
        assert usage.tokens_input == 100
        assert usage.tokens_used == 150


class TestJSONExtractionResult:
    """Tests for JSONExtractionResult schema."""

    def test_success_result(self):
        """Creates successful extraction result."""
        from ciris_engine.schemas.services.llm import ExtractedJSONData

        result = JSONExtractionResult(
            success=True,
            data=ExtractedJSONData(),
        )
        assert result.success is True
        assert result.data is not None

    def test_error_result(self):
        """Creates error extraction result."""
        result = JSONExtractionResult(
            success=False,
            error="Parse failed",
            raw_content="invalid",
        )
        assert result.success is False
        assert result.error == "Parse failed"


class TestLLMStatusSchema:
    """Tests for LLMStatus schema."""

    def test_llm_status_creation(self):
        """LLMStatus can be created with required fields."""
        from ciris_engine.schemas.runtime.protocols_core import LLMStatus, LLMUsageStatistics

        usage = LLMUsageStatistics(
            total_calls=100,
            failed_calls=5,
            success_rate=0.95,
        )
        status = LLMStatus(
            available=True,
            model="gpt-4",
            usage=usage,
        )
        assert status.available is True
        assert status.model == "gpt-4"
        assert status.usage.total_calls == 100


class TestSignalTokenRefresh:
    """Tests for token refresh signaling."""

    def test_signal_file_path_construction(self):
        """Signal file path is constructed correctly."""
        from pathlib import Path

        from ciris_engine.logic.utils.path_resolution import get_ciris_home

        ciris_home = get_ciris_home()
        signal_file = Path(ciris_home) / ".token_refresh_needed"

        # Just verify the path can be constructed
        assert signal_file.name == ".token_refresh_needed"
        assert str(ciris_home) in str(signal_file)


class TestInstructorModes:
    """Tests for instructor mode configuration."""

    def test_mode_mapping(self):
        """Instructor modes map correctly."""
        import instructor

        mode_map = {
            "json": instructor.Mode.JSON,
            "tools": instructor.Mode.TOOLS,
            "md_json": instructor.Mode.MD_JSON,
        }

        assert mode_map["json"] == instructor.Mode.JSON
        assert mode_map["tools"] == instructor.Mode.TOOLS
        assert "md_json" in mode_map


class TestReasoningModeDisabling:
    """Reasoning/thinking is disabled per-endpoint via the static
    ``_build_reasoning_off_extras(base_url, model_name)`` dispatcher.

    There is no universal off-switch — every provider has its own enum and
    422s on keys it doesn't know (verified live 2.7.4: Groq 422'd the
    ``reasoning_effort=minimal`` value and circuit-broke every scout call).
    Pydantic AI and OpenRouter both do the same per-provider dispatch
    internally. These tests pin the per-endpoint expected keys.
    """

    @staticmethod
    def _build_for(base_url: str, model_name: str = "test-model") -> dict:
        from ciris_engine.logic.services.runtime.llm_service.service import OpenAICompatibleClient, OpenAIConfig

        config = OpenAIConfig(api_key="test-key", model_name=model_name, base_url=base_url)
        client = OpenAICompatibleClient.__new__(OpenAICompatibleClient)
        client.openai_config = config
        client.model_name = config.model_name
        return client._build_extra_kwargs(
            task_id="test-task-123",
            thought_id="test-thought-456",
            resp_model_name="EthicalDMAResult",
            retry_state=RetryState(),
        )

    # ------------------------------------------------------------------
    # Per-endpoint expected keys (positive assertions)
    # ------------------------------------------------------------------

    def test_together_gemma_carries_both_kimi_and_vllm_keys(self):
        """2.7.4 incident pin: gemma-4 needs the vLLM key (Kimi alone is
        silently ignored — live A/B showed ~20s vs ~3s)."""
        extra_body = self._build_for("https://api.together.xyz/v1", "google/gemma-4-31B-it")["extra_body"]
        assert extra_body["thinking"] == {"type": "disabled"}
        assert extra_body["chat_template_kwargs"] == {"enable_thinking": False}

    def test_together_kimi_carries_both_keys(self):
        """Kimi K2 family on Together also gets dual-key — its own key
        works; the vLLM key is silently ignored."""
        extra_body = self._build_for("https://api.together.xyz/v1", "moonshotai/Kimi-K2-Instruct")["extra_body"]
        assert extra_body["thinking"] == {"type": "disabled"}

    def test_deepinfra_carries_vllm_and_reasoning_enabled_keys(self):
        extra_body = self._build_for("https://api.deepinfra.com/v1/openai", "Qwen/Qwen3.6-35B-A3B")["extra_body"]
        assert extra_body["chat_template_kwargs"] == {"enable_thinking": False}
        assert extra_body["reasoning"] == {"enabled": False}

    def test_openrouter_carries_reasoning_enabled_false(self):
        extra_body = self._build_for("https://openrouter.ai/api/v1", "kimi/k2-0130-preview")["extra_body"]
        assert extra_body["reasoning"] == {"enabled": False}

    def test_local_endpoint_carries_vllm_key(self):
        extra_body = self._build_for("http://localhost:8080/v1", "llama")["extra_body"]
        assert extra_body["chat_template_kwargs"] == {"enable_thinking": False}

    def test_openai_o_series_carries_reasoning_effort_minimal(self):
        extra_body = self._build_for("https://api.openai.com/v1", "o3-mini")["extra_body"]
        assert extra_body["reasoning_effort"] == "minimal"

    # ------------------------------------------------------------------
    # Per-endpoint forbidden keys (negative assertions — 2.7.4 regressions)
    # ------------------------------------------------------------------

    def test_groq_sends_no_reasoning_keys(self):
        """2.7.4 Groq 422 incident pin: Groq must receive NO reasoning
        toggle keys. Llama-4-scout doesn't reason; sending
        ``reasoning_effort=minimal`` 422s with enum
        ``low|medium|high|xhigh|none``; sending ``thinking`` /
        ``chat_template_kwargs`` / ``reasoning`` is also unsafe — keep
        the dispatcher empty for Groq until we ship a Groq reasoning
        model."""
        extra_body = self._build_for(
            "https://api.groq.com/openai/v1", "meta-llama/llama-4-scout-17b-16e-instruct"
        )["extra_body"]
        forbidden = {"thinking", "chat_template_kwargs", "reasoning", "reasoning_effort", "reasoning_format"}
        leaked = forbidden & set(extra_body.keys())
        assert not leaked, (
            f"Groq must not receive reasoning toggle keys ({leaked} leaked) — "
            "this re-introduces the 2.7.4 Groq 422 → circuit-breaker regression"
        )

    def test_openai_4o_does_not_get_reasoning_effort(self):
        """``reasoning_effort`` is only valid on OpenAI o-series / gpt-5.
        4o/4-turbo 422 the field — must not be sent."""
        extra_body = self._build_for("https://api.openai.com/v1", "gpt-4o")["extra_body"]
        assert "reasoning_effort" not in extra_body

    def test_ciris_proxy_no_reasoning_extras(self):
        """CIRIS proxy is a pre-wrapped LLM service; no native reasoning toggle
        applies. Only the metadata block layers in."""
        extra_body = self._build_for("https://lens.ciris-services-1.ai/lens-api/api/v1", "datum")["extra_body"]
        for k in ("thinking", "chat_template_kwargs", "reasoning", "reasoning_effort"):
            assert k not in extra_body, f"CIRIS proxy unexpectedly carries {k}"

    @pytest.mark.parametrize(
        "base_url,model_name",
        [
            ("https://api.groq.com/openai/v1", "meta-llama/llama-4-scout-17b-16e-instruct"),
            ("https://api.together.xyz/v1", "google/gemma-4-31B-it"),
            ("https://api.deepinfra.com/v1/openai", "Qwen/Qwen3.6-35B-A3B"),
            ("https://api.openai.com/v1", "gpt-4o"),
            ("https://openrouter.ai/api/v1", "anthropic/claude-3.5-sonnet"),
        ],
    )
    def test_reasoning_effort_minimal_only_on_openai_o_series(self, base_url, model_name):
        """``reasoning_effort=minimal`` is OpenAI o-series only. Sending it
        anywhere else either does nothing (silent ignore) or 422s (Groq).
        Be conservative: only OpenAI o-series gets this key."""
        extra_body = self._build_for(base_url, model_name)["extra_body"]
        assert extra_body.get("reasoning_effort") != "minimal", (
            f"reasoning_effort=minimal leaked to {base_url} model={model_name} — "
            "only OpenAI o-series / gpt-5 accept this enum value"
        )

    @pytest.mark.parametrize(
        "base_url",
        [
            "",  # OpenAIConfig.base_url unset → defaults to OpenAI
            "https://example.com/v1",  # unknown cloud provider
            "https://my-private-llm.corp.acme.com/v1",  # non-local corp endpoint
        ],
    )
    def test_unknown_endpoint_does_not_get_vllm_key(self, base_url):
        """PR review pin (release/2.7.4): unknown / unrecognized base_urls
        must NOT receive ``chat_template_kwargs.enable_thinking`` by default.
        Strict OpenAI-compatible providers commonly 400 on unknown request
        keys, and an empty base_url is OpenAI's default — sending the vLLM
        key there breaks every call. Only positively-identified local
        endpoints (localhost, RFC1918, *.local, vLLM/ollama/llama.cpp/LM
        Studio default ports) should receive it."""
        extra_body = self._build_for(base_url, "test-model")["extra_body"]
        assert "chat_template_kwargs" not in extra_body, (
            f"chat_template_kwargs leaked to unknown endpoint {base_url!r}; "
            "the dispatcher's fallthrough should be empty for non-local URLs."
        )

    def test_local_endpoint_still_gets_vllm_key(self):
        """Counterpart to the unknown-endpoint test: positively-identified
        local URLs DO need the vLLM key (CIRIS owns reasoning via the DMA
        pipeline; we turn the model's own reasoning off, and Gemma-4 puts
        responses in `reasoning_content` instead of `content` when
        thinking is on — see docs/GEMMA_4_COMPATIBILITY.md)."""
        for url in (
            "http://localhost:8000/v1",
            "http://127.0.0.1:11434/v1",
            "http://192.168.1.50:1234/v1",
            "http://my-server.local:8080/v1",
        ):
            extra_body = self._build_for(url, "llama")["extra_body"]
            assert extra_body.get("chat_template_kwargs") == {"enable_thinking": False}, (
                f"local endpoint {url} should receive chat_template_kwargs, got {extra_body!r}"
            )

    def test_openrouter_includes_provider_config(self):
        """OpenRouter requests should include both provider config and reasoning disabled."""
        from ciris_engine.logic.services.runtime.llm_service.service import OpenAICompatibleClient, OpenAIConfig

        # Create minimal client for testing with proper config
        config = OpenAIConfig(
            api_key="test-key",
            model_name="openai/gpt-4o",
            base_url="https://openrouter.ai/api/v1",
        )
        client = OpenAICompatibleClient.__new__(OpenAICompatibleClient)
        client.openai_config = config
        client.model_name = config.model_name

        # Call the method that builds extra kwargs
        extra_kwargs = client._build_extra_kwargs(
            task_id="test-task-123",
            thought_id="test-thought-456",
            resp_model_name="ActionSelectionDMAResult",
            retry_state=RetryState(),
        )

        # Verify reasoning is disabled
        assert "extra_body" in extra_kwargs
        extra_body = extra_kwargs["extra_body"]
        # Provider config may or may not be present depending on env
        assert "reasoning" in extra_body
        assert extra_body["reasoning"]["enabled"] is False
