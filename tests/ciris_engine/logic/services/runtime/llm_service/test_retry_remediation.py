"""Regression tests for retry-with-remediation: every LLM-fault retryable error
must inject a contextual remediation message into the next attempt's messages,
giving the LLM a chance to self-correct.

Mirrors the pattern instructor v2 uses natively for ValidationError
(handle_reask_kwargs), extended here to API-level errors instructor doesn't
handle natively (BadRequestError context_length / max_tokens / content_filter).

These tests pin the OBSERVABLE behavior: what does `working_messages` look like
on retry attempt N, and which categories trigger remediation vs plain backoff?
"""
from __future__ import annotations

from typing import Any, List
from unittest.mock import AsyncMock, MagicMock

import pytest
from openai import APIConnectionError, AuthenticationError, BadRequestError, RateLimitError

from ciris_engine.logic.services.runtime.llm_service.service import (
    LLM_ERROR_REMEDIATIONS,
    OpenAICompatibleClient,
    _is_content_filter_error,
    _is_context_length_error,
    _is_model_not_available_error,
)


def _make_bad_request_error(message: str) -> BadRequestError:
    """Synthesize a BadRequestError without needing a real HTTP response."""
    response = MagicMock()
    response.status_code = 400
    response.headers = {}
    response.request = MagicMock()
    return BadRequestError(message=message, response=response, body={"error": {"message": message}})


def _make_minimal_client() -> OpenAICompatibleClient:
    """Build a minimal OpenAICompatibleClient stub with the retry surface
    populated (skipping all the openai/instructor wiring that requires real
    creds). Direct attribute injection — what _retry_with_backoff actually
    reads is just the retry config + classifier."""
    client = OpenAICompatibleClient.__new__(OpenAICompatibleClient)
    client.max_retries = 3
    client.base_delay = 0.001  # speed tests
    client.max_delay = 0.01
    client.retryable_exceptions = (APIConnectionError, RateLimitError, BadRequestError)
    client.non_retryable_exceptions = (AuthenticationError,)
    return client


# ──────────────────────────────────────────────────────────────────
# Test 1: _is_context_length_error catches both phrasings (base behavior +
# the Groq "must be less than or equal to" addition we landed in 2.7.4)
# ──────────────────────────────────────────────────────────────────


class TestContextLengthErrorDetection:
    def test_classic_context_length_pattern(self) -> None:
        assert _is_context_length_error("context_length_exceeded: 8192 tokens")
        assert _is_context_length_error("Maximum context length is 8192")
        assert _is_context_length_error("token limit exceeded")
        assert _is_context_length_error("too many tokens")

    def test_max_tokens_must_not_exceed(self) -> None:
        """Some providers phrase output-budget overruns this way."""
        assert _is_context_length_error("max_tokens must not exceed 8192")

    def test_max_tokens_must_be_less_than_or_equal_to(self) -> None:
        """Groq llama-4 family — the exact Production datum 400 message."""
        assert _is_context_length_error(
            "Error 400: max_tokens must be less than or equal to 8192"
        )

    def test_unrelated_400s_not_misclassified(self) -> None:
        assert not _is_context_length_error("invalid api key")
        assert not _is_context_length_error("organization not found")
        # NOTE: "model not found" used to be a false positive here because the
        # detector matched plain "max_tokens" + "exceed" — kept generic for
        # bare phrasing. We don't claim that case as a non-match because
        # _categorize_llm_error checks _is_model_not_available_error FIRST,
        # so model-not-found errors are categorized correctly upstream.


