"""Tests for GET /v1/setup/tool-disclosure (#941).

The route is the wire between the generated disclosure and the first-run wizard.
These tests check that it surfaces the generated report intact -- the disclosure's
correctness itself is guarded by
``tests/ciris_engine/logic/services/tool/test_tool_disclosure.py``.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from ciris_engine.logic.adapters.api.routes.setup.providers import list_tool_disclosure
from ciris_engine.schemas.adapters.tools import (
    AdapterToolDisclosure,
    ToolCapabilityFlag,
    ToolDisclosure,
    ToolDisclosureReport,
    ToolDisclosureSource,
)


@pytest.mark.asyncio
async def test_route_returns_the_generated_report() -> None:
    """The route wraps the generator's output without editing it."""
    response = await list_tool_disclosure(include_discovered=False)
    report = response.data

    assert isinstance(report, ToolDisclosureReport)
    adapter_ids = {g.adapter_id for g in report.adapters}
    # api is the default adapter (main.py defaults to ["api"]), so its grants are
    # what most operators are actually accepting.
    assert "api" in adapter_ids
    assert report.always_on, "the tools no choice controls must reach the wizard"
    assert report.total_tools > 0


@pytest.mark.asyncio
async def test_route_discloses_default_egress_and_undeclinable_secret_access() -> None:
    """The two facts an operator could not otherwise learn from this screen."""
    response = await list_tool_disclosure(include_discovered=False)
    report = response.data

    api = next(g for g in report.adapters if g.adapter_id == "api")
    api_flags = {f for t in api.tools for f in t.capability_flags}
    assert ToolCapabilityFlag.NETWORK_FETCH in api_flags
    assert ToolCapabilityFlag.CUSTOM_HEADERS in api_flags

    always_on_flags = {f for g in report.always_on for t in g.tools for f in t.capability_flags}
    assert ToolCapabilityFlag.SECRET_PLAINTEXT in always_on_flags


@pytest.mark.asyncio
async def test_include_discovered_is_forwarded() -> None:
    """The expensive third-party enumeration is opt-outable but on by default."""
    fake = ToolDisclosureReport(
        adapters=[
            AdapterToolDisclosure(
                adapter_id="api",
                adapter_name="Web API",
                source=ToolDisclosureSource.PROSPECTIVE,
                tools=[ToolDisclosure(name="curl", description="d")],
            )
        ],
        total_tools=1,
    )
    target = "ciris_engine.logic.services.tool.tool_disclosure.build_tool_disclosure"
    with patch(target, new=AsyncMock(return_value=fake)) as builder:
        await list_tool_disclosure(include_discovered=False)
        builder.assert_awaited_once_with(include_discovered=False)

    with patch(target, new=AsyncMock(return_value=fake)) as builder:
        await list_tool_disclosure()
        builder.assert_awaited_once_with(include_discovered=True)


@pytest.mark.asyncio
async def test_generation_failure_surfaces_as_500_not_an_empty_list() -> None:
    """A failed build must not degrade into "grants nothing".

    Returning an empty disclosure on error would be the worst possible outcome:
    a silent, confident, wrong answer at the consent point.
    """
    target = "ciris_engine.logic.services.tool.tool_disclosure.build_tool_disclosure"
    with patch(target, new=AsyncMock(side_effect=RuntimeError("boom"))):
        with pytest.raises(HTTPException) as exc:
            await list_tool_disclosure(include_discovered=False)
    assert exc.value.status_code == 500
