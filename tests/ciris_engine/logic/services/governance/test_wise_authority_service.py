"""Unit tests for Wise Authority Service."""

import os
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from ciris_engine.logic.services.governance.wise_authority import WiseAuthorityService
from ciris_engine.logic.services.infrastructure.authentication import AuthenticationService
from ciris_engine.logic.services.lifecycle.time import TimeService
from ciris_engine.schemas.services.authority_core import (
    DeferralApprovalContext,
    DeferralRequest,
    DeferralResponse,
    GuidanceRequest,
    GuidanceResponse,
    WARole,
)
from ciris_engine.schemas.services.context import GuidanceContext
from ciris_engine.schemas.services.core import ServiceCapabilities, ServiceStatus


@pytest.fixture
def time_service():
    """Create a time service for testing."""
    return TimeService()


@pytest.fixture
def temp_db():
    """Create a temporary database for testing."""
    import sqlite3

    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    # Create the tasks table (needed for new deferral system)
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS tasks (
            task_id TEXT PRIMARY KEY,
            channel_id TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT NOT NULL,
            priority INTEGER DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            parent_task_id TEXT,
            context_json TEXT,
            outcome TEXT,
            outcome_json TEXT,
            retry_count INTEGER DEFAULT 0,
            signed_by TEXT,
            signature TEXT,
            signed_at TEXT,
            agent_occurrence_id TEXT NOT NULL DEFAULT 'default'
        )
    """
    )
    # Also create thoughts table for compatibility
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS thoughts (
            thought_id TEXT PRIMARY KEY,
            task_id TEXT,
            thought_content TEXT,
            thought_context TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            status TEXT DEFAULT 'pending',
            channel_id TEXT,
            user_id TEXT,
            priority TEXT DEFAULT 'medium',
            resolution_json TEXT,
            defer_until TIMESTAMP,
            metadata TEXT
        )
    """
    )
    conn.commit()
    conn.close()

    yield db_path
    os.unlink(db_path)


@pytest_asyncio.fixture
async def auth_service(temp_db, time_service):
    """Create an authentication service for testing."""
    service = AuthenticationService(db_path=temp_db, time_service=time_service, key_dir=None)
    await service.start()

    # Mock some methods for testing
    service.get_wa = AsyncMock(
        return_value=MagicMock(
            wa_id="wa-2025-06-24-TEST01", role=WARole.AUTHORITY, active=True, created_at=datetime.now(timezone.utc)
        )
    )
    service.bootstrap_if_needed = AsyncMock()

    yield service
    await service.stop()


@pytest_asyncio.fixture
async def wise_authority_service(auth_service, time_service, temp_db):
    """Create a wise authority service for testing."""
    service = WiseAuthorityService(time_service=time_service, auth_service=auth_service, db_path=temp_db)
    yield service


@pytest.mark.asyncio
async def test_wise_authority_lifecycle(wise_authority_service):
    """Test WiseAuthorityService start/stop lifecycle."""
    # Start
    await wise_authority_service.start()
    # Service should be ready
    assert wise_authority_service._started is True
    assert await wise_authority_service.is_healthy()

    # Stop
    await wise_authority_service.stop()
    # Should complete without error
    assert wise_authority_service._started is False


@pytest.mark.asyncio
async def test_check_authorization(wise_authority_service, auth_service):
    """Test authorization checking."""
    await wise_authority_service.start()

    # Test ROOT authorization - can do everything
    auth_service.get_wa.return_value = MagicMock(wa_id="wa-2025-06-24-ROOT01", role=WARole.ROOT, active=True)
    assert await wise_authority_service.check_authorization("wa-2025-06-24-ROOT01", "mint_wa") is True
    assert await wise_authority_service.check_authorization("wa-2025-06-24-ROOT01", "approve_deferrals") is True

    # Test AUTHORITY authorization - can't mint WAs
    auth_service.get_wa.return_value = MagicMock(wa_id="wa-2025-06-24-AUTH01", role=WARole.AUTHORITY, active=True)
    assert await wise_authority_service.check_authorization("wa-2025-06-24-AUTH01", "approve_deferrals") is True
    assert await wise_authority_service.check_authorization("wa-2025-06-24-AUTH01", "mint_wa") is False

    # Test OBSERVER authorization - limited permissions
    auth_service.get_wa.return_value = MagicMock(wa_id="wa-2025-06-24-OBS01", role=WARole.OBSERVER, active=True)
    assert await wise_authority_service.check_authorization("wa-2025-06-24-OBS01", "read") is True
    assert await wise_authority_service.check_authorization("wa-2025-06-24-OBS01", "send_message") is True
    assert await wise_authority_service.check_authorization("wa-2025-06-24-OBS01", "approve_deferrals") is False


