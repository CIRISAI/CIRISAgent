"""The constitutional-halt latch reader fails closed (CC 4.2.1.1, CIRISAgent#1231).

The node's ``GET /v1/accord/halt-status`` is mocked with an httpx MockTransport.
Nothing here touches :4243.
"""

from datetime import datetime, timedelta, timezone

import httpx
import pytest

from ciris_engine.logic.runtime import node_fold
from ciris_engine.logic.utils import halt_latch
from ciris_engine.schemas.runtime.accord_halt import (
    ACCORD_HALT_EXEMPT_ACTS,
    ACCORD_HALT_REFUSAL,
    AccordHaltExemptAct,
    AccordHaltReading,
)
from ciris_engine.schemas.runtime.enums import HandlerActionType

pytestmark = pytest.mark.real_halt_latch

_HALT = {
    "invocation_id": "inv-4211",
    "received_at": "2026-10-14T12:00:00+00:00",
    "fuse_secs": 86400,
    "lapses_at": "2026-10-15T12:00:00+00:00",
    "confirmed": False,
    "valid_signers": ["holder-a"],
}


@pytest.fixture
def node(monkeypatch):
    """A folded node whose halt-status answer each test sets."""
    answer: dict = {}
    monkeypatch.setattr(node_fold, "fold_status", lambda: {"folded": True, "reachable": True})
    real_client = httpx.AsyncClient

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == halt_latch.HALT_STATUS_URL
        raise_ = answer.get("raise")
        if raise_ is not None:
            raise raise_
        return httpx.Response(answer.get("status", 200), json=answer.get("json"), content=answer.get("content"))

    monkeypatch.setattr(
        halt_latch.httpx,
        "AsyncClient",
        lambda **kw: real_client(transport=httpx.MockTransport(handler), **kw),
    )
    return answer


async def _read():
    halt_latch.invalidate_halt_cache()
    return await halt_latch.read_halt_latch()


@pytest.mark.asyncio
async def test_no_latch_is_not_halted(node):
    node["json"] = {"halted": False, "lapsed": False, "halt": None, "record": None}
    state = await _read()
    assert state.halted is False
    assert state.reading == AccordHaltReading.NOT_HALTED


@pytest.mark.asyncio
async def test_a_standing_halt_is_halted_and_names_its_invocation(node):
    node["json"] = {"halted": True, "lapsed": False, "halt": _HALT}
    state = await _read()
    assert state.halted is True
    assert state.reading == AccordHaltReading.IN_EFFECT
    assert state.invocation_id == "inv-4211"
    assert state.fuse_secs == 86400
    assert state.valid_signers == ["holder-a"]
    assert state.refusal_reason() == f"{ACCORD_HALT_REFUSAL}:inv-4211"
    assert state.fail_closed is False


@pytest.mark.asyncio
async def test_lapsed_from_the_node_means_not_halted(node):
    """The agent honours only the node's `lapsed`; it computes no fuse."""
    halt = {**_HALT, "lapsed_at": "2026-10-15T12:00:00+00:00"}
    halt.pop("lapses_at")
    node["json"] = {"halted": False, "lapsed": True, "halt": halt}
    state = await _read()
    assert state.halted is False
    assert state.reading == AccordHaltReading.LAPSED
    assert state.invocation_id == "inv-4211"


@pytest.mark.asyncio
async def test_the_agent_computes_no_fuse_of_its_own(node):
    """A halt whose fuse is long past on the agent's clock still stands while the node says so."""
    halt = {**_HALT, "received_at": "2000-01-01T00:00:00+00:00", "fuse_secs": 1, "lapses_at": "2000-01-01T00:00:01Z"}
    node["json"] = {"halted": True, "lapsed": False, "halt": halt}
    assert (await _read()).halted is True


@pytest.mark.asyncio
async def test_lapsed_alongside_halted_true_reads_halted(node):
    node["json"] = {"halted": True, "lapsed": True, "halt": _HALT}
    assert (await _read()).halted is True


@pytest.mark.asyncio
async def test_halted_null_means_halted(node):
    node["json"] = {"halted": None, "lapsed": False, "halt": None, "error": "latch present but unreadable: EACCES"}
    state = await _read()
    assert state.halted is True
    assert state.reading == AccordHaltReading.LATCH_UNREADABLE
    assert "EACCES" in (state.read_error or "")
    assert state.fail_closed is True


@pytest.mark.asyncio
async def test_unreachable_means_halted(node):
    node["raise"] = httpx.ConnectError("connection refused")
    state = await _read()
    assert state.halted is True
    assert state.reading == AccordHaltReading.NODE_UNREACHABLE


@pytest.mark.asyncio
async def test_timeout_means_halted(node):
    node["raise"] = httpx.ReadTimeout("no answer")
    state = await _read()
    assert state.halted is True
    assert state.reading == AccordHaltReading.NODE_TIMEOUT


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "answer",
    [
        {"status": 500, "json": {"halted": False}},
        {"status": 200, "content": b"not json"},
        {"status": 200, "json": ["halted", False]},
        {"status": 200, "json": {"lapsed": False}},
        {"status": 200, "json": {"halted": "false"}},
        {"status": 200, "json": {"halted": 0}},
    ],
)
async def test_anything_but_a_literal_false_means_halted(node, answer):
    node.update(answer)
    state = await _read()
    assert state.halted is True
    assert state.reading == AccordHaltReading.NODE_ERROR


