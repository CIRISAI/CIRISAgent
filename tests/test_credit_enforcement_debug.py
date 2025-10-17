"""
Debug test for credit enforcement in API observer.

This test helps diagnose why credits aren't being deducted.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from ciris_engine.logic.adapters.api.api_observer import APIObserver
from ciris_engine.schemas.runtime.messages import IncomingMessage
from ciris_engine.schemas.services.credit_gate import (
    CreditAccount,
    CreditCheckResult,
    CreditContext,
    CreditSpendRequest,
    CreditSpendResult,
)

logger = logging.getLogger(__name__)


@pytest.fixture
def mock_resource_monitor():
    """Create a mock resource monitor with credit provider."""
    monitor = Mock()

    # Create mock credit provider
    credit_provider = Mock()
    credit_provider.check_credit = AsyncMock(
        return_value=CreditCheckResult(
            has_credit=True,
            credits_remaining=3,
            reason=None,
        )
    )
    credit_provider.spend_credit = AsyncMock(
        return_value=CreditSpendResult(
            succeeded=True,
            credits_remaining=2,
            reason=None,
        )
    )

    monitor.credit_provider = credit_provider
    monitor.check_credit = credit_provider.check_credit
    monitor.spend_credit = credit_provider.spend_credit

    return monitor


@pytest.fixture
def incoming_message_with_credit():
    """Create an incoming message WITH credit metadata attached."""
    msg = IncomingMessage(
        message_id="test-msg-123",
        author_id="test-user",
        author_name="Test User",
        content="Test message",
        channel_id="api_test-user",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    # Attach credit metadata
    account = CreditAccount(
        provider="oauth:google",
        account_id="12345",
        authority_id="wa-test-user",
        tenant_id=None,
    )

    context = CreditContext(
        agent_id="test-agent",
        channel_id="api_test-user",
        request_id="test-msg-123",
    )

    # Attach as model_dump (like agent.py does)
    msg = msg.model_copy(
        update={
            "credit_account": account.model_dump(),
            "credit_context": context.model_dump(),
        }
    )

    return msg


@pytest.fixture
def incoming_message_without_credit():
    """Create an incoming message WITHOUT credit metadata."""
    return IncomingMessage(
        message_id="test-msg-456",
        author_id="test-user",
        author_name="Test User",
        content="Test message without credit",
        channel_id="api_test-user",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )


@pytest.mark.asyncio
async def test_observer_has_resource_monitor(mock_resource_monitor):
    """Test that observer receives resource_monitor during initialization."""
    on_observe = AsyncMock()

    observer = APIObserver(
        on_observe=on_observe,
        resource_monitor=mock_resource_monitor,
    )

    # Verify observer has resource monitor
    assert observer.resource_monitor is not None
    assert observer.resource_monitor == mock_resource_monitor
    assert hasattr(observer.resource_monitor, "credit_provider")
    assert observer.resource_monitor.credit_provider is not None

    logger.info("✅ Observer has resource_monitor and credit_provider")


@pytest.mark.asyncio
async def test_credit_enforcement_with_metadata(mock_resource_monitor, incoming_message_with_credit):
    """Test that credit enforcement works when metadata IS attached."""
    on_observe = AsyncMock()

    observer = APIObserver(
        on_observe=on_observe,
        resource_monitor=mock_resource_monitor,
    )

    # Call _enforce_credit_policy directly
    await observer._enforce_credit_policy(incoming_message_with_credit)

    # Verify credit check was called
    assert mock_resource_monitor.check_credit.called
    assert mock_resource_monitor.spend_credit.called

    # Verify it was called with correct account
    check_call = mock_resource_monitor.check_credit.call_args
    account_arg = check_call[0][0]
    assert isinstance(account_arg, CreditAccount)
    assert account_arg.provider == "oauth:google"
    assert account_arg.account_id == "12345"

    logger.info("✅ Credit enforcement works with metadata attached")


@pytest.mark.asyncio
async def test_credit_enforcement_without_metadata(mock_resource_monitor, incoming_message_without_credit):
    """Test that credit enforcement is SKIPPED when metadata NOT attached."""
    on_observe = AsyncMock()

    observer = APIObserver(
        on_observe=on_observe,
        resource_monitor=mock_resource_monitor,
    )

    # Call _enforce_credit_policy directly
    await observer._enforce_credit_policy(incoming_message_without_credit)

    # Verify credit check was NOT called (no metadata)
    assert not mock_resource_monitor.check_credit.called
    assert not mock_resource_monitor.spend_credit.called

    logger.info("⚠️  Credit enforcement SKIPPED when no metadata attached")


@pytest.mark.asyncio
async def test_full_message_handling_with_credits(mock_resource_monitor, incoming_message_with_credit):
    """Test full message handling flow with credit enforcement."""
    on_observe = AsyncMock()

    # Create mock services
    mock_secrets_service = Mock()
    mock_secrets_service.process_incoming_text = AsyncMock(return_value=("Test message", []))

    observer = APIObserver(
        on_observe=on_observe,
        resource_monitor=mock_resource_monitor,
        secrets_service=mock_secrets_service,
    )

    # Handle full message
    result = await observer.handle_incoming_message(incoming_message_with_credit)

    # Verify credit enforcement happened
    assert mock_resource_monitor.check_credit.called
    assert mock_resource_monitor.spend_credit.called

    logger.info("✅ Full message handling enforces credits")


@pytest.mark.asyncio
async def test_observer_without_resource_monitor():
    """Test that observer works when NO resource_monitor provided."""
    from unittest.mock import patch

    on_observe = AsyncMock()
    mock_secrets_service = Mock()
    mock_secrets_service.process_incoming_text = AsyncMock(return_value=("Test message", []))

    observer = APIObserver(
        on_observe=on_observe,
        resource_monitor=None,  # NO resource monitor
        secrets_service=mock_secrets_service,
    )

    msg = IncomingMessage(
        message_id="test-msg-789",
        author_id="test-user",
        author_name="Test User",
        content="Test message",
        channel_id="api_test-user",
        timestamp=datetime.now(timezone.utc).isoformat(),
    )

    # Mock persistence layer to avoid database errors
    with patch("ciris_engine.logic.persistence.add_task"), patch("ciris_engine.logic.persistence.add_thought"), patch(
        "ciris_engine.logic.persistence.models.tasks.get_active_task_for_channel", return_value=None
    ):
        # Should work without errors
        result = await observer.handle_incoming_message(msg)

    # Verify task was still created (no credit gating when no monitor)
    assert result.task_id is not None

    logger.info("✅ Observer works without resource_monitor (no credit gating)")


if __name__ == "__main__":
    # Run tests with verbose output
    pytest.main([__file__, "-v", "-s", "--log-cli-level=INFO"])
