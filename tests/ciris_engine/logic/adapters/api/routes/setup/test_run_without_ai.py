"""Setup-complete records "Run without AI" so every later boot is ciris-server and the client (CIRISAgent#1149)."""

from __future__ import annotations

import asyncio
import io
from typing import Any, List
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from ciris_engine import node_only
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
    """Starlette runs BackgroundTasks after the response is sent -- that is the ordering guarantee."""
    import inspect

    from fastapi import BackgroundTasks

    sig = inspect.signature(complete.complete_setup)
    assert "background_tasks" in sig.parameters
    assert sig.parameters["background_tasks"].annotation is BackgroundTasks


def _runtime_with_server():
    server = type("S", (), {"should_exit": False})()
    adapter = type("A", (), {"_server": server})()
    runtime = type("R", (), {"adapters": [adapter], "request_shutdown": lambda self, reason: None})()
    return runtime, server


def test_the_handover_stops_8080_then_execs_into_the_node() -> None:
    """The runtime is PARKED during first-run, so this must not delegate to its shutdown."""
    runtime, server = _runtime_with_server()
    cfg = node_only.NodeOnlyConfig(home="/h", key_id="k")
    with patch.object(complete, "asyncio", wraps=asyncio) as _aio, patch(
        "ciris_engine.node_only.node_only_config", return_value=cfg
    ), patch("ciris_engine.node_only.exec_into_node", return_value=True) as execd:
        _aio.sleep = lambda s: asyncio.sleep(0)
        asyncio.run(complete._node_only_restart(runtime))
    assert server.should_exit is True, ":8080 must stop accepting so a stale client gets refused, not a hang"
    execd.assert_called_once_with(cfg)


def test_a_failed_exec_falls_back_to_asking_the_runtime_to_stop() -> None:
    reasons: List[str] = []
    runtime, _ = _runtime_with_server()
    runtime.request_shutdown = lambda reason: reasons.append(reason)  # type: ignore[method-assign]
    with patch.object(complete, "asyncio", wraps=asyncio) as _aio, patch(
        "ciris_engine.node_only.node_only_config", return_value=node_only.NodeOnlyConfig(home="/h", key_id=None)
    ), patch("ciris_engine.node_only.exec_into_node", return_value=False):
        _aio.sleep = lambda s: asyncio.sleep(0)
        asyncio.run(complete._node_only_restart(runtime))
    assert reasons and "exec into the ciris-server node failed" in reasons[0]


def test_a_flag_that_does_not_read_back_does_not_hand_off_blind() -> None:
    runtime, server = _runtime_with_server()
    with patch("ciris_engine.node_only.node_only_config", return_value=None), patch(
        "ciris_engine.node_only.exec_into_node"
    ) as execd:
        asyncio.run(complete._node_only_restart(runtime))
    execd.assert_not_called()
    assert server.should_exit is False


# ---- CIRISAgent#1158 review (Codex P1): a failed setup must not leave the flag behind ----


def test_a_failed_setup_retracts_the_flag_from_file_and_process(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    env = tmp_path / ".env"
    env.write_text("CIRIS_CONFIGURED=true\nCIRIS_RUN_WITHOUT_AI=true\nCIRIS_NODE_KEY_ID=k1\n")
    monkeypatch.setenv(node_only.ENV_FLAG, "true")
    monkeypatch.setenv(node_only.ENV_KEY_ID, "k1")
    complete._retract_run_without_ai(env)
    assert not env.exists(), "the next start must be a clean first run, not a node-only boot with no admin"
    import os

    assert node_only.ENV_FLAG not in os.environ and node_only.ENV_KEY_ID not in os.environ, (
        "this process's own exit path reads the environment and would still hand off to the node"
    )
    complete._retract_run_without_ai(None)  # nothing written yet: must not raise


def test_the_failure_handler_retracts_only_for_the_node_only_choice() -> None:
    """Source-level guard (the route needs a live app to drive): the outer handler
    calls the retraction, and only when the owner chose to run without AI."""
    import inspect

    src = inspect.getsource(complete.complete_setup)
    handler = src[src.rfind("except Exception as e:") :]
    assert "_retract_run_without_ai(config_path)" in handler
    assert "if setup.run_without_ai:" in handler
    assert "config_path: Optional[Path] = None" in src, "config_path must exist even when the save itself raised"
