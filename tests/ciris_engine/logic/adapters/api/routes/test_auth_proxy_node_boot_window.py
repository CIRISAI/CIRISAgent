"""The auth proxy answers the node's boot window as "starting", not as an outage (#1262 staged QA).

:8080 serves a few seconds before the node binds :4243. A login in that window
reached nothing and the proxy logged it at ERROR, which the QA incidents gate
counts as a failure: main's all_1 logged one per backend before the gate's
snapshot, #1262's 0.5.226 run logged two and tripped it. A miss while the node
is still starting is now WARNING + 503 Retry-After; a miss once it is listening
is still ERROR + 502.
"""

import logging

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from ciris_engine.logic.adapters.api.routes import auth_proxy
from ciris_engine.logic.runtime import node_fold


@pytest.fixture
def app(monkeypatch):
    real_client = httpx.AsyncClient

    def refuse(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("All connection attempts failed")

    monkeypatch.setattr(
        auth_proxy.httpx, "AsyncClient", lambda **kw: real_client(transport=httpx.MockTransport(refuse), **kw)
    )
    monkeypatch.setenv("CIRIS_NODE_FOLD", "true")
    monkeypatch.setattr(node_fold, "_node_error", None)
    application = FastAPI()
    application.include_router(auth_proxy.router, prefix="/v1")
    return application


def _proxy_errors(caplog):
    return [r for r in caplog.records if r.name == auth_proxy.logger.name and r.levelno >= logging.ERROR]


def test_a_miss_in_the_boot_window_is_503_retry_after_and_not_an_error(app, monkeypatch, caplog):
    monkeypatch.setattr(node_fold, "_node_ready", False)
    with caplog.at_level(logging.INFO):
        response = TestClient(app).post("/v1/auth/login", json={"username": "admin", "password": "x"})
    assert response.status_code == 503
    assert response.headers["Retry-After"] == str(auth_proxy.NODE_STARTING_RETRY_AFTER_SECONDS)
    assert _proxy_errors(caplog) == []  # the QA incidents gate counts ERROR lines
    assert any("still starting" in r.getMessage() for r in caplog.records if r.levelno == logging.WARNING)


def test_a_miss_once_the_node_is_listening_is_still_an_error(app, monkeypatch, caplog):
    """Not a blanket downgrade: a node that went away after binding is an outage."""
    monkeypatch.setattr(node_fold, "_node_ready", True)
    with caplog.at_level(logging.INFO):
        response = TestClient(app).post("/v1/auth/login", json={"username": "admin", "password": "x"})
    assert response.status_code == 502
    assert len(_proxy_errors(caplog)) == 1


@pytest.mark.parametrize(
    "fold_env, ready, error, booting",
    [
        ("true", False, None, True),
        ("true", True, None, False),
        ("true", False, "RuntimeError: bind failed", False),  # failed, not booting
        ("false", False, None, False),  # no node in this deployment
    ],
)
def test_node_booting(monkeypatch, fold_env, ready, error, booting):
    monkeypatch.setenv("CIRIS_NODE_FOLD", fold_env)
    monkeypatch.setattr(node_fold, "_node_ready", ready)
    monkeypatch.setattr(node_fold, "_node_error", error)
    assert node_fold.node_booting() is booting
