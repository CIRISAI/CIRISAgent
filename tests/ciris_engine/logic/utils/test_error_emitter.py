"""Tests for error_emitter module."""

import asyncio
import time
from unittest.mock import AsyncMock, patch

import pytest

from ciris_engine.logic.utils.error_emitter import (
    clear_error_callback,
    emit_circuit_breaker_open,
    emit_dma_failure,
    emit_error,
    emit_llm_failure,
    emit_rate_limit_error,
    set_error_callback,
    _last_emit_times,
    _MIN_EMIT_INTERVAL,
)


class TestErrorEmitter:
    """Tests for error emitter functions."""

    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """Clear callback before and after each test."""
        clear_error_callback()
        _last_emit_times.clear()
        yield
        clear_error_callback()
        _last_emit_times.clear()

    @pytest.mark.asyncio
    async def test_set_error_callback(self):
        """Test setting the error callback."""
        mock_callback = AsyncMock()
        set_error_callback(mock_callback)

        result = await emit_error("Test error", "test_channel")

        assert result is True
        mock_callback.assert_called_once_with("test_channel", "Test error", "error")

    @pytest.mark.asyncio
    async def test_emit_error_no_callback(self):
        """Test emit_error returns False when no callback is set."""
        result = await emit_error("Test error")
        assert result is False

    @pytest.mark.asyncio
    async def test_emit_error_with_callback(self):
        """Test emit_error with a registered callback."""
        mock_callback = AsyncMock()
        set_error_callback(mock_callback)

        result = await emit_error(
            content="Test message",
            channel_id="my_channel",
            category="test_cat",
            message_type="system"
        )

        assert result is True
        mock_callback.assert_called_once_with("my_channel", "Test message", "system")

    @pytest.mark.asyncio
    async def test_emit_error_rate_limiting(self):
        """Test rate limiting of same-category messages."""
        mock_callback = AsyncMock()
        set_error_callback(mock_callback)

        # First emit should succeed
        result1 = await emit_error("Error 1", category="test_category")
        assert result1 is True

        # Immediate second emit should be rate-limited
        result2 = await emit_error("Error 2", category="test_category")
        assert result2 is False

        # Callback should only be called once
        assert mock_callback.call_count == 1

    @pytest.mark.asyncio
    async def test_emit_error_different_categories_not_rate_limited(self):
        """Test different categories are not rate-limited together."""
        mock_callback = AsyncMock()
        set_error_callback(mock_callback)

        result1 = await emit_error("Error 1", category="category_a")
        result2 = await emit_error("Error 2", category="category_b")

        assert result1 is True
        assert result2 is True
        assert mock_callback.call_count == 2

    @pytest.mark.asyncio
    async def test_emit_error_callback_exception(self):
        """Test emit_error handles callback exceptions gracefully."""
        mock_callback = AsyncMock(side_effect=Exception("Callback failed"))
        set_error_callback(mock_callback)

        result = await emit_error("Test error")

        assert result is False

    @pytest.mark.asyncio
    async def test_emit_rate_limit_error(self):
        """Test emit_rate_limit_error helper."""
        mock_callback = AsyncMock()
        set_error_callback(mock_callback)

        result = await emit_rate_limit_error("OpenRouter", 5.0, "test_channel")

        assert result is True
        mock_callback.assert_called_once()
        call_args = mock_callback.call_args[0]
        assert call_args[0] == "test_channel"
        assert "OpenRouter" in call_args[1]
        assert "5.0s" in call_args[1]
        assert call_args[2] == "error"

    @pytest.mark.asyncio
    async def test_emit_llm_failure(self):
        """Test emit_llm_failure helper."""
        mock_callback = AsyncMock()
        set_error_callback(mock_callback)

        result = await emit_llm_failure(
            error_summary="Connection timeout",
            retry_count=2,
            max_retries=3,
            channel_id="my_channel"
        )

        assert result is True
        mock_callback.assert_called_once()
        call_args = mock_callback.call_args[0]
        assert call_args[0] == "my_channel"
        assert "2/3" in call_args[1]
        assert "Connection timeout" in call_args[1]

    @pytest.mark.asyncio
    async def test_emit_circuit_breaker_open(self):
        """Test emit_circuit_breaker_open helper."""
        mock_callback = AsyncMock()
        set_error_callback(mock_callback)

        result = await emit_circuit_breaker_open("openai_service", "test_channel")

        assert result is True
        mock_callback.assert_called_once()
        call_args = mock_callback.call_args[0]
        assert "openai_service" in call_args[1]
        assert "temporarily unavailable" in call_args[1]

    @pytest.mark.asyncio
    async def test_emit_dma_failure(self):
        """Test emit_dma_failure helper."""
        mock_callback = AsyncMock()
        set_error_callback(mock_callback)

        result = await emit_dma_failure(
            dma_name="ActionSelection",
            error_summary="Model returned invalid JSON",
            channel_id="system"
        )

        assert result is True
        mock_callback.assert_called_once()
        call_args = mock_callback.call_args[0]
        assert "ActionSelection" in call_args[1]
        assert "invalid JSON" in call_args[1]

    @pytest.mark.asyncio
    async def test_emit_error_truncates_long_summary(self):
        """Test that long error summaries are truncated."""
        mock_callback = AsyncMock()
        set_error_callback(mock_callback)

        long_summary = "A" * 200
        result = await emit_llm_failure(
            error_summary=long_summary,
            retry_count=1,
            max_retries=3
        )

        assert result is True
        call_args = mock_callback.call_args[0]
        # Should be truncated to 100 chars in error_summary
        assert len(call_args[1]) < 200

    @pytest.mark.asyncio
    async def test_clear_error_callback(self):
        """Test clear_error_callback removes the callback."""
        mock_callback = AsyncMock()
        set_error_callback(mock_callback)

        # Emit should work
        result1 = await emit_error("Test", category="cat1")
        assert result1 is True

        # Clear callback
        clear_error_callback()

        # Now emit should fail
        result2 = await emit_error("Test", category="cat2")
        assert result2 is False

    @pytest.mark.asyncio
    async def test_default_channel_is_system(self):
        """Test that default channel is 'system'."""
        mock_callback = AsyncMock()
        set_error_callback(mock_callback)

        await emit_error("Test message")

        call_args = mock_callback.call_args[0]
        assert call_args[0] == "system"

    @pytest.mark.asyncio
    async def test_default_message_type_is_error(self):
        """Test that default message type is 'error'."""
        mock_callback = AsyncMock()
        set_error_callback(mock_callback)

        await emit_error("Test message")

        call_args = mock_callback.call_args[0]
        assert call_args[2] == "error"