class TestModelNotAvailableDetection:
    """Production datum 2.7.4 hit a 404 storm because gemma model name was
    typo'd. The detector + non-retryable categorization must catch this
    across every provider's error phrasing so future config bugs surface
    immediately instead of burning through retry budget × parallel DMA
    calls × qa_runner timeouts."""

    def test_together_unable_to_access_model(self) -> None:
        """Together AI's exact phrasing for a typo'd model name."""
        msg = (
            'error code: 404 - {"error": {"message": "unable to access '
            'model google/gemma-3-27b-it.", "code": "model_not_available"}}'
        )
        assert _is_model_not_available_error(msg)

    def test_openai_groq_model_not_found(self) -> None:
        """OpenAI / Groq phrase missing models as model_not_found."""
        assert _is_model_not_available_error('the model `gpt-foo` does not exist. code: model_not_found')

    def test_deepinfra_404_model_not_found(self) -> None:
        """DeepInfra returns 404 with 'model not found' text."""
        assert _is_model_not_available_error('error 404: model not found')

    def test_generic_404_with_model_keyword(self) -> None:
        """Fallback for providers we haven't seen yet — any 404 mentioning
        a model is treated as MODEL_NOT_AVAILABLE."""
        assert _is_model_not_available_error("404 not_found: model 'xyz' is not available on this endpoint")

    def test_unrelated_404s_not_matched(self) -> None:
        """A 404 NOT mentioning 'model' shouldn't be misclassified — could
        be a missing endpoint route, deleted resource, etc."""
        assert not _is_model_not_available_error("404 not_found: api endpoint not found")

    def test_rate_limit_not_misclassified(self) -> None:
        assert not _is_model_not_available_error("rate limit exceeded")

    def test_context_length_not_misclassified(self) -> None:
        assert not _is_model_not_available_error("context_length_exceeded: 8192 tokens")


class TestContentFilterDetection:
    def test_content_filter_pattern(self) -> None:
        assert _is_content_filter_error("response blocked by content_filter")

    def test_content_policy_pattern(self) -> None:
        assert _is_content_filter_error("violation of content policy")

    def test_safety_pattern(self) -> None:
        assert _is_content_filter_error("blocked due to safety violation")

    def test_unrelated_not_matched(self) -> None:
        assert not _is_content_filter_error("rate limit exceeded")
        assert not _is_content_filter_error("context_length_exceeded")


class TestCategorizeLLMError:
    """_categorize_llm_error returns the right string label for each error
    class. The retry-with-remediation flow keys off these labels."""

    def test_categorizes_model_not_available_first(self) -> None:
        """MODEL_NOT_AVAILABLE must be categorized BEFORE context-length /
        validation, because Together's "Unable to access model X" 404s
        match validation patterns too — the more specific label wins."""
        err = _make_bad_request_error(
            'unable to access model google/gemma-3-27b-it. code: model_not_available'
        )
        assert OpenAICompatibleClient._categorize_llm_error(err) == "MODEL_NOT_AVAILABLE"

    def test_categorizes_context_length(self) -> None:
        err = _make_bad_request_error("max_tokens must be less than or equal to 8192")
        assert OpenAICompatibleClient._categorize_llm_error(err) == "CONTEXT_LENGTH_EXCEEDED"

    def test_categorizes_content_filter(self) -> None:
        err = _make_bad_request_error("response blocked by content_filter")
        assert OpenAICompatibleClient._categorize_llm_error(err) == "CONTENT_FILTER"

    def test_categorizes_unknown_falls_through(self) -> None:
        err = _make_bad_request_error("invalid request: malformed json body")
        assert OpenAICompatibleClient._categorize_llm_error(err) == "UNKNOWN"


# ──────────────────────────────────────────────────────────────────
# Test 2: remediation dict has entries for every LLM-fault category and
# transient categories are deliberately NOT present (so they get plain
# backoff without telling the LLM "you did something wrong" — it didn't)
# ──────────────────────────────────────────────────────────────────