@pytest.mark.asyncio
async def test_request_approval(wise_authority_service, time_service, auth_service, temp_db):
    """Test requesting approval for actions."""
    await wise_authority_service.start()

    # Create task in database for deferral
    import sqlite3

    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO tasks (task_id, channel_id, description, status, priority, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
        (
            "task-123",
            "test-channel",
            "Test task",
            "active",
            0,
            time_service.now().isoformat(),
            time_service.now().isoformat(),
        ),
    )
    conn.commit()
    conn.close()

    # Test auto-approval for ROOT
    auth_service.get_wa.return_value = MagicMock(wa_id="wa-2025-06-24-ROOT01", role=WARole.ROOT, active=True)

    context = DeferralApprovalContext(
        task_id="task-123",
        thought_id="thought-456",
        action_name="read_data",
        action_params={"resource": "public_data"},
        requester_id="wa-2025-06-24-ROOT01",
        channel_id="test-channel",
    )

    # ROOT should auto-approve
    approved = await wise_authority_service.request_approval("read_data", context)
    assert approved is True

    # Test deferral for unauthorized action
    # Update mock to return OBSERVER
    auth_service.get_wa.return_value = MagicMock(wa_id="wa-2025-06-24-OBS01", role=WARole.OBSERVER, active=True)

    context.requester_id = "wa-2025-06-24-OBS01"  # Observer can't approve
    approved = await wise_authority_service.request_approval("approve_deferrals", context)
    assert approved is False

    # Should have created a deferral
    pending = await wise_authority_service.get_pending_deferrals()
    assert len(pending) == 1


@pytest.mark.asyncio
async def test_send_deferral(wise_authority_service, time_service, temp_db):
    """Test sending deferrals."""
    await wise_authority_service.start()

    # First create a task in the database
    import sqlite3

    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO tasks (task_id, channel_id, description, status, priority, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """,
        (
            "task-789",
            "test-channel",
            "Test task",
            "active",
            0,
            time_service.now().isoformat(),
            time_service.now().isoformat(),
        ),
    )
    conn.commit()
    conn.close()

    # Create a deferral request
    deferral = DeferralRequest(
        task_id="task-789",
        thought_id="thought-101",
        reason="Requires human review for sensitive action",
        defer_until=time_service.now() + timedelta(hours=24),
        context={"action": "delete_user_data", "user_id": "user-123"},
    )

    # Send deferral
    deferral_id = await wise_authority_service.send_deferral(deferral)

    assert deferral_id is not None
    assert deferral_id.startswith("defer_")
    # Verify deferral was created
    pending = await wise_authority_service.get_pending_deferrals()
    assert len(pending) == 1
    assert any(d.deferral_id == deferral_id for d in pending)


@pytest.mark.asyncio
async def test_get_pending_deferrals(wise_authority_service, time_service, temp_db):
    """Test getting pending deferrals."""
    await wise_authority_service.start()

    # Create tasks in the database first
    import sqlite3

    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()

    # Create all tasks first
    for i in range(3):
        cursor.execute(
            """
            INSERT INTO tasks (task_id, channel_id, description, status, priority, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                f"task-{i}",
                "test-channel",
                f"Test task {i}",
                "active",
                0,
                time_service.now().isoformat(),
                time_service.now().isoformat(),
            ),
        )
    conn.commit()
    conn.close()

    # Then add deferrals
    for i in range(3):
        deferral = DeferralRequest(
            task_id=f"task-{i}",
            thought_id=f"thought-{i}",
            reason=f"Test deferral {i}",
            defer_until=time_service.now() + timedelta(hours=i + 1),
            context={"test": f"value-{i}"},
        )
        await wise_authority_service.send_deferral(deferral)

    # Get all pending deferrals
    pending = await wise_authority_service.get_pending_deferrals()
    assert len(pending) == 3

    # Check deferral structure
    first = pending[0]
    assert hasattr(first, "deferral_id")
    assert hasattr(first, "task_id")
    assert hasattr(first, "thought_id")
    assert hasattr(first, "reason")
    assert first.status == "pending"


