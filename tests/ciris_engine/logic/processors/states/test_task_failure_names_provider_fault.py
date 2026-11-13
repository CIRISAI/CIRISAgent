"""A failed task tells the user the provider's reason when it gave one we can name.

Client five-platform run 43438260138: the Anthropic account was out of credit
(``HTTP 400 Your credit balance is too low``) and every message got "I
encountered an issue processing your request. Please try again." Retrying cannot
fix a billing refusal, a rejected key or an unknown model.
"""

import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from ciris_engine.logic.processors.states.work_processor import _FAULT_NOTICE_KEYS, WorkProcessor
from ciris_engine.logic.services.runtime.llm_service.service import OpenAICompatibleClient
from ciris_engine.logic.utils.localization import get_string
from ciris_engine.schemas.runtime.enums import ServiceType


def _llm(code: str = "", fault_at: float = 0.0, success_at: float = 0.0) -> OpenAICompatibleClient:
    svc = OpenAICompatibleClient.__new__(OpenAICompatibleClient)
    svc.last_fault_code = code
    svc.last_fault_at = fault_at
    svc.last_success_at = success_at
    return svc


def _processor(*services: object) -> tuple[WorkProcessor, AsyncMock]:
    obj = WorkProcessor.__new__(WorkProcessor)
    bus = Mock()
    bus.send_message_sync = AsyncMock(return_value=True)
    obj.services = Mock(communication_bus=bus)
    obj.service_registry = SimpleNamespace(
        _services={ServiceType.LLM: [SimpleNamespace(instance=s) for s in services]}
    )
    return obj, bus.send_message_sync


async def _notify(obj: WorkProcessor) -> None:
    with patch(
        "ciris_engine.logic.utils.halt_latch.refuse_agent_send_under_halt", AsyncMock(return_value=False)
    ), patch("ciris_engine.logic.utils.localization.get_preferred_language", return_value="en"):
        await obj._notify_task_failed(Mock(task_id="t", channel_id="api_u1"), "th")


def test_a_fault_is_live_until_a_call_succeeds():
    now = time.monotonic()
    assert _llm("insufficient_quota", fault_at=now).live_fault_code() == "insufficient_quota"
    assert _llm("insufficient_quota", fault_at=now, success_at=now + 1).live_fault_code() == ""
    assert _llm("", fault_at=now).live_fault_code() == ""


@pytest.mark.asyncio
async def test_out_of_credit_is_named_in_the_notice():
    obj, send = _processor(_llm("insufficient_quota", fault_at=time.monotonic()))
    await _notify(obj)
    content = send.await_args.kwargs["content"]
    assert content == get_string("en", "agent.error_llm_out_of_credit")
    assert "credit" in content and content != get_string("en", "agent.error_generic")


@pytest.mark.asyncio
async def test_a_recovered_provider_is_not_blamed():
    now = time.monotonic()
    obj, send = _processor(_llm("insufficient_quota", fault_at=now, success_at=now + 1))
    await _notify(obj)
    assert send.await_args.kwargs["content"] == get_string("en", "agent.error_generic")


@pytest.mark.asyncio
async def test_an_unnamed_fault_keeps_the_generic_notice():
    obj, send = _processor(_llm("something_new", fault_at=time.monotonic()))
    await _notify(obj)
    assert send.await_args.kwargs["content"] == get_string("en", "agent.error_generic")


@pytest.mark.asyncio
async def test_no_registry_keeps_the_generic_notice():
    obj, send = _processor()
    del obj.service_registry
    await _notify(obj)
    assert send.await_args.kwargs["content"] == get_string("en", "agent.error_generic")


def test_every_named_fault_has_an_english_string():
    for key in _FAULT_NOTICE_KEYS.values():
        value = get_string("en", key)
        assert value and value != key, key
