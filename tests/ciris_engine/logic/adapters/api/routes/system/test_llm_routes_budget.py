"""A provider added at runtime gets its timeout from the LLM budget profile (CIRISAgent#1186).

It used to be a hardcoded 30s for every provider — an eighth of what a local
model on an edge box gets once the agent restarts and restores it.
"""

from __future__ import annotations

import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ciris_engine.logic.config import llm_budget as lb
from ciris_engine.schemas.config.llm_budget import LOCAL_PROFILE, REMOTE_PROFILE

ROUTES = "ciris_engine.logic.adapters.api.routes.system.llm_routes"


@pytest.fixture
def app(monkeypatch) -> FastAPI:
    monkeypatch.setattr(lb, "get_env_var", lambda name, default=None: os.environ.get(name, default))
    monkeypatch.delenv("CIRIS_LLM_TIMEOUT", raising=False)
    monkeypatch.delenv("CIRIS_LLM_BUDGET_PROFILE", raising=False)
    from ciris_engine.logic.adapters.api.routes.system.llm_routes import router

    application = FastAPI()
    application.include_router(router, prefix="/system")
    application.state.runtime = MagicMock(agent_processor=MagicMock())
    application.state.time_service = MagicMock()
    application.state.telemetry_service = None
    return application


def _add(app: FastAPI, body: dict):
    with patch(f"{ROUTES}._is_setup_allowed_without_auth", return_value=True), patch(
        f"{ROUTES}.get_global_registry"
    ) as registry, patch(
        f"{ROUTES}.persist_create_provider", AsyncMock(return_value=MagicMock(success=True))
    ), patch(
        "ciris_engine.logic.services.runtime.llm_service.service.OpenAICompatibleClient"
    ) as client_cls:
        registry.return_value.get_provider_by_name.return_value = None
        client_cls.return_value.start = AsyncMock()
        response = TestClient(app).post("/system/llm/providers", json=body)
    assert response.status_code == 200, response.text
    return client_cls.call_args.kwargs["config"]


@pytest.mark.parametrize("provider_id", ["local", "local_inference"])
def test_a_local_provider_is_keyless_and_gets_the_local_timeout(app, provider_id):
    cfg = _add(
        app,
        {"provider_id": provider_id, "name": "edge", "base_url": "http://jetson.local:8080/v1", "model": "gemma"},
    )
    assert cfg.api_key == "local"
    assert cfg.timeout_seconds == int(LOCAL_PROFILE.llm_http_timeout_s)


def test_a_cloud_provider_gets_the_remote_timeout(app):
    cfg = _add(
        app,
        {
            "provider_id": "groq",
            "name": "groq",
            "base_url": "https://api.groq.com/openai/v1",
            "model": "llama",
            "api_key": "gsk-123",
        },
    )
    assert cfg.api_key == "gsk-123"
    assert cfg.timeout_seconds == int(REMOTE_PROFILE.llm_http_timeout_s)
