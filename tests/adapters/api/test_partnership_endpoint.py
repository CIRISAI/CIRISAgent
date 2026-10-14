"""
Partnership API surface after CIRISAgent#1251.

Partnership is a data-management record (CC 4.4.3.4.3): there is no agent-side
approval queue, so the queue's endpoints are gone. The only partnership route
left is the read-only description of the PARTNERED stream. Choosing it goes
through POST /v1/consent/grant; a non-steward's choice is deferred to the
steward through WBD and answered through POST /v1/wa/deferrals/{id}/resolve.
"""

import pytest
from fastapi import status
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from ciris_engine.logic.adapters.api.app import create_app
from ciris_engine.logic.adapters.api.auth import get_current_user
from ciris_engine.logic.adapters.api.models import TokenData

REMOVED = [
    ("POST", "/v1/partnership/decide"),
    ("GET", "/v1/partnership/pending"),
    ("GET", "/v1/partnership/metrics"),
    ("GET", "/v1/partnership/history/discord_123456"),
]


@pytest.fixture
def app(monkeypatch):
    # Unmatched /v1 paths are forwarded to the folded node on 127.0.0.1:4243.
    # A developer's own ciris_server may hold that port: point the proxy at a
    # port nothing listens on so these requests never leave the test.
    import socket

    from ciris_engine.logic.adapters.api.routes import node_proxy

    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        dead_port = sock.getsockname()[1]
    monkeypatch.setattr(node_proxy, "NODE_FOLD_PORT", dead_port)

    app = create_app()
    app.dependency_overrides[get_current_user] = lambda: TokenData(
        username="admin", email="admin@test.com", role="SYSTEM_ADMIN"
    )
    return app


@pytest.fixture
def client(app):
    return TestClient(app)


def _registered(app, method: str, path_template: str) -> bool:
    return any(isinstance(r, APIRoute) and r.path == path_template and method in r.methods for r in app.router.routes)


class TestRemovedQueueEndpoints:
    """The approval queue and its observability endpoints no longer exist."""

    @pytest.mark.parametrize(
        "method,template",
        [
            ("POST", "/v1/partnership/decide"),
            ("GET", "/v1/partnership/pending"),
            ("GET", "/v1/partnership/metrics"),
            ("GET", "/v1/partnership/history/{user_id}"),
        ],
    )
    def test_route_not_registered(self, app, method, template):
        assert not _registered(app, method, template), f"{method} {template} must not be mounted"

    @pytest.mark.parametrize("method,path", REMOVED)
    def test_route_returns_404(self, client, method, path):
        response = client.request(
            method,
            path,
            json={"task_id": "partnership_u_1", "decision": "accept"} if method == "POST" else None,
            headers={"Authorization": "Bearer admin_token"},
        )
        assert response.status_code == status.HTTP_404_NOT_FOUND, (method, path, response.status_code)

    def test_negative_control_options_still_mounted(self, app, client):
        """The 404 checks would pass vacuously if the router were simply not mounted."""
        assert _registered(app, "GET", "/v1/partnership/options")
        response = client.get("/v1/partnership/options", headers={"Authorization": "Bearer admin_token"})
        assert response.status_code == status.HTTP_200_OK


class TestPartnershipOptions:
    def test_options_describe_the_steward_route_not_agent_approval(self, client):
        data = client.get("/v1/partnership/options", headers={"Authorization": "Bearer admin_token"}).json()["data"]
        text = data["approval_process"].lower()
        assert "steward" in text
        assert "bilateral" not in text
        assert "the agent will review" not in text
        assert "interaction" in data["required_categories"]


class TestDoctrineRemoved:
    """The superseded 'EQUAL moral agency ... No admin bypass' doctrine is gone from the code."""

    @pytest.mark.parametrize(
        "module",
        [
            "ciris_engine.logic.adapters.api.routes.partnership",
            "ciris_engine.logic.services.governance.consent.partnership",
        ],
    )
    def test_docstring(self, module):
        import importlib
        import inspect

        source = inspect.getsource(importlib.import_module(module))
        assert "EQUAL moral agency" not in source
        assert "No admin bypass" not in source
