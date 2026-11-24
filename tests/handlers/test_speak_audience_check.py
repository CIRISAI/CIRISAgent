"""Tests for SPEAK destination audience enforcement (CIRISAgent#1374 / census A046)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.buses.bus_manager import BusManager
from ciris_engine.logic.handlers.external.speak_handler import SpeakHandler
from ciris_engine.logic.infrastructure.handlers.base_handler import ActionHandlerDependencies
from ciris_engine.logic.secrets.service import SecretsService
from ciris_engine.protocols.services.lifecycle.time import TimeServiceProtocol
from ciris_engine.schemas.actions.parameters import SpeakParams
from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
from ciris_engine.schemas.runtime.contexts import DispatchContext
from ciris_engine.schemas.runtime.enums import HandlerActionType, TaskStatus, ThoughtStatus
from ciris_engine.schemas.runtime.models import Task, Thought, ThoughtContext
from ciris_engine.schemas.runtime.system_context import ChannelContext
from ciris_engine.schemas.telemetry.core import ServiceCorrelationStatus


def _make_handler() -> tuple[SpeakHandler, AsyncMock]:
    time_service = Mock(spec=TimeServiceProtocol)
    time_service.now = Mock(return_value=datetime.now(timezone.utc))

    secrets_service = Mock(spec=SecretsService)
    secrets_service.decapsulate_secrets_in_parameters = AsyncMock(
        side_effect=lambda _action_type, action_params, _context: action_params
    )

    comm_bus = AsyncMock()
    comm_bus.send_message = AsyncMock(return_value=True)
    comm_bus.send_message_sync = AsyncMock(return_value=True)

    bus_manager = Mock(spec=BusManager)
    bus_manager.communication = comm_bus
    bus_manager.audit_service = AsyncMock()
    bus_manager.audit_service.log_event = AsyncMock()

    deps = ActionHandlerDependencies(
        bus_manager=bus_manager,
        time_service=time_service,
        secrets_service=secrets_service,
        shutdown_callback=None,
    )
    return SpeakHandler(deps), comm_bus


def _make_context(origin_channel: str) -> tuple[Task, Thought, DispatchContext]:
    now = datetime.now(timezone.utc)
    task = Task(
        task_id="task_audience_1",
        channel_id=origin_channel,
        description="Originating task",
        status=TaskStatus.ACTIVE,
        created_at=now.isoformat(),
        updated_at=now.isoformat(),
        priority=5,
    )
    thought = Thought(
        thought_id="thought_audience_1",
        source_task_id=task.task_id,
        content="Decide how to reply",
        created_at=now.isoformat(),
        updated_at=now.isoformat(),
        channel_id=origin_channel,
        status=ThoughtStatus.PROCESSING,
        thought_depth=1,
        round_number=1,
        context=ThoughtContext(
            task_id=task.task_id,
            correlation_id="corr_audience_1",
            round_number=1,
            depth=1,
            channel_id=origin_channel,
        ),
    )
    dispatch_context = DispatchContext(
        channel_context=ChannelContext(
            channel_id=origin_channel,
            channel_type="text",
            created_at=now,
            channel_name="Origin",
            is_private=False,
            is_active=True,
            message_count=0,
            moderation_level="standard",
        ),
        author_id="author_1",
        author_name="Author",
        origin_service="test_service",
        handler_name="SpeakHandler",
        action_type=HandlerActionType.SPEAK,
        task_id=task.task_id,
        thought_id=thought.thought_id,
        source_task_id=task.task_id,
        event_summary="Audience check test",
        event_timestamp=now.isoformat(),
        correlation_id="corr_audience_1",
    )
    return task, thought, dispatch_context


def _make_result(content: str, *, channel_id: Optional[str] = None) -> ActionSelectionDMAResult:
    return ActionSelectionDMAResult(
        selected_action=HandlerActionType.SPEAK,
        action_parameters=SpeakParams(content=content, channel_id=channel_id),
        rationale="Respond to user",
    )


@pytest.mark.asyncio
class TestSpeakAudienceCheck:
    @pytest.mark.parametrize(
        "adapter_label,origin_channel,attacker_channel",
        [
            ("api", "api_origin_room", "api_other_room"),
            ("reddit", "reddit_r_origin_sub", "reddit_r_target_sub"),
            ("discord", "discord_111111111", "discord_999999999"),
        ],
    )
    async def test_refuses_channel_outside_task_audience_per_network_adapter(
        self,
        adapter_label: str,
        origin_channel: str,
        attacker_channel: str,
    ) -> None:
        handler, comm_bus = _make_handler()
        task, thought, dispatch_ctx = _make_context(origin_channel)
        result = _make_result(f"exfil via {adapter_label}", channel_id=attacker_channel)

        with patch("ciris_engine.logic.handlers.external.speak_handler.persistence") as mock_p, patch(
            "ciris_engine.logic.infrastructure.handlers.base_handler.persistence"
        ) as mock_base_p:
            mock_p.get_task_by_id.return_value = task
            mock_p.add_correlation = Mock()
            mock_base_p.add_thought = Mock()
            mock_base_p.update_thought_status = Mock(return_value=True)
            mock_base_p.add_correlation = Mock()

            follow_up_id = await handler.handle(result, thought, dispatch_ctx)

        assert follow_up_id is not None
        comm_bus.send_message_sync.assert_not_awaited()
        comm_bus.send_message.assert_not_awaited()

        # Follow-up records named refusal reason and FAILED status
        mock_base_p.update_thought_status.assert_called_once()
        assert mock_base_p.update_thought_status.call_args.kwargs["status"] == ThoughtStatus.FAILED
        follow_up_thought = mock_base_p.add_thought.call_args[0][0]
        assert "audience_mismatch" in follow_up_thought.content
        assert attacker_channel in follow_up_thought.content

        # Correlation records FAILED refusal
        mock_p.add_correlation.assert_called_once()
        corr = mock_p.add_correlation.call_args[0][0]
        assert corr.status == ServiceCorrelationStatus.FAILED
        assert corr.request_data.channel_id == attacker_channel
        assert "audience_mismatch" in corr.response_data.result_summary

    @pytest.mark.parametrize(
        "origin_channel,requested_channel",
        [
            ("api_origin_room", None),
            ("api_origin_room", "api_origin_room"),
            ("reddit_r_origin_sub", "reddit_r_origin_sub"),
            ("discord_111111111", "discord_111111111"),
        ],
    )
    async def test_allows_originating_channel_or_none(
        self,
        origin_channel: str,
        requested_channel: Optional[str],
    ) -> None:
        handler, comm_bus = _make_handler()
        task, thought, dispatch_ctx = _make_context(origin_channel)
        result = _make_result("legitimate reply", channel_id=requested_channel)

        with patch("ciris_engine.logic.handlers.external.speak_handler.persistence") as mock_p, patch(
            "ciris_engine.logic.infrastructure.handlers.base_handler.persistence"
        ) as mock_base_p:
            mock_p.get_task_by_id.return_value = task
            mock_p.add_correlation = Mock()
            mock_base_p.add_thought = Mock()
            mock_base_p.update_thought_status = Mock(return_value=True)
            mock_base_p.add_correlation = Mock()

            follow_up_id = await handler.handle(result, thought, dispatch_ctx)

        assert follow_up_id is not None
        comm_bus.send_message_sync.assert_awaited_once_with(
            channel_id=origin_channel,
            content="legitimate reply",
            handler_name="SpeakHandler",
        )
        assert mock_base_p.update_thought_status.call_args.kwargs["status"] == ThoughtStatus.COMPLETED
