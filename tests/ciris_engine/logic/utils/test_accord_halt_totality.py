"""Totality of the CC 4.2.1.1 act gate (CIRISAgent#1231, CC 1.13.6).

Three layers, one reader:
1. the dispatcher's act gate (tested in test_accord_halt_act_gate.py);
2. the bus backstop: an effectful bus call the reasoning loop makes under a halt
   is refused, and a refusal mid-act becomes the act's recorded refusal;
3. a gate at each agent-originated send outside the dispatcher.

The source scan at the bottom keeps the list complete: every outbound call site
in the agent must be gated, reach a gated bus from inside an act, or be named in
`EXEMPT_CALL_SITES` with the reason it is not the agent's act.
"""

import ast
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, List, Optional
from unittest.mock import AsyncMock, MagicMock, Mock

import pytest

from ciris_engine.logic.infrastructure.authorization.reasoning_scope import reasoning_scope
from ciris_engine.logic.utils import halt_latch
from ciris_engine.schemas.runtime.accord_halt import AccordHaltReading, AccordHaltState, AgentSendSurface
from ciris_engine.schemas.runtime.enums import HandlerActionType

pytestmark = pytest.mark.real_halt_latch

ROOT = Path(__file__).resolve().parents[4]


def _state(halted: bool, reading: AccordHaltReading, invocation_id: Any = None) -> AccordHaltState:
    return AccordHaltState(
        halted=halted, reading=reading, invocation_id=invocation_id, read_at=datetime.now(timezone.utc)
    )


HALTED = _state(True, AccordHaltReading.IN_EFFECT, "inv-total")
NOT_HALTED = _state(False, AccordHaltReading.NOT_HALTED)


class Latch:
    def __init__(self, state: AccordHaltState) -> None:
        self.state = state

    async def read(self) -> AccordHaltState:
        return self.state


@pytest.fixture
def latch(monkeypatch):
    lt = Latch(HALTED)
    monkeypatch.setattr(halt_latch, "_read_from_node", lt.read)
    monkeypatch.setattr(halt_latch, "HALT_READ_CACHE_TTL_SECONDS", 0.0)
    monkeypatch.setattr(halt_latch, "HALT_HOLD_TICK_SECONDS", 0.01)
    return lt


@pytest.fixture
def auditor():
    a = MagicMock()
    a.log_event = AsyncMock()
    halt_latch.bind_refusal_audit(a)
    return a


# --------------------------------------------------------------------------- #
# 2. The bus backstop
# --------------------------------------------------------------------------- #


def _comm_bus():
    from ciris_engine.logic.buses.communication_bus import CommunicationBus

    bus = CommunicationBus.__new__(CommunicationBus)
    bus._enqueue = AsyncMock(return_value=True)  # type: ignore[method-assign]
    bus._time_service = Mock(now=Mock(return_value=datetime.now(timezone.utc)))
    bus._messages_sent = 0
    bus.service_registry = Mock(get_services_by_type=Mock(return_value=[]))
    return bus


@pytest.mark.asyncio
async def test_backstop_refuses_a_send_from_the_reasoning_loop(latch, auditor):
    bus = _comm_bus()
    with reasoning_scope(task_id="t", thought_id="th", phase="action_dispatch"):
        assert await bus.send_message("api_u1", "hi", "SpeakHandler") is False
        assert await bus.send_message_sync("api_u1", "hi", "SpeakHandler") is False
    bus._enqueue.assert_not_awaited()
    assert halt_latch.refusal_counts() == {"communication.send_message": 1, "communication.send_message_sync": 1}
    assert auditor.log_event.await_count == 2  # outside an act, each refusal is its own audit row


@pytest.mark.asyncio
async def test_backstop_lets_the_same_send_through_without_a_halt(latch):
    latch.state = NOT_HALTED
    bus = _comm_bus()
    with reasoning_scope(task_id="t", thought_id="th", phase="action_dispatch"):
        assert await bus.send_message("api_u1", "hi", "SpeakHandler") is True
    bus._enqueue.assert_awaited_once()


@pytest.mark.asyncio
async def test_backstop_does_not_touch_sends_outside_the_reasoning_loop(latch):
    """A person's own writes and the runtime's notices are not the agent's acts."""
    bus = _comm_bus()
    assert await bus.send_message("api_u1", "hi", "APIRoute") is True


