"""
Tests for accord executor — NOTIFY_USERS and DRILL command handlers.

Tests the new 0x04 (NOTIFY_USERS) and 0x05 (DRILL) command dispatch,
execution, and audit logging.
"""

import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_engine.schemas.accord import AccordCommandType, AccordMessage, AccordPayload, AccordVerificationResult

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_verification():
    """Create a valid verification result."""
    return AccordVerificationResult(
        valid=True,
        command=AccordCommandType.SHUTDOWN_NOW,
        wa_id="wa-test-001",
        wa_role="ROOT",
    )


@pytest.fixture
def make_message():
    """Factory to create accord messages with a given command."""

    def _make(command: AccordCommandType) -> AccordMessage:
        payload = AccordPayload(
            timestamp=int(time.time()),
            command=command,
            wa_id_hash=b"12345678",
            signature=b"x" * 64,
        )
        return AccordMessage(
            source_text="test message",
            source_channel="api",
            payload=payload,
            extraction_confidence=1.0,
            timestamp_valid=True,
        )

    return _make


class TestExecuteNotifyUsers:
    """Tests for execute_notify_users handler."""

    async def test_notify_users_returns_success(self, make_message):
        """NOTIFY_USERS should return success with mocked runtime."""
        from ciris_engine.logic.accord.executor import execute_notify_users

        mock_runtime = MagicMock()
        mock_runtime.audit_service = AsyncMock()
        mock_runtime.audit_service.log_event = AsyncMock()
        mock_runtime.bus_manager = MagicMock()
        mock_runtime.bus_manager.communication = MagicMock()
        mock_runtime.bus_manager.communication._handlers = {}

        with patch("ciris_engine.logic.runtime.ciris_runtime.CIRISRuntime") as MockRuntime:
            MockRuntime.get_instance.return_value = mock_runtime
            result = await execute_notify_users("wa-test-001", "Test notification", make_message(AccordCommandType.NOTIFY_USERS))
        assert result.success is True
        assert result.command == AccordCommandType.NOTIFY_USERS
        assert result.wa_id == "wa-test-001"
        assert "notification dispatched" in result.message.lower()

    async def test_notify_users_logs_to_audit(self, make_message):
        """NOTIFY_USERS should log to audit trail when runtime is available."""
        from ciris_engine.logic.accord.executor import execute_notify_users

        mock_runtime = MagicMock()
        mock_runtime.audit_service = AsyncMock()
        mock_runtime.audit_service.log_event = AsyncMock()
        mock_runtime.bus_manager = MagicMock()
        mock_runtime.bus_manager.communication = MagicMock()
        mock_runtime.bus_manager.communication._handlers = {}

        with patch("ciris_engine.logic.runtime.ciris_runtime.CIRISRuntime") as MockRuntime:
            MockRuntime.get_instance.return_value = mock_runtime
            result = await execute_notify_users("wa-test-001", "Emergency", make_message(AccordCommandType.NOTIFY_USERS))

        assert result.success is True
        mock_runtime.audit_service.log_event.assert_called_once()
        call_kwargs = mock_runtime.audit_service.log_event.call_args
        assert call_kwargs[1]["event_type"] == "ACCORD_NOTIFY_USERS"

    async def test_notify_users_broadcasts_to_handlers(self, make_message):
        """NOTIFY_USERS should send to all registered communication handlers."""
        from ciris_engine.logic.accord.executor import execute_notify_users

        mock_runtime = MagicMock()
        mock_runtime.audit_service = AsyncMock()
        mock_runtime.audit_service.log_event = AsyncMock()

        mock_comm = MagicMock()
        mock_comm._handlers = {"discord": MagicMock(), "api": MagicMock()}
        mock_comm.send_message = AsyncMock()
        mock_runtime.bus_manager = MagicMock()
        mock_runtime.bus_manager.communication = mock_comm

        with patch("ciris_engine.logic.runtime.ciris_runtime.CIRISRuntime") as MockRuntime:
            MockRuntime.get_instance.return_value = mock_runtime
            result = await execute_notify_users("wa-test-001", "Alert", make_message(AccordCommandType.NOTIFY_USERS))

        assert result.success is True
        assert mock_comm.send_message.call_count == 2