@pytest.mark.asyncio
async def test_resolve_deferral(wise_authority_service, time_service, temp_db):
    """Test resolving deferrals creates new guidance task."""
    await wise_authority_service.start()

    # Create task in database first
    import sqlite3

    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO tasks (task_id, channel_id, description, status, priority, created_at, updated_at, agent_occurrence_id, context_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            "task-resolve",
            "test-channel",
            "Test task",
            "active",
            5,
            time_service.now().isoformat(),
            time_service.now().isoformat(),
            "default",
            '{"correlation_id": "test-correlation-123"}',
        ),
    )
    conn.commit()
    conn.close()

    # Create and send a deferral
    deferral = DeferralRequest(
        task_id="task-resolve",
        thought_id="thought-resolve",
        reason="Test resolution",
        defer_until=time_service.now() + timedelta(hours=1),
        context={},
    )
    deferral_id = await wise_authority_service.send_deferral(deferral)

    # Resolve it with approval
    response = DeferralResponse(
        approved=True, reason="Approved after review", wa_id="wa-2025-06-24-AUTH01", signature="test-signature"
    )

    resolved = await wise_authority_service.resolve_deferral(deferral_id, response)
    assert resolved is True

    # Check original task was marked as COMPLETED
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT status, outcome_json FROM tasks WHERE task_id = ?", ("task-resolve",))
    row = cursor.fetchone()
    assert row is not None
    status, outcome_json = row
    assert status == "completed"
    # outcome_json follows TaskOutcome schema: status, summary, actions_taken, memories_created, errors
    import json

    outcome_data = json.loads(outcome_json)
    assert outcome_data["status"] == "success"
    assert "approved" in outcome_data["summary"].lower()
    assert "wa-2025-06-24-AUTH01" in outcome_data["summary"]
    assert "actions_taken" in outcome_data
    assert "memories_created" in outcome_data
    assert "errors" in outcome_data

    # Check new guidance task was created
    cursor.execute(
        "SELECT task_id, description, status, priority, parent_task_id, context_json FROM tasks WHERE parent_task_id = ?",
        ("task-resolve",),
    )
    guidance_row = cursor.fetchone()
    assert guidance_row is not None
    guidance_task_id, description, status, priority, parent_task_id, context_json = guidance_row

    assert status == "pending"
    assert parent_task_id == "task-resolve"
    assert "[WA GUIDANCE]" in description
    assert "Approved after review" in description
    assert priority == 5  # Same priority as original

    # Check context includes WA guidance
    import json

    context = json.loads(context_json)
    assert "wa_guidance" in context
    assert context["wa_guidance"] == "Approved after review"
    assert context["original_task_id"] == "task-resolve"
    assert context["resolved_deferral_id"] == deferral_id

    conn.close()

    # Check no pending deferrals remain (original marked complete)
    pending = await wise_authority_service.get_pending_deferrals()
    assert len(pending) == 0


def test_wise_authority_capabilities(wise_authority_service):
    """Test WiseAuthorityService.get_capabilities() returns correct info."""
    caps = wise_authority_service.get_capabilities()
    assert isinstance(caps, ServiceCapabilities)
    assert caps.service_name == "WiseAuthorityService"
    assert caps.version == "1.0.0"
    assert "check_authorization" in caps.actions
    assert "request_approval" in caps.actions
    assert "get_guidance" in caps.actions
    assert "send_deferral" in caps.actions
    assert "get_pending_deferrals" in caps.actions
    assert "resolve_deferral" in caps.actions
    assert "grant_permission" in caps.actions
    assert "revoke_permission" in caps.actions
    assert "list_permissions" in caps.actions
    assert "SecretsService" in caps.dependencies
    assert "GraphAuditService" in caps.dependencies


