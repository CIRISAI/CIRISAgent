"""A timeout against US-primary must fall back to EU (CIRISAgent#1079).

Reported from Scout: the message failed with a ReadTimeout and the EU region was
never contacted, though it exists precisely for this.

`_try_single_request` caught `httpx.ConnectTimeout` only. `httpx.ReadTimeout` is
not a subclass of it — they are siblings under `httpx.TimeoutException` — so a
read timeout fell into the generic `RequestError` branch, which returned "FATAL",
and FATAL returns from the region loop before EU-fallback is ever tried.

The distinction the code has to preserve: RETRY means "this region did not
answer"; FATAL means "no region will". A timeout is always the former.
"""

import asyncio

import httpx
import pytest

from ciris_engine.logic.services.infrastructure.resource_monitor.ciris_billing_provider import (
    CIRISBillingProvider,
)


@pytest.fixture
def billing_provider():
    p = CIRISBillingProvider(api_key="test_key", transport=httpx.MockTransport(lambda r: None))
    # _try_single_request reads self._client.headers; the provider is normally
    # started before any request. Only the headers are needed here.
    p._client = httpx.AsyncClient(headers={"authorization": "Bearer test_key"})
    return p


def _statuses(provider, exc):
    """Run _try_single_request against an exception and return its verdict."""

    class _Boom(httpx.AsyncBaseTransport):
        async def handle_async_request(self, request):  # noqa: D401
            raise exc

    provider._transport = _Boom()
    return asyncio.run(
        provider._try_single_request("http://billing.invalid", "US-primary", "/p", {}, "cache")
    )


@pytest.mark.parametrize(
    "exc",
    [
        httpx.ReadTimeout("timed out"),
        httpx.WriteTimeout("timed out"),
        httpx.PoolTimeout("timed out"),
        httpx.ConnectTimeout("timed out"),
        asyncio.TimeoutError(),
    ],
    ids=["read", "write", "pool", "connect", "asyncio"],
)
def test_every_timeout_retries_into_the_next_region(billing_provider, exc):
    _resp, status, _category, _detail = _statuses(billing_provider, exc)
    assert status == "RETRY", (
        f"{type(exc).__name__} returned {status!r}; FATAL returns from the region loop "
        "before EU-fallback is tried, which is how Scout timed out without ever "
        "contacting the region that exists for exactly this"
    )


def test_a_transport_error_is_not_treated_as_a_global_outage(billing_provider):
    # Different hosts on different networks: one being unreachable says nothing
    # about the other. FATAL here made a single-region failure look total.
    _resp, status, category, _detail = _statuses(billing_provider, httpx.ReadError("connection reset"))
    assert status == "RETRY"
    assert category == "NETWORK_ERROR"


def test_read_timeout_is_not_a_connect_timeout(billing_provider):
    # The assumption the original code rested on, stated so it cannot rot back.
    assert issubclass(httpx.ReadTimeout, httpx.TimeoutException)
    assert not issubclass(httpx.ReadTimeout, httpx.ConnectTimeout)