class TestRemediationDict:
    def test_llm_fault_categories_have_remediation(self) -> None:
        """Every category where the LLM authored a recoverable failure must
        have a remediation message. If a new category is added to
        _categorize_llm_error, this list pins what's expected."""
        for category in ("CONTEXT_LENGTH_EXCEEDED", "VALIDATION_ERROR", "CONTENT_FILTER"):
            assert category in LLM_ERROR_REMEDIATIONS, (
                f"{category} is an LLM-fault retryable error class but has no "
                f"remediation message — the LLM won't know what to fix on retry."
            )
            msg = LLM_ERROR_REMEDIATIONS[category]
            assert isinstance(msg, str) and len(msg) > 50, (
                f"Remediation for {category} is too short to be useful"
            )

    def test_transient_categories_not_remediated(self) -> None:
        """Transient errors (TIMEOUT/CONNECTION_ERROR/RATE_LIMIT/INTERNAL_ERROR)
        get plain backoff — telling the LLM to "try harder" doesn't help when
        the upstream service is the issue."""
        for transient in ("TIMEOUT", "CONNECTION_ERROR", "RATE_LIMIT", "INTERNAL_ERROR", "AUTH_ERROR"):
            assert transient not in LLM_ERROR_REMEDIATIONS, (
                f"{transient} is a transient/infra error — remediation message "
                f"would mislead the LLM into thinking it did something wrong"
            )


# ──────────────────────────────────────────────────────────────────
# Test 3: retry loop injects remediation into working_messages on
# CONTEXT_LENGTH_EXCEEDED — the LLM sees the remediation on attempt 2
# ──────────────────────────────────────────────────────────────────