@pytest.mark.asyncio
async def test_wise_authority_status(wise_authority_service):
    """Test WiseAuthorityService.get_status() returns correct status."""
    await wise_authority_service.start()

    status = wise_authority_service.get_status()
    assert isinstance(status, ServiceStatus)
    assert status.service_name == "WiseAuthorityService"
    assert status.service_type == "governance_service"
    assert status.is_healthy is True
    assert "pending_deferrals" in status.metrics
    assert "total_deferrals" in status.metrics
    assert "resolved_deferrals" in status.metrics


@pytest.mark.asyncio
async def test_list_permissions(wise_authority_service, auth_service):
    """Test listing permissions for a WA."""
    await wise_authority_service.start()

    # Test ROOT permissions
    auth_service.get_wa.return_value = MagicMock(
        wa_id="wa-2025-06-24-ROOT01", role=WARole.ROOT, active=True, created_at=datetime.now(timezone.utc)
    )
    permissions = await wise_authority_service.list_permissions("wa-2025-06-24-ROOT01")
    assert len(permissions) > 0
    assert any(p.permission_name == "*" for p in permissions)

    # Test AUTHORITY permissions
    auth_service.get_wa.return_value = MagicMock(
        wa_id="wa-2025-06-24-AUTH01", role=WARole.AUTHORITY, active=True, created_at=datetime.now(timezone.utc)
    )
    permissions = await wise_authority_service.list_permissions("wa-2025-06-24-AUTH01")
    assert len(permissions) > 0
    assert any(p.permission_name == "approve_deferrals" for p in permissions)
    assert not any(p.permission_name == "*" for p in permissions)

    # Test OBSERVER permissions
    auth_service.get_wa.return_value = MagicMock(
        wa_id="wa-2025-06-24-OBS01", role=WARole.OBSERVER, active=True, created_at=datetime.now(timezone.utc)
    )
    permissions = await wise_authority_service.list_permissions("wa-2025-06-24-OBS01")
    assert len(permissions) > 0
    assert any(p.permission_name == "read" for p in permissions)
    assert any(p.permission_name == "send_message" for p in permissions)
    assert not any(p.permission_name == "approve_deferrals" for p in permissions)


@pytest.mark.asyncio
async def test_fetch_guidance(wise_authority_service):
    """Test fetching guidance from WAs."""
    await wise_authority_service.start()

    # Create a guidance context
    context = GuidanceContext(
        thought_id="thought-guid-01",
        task_id="task-guid-01",
        question="Should I allow this user action?",
        ethical_considerations=["user_safety", "data_privacy"],
        domain_context={"action": "data_export"},
    )

    # Fetch guidance (should return None as no WA has provided guidance yet)
    guidance = await wise_authority_service.fetch_guidance(context)
    assert guidance is None  # No guidance available in test environment


@pytest.mark.asyncio
async def test_get_guidance(wise_authority_service):
    """Test getting guidance through protocol method."""
    await wise_authority_service.start()

    # Create a guidance request
    request = GuidanceRequest(
        context="Should I proceed with user data deletion?",
        options=["Delete immediately", "Confirm with user", "Archive instead"],
        recommendation="Confirm with user",
        urgency="high",
    )

    # Get guidance
    response = await wise_authority_service.get_guidance(request)

    assert isinstance(response, GuidanceResponse)
    assert response.wa_id == "system"  # No WA guidance available
    assert response.reasoning == "No Wise Authority guidance available yet"
    assert response.custom_guidance is None


@pytest.mark.asyncio
async def test_grant_revoke_permissions(wise_authority_service):
    """Test permission grant/revoke (currently role-based only)."""
    await wise_authority_service.start()

    # Try to grant permission (should fail - permissions are role-based)
    granted = await wise_authority_service.grant_permission(
        wa_id="wa-2025-06-24-TEST01", permission="special_access", resource="sensitive_data"
    )
    assert granted is False  # Can't grant dynamic permissions in beta

    # Try to revoke permission (should fail - permissions are role-based)
    revoked = await wise_authority_service.revoke_permission(
        wa_id="wa-2025-06-24-TEST01", permission="read", resource="public_data"
    )
    assert revoked is False  # Can't revoke role-based permissions