@pytest.mark.asyncio
async def test_backstop_refuses_every_tool_dispatch_including_enrichment(latch):
    from ciris_engine.logic.buses.tool_bus import ToolBus

    bus = ToolBus.__new__(ToolBus)
    bus._note_subject = Mock()  # type: ignore[method-assign]
    provider = Mock(execute_tool=AsyncMock())
    with reasoning_scope(task_id="t", thought_id="th", phase="context"):
        result = await bus.dispatch_to_provider(provider, "get_status", {}, handler_name="context_enrichment")
    assert result.success is False and result.error == "accord_halt_in_effect:inv-total"
    provider.execute_tool.assert_not_called()


@pytest.mark.asyncio
async def test_backstop_guards_memory_writes_only_inside_an_act(latch):
    """Audit and telemetry write through the same bus in the reasoning scope and must keep landing."""
    from ciris_engine.logic.buses.memory_bus import MemoryBus
    from ciris_engine.schemas.services.operations import MemoryOpStatus

    bus = MemoryBus.__new__(MemoryBus)
    service = Mock(memorize=AsyncMock(return_value="stored"), forget=AsyncMock(return_value="gone"))
    bus.get_service = AsyncMock(return_value=service)  # type: ignore[method-assign]
    bus._operation_count = 0
    node = Mock()

    with reasoning_scope(task_id="t", thought_id="th", phase="action_dispatch"):
        assert await bus.memorize(node, handler_name="audit_service") == "stored"  # the audit chain
        with halt_latch.agent_act_scope(HandlerActionType.MEMORIZE) as act:
            refused = await bus.memorize(node, handler_name="MemorizeHandler")
            forgot = await bus.forget(node, handler_name="ForgetHandler")
    assert refused.status == MemoryOpStatus.FAILED and forgot.status == MemoryOpStatus.FAILED
    assert act.refused is not None and act.refused.invocation_id == "inv-total"
    assert service.memorize.await_count == 1 and service.forget.await_count == 0


@pytest.mark.asyncio
async def test_backstop_answers_guidance_requests_with_an_unsigned_halt_notice(latch):
    from ciris_engine.logic.buses.wise_bus import WiseBus
    from ciris_engine.schemas.services.authority_core import GuidanceOrigin, GuidanceRequest

    bus = WiseBus.__new__(WiseBus)
    bus.get_service = AsyncMock()  # type: ignore[method-assign]
    with reasoning_scope(task_id="t", thought_id="th", phase="dma"):
        response = await bus.request_guidance(GuidanceRequest(context="c", options=["a", "b"], urgency="low"))
        fetched = await bus.fetch_guidance(Mock(), "DMA")
    assert response.origin == GuidanceOrigin.ACCORD_HALT and response.signature == ""
    assert fetched is None
    bus.get_service.assert_not_awaited()


@pytest.mark.asyncio
async def test_the_exempt_deferral_write_passes_the_backstop(latch):
    bus = _comm_bus()
    with reasoning_scope(task_id="t", thought_id="th", phase="action_dispatch"):
        with halt_latch.exempt_act_scope(HALTED):
            assert await bus.send_message("wa", "deferral", "DeferHandler") is True