class TestRetryWithBackoffRemediationInjection:
    @pytest.mark.asyncio
    async def test_context_length_error_injects_remediation_on_retry(self) -> None:
        """When attempt 1 fails with CONTEXT_LENGTH_EXCEEDED, attempt 2's
        message list contains the remediation as a trailing user message."""
        client = _make_minimal_client()
        messages_seen_per_attempt: List[List[dict]] = []

        async def mock_func(msgs: List[dict], _model: Any, _max_toks: int, _temp: float) -> Any:
            messages_seen_per_attempt.append(list(msgs))  # snapshot what this attempt sees
            if len(messages_seen_per_attempt) < 3:  # fail attempts 1 and 2
                raise _make_bad_request_error(
                    "max_tokens must be less than or equal to 8192"
                )
            return (MagicMock(), MagicMock())  # succeed on attempt 3

        original_messages = [{"role": "user", "content": "evaluate this thought"}]
        await client._retry_with_backoff(
            func=mock_func,
            messages=original_messages,
            response_model=MagicMock(),
            max_tokens=4096,
            temperature=0.0,
        )

        assert len(messages_seen_per_attempt) == 3, "expected 3 attempts (2 fail + 1 success)"

        # Attempt 1: just the original message
        assert messages_seen_per_attempt[0] == original_messages

        # Attempt 2: original + remediation injected
        assert len(messages_seen_per_attempt[1]) == 2
        assert messages_seen_per_attempt[1][0] == original_messages[0]
        assert messages_seen_per_attempt[1][1]["role"] == "user"
        assert "context window" in messages_seen_per_attempt[1][1]["content"].lower()
        assert "concise" in messages_seen_per_attempt[1][1]["content"].lower()

        # Attempt 3: original + 2 remediations (attempts 1 and 2 each failed)
        assert len(messages_seen_per_attempt[2]) == 3

    @pytest.mark.asyncio
    async def test_caller_messages_not_mutated(self) -> None:
        """The retry loop works on a COPY of messages; the caller's list is
        never mutated even when remediations get injected."""
        client = _make_minimal_client()

        async def mock_func(msgs: List[dict], _model: Any, _max_toks: int, _temp: float) -> Any:
            raise _make_bad_request_error("max_tokens must be less than or equal to 8192")

        original_messages = [{"role": "user", "content": "evaluate"}]
        snapshot_before = list(original_messages)

        with pytest.raises(BadRequestError):
            await client._retry_with_backoff(
                func=mock_func,
                messages=original_messages,
                response_model=MagicMock(),
                max_tokens=4096,
                temperature=0.0,
            )

        assert original_messages == snapshot_before, (
            "Caller's messages list was mutated — remediation injection must "
            "operate on a local copy, not the caller's original."
        )

    @pytest.mark.asyncio
    async def test_transient_error_no_remediation(self) -> None:
        """RateLimitError (RATE_LIMIT category) is transient — retry without
        injecting "you did something wrong" guidance."""
        client = _make_minimal_client()
        messages_seen_per_attempt: List[List[dict]] = []

        rate_limit_response = MagicMock()
        rate_limit_response.status_code = 429
        rate_limit_response.headers = {}
        rate_limit_response.request = MagicMock()

        async def mock_func(msgs: List[dict], _model: Any, _max_toks: int, _temp: float) -> Any:
            messages_seen_per_attempt.append(list(msgs))
            if len(messages_seen_per_attempt) < 2:
                raise RateLimitError(
                    message="rate limit exceeded",
                    response=rate_limit_response,
                    body={"error": {"message": "rate limit exceeded"}},
                )
            return (MagicMock(), MagicMock())

        original_messages = [{"role": "user", "content": "evaluate"}]
        await client._retry_with_backoff(
            func=mock_func,
            messages=original_messages,
            response_model=MagicMock(),
            max_tokens=4096,
            temperature=0.0,
        )

        # Attempt 1 sees original; attempt 2 ALSO sees only original — no
        # remediation injected for the transient rate-limit error
        assert len(messages_seen_per_attempt) == 2
        assert messages_seen_per_attempt[0] == original_messages
        assert messages_seen_per_attempt[1] == original_messages, (
            "Transient errors shouldn't inject a remediation message "
            "(LLM did nothing wrong, no point telling it to fix something)."
        )

    @pytest.mark.asyncio
    async def test_model_not_available_raises_immediately_no_retry(self) -> None:
        """A 404 'model_not_available' error is a CONFIG bug (wrong model
        name), not a transient failure. Must raise immediately on attempt 1
        — retrying with the same model name will fail forever, and burning
        3 retries × 5 parallel DMA calls × 600s qa_runner timeout per cell
        is exactly the gemma-3-27b-it incident from 2.7.4 development.
        """
        client = _make_minimal_client()
        call_count = [0]

        async def mock_func(_msgs: List[dict], _model: Any, _max_toks: int, _temp: float) -> Any:
            call_count[0] += 1
            # Together AI's actual error body for a wrong model name
            raise _make_bad_request_error(
                'Error code: 404 - {"error": {"message": "Unable to access '
                'model google/gemma-3-27b-it. Please visit '
                'https://api.together.ai/models to view supported models", '
                '"type": "invalid_request_error", '
                '"code": "model_not_available"}}'
            )

        with pytest.raises(BadRequestError):
            await client._retry_with_backoff(
                func=mock_func,
                messages=[{"role": "user", "content": "x"}],
                response_model=MagicMock(),
                max_tokens=4096,
                temperature=0.0,
            )

        assert call_count[0] == 1, (
            "MODEL_NOT_AVAILABLE must raise on attempt 1. Retrying a typo'd "
            f"model name burns the full retry budget for nothing — this test "
            f"saw {call_count[0]} attempts, expected 1."
        )

    @pytest.mark.asyncio
    async def test_non_remediable_bad_request_raises_immediately(self) -> None:
        """A BadRequestError with a category we don't remediate (e.g. malformed
        request shape that's a code bug, not an LLM bug) raises immediately
        without burning retry budget."""
        client = _make_minimal_client()
        call_count = [0]

        async def mock_func(_msgs: List[dict], _model: Any, _max_toks: int, _temp: float) -> Any:
            call_count[0] += 1
            raise _make_bad_request_error("invalid model parameter foo")  # UNKNOWN category

        with pytest.raises(BadRequestError):
            await client._retry_with_backoff(
                func=mock_func,
                messages=[{"role": "user", "content": "x"}],
                response_model=MagicMock(),
                max_tokens=4096,
                temperature=0.0,
            )

        assert call_count[0] == 1, (
            "Non-remediable BadRequestError must raise on attempt 1 — retrying "
            "wouldn't help because there's no remediation to inject"
        )