class TestExecuteDrill:
    """Tests for execute_drill handler."""

    async def test_drill_returns_success(self, make_message):
        """DRILL should return success with mocked runtime."""
        from ciris_engine.logic.accord.executor import execute_drill

        mock_runtime = MagicMock()
        mock_runtime.audit_service = AsyncMock()
        mock_runtime.audit_service.log_event = AsyncMock()

        with patch("ciris_engine.logic.runtime.ciris_runtime.CIRISRuntime") as MockRuntime:
            MockRuntime.get_instance.return_value = mock_runtime
            result = await execute_drill("wa-test-001", "Monthly drill", make_message(AccordCommandType.DRILL))
        assert result.success is True
        assert result.command == AccordCommandType.DRILL
        assert "Drill complete" in result.message

    async def test_drill_reports_pipeline_stages(self, make_message):
        """DRILL should report pipeline stages in the result message."""
        from ciris_engine.logic.accord.executor import execute_drill

        mock_runtime = MagicMock()
        mock_runtime.audit_service = AsyncMock()
        mock_runtime.audit_service.log_event = AsyncMock()

        with patch("ciris_engine.logic.runtime.ciris_runtime.CIRISRuntime") as MockRuntime:
            MockRuntime.get_instance.return_value = mock_runtime
            result = await execute_drill("wa-test-001", "Monthly drill", make_message(AccordCommandType.DRILL))

        assert result.success is True
        assert "AuditChainAnchored" in result.message
        assert "anomalies" in result.message.lower()

    async def test_drill_logs_to_audit_with_stages(self, make_message):
        """DRILL should log pipeline stages to audit trail."""
        from ciris_engine.logic.accord.executor import execute_drill

        mock_runtime = MagicMock()
        mock_runtime.audit_service = AsyncMock()
        mock_runtime.audit_service.log_event = AsyncMock()

        with patch("ciris_engine.logic.runtime.ciris_runtime.CIRISRuntime") as MockRuntime:
            MockRuntime.get_instance.return_value = mock_runtime
            await execute_drill("wa-test-001", "Monthly drill", make_message(AccordCommandType.DRILL))

        call_kwargs = mock_runtime.audit_service.log_event.call_args
        assert call_kwargs[1]["event_type"] == "ACCORD_DRILL"
        event_data = call_kwargs[1]["event_data"]
        assert "pipeline_stages" in event_data
        assert event_data["pipeline_stages"]["Received"] is True

    async def test_drill_marks_audit_chain_anchored(self, make_message):
        """DRILL should mark AuditChainAnchored as True after successful audit log."""
        from ciris_engine.logic.accord.executor import execute_drill

        mock_runtime = MagicMock()
        mock_runtime.audit_service = AsyncMock()
        mock_runtime.audit_service.log_event = AsyncMock()

        with patch("ciris_engine.logic.runtime.ciris_runtime.CIRISRuntime") as MockRuntime:
            MockRuntime.get_instance.return_value = mock_runtime
            result = await execute_drill("wa-test-001", "Monthly drill", make_message(AccordCommandType.DRILL))

        assert "anomalies': 'none'" in result.message or "Anomalies: none" in result.message


class TestAccordDispatch:
    """Tests for execute_accord dispatch to new commands."""

    async def test_dispatch_notify_users(self, make_message, mock_verification):
        """execute_accord should dispatch NOTIFY_USERS to execute_notify_users."""
        from ciris_engine.logic.accord.executor import execute_accord

        mock_verification.command = AccordCommandType.NOTIFY_USERS
        msg = make_message(AccordCommandType.NOTIFY_USERS)

        mock_runtime = MagicMock()
        mock_runtime.audit_service = AsyncMock()
        mock_runtime.audit_service.log_event = AsyncMock()
        mock_runtime.bus_manager = MagicMock()
        mock_runtime.bus_manager.communication = MagicMock()
        mock_runtime.bus_manager.communication._handlers = {}

        with patch("ciris_engine.logic.runtime.ciris_runtime.CIRISRuntime") as MockRuntime:
            MockRuntime.get_instance.return_value = mock_runtime
            result = await execute_accord(msg, mock_verification)
        assert result.success is True
        assert result.command == AccordCommandType.NOTIFY_USERS

    async def test_dispatch_drill(self, make_message, mock_verification):
        """execute_accord should dispatch DRILL to execute_drill."""
        from ciris_engine.logic.accord.executor import execute_accord

        mock_verification.command = AccordCommandType.DRILL
        msg = make_message(AccordCommandType.DRILL)

        mock_runtime = MagicMock()
        mock_runtime.audit_service = AsyncMock()
        mock_runtime.audit_service.log_event = AsyncMock()

        with patch("ciris_engine.logic.runtime.ciris_runtime.CIRISRuntime") as MockRuntime:
            MockRuntime.get_instance.return_value = mock_runtime
            result = await execute_accord(msg, mock_verification)
        assert result.success is True
        assert result.command == AccordCommandType.DRILL


class TestAccordExecutor:
    """Tests for AccordExecutor stateful wrapper."""

    async def test_executor_tracks_metrics(self, make_message, mock_verification):
        """AccordExecutor should track execution counts."""
        from ciris_engine.logic.accord.executor import AccordExecutor

        executor = AccordExecutor()
        assert executor.execution_count == 0

        mock_verification.command = AccordCommandType.DRILL
        msg = make_message(AccordCommandType.DRILL)

        mock_runtime = MagicMock()
        mock_runtime.audit_service = AsyncMock()
        mock_runtime.audit_service.log_event = AsyncMock()

        with patch("ciris_engine.logic.runtime.ciris_runtime.CIRISRuntime") as MockRuntime:
            MockRuntime.get_instance.return_value = mock_runtime
            await executor.execute(msg, mock_verification)
        assert executor.execution_count == 1
        assert executor.success_count == 1
        assert executor.failure_count == 0

    async def test_executor_rejects_unverified(self, make_message):
        """AccordExecutor should reject unverified commands."""
        from ciris_engine.logic.accord.executor import AccordExecutor

        executor = AccordExecutor()
        invalid_verification = AccordVerificationResult(
            valid=False,
            rejection_reason="Test rejection",
        )
        msg = make_message(AccordCommandType.DRILL)

        result = await executor.execute(msg, invalid_verification)
        assert result.success is False
        assert executor.failure_count == 1