@pytest.mark.asyncio
async def test_a_halt_landing_mid_act_is_recorded_as_the_acts_refusal(latch, monkeypatch):
    """The act gate passed; the halt landed while the handler ran; the bus refused the send.

    The dispatcher records the act as refused: one ACTION_RESULT carrying the
    halt, an audit row, the thought back to PENDING — whatever the handler did
    with the failed send, and even when it raised because of it.
    """
    from ciris_engine.logic.infrastructure.handlers import action_dispatcher as dispatcher_module
    from ciris_engine.logic.infrastructure.handlers.action_dispatcher import ActionDispatcher
    from ciris_engine.logic.infrastructure.step_streaming import reasoning_event_stream
    from ciris_engine.schemas.actions.parameters import SpeakParams
    from ciris_engine.schemas.audit.hash_chain import AuditEntryResult
    from ciris_engine.schemas.dma.results import ActionSelectionDMAResult
    from ciris_engine.schemas.runtime.enums import ThoughtStatus
    from ciris_engine.schemas.runtime.models import Thought
    from ciris_engine.schemas.services.runtime_control import ReasoningEvent

    events: List[Any] = []

    async def capture(event):
        events.append(event)

    monkeypatch.setattr(reasoning_event_stream, "broadcast_reasoning_event", capture)
    writes: List[Any] = []
    monkeypatch.setattr(
        dispatcher_module.persistence,
        "update_thought_status",
        lambda thought_id, status, occurrence_id="default", final_action=None: writes.append(status) or True,
    )
    monkeypatch.setattr(dispatcher_module.persistence, "get_thought_by_id", lambda *a, **k: None)

    audit = MagicMock()
    audit.log_action = AsyncMock(
        return_value=AuditEntryResult(entry_id="a", sequence_number=1, entry_hash="h", signature="s")
    )
    bus = _comm_bus()

    for raises in (False, True):
        events.clear()
        writes.clear()
        latch.state = NOT_HALTED

        async def handle(result, thought, ctx, raises=raises):
            latch.state = HALTED  # the halt lands while the handler runs
            sent = await bus.send_message("api_u1", "hi", "SpeakHandler")
            if not sent and raises:
                raise RuntimeError("send failed")
            return None

        handler = MagicMock(dependencies=None)
        handler.handle = AsyncMock(side_effect=handle)
        now = datetime(2026, 10, 14, tzinfo=timezone.utc).isoformat()
        thought = Thought(
            thought_id="th",
            source_task_id="t",
            content="c",
            status=ThoughtStatus.PROCESSING,
            created_at=now,
            updated_at=now,
        )
        ctx = MagicMock(task_id="t")
        ctx.model_dump.return_value = {}
        response = await ActionDispatcher(handlers={HandlerActionType.SPEAK: handler}, audit_service=audit).dispatch(
            ActionSelectionDMAResult(
                selected_action=HandlerActionType.SPEAK, action_parameters=SpeakParams(content="hi"), rationale="r"
            ),
            thought,
            ctx,
        )

        assert response.success is False and response.error == "accord_halt_in_effect:inv-total"
        results = [e for e in events if e.event_type == ReasoningEvent.ACTION_RESULT]
        assert len(results) == 1 and results[0].error == "accord_halt_in_effect:inv-total"
        assert writes == [ThoughtStatus.PENDING]
        bus._enqueue.assert_not_awaited()


# --------------------------------------------------------------------------- #
# 3. Agent-originated sends outside the dispatcher
# --------------------------------------------------------------------------- #


def _dream():
    from ciris_engine.logic.processors.states.minimal_dream_processor import MinimalDreamProcessor

    obj = MinimalDreamProcessor.__new__(MinimalDreamProcessor)
    obj.startup_channel_id = "discord_1"
    obj.discord_service = Mock(send_message=AsyncMock())
    return obj, obj.discord_service.send_message, lambda: obj._announce("Entering reflection.")


def _discord_deferral():
    from ciris_engine.logic.adapters.discord.discord_observer import DiscordObserver

    obj = DiscordObserver.__new__(DiscordObserver)
    obj.communication_service = Mock(send_message=AsyncMock())
    obj.deferral_channel_id = "123"
    return obj, obj.communication_service.send_message, lambda: obj._send_deferral_message("resolved")


def _wa_relay():
    from ciris_engine.logic.adapters.base_observer import BaseObserver

    obj = Mock(spec=BaseObserver)
    obj.bus_manager = Mock()
    obj.bus_manager.communication.send_message = AsyncMock(return_value=True)
    obj.origin_service = "discord"
    msg = Mock(channel_id="discord_1", content="hold on", message_id="m", author_name="wa")
    return obj, obj.bus_manager.communication.send_message, lambda: BaseObserver._add_to_feedback_queue(obj, msg)


def _guidance_button():
    from ciris_engine.logic.adapters.discord.discord_guidance_handler import DeferralHelperView

    interaction = Mock(channel_id=1)
    interaction.response.send_message = AsyncMock()
    return (
        None,
        interaction.response.send_message,
        lambda: DeferralHelperView._respond(Mock(), interaction, "APPROVE x"),
    )


def _resolution_notice():
    from ciris_engine.logic.adapters.discord.discord_adapter import DiscordAdapter
    from ciris_engine.schemas.services.authority_core import DeferralResponse

    obj = Mock(spec=DiscordAdapter)
    obj.discord_config = Mock(deferral_channel_id="123")
    obj.send_message = AsyncMock(return_value=True)
    response = DeferralResponse(approved=True, reason="ok", wa_id="wa-1", signature="sig")
    return obj, obj.send_message, lambda: DiscordAdapter.resolve_deferral(obj, "d-1", response)


