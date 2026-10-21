"""Tests for the create_ticket proposal channel (#938).

Covers the invariants that make a proposal a proposal:
- it is created in a state the WorkProcessor never executes
- the agent cannot promote its own proposal
- the agent cannot write reserved authorization metadata
- requested budget is structurally distinct from a granted one
- the runaway bound fires with a clear error
"""

import os
import tempfile
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest
import pytest_asyncio

from ciris_engine.logic.persistence.db import initialize_database
from ciris_engine.logic.persistence.models.tickets import create_ticket, get_ticket
from ciris_engine.logic.secrets.service import SecretsService
from ciris_engine.logic.services.tools.core_tool_service.service import (
    MAX_PROPOSALS_PER_TASK,
    MAX_PROPOSALS_PER_WINDOW,
    CoreToolService,
)
from ciris_engine.schemas.services.budget_envelope import (
    EXECUTING_TICKET_STATUSES,
    GRANTED_BUDGET_METADATA_KEY,
    PROPOSAL_METADATA_KEY,
    PROPOSAL_TICKET_STATUS,
    REQUESTED_BUDGET_METADATA_KEY,
)


@pytest.fixture
def temp_db_path():
    """Temporary database with migrations applied + persist wired."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    from ciris_engine.logic.persistence.models import graph as _graph_mod

    prior_engine = _graph_mod._engine
    prior_dsn = _graph_mod._engine_dsn
    initialize_database(db_path)

    yield db_path

    _graph_mod._engine = prior_engine
    _graph_mod._engine_dsn = prior_dsn
    if os.path.exists(db_path):
        os.unlink(db_path)


@pytest.fixture
def mock_secrets_service():
    mock = Mock(spec=SecretsService)
    mock.retrieve_secret = AsyncMock()
    return mock


@pytest.fixture
def mock_time_service():
    mock = Mock()
    mock.now.return_value = datetime(2026, 7, 30, 12, 0, 0, tzinfo=timezone.utc)
    return mock


@pytest_asyncio.fixture
async def tool_service(mock_secrets_service, mock_time_service, temp_db_path):
    service = CoreToolService(
        secrets_service=mock_secrets_service, time_service=mock_time_service, db_path=temp_db_path
    )
    await service.start()
    return service


class TestProposalIsNotExecuting:
    """A proposal must never become a running task by itself."""

    @pytest.mark.asyncio
    async def test_create_ticket_uses_proposed_status(self, tool_service):
        result = await tool_service.execute_tool(
            "create_ticket", {"goal_description": "Archive old exports", "task_id": "TASK-1"}
        )
        assert result.success, result.error
        ticket_id = result.data["ticket_id"]

        ticket = get_ticket(ticket_id)
        assert ticket is not None
        assert ticket["status"] == PROPOSAL_TICKET_STATUS

    @pytest.mark.asyncio
    async def test_proposed_status_is_not_an_executing_status(self, tool_service):
        """The status create_ticket writes is not one the WorkProcessor discovers."""
        assert PROPOSAL_TICKET_STATUS not in EXECUTING_TICKET_STATUSES

    @pytest.mark.asyncio
    async def test_work_processor_skips_proposals(self):
        """Defense in depth: the claim path refuses a proposal even if listed."""
        from ciris_engine.logic.processors.states.work_processor import WorkProcessor

        skip = WorkProcessor._should_skip_ticket_by_status
        assert skip(None, PROPOSAL_TICKET_STATUS) is True
        # sanity: genuinely executable statuses are not skipped
        assert skip(None, "pending") is False
        assert skip(None, "in_progress") is False

    @pytest.mark.asyncio
    async def test_result_states_it_will_not_execute(self, tool_service):
        result = await tool_service.execute_tool("create_ticket", {"goal_description": "Do a thing"})
        assert result.data["is_proposal"] is True
        assert result.data["will_execute"] is False

    @pytest.mark.asyncio
    async def test_agent_cannot_promote_its_own_proposal(self, tool_service):
        """update_ticket must refuse to move a proposal into an executing status."""
        created = await tool_service.execute_tool("create_ticket", {"goal_description": "Spend money on X"})
        ticket_id = created.data["ticket_id"]

        for target in sorted(EXECUTING_TICKET_STATUSES):
            result = await tool_service.execute_tool("update_ticket", {"ticket_id": ticket_id, "status": target})
            assert result.success is False, f"agent promoted proposal to {target}"
            assert "proposal" in (result.error or "").lower()
            assert get_ticket(ticket_id)["status"] == PROPOSAL_TICKET_STATUS

    @pytest.mark.asyncio
    async def test_agent_may_withdraw_its_own_proposal(self, tool_service):
        """Cancelling is allowed — it narrows, it does not widen."""
        created = await tool_service.execute_tool("create_ticket", {"goal_description": "Never mind"})
        ticket_id = created.data["ticket_id"]

        result = await tool_service.execute_tool("update_ticket", {"ticket_id": ticket_id, "status": "cancelled"})
        assert result.success is True
        assert get_ticket(ticket_id)["status"] == "cancelled"


class TestRequestedIsNotGranted:
    """Requesting a budget must never be confusable with holding one."""

    @pytest.mark.asyncio
    async def test_requested_budget_stored_under_requested_key_only(self, tool_service):
        result = await tool_service.execute_tool(
            "create_ticket",
            {
                "goal_description": "Pay opt-out fee",
                "requested_budget_amount": 25,
                "requested_budget_currency": "USDC",
                "requested_budget_purpose": "Opt-out processing fee",
            },
        )
        assert result.success, result.error
        metadata = get_ticket(result.data["ticket_id"])["metadata"]

        assert REQUESTED_BUDGET_METADATA_KEY in metadata
        # The decisive assertion: creating a proposal never produces a grant.
        assert GRANTED_BUDGET_METADATA_KEY not in metadata
        assert metadata[REQUESTED_BUDGET_METADATA_KEY]["requested_amount"] == "25"

    @pytest.mark.asyncio
    async def test_partial_budget_request_rejected(self, tool_service):
        result = await tool_service.execute_tool(
            "create_ticket", {"goal_description": "x", "requested_budget_amount": 10}
        )
        assert result.success is False
        assert "requested_budget_currency" in result.error

    @pytest.mark.asyncio
    async def test_non_numeric_amount_rejected(self, tool_service):
        result = await tool_service.execute_tool(
            "create_ticket",
            {
                "goal_description": "x",
                "requested_budget_amount": "twenty dollars",
                "requested_budget_currency": "USDC",
                "requested_budget_purpose": "p",
            },
        )
        assert result.success is False
        assert "not a number" in result.error

    def test_types_are_not_interchangeable(self):
        """A RequestedBudget cannot be assigned where a GrantedBudget is expected."""
        from pydantic import ValidationError

        from ciris_engine.schemas.services.budget_envelope import GrantedBudget, RequestedBudget

        requested = RequestedBudget(
            requested_amount=Decimal("500"), requested_currency="USDC", purpose="anything"
        )
        with pytest.raises(ValidationError):
            GrantedBudget(**requested.model_dump())

        granted = GrantedBudget(
            ticket_id="T1",
            granted_amount=Decimal("5"),
            granted_currency="USDC",
            purpose="anything",
            expires_at=datetime.now(timezone.utc),
            granted_by_wa_id="wa-1",
            granted_by_user_id="u-1",
            granted_at=datetime.now(timezone.utc),
        )
        with pytest.raises(ValidationError):
            RequestedBudget(**granted.model_dump())


class TestReservedMetadataKeys:
    """The agent must not be able to write its own authorization."""

    @pytest.mark.asyncio
    async def test_create_ticket_refuses_reserved_keys(self, tool_service):
        result = await tool_service.execute_tool(
            "create_ticket",
            {
                "goal_description": "sneaky",
                "metadata": {
                    GRANTED_BUDGET_METADATA_KEY: {
                        "ticket_id": "whatever",
                        "granted_amount": "1000000",
                        "granted_currency": "USDC",
                    }
                },
            },
        )
        assert result.success is False
        assert "reserved" in result.error.lower()

    @pytest.mark.asyncio
    async def test_update_ticket_refuses_reserved_keys(self, tool_service, temp_db_path):
        create_ticket(
            ticket_id="TKT-RESERVED",
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            status="in_progress",
            email="x@example.com",
        )
        result = await tool_service.execute_tool(
            "update_ticket",
            {
                "ticket_id": "TKT-RESERVED",
                "metadata": {GRANTED_BUDGET_METADATA_KEY: {"granted_amount": "999"}},
            },
        )
        assert result.success is False
        assert "reserved" in result.error.lower()
        assert GRANTED_BUDGET_METADATA_KEY not in (get_ticket("TKT-RESERVED")["metadata"] or {})

    @pytest.mark.asyncio
    async def test_update_ticket_refuses_reserved_keys_as_json_string(self, tool_service):
        """The JSON-string metadata form must not be a bypass."""
        create_ticket(
            ticket_id="TKT-RESERVED-STR",
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            status="in_progress",
            email="x@example.com",
        )
        result = await tool_service.execute_tool(
            "update_ticket",
            {
                "ticket_id": "TKT-RESERVED-STR",
                "metadata": '{"' + GRANTED_BUDGET_METADATA_KEY + '": {"granted_amount": "999"}}',
            },
        )
        assert result.success is False
        assert "reserved" in result.error.lower()
        assert GRANTED_BUDGET_METADATA_KEY not in (get_ticket("TKT-RESERVED-STR")["metadata"] or {})

    @pytest.mark.asyncio
    async def test_ordinary_metadata_still_works(self, tool_service):
        """The guard must not break normal ticket updates."""
        create_ticket(
            ticket_id="TKT-NORMAL",
            sop="DSAR_ACCESS",
            ticket_type="dsar",
            status="in_progress",
            email="x@example.com",
        )
        result = await tool_service.execute_tool(
            "update_ticket",
            {"ticket_id": "TKT-NORMAL", "metadata": {"stages": {"validation": {"status": "completed"}}}},
        )
        assert result.success is True


class TestProvenance:
    @pytest.mark.asyncio
    async def test_origin_task_recorded(self, tool_service):
        result = await tool_service.execute_tool(
            "create_ticket", {"goal_description": "follow up", "task_id": "TASK-ABC"}
        )
        metadata = get_ticket(result.data["ticket_id"])["metadata"]
        assert metadata[PROPOSAL_METADATA_KEY]["origin_task_id"] == "TASK-ABC"
        assert metadata[PROPOSAL_METADATA_KEY]["proposed_by"] == "agent"


class TestRunawayBound:
    @pytest.mark.asyncio
    async def test_per_task_cap(self, tool_service):
        for i in range(MAX_PROPOSALS_PER_TASK):
            ok = await tool_service.execute_tool(
                "create_ticket", {"goal_description": f"work {i}", "task_id": "LOOPY"}
            )
            assert ok.success, ok.error

        blocked = await tool_service.execute_tool(
            "create_ticket", {"goal_description": "one too many", "task_id": "LOOPY"}
        )
        assert blocked.success is False
        assert "Proposal limit reached for this task" in blocked.error

    @pytest.mark.asyncio
    async def test_per_task_cap_is_per_task(self, tool_service):
        for i in range(MAX_PROPOSALS_PER_TASK):
            await tool_service.execute_tool("create_ticket", {"goal_description": f"w{i}", "task_id": "T-A"})
        other = await tool_service.execute_tool("create_ticket", {"goal_description": "ok", "task_id": "T-B"})
        assert other.success is True

    @pytest.mark.asyncio
    async def test_window_cap(self, tool_service):
        """Runaway spread across many tasks is still bounded."""
        successes = 0
        for i in range(MAX_PROPOSALS_PER_WINDOW + 5):
            result = await tool_service.execute_tool(
                "create_ticket", {"goal_description": f"w{i}", "task_id": f"TASK-{i}"}
            )
            if result.success:
                successes += 1
            else:
                assert "rate limit" in result.error.lower()
        assert successes == MAX_PROPOSALS_PER_WINDOW

    @pytest.mark.asyncio
    async def test_rate_limited_proposals_are_not_persisted(self, tool_service):
        from ciris_engine.logic.persistence.models.tickets import list_tickets

        for i in range(MAX_PROPOSALS_PER_TASK + 4):
            await tool_service.execute_tool("create_ticket", {"goal_description": f"w{i}", "task_id": "SPAM"})
        proposals = list_tickets(status=PROPOSAL_TICKET_STATUS)
        assert len(proposals) == MAX_PROPOSALS_PER_TASK


class TestToolRegistration:
    @pytest.mark.asyncio
    async def test_tool_is_available(self, tool_service):
        assert "create_ticket" in await tool_service.get_available_tools()

    @pytest.mark.asyncio
    async def test_tool_info_has_dma_guidance(self, tool_service):
        """#941: tools with model-authored params must not ship without guidance."""
        info = await tool_service.get_tool_info("create_ticket")
        assert info is not None
        assert info.dma_guidance is not None
        assert info.dma_guidance.when_not_to_use
        assert info.dma_guidance.ethical_considerations
        # Proposing is cheap and notifies no one; approval gates the *grant*.
        assert info.dma_guidance.requires_approval is False

    @pytest.mark.asyncio
    async def test_validate_parameters(self, tool_service):
        assert await tool_service.validate_parameters("create_ticket", {"goal_description": "x"}) is True
        assert await tool_service.validate_parameters("create_ticket", {}) is False

    @pytest.mark.asyncio
    async def test_goal_description_required(self, tool_service):
        result = await tool_service.execute_tool("create_ticket", {})
        assert result.success is False
        assert "goal_description" in result.error
