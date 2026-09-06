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


def test_the_restart_is_a_background_task_so_the_response_lands_first() -> None:
    """Starlette runs BackgroundTasks after the response is sent -- that is the whole guarantee."""
    import inspect

    from fastapi import BackgroundTasks

    sig = inspect.signature(complete.complete_setup)
    assert "background_tasks" in sig.parameters, "the handler must take BackgroundTasks for the ordering to hold"
    assert sig.parameters["background_tasks"].annotation is BackgroundTasks

    reasons: List[str] = []
    runtime = type("R", (), {"request_shutdown": lambda self, reason: reasons.append(reason)})()
    tasks = BackgroundTasks()
    tasks.add_task(complete._node_only_restart, runtime)
    assert reasons == [], "nothing runs at registration time; the response is still being sent"
    asyncio.run(tasks())
    assert len(reasons) == 1 and "Run without AI" in reasons[0] and "node" in reasons[0]