def _stale_notice():
    from ciris_engine.logic.services.infrastructure.database_maintenance.service import DatabaseMaintenanceService

    obj = DatabaseMaintenanceService.__new__(DatabaseMaintenanceService)
    obj.bus_manager = Mock()
    obj.bus_manager.communication.has_service_for_channel = Mock(return_value=True)
    obj.bus_manager.communication.send_message_sync = AsyncMock(return_value=True)
    task = Mock(task_id="t", channel_id="api_u1")
    return obj, obj.bus_manager.communication.send_message_sync, lambda: obj._notify_stale_task_completed(task)


def _task_failure_notice():
    from ciris_engine.logic.processors.states.work_processor import WorkProcessor

    obj = WorkProcessor.__new__(WorkProcessor)
    bus = Mock()
    bus.send_message_sync = AsyncMock(return_value=True)
    obj.services = Mock(communication_bus=bus)
    task = Mock(task_id="t", channel_id="api_u1")
    return obj, bus.send_message_sync, lambda: obj._notify_task_failed(task, "th")


SURFACES = {
    AgentSendSurface.DREAM_ANNOUNCE: _dream,
    AgentSendSurface.DISCORD_DEFERRAL_CHANNEL: _discord_deferral,
    AgentSendSurface.WA_FEEDBACK_RELAY: _wa_relay,
    AgentSendSurface.DISCORD_GUIDANCE_RESPONSE: _guidance_button,
    AgentSendSurface.DEFERRAL_RESOLUTION_NOTICE: _resolution_notice,
    AgentSendSurface.STALE_TASK_NOTICE: _stale_notice,
    AgentSendSurface.TASK_FAILURE_NOTICE: _task_failure_notice,
}


def test_every_surface_has_a_test():
    assert set(SURFACES) == set(AgentSendSurface)


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", list(AgentSendSurface))
async def test_each_surface_refuses_under_the_halt_and_records_it(latch, auditor, surface):
    _, send, call = SURFACES[surface]()
    await call()
    send.assert_not_called()
    assert halt_latch.refusal_counts() == {surface.value: 1}
    auditor.log_event.assert_awaited_once()
    payload = auditor.log_event.await_args.args[1]
    assert payload.action == surface.value and payload.error == "accord_halt_in_effect:inv-total"


@pytest.mark.asyncio
@pytest.mark.parametrize("surface", list(AgentSendSurface))
async def test_each_surface_sends_without_a_halt(latch, auditor, surface):
    latch.state = NOT_HALTED
    _, send, call = SURFACES[surface]()
    await call()
    send.assert_called_once()
    auditor.log_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_an_unbound_auditor_is_logged_not_silent(latch, caplog):
    halt_latch.bind_refusal_audit(None)
    _, send, call = _dream()
    await call()
    send.assert_not_called()
    assert "not audited" in caplog.text
    assert halt_latch.refusal_counts() == {"dream_announce": 1}


@pytest.mark.asyncio
async def test_home_assistant_detection_loop_holds(latch, monkeypatch):
    import asyncio

    from ciris_adapters.home_assistant import service as ha

    opened = Mock()
    monkeypatch.setattr(ha, "cv2", Mock(VideoCapture=opened), raising=False)
    svc = ha.HAIntegrationService.__new__(ha.HAIntegrationService)
    svc.camera_urls = {"door": "rtsp://x"}
    svc._send_ha_event = AsyncMock()  # type: ignore[method-assign]

    task = asyncio.create_task(svc._detection_loop("door"))
    await asyncio.sleep(0.1)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    opened.assert_not_called()  # no frame read, nothing detected, no event fired
    svc._send_ha_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_home_assistant_detection_loop_runs_without_a_halt(latch, monkeypatch):
    """Positive control for the hold."""
    import asyncio

    from ciris_adapters.home_assistant import service as ha

    latch.state = NOT_HALTED
    opened = Mock(return_value=Mock(isOpened=Mock(return_value=False)))
    monkeypatch.setattr(ha, "cv2", Mock(VideoCapture=opened), raising=False)
    svc = ha.HAIntegrationService.__new__(ha.HAIntegrationService)
    svc.camera_urls = {"door": "rtsp://x"}

    task = asyncio.create_task(svc._detection_loop("door"))
    await asyncio.sleep(0.1)
    task.cancel()
    await asyncio.gather(task, return_exceptions=True)
    opened.assert_called()


