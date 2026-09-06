"""Setup-complete records "Run without AI" so every later boot is ciris-server and the client (CIRISAgent#1149)."""

from __future__ import annotations

import asyncio
import io
from typing import Any, List
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from ciris_engine.logic.adapters.api.routes.setup import complete
from ciris_engine.logic.adapters.api.routes.setup.models import SetupCompleteRequest

_BASE = {
    "template_id": "default",
    "enabled_adapters": ["api"],
    "adapter_config": {},
    "admin_username": "owner",
    "admin_password": "Password-12345",
    "system_admin_password": "Admin-67890",
}


def test_provider_is_required_unless_run_without_ai() -> None:
    with pytest.raises(ValidationError, match="llm_provider is required unless run_without_ai"):
        SetupCompleteRequest(**_BASE)
    req = SetupCompleteRequest(**_BASE, run_without_ai=True)
    assert req.llm_provider is None and req.llm_api_key is None and req.run_without_ai
    assert not complete._has_usable_llm_provider(req)


def test_a_provider_still_validates_without_a_key() -> None:
    req = SetupCompleteRequest(**_BASE, llm_provider="openai", llm_api_key="")
    assert req.llm_provider == "openai" and not req.run_without_ai


def test_run_without_ai_writes_the_flag_and_the_node_key_alias() -> None:
    req = SetupCompleteRequest(**_BASE, run_without_ai=True)
    out = io.StringIO()
    with patch("ciris_engine.logic.runtime.node_fold._resolve_key_id", return_value="ciris-agent-bootstrap"):
        complete._write_llm_availability_config(out, req)
    text = out.getvalue()
    assert "CIRIS_SERVICES_DISABLED=true" in text
    assert "CIRIS_RUN_WITHOUT_AI=true" in text
    assert "CIRIS_NODE_KEY_ID=ciris-agent-bootstrap" in text


def test_no_usable_provider_without_the_choice_degrades_the_brain_only() -> None:
    req = SetupCompleteRequest(**_BASE, llm_provider="openai", llm_api_key="")
    out = io.StringIO()
    complete._write_llm_availability_config(out, req)
    text = out.getvalue()
    assert "CIRIS_SERVICES_DISABLED=true" in text
    assert "CIRIS_RUN_WITHOUT_AI" not in text, "an accidental missing key is not a decision to have no brain"


def test_the_flag_is_written_even_when_the_alias_cannot_be_resolved() -> None:
    req = SetupCompleteRequest(**_BASE, run_without_ai=True)
    out = io.StringIO()
    with patch("ciris_engine.logic.runtime.node_fold._resolve_key_id", side_effect=RuntimeError("no fold")):
        complete._write_llm_availability_config(out, req)
    text = out.getvalue()
    assert "CIRIS_RUN_WITHOUT_AI=true" in text and "CIRIS_NODE_KEY_ID" not in text


def test_node_only_restart_ends_the_brain_after_the_response() -> None:
    reasons: List[str] = []
    runtime = type("R", (), {"request_shutdown": lambda self, reason: reasons.append(reason)})()

    async def _go() -> None:
        before = set(complete._background_tasks)
        await complete._schedule_node_only_restart(runtime)
        scheduled = [task for task in complete._background_tasks if task not in before]
        assert len(scheduled) == 1, "exactly one restart task is scheduled"
        assert reasons == [], "the response goes out before the brain is asked to stop"
        await asyncio.wait_for(scheduled[0], timeout=5.0)

    asyncio.run(_go())
    assert reasons and "Run without AI" in reasons[0] and "node" in reasons[0]
