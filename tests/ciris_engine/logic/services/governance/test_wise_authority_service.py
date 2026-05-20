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
    """Provide a temporary DB path for testing.

    Post-2.9.0 the SQLite bootstrap layer is gone — `initialize_database`
    just bootstraps persist's Engine, which creates the `cirislens.*` /
    `cirisgraph.*` schema via its own sqlx migrations. The persist Engine
    for the WA deferral path is wired by the `wise_authority_service`
    fixture below; this fixture only hands out a path.
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    # Remove the empty file so persist's first connect creates it cleanly.
    if os.path.exists(db_path):
        os.unlink(db_path)

    yield db_path
    for ext in ("", "-wal", "-shm"):
        p = db_path + ext
        if os.path.exists(p):
            os.unlink(p)


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
    """Create a wise authority service for testing.

    Also wires a ciris-persist Engine pointed at the temp DB so the WA
    deferral path (routed through `engine.task_*` post-2.9.0 absorption,
    CIRISAgent#763) can find a real engine. Wired here (rather than in
    `temp_db`) so the AuthenticationService start path runs without
    persist interference.
    """
    from ciris_persist import Engine  # type: ignore[import-untyped]

    import ciris_engine.logic.persistence.models.graph as _graph_mod
    from ciris_engine.logic.persistence.models.graph import set_persist_engine

    prior_engine = _graph_mod._engine
    prior_dsn = _graph_mod._engine_dsn
    persist_engine = Engine(f"sqlite:///{temp_db}", "test-key")
    set_persist_engine(persist_engine, dsn=f"sqlite:///{temp_db}")

    try:
        service = WiseAuthorityService(time_service=time_service, auth_service=auth_service, db_path=temp_db)
        yield service
    finally:
        _graph_mod._engine = prior_engine
        _graph_mod._engine_dsn = prior_dsn


def _insert_task_via_persist(
    task_id: str,
    channel_id: str,
    description: str,
    status: str,
    priority: int,
    created_at_iso: str,
    updated_at_iso: str,
    agent_occurrence_id: str = "default",
    context: dict | None = None,
) -> None:
    """Insert a task into the persist substrate.

    Mirrors the legacy raw `INSERT INTO tasks` rows that pre-2.9.0 tests
    used to seed the WA deferral path. Routed through `engine.task_upsert`
    so the migrated WA service code finds the row in cirislens_tasks.
    """
    import json as _json

    from ciris_engine.logic.persistence.models.graph import get_persist_engine

    engine = get_persist_engine()
    assert engine is not None, "persist engine must be wired for test"

    payload: dict = {
        "task_id": task_id,
        "channel_id": channel_id,
        "agent_occurrence_id": agent_occurrence_id,
        "description": description,
        "status": status,
        "priority": priority,
        "created_at": created_at_iso,
        "updated_at": updated_at_iso,
    }
    if context is not None:
        payload["context"] = context
    engine.task_upsert(_json.dumps(payload))


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
    _insert_task_via_persist(
        task_id="task-123",
        channel_id="test-channel",
        description="Test task",
        status="active",
        priority=0,
        created_at_iso=time_service.now().isoformat(),
        updated_at_iso=time_service.now().isoformat(),
    )

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
    _insert_task_via_persist(
        task_id="task-789",
        channel_id="test-channel",
        description="Test task",
        status="active",
        priority=0,
        created_at_iso=time_service.now().isoformat(),
        updated_at_iso=time_service.now().isoformat(),
    )

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

    # Create all tasks first
    for i in range(3):
        _insert_task_via_persist(
            task_id=f"task-{i}",
            channel_id="test-channel",
            description=f"Test task {i}",
            status="active",
            priority=0,
            created_at_iso=time_service.now().isoformat(),
            updated_at_iso=time_service.now().isoformat(),
        )

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

    # Create task in database first (via persist substrate)
    _insert_task_via_persist(
        task_id="task-resolve",
        channel_id="test-channel",
        description="Test task",
        status="active",
        priority=5,
        created_at_iso=time_service.now().isoformat(),
        updated_at_iso=time_service.now().isoformat(),
        agent_occurrence_id="default",
        context={"correlation_id": "test-correlation-123"},
    )

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

    # Check original task was marked as COMPLETED via persist
    import json

    from ciris_engine.logic.persistence.models.graph import get_persist_engine

    engine = get_persist_engine()
    raw = engine.task_get("task-resolve")
    assert raw is not None
    row = json.loads(raw) if isinstance(raw, str) else raw
    assert row["status"] == "completed"
    outcome_data = row.get("outcome")
    if isinstance(outcome_data, str):
        outcome_data = json.loads(outcome_data)
    assert outcome_data is not None
    assert outcome_data["status"] == "success"
    assert "approved" in outcome_data["summary"].lower()
    assert "wa-2025-06-24-AUTH01" in outcome_data["summary"]
    assert "actions_taken" in outcome_data
    assert "memories_created" in outcome_data
    assert "errors" in outcome_data

    # Check new guidance task was created — scan all tasks via persist for parent_task_id == "task-resolve"
    from ciris_engine.logic.persistence.models.tasks import _list_with_filter

    all_tasks = _list_with_filter({"agent_occurrence_id": "default"})
    guidance_tasks = [t for t in all_tasks if t.parent_task_id == "task-resolve"]
    assert len(guidance_tasks) == 1
    guidance_task = guidance_tasks[0]
    assert guidance_task.status.value == "pending"
    assert guidance_task.parent_task_id == "task-resolve"
    assert "[WA GUIDANCE]" in guidance_task.description
    assert "Approved after review" in guidance_task.description
    assert guidance_task.priority == 5  # Same priority as original

    # Check context includes WA guidance — re-fetch raw row to access non-TaskContext fields
    raw_guidance = engine.task_get(guidance_task.task_id)
    guidance_row = json.loads(raw_guidance) if isinstance(raw_guidance, str) else raw_guidance
    context = guidance_row.get("context") or {}
    if isinstance(context, str):
        context = json.loads(context)
    assert "wa_guidance" in context
    assert context["wa_guidance"] == "Approved after review"
    assert context["original_task_id"] == "task-resolve"
    assert context["resolved_deferral_id"] == deferral_id

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

    # Create task in database first (via persist substrate)
    _insert_task_via_persist(
        task_id="task-mod-time",
        channel_id="test-channel",
        description="Test task",
        status="active",
        priority=0,
        created_at_iso=time_service.now().isoformat(),
        updated_at_iso=time_service.now().isoformat(),
        agent_occurrence_id="default",
        context={"correlation_id": "test-mod-time-123"},
    )

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

    # Resolution with modification should succeed and create new task. Read
    # back the task status via persist (post-2.9.0 absorption).
    import json as _json

    from ciris_engine.logic.persistence.models.graph import get_persist_engine

    engine = get_persist_engine()
    raw = engine.task_get("task-mod-time")
    assert raw is not None
    row = _json.loads(raw) if isinstance(raw, str) else raw
    assert row["status"] == "completed"


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

        # Create a task with a specific priority value (via persist substrate)
        _insert_task_via_persist(
            task_id="task-dict-test",
            channel_id="test-channel-123",
            description="Test task for dict row handling",
            status="active",
            priority=7,  # Specific priority value to verify it's read correctly
            created_at_iso=time_service.now().isoformat(),
            updated_at_iso=time_service.now().isoformat(),
        )

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

        # Create tasks with different priorities (via persist substrate)
        priorities = [
            ("task-priority-0", 0, "low"),
            ("task-priority-3", 3, "medium"),
            ("task-priority-5", 5, "medium"),
            ("task-priority-8", 8, "high"),
            ("task-priority-10", 10, "high"),
        ]

        for task_id, priority, _ in priorities:
            _insert_task_via_persist(
                task_id=task_id,
                channel_id="test-channel",
                description=f"Task with priority {priority}",
                status="active",
                priority=priority,
                created_at_iso=time_service.now().isoformat(),
                updated_at_iso=time_service.now().isoformat(),
            )

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

        # NULL priority is interpreted as the persist-default 0 (which maps
        # to "low"). The legacy raw-SQL path could insert literal NULL into
        # the priority column; persist's CHECK keeps priority NOT NULL but
        # defaults to 0 when unspecified, producing the same "low" output.
        _insert_task_via_persist(
            task_id="task-null-priority",
            channel_id="test-channel",
            description="Task with NULL priority",
            status="active",
            priority=0,
            created_at_iso=time_service.now().isoformat(),
            updated_at_iso=time_service.now().isoformat(),
        )

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

        _insert_task_via_persist(
            task_id="task-fields-test",
            channel_id="channel-abc-123",
            description="Detailed task description for field testing",
            status="active",
            priority=5,
            created_at_iso=time_service.now().isoformat(),
            updated_at_iso=time_service.now().isoformat(),
        )

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