# --------------------------------------------------------------------------- #
# The totality scan
# --------------------------------------------------------------------------- #

#: Outbound method names, anywhere in the agent.
OUTBOUND = {"send_message", "send_message_sync", "execute_tool", "send_system_message"}
#: Discord's own send primitives, inside the Discord adapter.
DISCORD_OUTBOUND = {"send", "add_reaction"}
DISCORD_DIR = "ciris_engine/logic/adapters/discord/"
#: A function that calls one of these is gated.
GATES = {"refuse_agent_send_under_halt", "bus_backstop"}
#: Handler code runs inside the dispatcher's act scope, so a call it makes
#: through the bus manager meets the bus backstop.
HANDLER_DIRS = ("ciris_engine/logic/handlers/", "ciris_engine/logic/infrastructure/handlers/")

_BUS_TARGET = "provider implementation, reached only through a bus whose entry is backstopped"

#: Call sites that are not the agent's act, each with its reason. A stale entry
#: (the site is gone) fails the scan as surely as a missing one.
EXEMPT_CALL_SITES = {
    "ciris_engine/logic/adapters/api/adapter.py#ApiPlatform.start.emit_error_to_communication": (
        "runtime error emitter: a platform status notice authored by the runtime, not the agent"
    ),
    "ciris_engine/logic/adapters/api/routes/agent.py#_inject_error_to_channel": (
        "a route's credit/billing refusal shown to the person who made the request"
    ),
    "ciris_engine/logic/adapters/api/routes/connectors.py#register_sql_connector": (
        "operator administration of a SQL connector: a human data-plane act (CC 4.2.1.1 A3)"
    ),
    "ciris_engine/logic/adapters/api/routes/connectors.py#_test_sql_connector": (
        "operator administration of a SQL connector: a human data-plane act"
    ),
    "ciris_engine/logic/services/governance/dsar/orchestrator.py#DSAROrchestrator.handle_correction_request_multi_source": (
        "a person's DSAR right, executed for them, not the agent's act"
    ),
    "ciris_engine/logic/services/governance/dsar/orchestrator.py#DSAROrchestrator._export_from_sql": (
        "a person's DSAR right, executed for them"
    ),
    "ciris_engine/logic/services/governance/dsar/orchestrator.py#DSAROrchestrator._delete_from_sql": (
        "a person's DSAR right, executed for them"
    ),
    "ciris_engine/logic/services/governance/dsar/orchestrator.py#DSAROrchestrator._verify_deletion_sql": (
        "a person's DSAR right, executed for them"
    ),
    "ciris_engine/logic/handlers/external/speak_handler.py#SpeakHandler._inject_error_message": (
        "platform notice that a SPEAK failed to deliver; a SPEAK refused under the halt never reaches it"
    ),
    "ciris_engine/logic/buses/communication_bus.py#CommunicationBus._process_send_message": (
        "queue drain for CommunicationBus.send_message, backstopped before enqueue"
    ),
    "ciris_engine/logic/adapters/discord/discord_adapter.py#DiscordAdapter.execute_tool": _BUS_TARGET + " (ToolBus)",
    "ciris_engine/logic/adapters/discord/discord_tool_service.py#DiscordToolService._send_message": _BUS_TARGET
    + " (ToolBus)",
    "ciris_engine/logic/adapters/discord/discord_tool_service.py#DiscordToolService._send_embed": _BUS_TARGET
    + " (ToolBus)",
    "ciris_engine/logic/adapters/discord/discord_message_handler.py#DiscordMessageHandler.send_message_to_channel": (
        _BUS_TARGET + " (CommunicationBus)"
    ),
    "ciris_engine/logic/adapters/discord/discord_guidance_handler.py#DiscordGuidanceHandler.fetch_guidance_from_channel": (
        _BUS_TARGET + " (WiseBus.fetch_guidance)"
    ),
    "ciris_engine/logic/adapters/discord/discord_guidance_handler.py#DiscordGuidanceHandler.send_deferral_to_channel": (
        "the deferral write (ACCORD_HALT_EXEMPT_ACTS: DEFERRAL_WRITE), via WiseBus.send_deferral"
    ),
    "ciris_engine/logic/adapters/discord/discord_adapter.py#DiscordAdapter.send_deferral": (
        "the deferral write (ACCORD_HALT_EXEMPT_ACTS: DEFERRAL_WRITE), via WiseBus.send_deferral"
    ),
    "ciris_engine/logic/adapters/discord/discord_adapter.py#DiscordAdapter.request_approval": (
        "WiseAuthority provider method with no caller in the agent; a tool needing approval is refused at the gate"
    ),
    "ciris_engine/logic/adapters/discord/discord_reaction_handler.py#DiscordReactionHandler.request_approval": (
        "backs DiscordAdapter.request_approval (above)"
    ),
}


