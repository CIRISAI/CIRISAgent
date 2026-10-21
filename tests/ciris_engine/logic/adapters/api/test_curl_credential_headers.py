"""curl must not present model-authored credentials (#941 item 3).

The SSRF guard decides WHERE a request may go. It says nothing about WHAT is
presented on arrival — and `curl`'s headers are model-authored. A model that can
write `Authorization: Bearer <anything it has seen>` to an *allowed* host has a
credential-egress channel no URL check closes: the destination is legitimate,
which is exactly what makes it useful for exfiltration.

Deny by default. Nothing in the tool's purpose — fetch a URL, post a body —
requires authenticating as anyone.
"""

import pytest

from ciris_engine.logic.adapters.api.api_tools import APIToolService


@pytest.fixture
def tools():
    return APIToolService()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "header",
    ["Authorization", "authorization", "AUTHORIZATION", "Proxy-Authorization", "Cookie", "X-Api-Key", "x-auth-token"],
)
async def test_credential_headers_are_refused(tools, header):
    result = await tools._curl({"url": "https://example.com", "headers": {header: "Bearer sk-secret"}})
    assert "error" in result, f"{header} was allowed through"
    assert header.lower() in result["error"].lower()
    # The refusal must not echo the credential it just refused to send.
    assert "sk-secret" not in result["error"]


@pytest.mark.asyncio
async def test_ordinary_headers_are_untouched(tools, monkeypatch):
    # Refusing everything would be safe and useless; the tool still has a job.
    captured = {}

    class _Resp:
        status = 200
        headers = {}

        async def text(self):
            return "ok"

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

    class _Session:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def request(self, method, url, **kw):
            captured.update(kw)
            return _Resp()

    monkeypatch.setattr("ciris_engine.logic.adapters.api.api_tools.aiohttp.ClientSession", lambda *a, **k: _Session())
    result = await tools._curl(
        {"url": "https://example.com", "headers": {"Accept": "application/json", "User-Agent": "ciris"}}
    )
    assert "error" not in result or "credential" not in str(result.get("error", "")).lower()


@pytest.mark.asyncio
async def test_the_url_guard_still_runs_first(tools):
    # Loopback is refused regardless of headers — the two checks are independent
    # and neither substitutes for the other.
    result = await tools._curl({"url": "http://127.0.0.1:8080/admin", "headers": {}})
    assert "error" in result
    assert "ssrf" in result["error"].lower()