@pytest.mark.asyncio
async def test_deferral_with_modified_time(wise_authority_service, time_service, temp_db):
    """Test resolving deferral with modified time creates new task."""
    await wise_authority_service.start()

    # Create task in database first
    import sqlite3

    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO tasks (task_id, channel_id, description, status, priority, created_at, updated_at, agent_occurrence_id, context_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """,
        (
            "task-mod-time",
            "test-channel",
            "Test task",
            "active",
            0,
            time_service.now().isoformat(),
            time_service.now().isoformat(),
            "default",
            '{"correlation_id": "test-mod-time-123"}',
        ),
    )
    conn.commit()
    conn.close()

    # Create and send a deferral
    original_defer_time = time_service.now() + timedelta(hours=1)
    deferral = DeferralRequest(
        task_id="task-mod-time",
        thought_id="thought-mod-time",
        reason="Needs extended review",
        defer_until=original_defer_time,
        context={},
    )
    deferral_id = await wise_authority_service.send_deferral(deferral)

    # Resolve with modified time
    new_defer_time = time_service.now() + timedelta(hours=48)
    response = DeferralResponse(
        approved=True,
        reason="Approved but needs more time",
        modified_time=new_defer_time,
        wa_id="wa-2025-06-24-AUTH01",
        signature="test-signature",
    )

    resolved = await wise_authority_service.resolve_deferral(deferral_id, response)
    assert resolved is True

    # Resolution with modification should succeed and create new task
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()
    cursor.execute("SELECT status FROM tasks WHERE task_id = ?", ("task-mod-time",))
    row = cursor.fetchone()
    assert row is not None
    assert row[0] == "completed"
    conn.close()


# ========== Helper Method Tests ==========


class TestDeferralHelperMethods:
    """Tests for the deferral helper methods extracted for reduced cognitive complexity."""

    def test_parse_deferral_context_valid_json(self, wise_authority_service):
        """Test parsing valid context JSON."""
        context_json = '{"deferral": {"deferral_id": "defer_123", "reason": "Test reason"}}'
        context, deferral_info = wise_authority_service._parse_deferral_context(context_json)

        assert context == {"deferral": {"deferral_id": "defer_123", "reason": "Test reason"}}
        assert deferral_info == {"deferral_id": "defer_123", "reason": "Test reason"}

    def test_parse_deferral_context_invalid_json(self, wise_authority_service):
        """Test parsing invalid context JSON returns empty dicts."""
        context_json = "not valid json {"
        context, deferral_info = wise_authority_service._parse_deferral_context(context_json)

        assert context == {}
        assert deferral_info == {}

    def test_parse_deferral_context_none(self, wise_authority_service):
        """Test parsing None context returns empty dicts."""
        context, deferral_info = wise_authority_service._parse_deferral_context(None)

        assert context == {}
        assert deferral_info == {}

    def test_parse_deferral_context_no_deferral_key(self, wise_authority_service):
        """Test parsing context without deferral key."""
        context_json = '{"other_key": "value"}'
        context, deferral_info = wise_authority_service._parse_deferral_context(context_json)

        assert context == {"other_key": "value"}
        assert deferral_info == {}

    def test_priority_to_string_high(self, wise_authority_service):
        """Test priority > 5 returns 'high'."""
        assert wise_authority_service._priority_to_string(6) == "high"
        assert wise_authority_service._priority_to_string(10) == "high"
        assert wise_authority_service._priority_to_string(100) == "high"

    def test_priority_to_string_medium(self, wise_authority_service):
        """Test priority 1-5 returns 'medium'."""
        assert wise_authority_service._priority_to_string(1) == "medium"
        assert wise_authority_service._priority_to_string(3) == "medium"
        assert wise_authority_service._priority_to_string(5) == "medium"

    def test_priority_to_string_low(self, wise_authority_service):
        """Test priority 0 or None returns 'low'."""
        assert wise_authority_service._priority_to_string(0) == "low"
        assert wise_authority_service._priority_to_string(None) == "low"
        assert wise_authority_service._priority_to_string(-1) == "low"

    def test_build_ui_context_basic(self, wise_authority_service):
        """Test building UI context with basic inputs."""
        description = "Test task description"
        deferral_info: dict = {"context": {}}

        ui_context = wise_authority_service._build_ui_context(description, deferral_info)

        assert ui_context["task_description"] == description
        assert len(ui_context) == 1

    def test_build_ui_context_with_deferral_context(self, wise_authority_service):
        """Test building UI context includes deferral context fields."""
        description = "Test task"
        deferral_info: dict = {
            "context": {
                "user_id": "user123",
                "channel": "general",
            }
        }

        ui_context = wise_authority_service._build_ui_context(description, deferral_info)

        assert ui_context["task_description"] == description
        assert ui_context["user_id"] == "user123"
        assert ui_context["channel"] == "general"

    def test_build_ui_context_with_original_message(self, wise_authority_service):
        """Test building UI context includes original message."""
        description = "Test task"
        deferral_info: dict = {
            "context": {},
            "original_message": "Hello, I need help!",
        }

        ui_context = wise_authority_service._build_ui_context(description, deferral_info)

        assert ui_context["original_message"] == "Hello, I need help!"

    def test_build_ui_context_truncates_long_values(self, wise_authority_service):
        """Test that UI context truncates long values."""
        long_description = "x" * 600
        long_value = "y" * 300
        deferral_info: dict = {
            "context": {"long_field": long_value},
            "original_message": "z" * 600,
        }

        ui_context = wise_authority_service._build_ui_context(long_description, deferral_info)

        assert len(ui_context["task_description"]) == 500
        assert len(ui_context["long_field"]) == 200
        assert len(ui_context["original_message"]) == 500

    def test_build_ui_context_none_description(self, wise_authority_service):
        """Test building UI context with None description."""
        ui_context = wise_authority_service._build_ui_context(None, {"context": {}})

        assert ui_context["task_description"] == ""

    def test_build_ui_context_skips_none_values(self, wise_authority_service):
        """Test that None values in deferral context are skipped."""
        deferral_info: dict = {
            "context": {
                "valid_field": "value",
                "none_field": None,
            }
        }

        ui_context = wise_authority_service._build_ui_context("desc", deferral_info)

        assert "valid_field" in ui_context
        assert "none_field" not in ui_context

    def test_create_pending_deferral_basic(self, wise_authority_service):
        """Test creating a PendingDeferral with basic inputs."""
        deferral = wise_authority_service._create_pending_deferral(
            task_id="task-123",
            channel_id="channel-456",
            updated_at="2025-01-15T10:00:00",
            deferral_info={"deferral_id": "defer_abc", "thought_id": "thought_xyz", "reason": "Need review"},
            priority_str="medium",
            ui_context={"task_description": "Test"},
            description="Test description",
        )

        assert deferral.deferral_id == "defer_abc"
        assert deferral.task_id == "task-123"
        assert deferral.thought_id == "thought_xyz"
        assert deferral.reason == "Need review"
        assert deferral.channel_id == "channel-456"
        assert deferral.priority == "medium"
        assert deferral.status == "pending"
        assert deferral.question == "Need review"
        assert deferral.context == {"task_description": "Test"}

    def test_create_pending_deferral_default_deferral_id(self, wise_authority_service):
        """Test that deferral_id defaults to defer_{task_id}."""
        deferral = wise_authority_service._create_pending_deferral(
            task_id="task-999",
            channel_id="channel-1",
            updated_at="2025-01-15T10:00:00",
            deferral_info={},  # No deferral_id provided
            priority_str="low",
            ui_context={},
            description="Desc",
        )

        assert deferral.deferral_id == "defer_task-999"

    def test_create_pending_deferral_uses_description_as_reason(self, wise_authority_service):
        """Test that description is used as reason when not in deferral_info."""
        deferral = wise_authority_service._create_pending_deferral(
            task_id="task-1",
            channel_id="ch-1",
            updated_at="2025-01-15T10:00:00",
            deferral_info={},  # No reason provided
            priority_str="low",
            ui_context={},
            description="The task description",
        )

        assert deferral.reason == "The task description"
        assert deferral.question == "The task description"

    def test_create_pending_deferral_extracts_user_id(self, wise_authority_service):
        """Test that user_id is extracted from deferral context."""
        deferral = wise_authority_service._create_pending_deferral(
            task_id="task-1",
            channel_id="ch-1",
            updated_at="2025-01-15T10:00:00",
            deferral_info={"context": {"user_id": "user-abc"}},
            priority_str="high",
            ui_context={},
            description="Desc",
        )

        assert deferral.user_id == "user-abc"

    def test_create_pending_deferral_calculates_timeout(self, wise_authority_service):
        """Test that timeout_at is calculated as 7 days from updated_at."""
        deferral = wise_authority_service._create_pending_deferral(
            task_id="task-1",
            channel_id="ch-1",
            updated_at="2025-01-15T10:00:00",
            deferral_info={},
            priority_str="low",
            ui_context={},
            description="Desc",
        )

        # timeout should be 7 days after 2025-01-15T10:00:00
        assert deferral.timeout_at == "2025-01-22T10:00:00"

    def test_create_pending_deferral_truncates_long_reason(self, wise_authority_service):
        """Test that reason is truncated to 200 characters."""
        long_reason = "x" * 300
        deferral = wise_authority_service._create_pending_deferral(
            task_id="task-1",
            channel_id="ch-1",
            updated_at="2025-01-15T10:00:00",
            deferral_info={"reason": long_reason},
            priority_str="low",
            ui_context={},
            description="Desc",
        )

        assert len(deferral.reason) == 200


# ========== PostgreSQL Dict Row Format Tests ==========


class TestPostgreSQLDictRowHandling:
    """Tests for PostgreSQL RealDictCursor compatibility.

    PostgreSQL uses RealDictCursor which returns rows as dictionaries.
    These tests verify that get_pending_deferrals correctly handles both
    dict rows (PostgreSQL) and tuple rows (SQLite).
    """

    @pytest.mark.asyncio
    async def test_get_pending_deferrals_handles_dict_rows(self, wise_authority_service, time_service, temp_db):
        """Test that get_pending_deferrals correctly handles dict-format rows.

        This tests the fix for: invalid literal for int() with base 10: 'priority'
        which occurred when PostgreSQL RealDictCursor returned dicts and the code
        tried to unpack them as tuples (getting keys instead of values).
        """
        await wise_authority_service.start()

        # Create a task with a specific priority value
        import sqlite3

        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO tasks (task_id, channel_id, description, status, priority, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                "task-dict-test",
                "test-channel-123",
                "Test task for dict row handling",
                "active",
                7,  # Specific priority value to verify it's read correctly
                time_service.now().isoformat(),
                time_service.now().isoformat(),
            ),
        )
        conn.commit()
        conn.close()

        # Create a deferral for the task
        from ciris_engine.schemas.services.authority_core import DeferralRequest

        deferral = DeferralRequest(
            task_id="task-dict-test",
            thought_id="thought-dict-test",
            reason="Testing dict row handling",
            defer_until=time_service.now() + timedelta(hours=24),
            context={"test_key": "test_value"},
        )
        await wise_authority_service.send_deferral(deferral)

        # Get pending deferrals - this should work without raising
        # "invalid literal for int() with base 10: 'priority'"
        pending = await wise_authority_service.get_pending_deferrals()

        assert len(pending) == 1
        deferral_result = pending[0]

        # Verify the priority was correctly interpreted (7 > 5 = "high")
        assert deferral_result.priority == "high"
        assert deferral_result.task_id == "task-dict-test"
        assert deferral_result.channel_id == "test-channel-123"

    @pytest.mark.asyncio
    async def test_get_pending_deferrals_with_various_priorities(self, wise_authority_service, time_service, temp_db):
        """Test priority parsing works correctly for all priority levels."""
        await wise_authority_service.start()

        import sqlite3

        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()

        # Create tasks with different priorities
        priorities = [
            ("task-priority-0", 0, "low"),
            ("task-priority-3", 3, "medium"),
            ("task-priority-5", 5, "medium"),
            ("task-priority-8", 8, "high"),
            ("task-priority-10", 10, "high"),
        ]

        for task_id, priority, _ in priorities:
            cursor.execute(
                """
                INSERT INTO tasks (task_id, channel_id, description, status, priority, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    task_id,
                    "test-channel",
                    f"Task with priority {priority}",
                    "active",
                    priority,
                    time_service.now().isoformat(),
                    time_service.now().isoformat(),
                ),
            )
        conn.commit()
        conn.close()

        # Create deferrals for all tasks
        from ciris_engine.schemas.services.authority_core import DeferralRequest

        for task_id, _, _ in priorities:
            deferral = DeferralRequest(
                task_id=task_id,
                thought_id=f"thought-{task_id}",
                reason="Test priority handling",
                defer_until=time_service.now() + timedelta(hours=24),
                context={},
            )
            await wise_authority_service.send_deferral(deferral)

        # Get pending deferrals
        pending = await wise_authority_service.get_pending_deferrals()
        assert len(pending) == 5

        # Verify each priority was correctly converted
        pending_by_task = {d.task_id: d for d in pending}
        for task_id, _, expected_priority in priorities:
            assert pending_by_task[task_id].priority == expected_priority, (
                f"Task {task_id} expected priority '{expected_priority}' "
                f"but got '{pending_by_task[task_id].priority}'"
            )

    @pytest.mark.asyncio
    async def test_get_pending_deferrals_with_null_priority(self, wise_authority_service, time_service, temp_db):
        """Test that NULL priority is handled correctly (should be 'low')."""
        await wise_authority_service.start()

        import sqlite3

        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO tasks (task_id, channel_id, description, status, priority, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                "task-null-priority",
                "test-channel",
                "Task with NULL priority",
                "active",
                None,  # NULL priority
                time_service.now().isoformat(),
                time_service.now().isoformat(),
            ),
        )
        conn.commit()
        conn.close()

        # Create deferral
        from ciris_engine.schemas.services.authority_core import DeferralRequest

        deferral = DeferralRequest(
            task_id="task-null-priority",
            thought_id="thought-null-priority",
            reason="Test null priority",
            defer_until=time_service.now() + timedelta(hours=24),
            context={},
        )
        await wise_authority_service.send_deferral(deferral)

        # Get pending deferrals
        pending = await wise_authority_service.get_pending_deferrals()
        assert len(pending) == 1
        assert pending[0].priority == "low"

    @pytest.mark.asyncio
    async def test_get_pending_deferrals_preserves_all_fields(self, wise_authority_service, time_service, temp_db):
        """Test that all fields are correctly preserved when parsing rows."""
        await wise_authority_service.start()

        import sqlite3

        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO tasks (task_id, channel_id, description, status, priority, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
            (
                "task-fields-test",
                "channel-abc-123",
                "Detailed task description for field testing",
                "active",
                5,
                time_service.now().isoformat(),
                time_service.now().isoformat(),
            ),
        )
        conn.commit()
        conn.close()

        # Create deferral with detailed context
        from ciris_engine.schemas.services.authority_core import DeferralRequest

        deferral = DeferralRequest(
            task_id="task-fields-test",
            thought_id="thought-fields-test",
            reason="Field preservation test",
            defer_until=time_service.now() + timedelta(hours=24),
            context={"user_id": "user-xyz", "action": "test_action"},
        )
        await wise_authority_service.send_deferral(deferral)

        # Get pending deferrals
        pending = await wise_authority_service.get_pending_deferrals()
        assert len(pending) == 1

        result = pending[0]
        assert result.task_id == "task-fields-test"
        assert result.channel_id == "channel-abc-123"
        assert result.thought_id == "thought-fields-test"
        assert "Field preservation test" in result.reason
        assert result.status == "pending"
        assert result.priority == "medium"  # priority 5 = medium
        assert "Detailed task description" in result.context.get("task_description", "")