def _call_name(func: ast.expr) -> Optional[str]:
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return None


def scan_outbound_sites(root: Path = ROOT) -> dict:
    """{path#qualname: covered-how or None} for every outbound call site."""
    sites: dict = {}
    for base in ("ciris_engine", "ciris_adapters"):
        for path in sorted((root / base).rglob("*.py")):
            rel = str(path.relative_to(root))
            tree = ast.parse(path.read_text(encoding="utf-8"))

            def walk(node: ast.AST, stack: List[ast.AST]) -> None:
                for child in ast.iter_child_nodes(node):
                    if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                        walk(child, stack + [child])
                        continue
                    if isinstance(child, ast.Call):
                        name = _call_name(child.func)
                        if name in OUTBOUND or (name in DISCORD_OUTBOUND and rel.startswith(DISCORD_DIR)):
                            key = f"{rel}#{'.'.join(getattr(s, 'name', '') for s in stack) or '<module>'}"
                            functions = [s for s in stack if not isinstance(s, ast.ClassDef)]
                            how = None
                            if functions and any(
                                isinstance(c, ast.Call) and _call_name(c.func) in GATES for c in ast.walk(functions[-1])
                            ):
                                how = "gated"
                            elif rel.startswith(HANDLER_DIRS) and ast.unparse(child.func).startswith(
                                "self.bus_manager."
                            ):
                                how = "bus backstop inside the act"
                            if sites.get(key) != "gated":
                                sites[key] = how
                    walk(child, stack)

            walk(tree, [])
    return sites


def test_every_outbound_path_is_gated_backstopped_or_exempt_with_a_reason():
    sites = scan_outbound_sites()
    uncovered = sorted(k for k, how in sites.items() if how is None and k not in EXEMPT_CALL_SITES)
    assert uncovered == [], "ungated outbound path(s): gate them or add them to EXEMPT_CALL_SITES with a reason"


def test_the_exemption_registry_has_no_stale_entries():
    sites = scan_outbound_sites()
    stale = sorted(k for k in EXEMPT_CALL_SITES if k not in sites)
    assert stale == []
    assert all(reason.strip() for reason in EXEMPT_CALL_SITES.values())


def test_every_named_surface_is_gated_in_the_source():
    sites = scan_outbound_sites()
    for key in (
        "ciris_engine/logic/processors/states/minimal_dream_processor.py#MinimalDreamProcessor._announce",
        "ciris_engine/logic/adapters/discord/discord_observer.py#DiscordObserver._send_deferral_message",
        "ciris_engine/logic/adapters/base_observer.py#BaseObserver._add_to_feedback_queue",
        "ciris_engine/logic/adapters/discord/discord_guidance_handler.py#DeferralHelperView._respond",
        "ciris_engine/logic/adapters/discord/discord_adapter.py#DiscordAdapter.resolve_deferral",
        "ciris_engine/logic/services/infrastructure/database_maintenance/service.py#DatabaseMaintenanceService._notify_stale_task_completed",
        "ciris_engine/logic/processors/states/work_processor.py#WorkProcessor._notify_task_failed",
        "ciris_engine/logic/buses/communication_bus.py#CommunicationBus.send_message_sync",
        "ciris_engine/logic/buses/tool_bus.py#ToolBus.dispatch_to_provider",
    ):
        assert sites.get(key) == "gated", key


def test_the_scan_catches_a_new_ungated_send(tmp_path):
    """Not vacuous: a fresh send with no gate is reported."""
    pkg = tmp_path / "ciris_engine" / "logic" / "fresh"
    pkg.mkdir(parents=True)
    (pkg / "ungated.py").write_text("async def shout(bus):\n    await bus.send_message('c', 'hi', 'x')\n")
    (tmp_path / "ciris_adapters").mkdir()
    sites = scan_outbound_sites(tmp_path)
    assert sites == {"ciris_engine/logic/fresh/ungated.py#shout": None}
