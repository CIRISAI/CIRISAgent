"""SDK interact(): outlasts the server's deadline, and reports how it ended."""

from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

from ciris_sdk import InteractOutcome, InteractResponse
from ciris_sdk.client import CIRISClient
from ciris_sdk.resources.agent import INTERACT_CLIENT_TIMEOUT_S, AgentResource
from ciris_sdk.transport import Transport

BODY = {"message_id": "m1", "response": "hi", "state": "WORK", "processing_time_ms": 12}


def _resource(transport_timeout: float = 50.0) -> tuple[AgentResource, AsyncMock]:
    transport = MagicMock()
    transport.timeout = transport_timeout
    transport.request = AsyncMock(return_value=dict(BODY))
    return AgentResource(transport), transport.request


@pytest.mark.asyncio
async def test_interact_timeout_exceeds_the_servers_local_deadline():
    resource, request = _resource()
    await resource.interact("hello")
    timeout = request.call_args.kwargs["timeout"]
    # LOCAL interact deadline is 900s; the client must wait longer.
    assert timeout == INTERACT_CLIENT_TIMEOUT_S > 900.0


@pytest.mark.asyncio
async def test_explicit_timeout_wins_and_larger_transport_timeout_is_kept():
    resource, request = _resource()
    await resource.interact("hello", timeout=12.5)
    assert request.call_args.kwargs["timeout"] == 12.5

    resource, request = _resource(transport_timeout=5000.0)
    await resource.interact("hello")
    assert request.call_args.kwargs["timeout"] == 5000.0


@pytest.mark.asyncio
async def test_other_endpoints_keep_the_transport_default():
    resource, request = _resource()
    request.return_value = {
        "message_id": "m1",
        "task_id": "t1",
        "channel_id": "c",
        "submitted_at": "2026-01-01T00:00:00+00:00",
        "accepted": True,
    }
    await resource.submit_message("hello")
    assert "timeout" not in request.call_args.kwargs


@pytest.mark.asyncio
async def test_timeout_reaches_httpx_as_a_per_request_timeout():
    """The kwarg flows through Transport.request into httpx unchanged."""
    transport = Transport("http://test", api_key="k", timeout=50.0, use_auth_store=False)
    captured = {}

    async def fake_request(method, url, **kwargs):
        captured.update(kwargs)
        return httpx.Response(200, json={"data": BODY}, request=httpx.Request(method, url))

    transport._client = MagicMock()
    transport._client.request = fake_request
    await AgentResource(transport).interact("hello")
    assert captured["timeout"] == INTERACT_CLIENT_TIMEOUT_S


@pytest.mark.asyncio
async def test_client_interact_passes_timeout_through():
    client = CIRISClient.__new__(CIRISClient)
    client.agent = MagicMock()
    client.agent.interact = AsyncMock(return_value=InteractResponse(**BODY))
    await client.interact("hello", timeout=33.0)
    assert client.agent.interact.call_args.kwargs["timeout"] == 33.0


def test_response_parses_from_an_old_server_without_the_new_fields():
    r = InteractResponse(**BODY)
    assert r.task_id is None
    assert r.outcome == InteractOutcome.COMPLETE
    assert not r.timed_out


def test_response_reports_timeout_and_task():
    r = InteractResponse(**BODY, task_id="t1", outcome="timeout")
    assert r.timed_out
    assert r.task_id == "t1"


def test_unknown_future_outcome_still_parses():
    r = InteractResponse(**BODY, outcome="something_new")
    assert r.outcome == "something_new"
    assert not r.timed_out