@pytest.mark.asyncio
async def test_boot_fails_closed(monkeypatch):
    """Before :4243 answers, the fold is configured but not up: halted."""
    monkeypatch.setattr(node_fold, "fold_status", lambda: {"folded": False, "reachable": False})

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    real_client = httpx.AsyncClient
    monkeypatch.setattr(
        halt_latch.httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(refuse), **kw)
    )
    state = await _read()
    assert state.halted is True
    assert state.reading == AccordHaltReading.NODE_UNREACHABLE


@pytest.mark.asyncio
async def test_no_node_deployment_fails_closed(monkeypatch):
    """CIRIS_NODE_FOLD=false (Discord-only and similar): no latch to read, so halted."""
    monkeypatch.setenv("CIRIS_NODE_FOLD", "false")
    state = await _read()
    assert state.halted is True
    assert state.reading == AccordHaltReading.NO_NODE


@pytest.mark.asyncio
async def test_cache_never_outlives_the_ttl(node, monkeypatch):
    node["json"] = {"halted": False, "lapsed": False}
    assert (await _read()).halted is False
    node["json"] = {"halted": True, "lapsed": False, "halt": _HALT}
    # Within the TTL the cached read stands ...
    assert (await halt_latch.read_halt_latch()).halted is False
    # ... and past it the node is asked again.
    monkeypatch.setattr(halt_latch, "_cached_at", halt_latch._cached_at - halt_latch.HALT_READ_CACHE_TTL_SECONDS)
    assert (await halt_latch.read_halt_latch()).halted is True
    assert halt_latch.HALT_READ_CACHE_TTL_SECONDS <= 2.0


def test_exemption_list_allows_deferral_and_refuses_speak_and_tools():
    assert exempt(HandlerActionType.DEFER) == AccordHaltExemptAct.DEFERRAL_WRITE
    for refused in (
        HandlerActionType.SPEAK,
        HandlerActionType.TOOL,
        HandlerActionType.MEMORIZE,
        HandlerActionType.FORGET,
        HandlerActionType.OBSERVE,
        HandlerActionType.PONDER,
        HandlerActionType.RECALL,
        HandlerActionType.REJECT,
        HandlerActionType.TASK_COMPLETE,
    ):
        assert exempt(refused) is None, refused
    # Every handler action is covered by the check above or is DEFER.
    assert {a for a in HandlerActionType if exempt(a) is not None} == {HandlerActionType.DEFER}


def test_exemption_list_is_frozen_and_names_the_retirement_steps():
    assert isinstance(ACCORD_HALT_EXEMPT_ACTS, frozenset)
    assert ACCORD_HALT_EXEMPT_ACTS == {
        AccordHaltExemptAct.DEFERRAL_WRITE,
        AccordHaltExemptAct.RETIREMENT_HOLD,
        AccordHaltExemptAct.RETIREMENT_ASSEMBLE,
        AccordHaltExemptAct.RETIREMENT_SEAL,
        AccordHaltExemptAct.RETIREMENT_HAND_OVER,
        AccordHaltExemptAct.RETIREMENT_NOTIFY,
    }
    with pytest.raises(TypeError):
        halt_latch._HANDLER_EXEMPT_ACTS[HandlerActionType.SPEAK] = AccordHaltExemptAct.DEFERRAL_WRITE  # type: ignore[index]


def exempt(action: HandlerActionType):
    return halt_latch.exempt_act_for(action)


@pytest.mark.asyncio
async def test_pause_notice_after_a_node_reported_halt_ends(node):
    node["json"] = {"halted": True, "lapsed": False, "halt": _HALT}
    await _read()
    assert halt_latch.accord_pause_notice() is None  # nothing to say while it stands

    node["json"] = {"halted": False, "lapsed": True, "halt": {**_HALT, "lapsed_at": "x"}}
    await _read()
    notice = halt_latch.accord_pause_notice()
    assert notice is not None
    assert "inv-4211" in notice and "lapsed after its fuse" in notice
    assert "No action is requested" in notice
    # Informational only: no H3ERE verb is instructed.
    for verb in ("DEFER", "REJECT", "PONDER", "SPEAK", "defer", "reject", "ponder"):
        assert verb not in notice
    # The window closes.
    later = datetime.now(timezone.utc) + halt_latch.ACCORD_PAUSE_NOTICE_WINDOW + timedelta(seconds=1)
    assert halt_latch.accord_pause_notice(now=later) is None


@pytest.mark.asyncio
async def test_fail_closed_episodes_leave_no_notice(node):
    """The boot window reads halted every boot; it must not tell the agent it was paused."""
    node["raise"] = httpx.ConnectError("booting")
    await _read()
    node.pop("raise")
    node["json"] = {"halted": False, "lapsed": False}
    await _read()
    assert halt_latch.accord_pause_notice() is None
