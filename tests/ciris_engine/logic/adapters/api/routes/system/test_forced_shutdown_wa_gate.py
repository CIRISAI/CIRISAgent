"""Forced / emergency shutdown: WA standing gate, and the host process survives (CIRISAgent#1240).

Two defects, one path:

1. ``POST /v1/system/shutdown`` with ``force=True`` needed only the ADMIN API role;
   the "ROOT/AUTHORITY" check in the shutdown processor called a
   ``get_requester_wa_id()`` that exists nowhere, so it only ever logged a warning.
   Now the entry point resolves the requester to an ACTIVE WA certificate in the
   authentication store and refuses (403, typed ``ForcedShutdownRefusal``)
   anything that is not ROOT or AUTHORITY.
2. ``ShutdownService.emergency_shutdown`` ran ``sys.exit(1)`` plus a SIGKILL timer
   against its own pid -- the host app on Android / iOS / desktop -- and signalled a
   ShutdownService instance the runtime loop does not watch. Now it sets the GLOBAL
   (loop-watched) shutdown and returns; only an owned headless process arms a
   bounded exit.

Every process-ending primitive is patched to FAIL the test in embedded mode.
"""

import os
import sys
import time
from datetime import datetime, timezone
from typing import Optional
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from ciris_engine.logic.adapters.api.dependencies.auth import require_admin, verify_forced_shutdown_standing
from ciris_engine.logic.adapters.api.routes import emergency as emergency_routes
from ciris_engine.logic.adapters.api.routes.system import shutdown as shutdown_routes
from ciris_engine.logic.adapters.api.services.auth_service import APIAuthService, User
from ciris_engine.logic.runtime import device_class
from ciris_engine.logic.services.lifecycle.shutdown import service as shutdown_service_module
from ciris_engine.logic.utils import shutdown_manager
from ciris_engine.schemas.api.auth import AuthContext, UserRole
from ciris_engine.schemas.runtime.api import APIRole
from ciris_engine.schemas.services.authority_core import WACertificate, WARole
from ciris_engine.schemas.services.shutdown import EmergencyCommandType, ForcedShutdownRefusalReason, WASignedCommand

ADMIN_WA_ID = "wa-2026-10-13-ADMIN1"
AUTHORITY_WA_ID = "wa-2026-10-13-AUTH01"
ROOT_WA_ID = "wa-2026-10-13-ROOT01"
OBSERVER_WA_ID = "wa-2026-10-13-OBSV01"


# --------------------------------------------------------------------------- #
# fixtures
# --------------------------------------------------------------------------- #


def _cert(wa_id: str, role: WARole) -> WACertificate:
    return WACertificate(
        wa_id=wa_id,
        name=wa_id,
        role=role,
        pubkey="dGVzdA",
        jwt_kid=f"kid-{wa_id}",
        scopes_json="[]",
        created_at=datetime.now(timezone.utc),
    )


class _FakeWAStore:
    """Stands in for the AuthenticationService: ``get_wa`` returns ACTIVE certs only."""

    def __init__(self, certs: dict[str, WACertificate]) -> None:
        self.certs = certs

    async def get_wa(self, wa_id: str) -> Optional[WACertificate]:
        return self.certs.get(wa_id)


def _api_auth(certs: dict[str, WACertificate]) -> APIAuthService:
    svc = APIAuthService(auth_service=_FakeWAStore(certs))  # type: ignore[arg-type]
    for wa_id, cert in certs.items():
        svc._users[wa_id] = User(wa_id=wa_id, name=wa_id, auth_type="password", api_role=APIRole.ADMIN)
    return svc


def _auth(user_id: str, role: UserRole = UserRole.ADMIN) -> AuthContext:
    return AuthContext(user_id=user_id, role=role, permissions=set(), authenticated_at=datetime.now(timezone.utc))


def _forbidden(*_a: object, **_k: object) -> None:
    raise AssertionError("forced shutdown tried to end the host process")


@pytest.fixture
def embedded_host(monkeypatch):
    """Embedded host (Android/iOS/desktop): every process-ending primitive FAILS the test."""
    shutdown_manager.reset_global_shutdown_service()
    monkeypatch.setattr(device_class, "agent_owns_process", lambda: False)
    for target, name in ((sys, "exit"), (os, "_exit"), (os, "kill"), (os, "execv"), (os, "execvp")):
        monkeypatch.setattr(target, name, _forbidden)
    yield
    shutdown_manager.reset_global_shutdown_service()


@pytest.fixture
def global_shutdown_spy(monkeypatch):
    spy = Mock(wraps=shutdown_manager.request_global_shutdown)
    monkeypatch.setattr(shutdown_manager, "request_global_shutdown", spy)
    return spy


def _shutdown_app(api_auth: APIAuthService, user_id: str) -> tuple[FastAPI, Mock, AsyncMock]:
    app = FastAPI()
    app.include_router(shutdown_routes.router, prefix="/v1/system")
    app.dependency_overrides[require_admin] = lambda: _auth(user_id)
    app.state.auth_service = api_auth
    runtime = Mock()
    runtime.shutdown_service = shutdown_manager.get_global_shutdown_service()
    runtime.request_shutdown = Mock()
    app.state.runtime = runtime
    audit = AsyncMock()
    app.state.audit_service = audit
    return app, runtime, audit


# --------------------------------------------------------------------------- #
# 1. the WA-standing gate
# --------------------------------------------------------------------------- #


class TestWAStandingGate:
    @pytest.mark.asyncio
    async def test_admin_without_wa_certificate_is_refused(self):
        api_auth = _api_auth({})
        api_auth._users[ADMIN_WA_ID] = User(
            wa_id=ADMIN_WA_ID, name="admin", auth_type="password", api_role=APIRole.ADMIN
        )
        with pytest.raises(HTTPException) as exc:
            await verify_forced_shutdown_standing(_auth(ADMIN_WA_ID), api_auth)
        assert exc.value.status_code == 403
        assert exc.value.detail["reason"] == ForcedShutdownRefusalReason.NO_WA_CERTIFICATE.value

    @pytest.mark.asyncio
    async def test_observer_wa_is_refused(self):
        api_auth = _api_auth({OBSERVER_WA_ID: _cert(OBSERVER_WA_ID, WARole.OBSERVER)})
        with pytest.raises(HTTPException) as exc:
            await verify_forced_shutdown_standing(_auth(OBSERVER_WA_ID), api_auth)
        assert exc.value.status_code == 403
        assert exc.value.detail["reason"] == ForcedShutdownRefusalReason.WA_ROLE_INSUFFICIENT.value
        assert exc.value.detail["wa_role"] == "observer"

    @pytest.mark.asyncio
    async def test_cached_role_is_not_trusted_over_the_store(self):
        """A user cached as AUTHORITY whose cert is gone (revoked) has no standing."""
        api_auth = _api_auth({})
        api_auth._users[AUTHORITY_WA_ID] = User(
            wa_id=AUTHORITY_WA_ID, name="x", auth_type="password", api_role=APIRole.AUTHORITY, wa_role=WARole.AUTHORITY
        )
        with pytest.raises(HTTPException) as exc:
            await verify_forced_shutdown_standing(_auth(AUTHORITY_WA_ID), api_auth)
        assert exc.value.detail["reason"] == ForcedShutdownRefusalReason.NO_WA_CERTIFICATE.value

    @pytest.mark.asyncio
    async def test_no_wa_store_is_refused(self):
        with pytest.raises(HTTPException) as exc:
            await verify_forced_shutdown_standing(_auth(ADMIN_WA_ID), APIAuthService(auth_service=None))
        assert exc.value.status_code == 403
        assert exc.value.detail["reason"] == ForcedShutdownRefusalReason.WA_STORE_UNAVAILABLE.value

    @pytest.mark.asyncio
    @pytest.mark.parametrize("wa_id,role", [(AUTHORITY_WA_ID, WARole.AUTHORITY), (ROOT_WA_ID, WARole.ROOT)])
    async def test_root_and_authority_are_allowed(self, wa_id, role):
        api_auth = _api_auth({wa_id: _cert(wa_id, role)})
        cert = await verify_forced_shutdown_standing(_auth(wa_id), api_auth)
        assert cert.wa_id == wa_id and cert.role == role

    @pytest.mark.asyncio
    async def test_oauth_alias_resolves_to_its_wa(self):
        """AuthContext.user_id may be an OAuth alias; it resolves through get_user to the wa_id."""
        api_auth = _api_auth({AUTHORITY_WA_ID: _cert(AUTHORITY_WA_ID, WARole.AUTHORITY)})
        api_auth._users["google:12345"] = api_auth._users[AUTHORITY_WA_ID]
        cert = await verify_forced_shutdown_standing(_auth("google:12345"), api_auth)
        assert cert.wa_id == AUTHORITY_WA_ID


# --------------------------------------------------------------------------- #
# 2. POST /v1/system/shutdown
# --------------------------------------------------------------------------- #


class TestSystemShutdownRoute:
    def test_admin_without_wa_standing_forced_is_403(self, embedded_host, global_shutdown_spy):
        api_auth = _api_auth({})
        api_auth._users[ADMIN_WA_ID] = User(
            wa_id=ADMIN_WA_ID, name="admin", auth_type="password", api_role=APIRole.ADMIN
        )
        app, runtime, audit = _shutdown_app(api_auth, ADMIN_WA_ID)
        with patch.object(shutdown_service_module.ShutdownService, "emergency_shutdown") as emergency:
            resp = TestClient(app).post(
                "/v1/system/shutdown", json={"reason": "stop now", "force": True, "confirm": True}
            )
        assert resp.status_code == 403
        assert resp.json()["detail"]["reason"] == ForcedShutdownRefusalReason.NO_WA_CERTIFICATE.value
        emergency.assert_not_called()
        global_shutdown_spy.assert_not_called()
        runtime.request_shutdown.assert_not_called()
        assert not shutdown_manager.is_global_shutdown_requested()

    def test_admin_graceful_shutdown_still_needs_only_admin_and_negotiates(self, embedded_host):
        api_auth = _api_auth({})
        app, runtime, _ = _shutdown_app(api_auth, ADMIN_WA_ID)
        resp = TestClient(app).post("/v1/system/shutdown", json={"reason": "bye", "force": False, "confirm": True})
        assert resp.status_code == 200
        runtime.request_shutdown.assert_called_once()
        # Not forced: the shutdown processor will negotiate.
        assert not shutdown_manager.get_global_shutdown_service().is_force_shutdown()

    @pytest.mark.parametrize("wa_id,role", [(AUTHORITY_WA_ID, WARole.AUTHORITY), (ROOT_WA_ID, WARole.ROOT)])
    def test_wa_forced_shutdown_stops_runtime_without_ending_process(
        self, embedded_host, global_shutdown_spy, wa_id, role
    ):
        api_auth = _api_auth({wa_id: _cert(wa_id, role)})
        app, runtime, audit = _shutdown_app(api_auth, wa_id)
        resp = TestClient(app).post("/v1/system/shutdown", json={"reason": "stop now", "force": True, "confirm": True})
        assert resp.status_code == 200, resp.text

        # The GLOBAL (loop-watched) shutdown is set, as forced/emergency.
        global_shutdown_spy.assert_called()
        assert shutdown_manager.is_global_shutdown_requested()
        assert shutdown_manager.get_global_shutdown_service().is_force_shutdown()
        runtime.request_shutdown.assert_called_once()

        # The stop is recorded (who, why) -- awaited, not fire-and-forget.
        audit.log_event.assert_awaited_once()
        event_type, event = audit.log_event.await_args.args
        assert event_type == "system_forced_shutdown"
        assert event.metadata["authorized_wa_id"] == wa_id
        assert event.metadata["authorized_wa_role"] == role.value
        assert "stop now" in event.reason

        # Embedded: no owned-process exit watchdog was armed.
        assert shutdown_manager.get_global_shutdown_service()._owned_exit_cancel is None

    def test_forced_escalates_a_pending_graceful_shutdown(self, embedded_host):
        api_auth = _api_auth({AUTHORITY_WA_ID: _cert(AUTHORITY_WA_ID, WARole.AUTHORITY)})
        app, _, _ = _shutdown_app(api_auth, AUTHORITY_WA_ID)
        shutdown_manager.request_global_shutdown("graceful, stuck in negotiation")
        resp = TestClient(app).post("/v1/system/shutdown", json={"reason": "escalate", "force": True, "confirm": True})
        assert resp.status_code == 200, resp.text
        assert shutdown_manager.get_global_shutdown_service().is_force_shutdown()
        # A second forced request is a duplicate.
        resp = TestClient(app).post("/v1/system/shutdown", json={"reason": "again", "force": True, "confirm": True})
        assert resp.status_code == 409


# --------------------------------------------------------------------------- #
# 3. WA-signed emergency paths (the signature is the authority)
# --------------------------------------------------------------------------- #


def _command() -> WASignedCommand:
    return WASignedCommand(
        command_id="cmd-1",
        command_type=EmergencyCommandType.SHUTDOWN_NOW,
        wa_id=ROOT_WA_ID,
        wa_public_key="AAAA",
        issued_at=datetime.now(timezone.utc),
        reason="kill switch",
        signature="00",
    )


class TestEmergencyRoute:
    def _app(self) -> tuple[FastAPI, Mock, AsyncMock]:
        app = FastAPI()
        app.include_router(emergency_routes.router)
        runtime = Mock()
        runtime.shutdown_service = shutdown_manager.get_global_shutdown_service()
        runtime.request_shutdown = Mock()
        app.state.runtime = runtime
        audit = AsyncMock()
        app.state.audit_service = audit
        return app, runtime, audit

    def test_unsigned_command_is_refused(self, embedded_host):
        """An ADMIN bearer is not authority here: without a valid WA signature, 403."""
        app, runtime, _ = self._app()
        resp = TestClient(app).post(
            "/emergency/shutdown",
            json=_command().model_dump(mode="json"),
            headers={"Authorization": "Bearer admin:password"},
        )
        assert resp.status_code == 403
        runtime.request_shutdown.assert_not_called()
        assert not shutdown_manager.is_global_shutdown_requested()

    def test_verified_command_stops_runtime_without_ending_process(self, embedded_host, global_shutdown_spy):
        app, runtime, audit = self._app()
        with (
            patch.object(emergency_routes, "verify_timestamp", return_value=True),
            patch.object(emergency_routes, "verify_signature", return_value=True),
            patch.object(emergency_routes, "is_authorized_key", return_value=True),
        ):
            resp = TestClient(app).post("/emergency/shutdown", json=_command().model_dump(mode="json"))
        assert resp.status_code == 200, resp.text
        global_shutdown_spy.assert_called()
        assert shutdown_manager.get_global_shutdown_service().is_force_shutdown()
        runtime.request_shutdown.assert_called_once()
        audit.log_event.assert_awaited_once()
        assert audit.log_event.await_args.args[0] == "emergency_shutdown"
        assert audit.log_event.await_args.args[1].actor == ROOT_WA_ID


class TestControlServiceEmergency:
    @pytest.mark.asyncio
    async def test_invalid_signature_is_refused(self, embedded_host):
        from ciris_engine.logic.services.runtime.control_service import RuntimeControlService

        svc = RuntimeControlService()
        with patch.object(svc, "_verify_wa_signature", return_value=False):
            status = await svc.handle_emergency_shutdown(_command())
        assert status.command_verified is False
        assert not shutdown_manager.is_global_shutdown_requested()

    @pytest.mark.asyncio
    async def test_verified_signature_sets_global_emergency(self, embedded_host, global_shutdown_spy):
        from ciris_engine.logic.services.runtime.control_service import RuntimeControlService

        svc = RuntimeControlService()
        svc.runtime = Mock()
        with patch.object(svc, "_verify_wa_signature", return_value=True):
            status = await svc.handle_emergency_shutdown(_command())
        assert status.command_verified is True
        assert status.exit_code == 0
        global_shutdown_spy.assert_called()
        assert shutdown_manager.get_global_shutdown_service().is_force_shutdown()
        svc.runtime.request_shutdown.assert_called_once()


class TestAPIRuntimeControlEmergency:
    @pytest.mark.asyncio
    async def test_without_a_verifier_the_command_is_refused(self, embedded_host):
        from ciris_engine.logic.adapters.api.api_runtime_control import APIRuntimeControlService

        runtime = Mock(spec=["shutdown_service"])
        runtime.shutdown_service = shutdown_manager.get_global_shutdown_service()
        svc = APIRuntimeControlService(runtime, time_service=None)
        status = await svc.handle_emergency_shutdown(_command())
        assert status.command_verified is False
        assert not shutdown_manager.is_global_shutdown_requested()

    @pytest.mark.asyncio
    async def test_delegates_to_the_verifying_control_service(self, embedded_host):
        from ciris_engine.logic.adapters.api.api_runtime_control import APIRuntimeControlService

        runtime = Mock()
        runtime.runtime_control_service.handle_emergency_shutdown = AsyncMock(return_value="verified-status")
        svc = APIRuntimeControlService(runtime, time_service=None)
        assert await svc.handle_emergency_shutdown(_command()) == "verified-status"
        runtime.runtime_control_service.handle_emergency_shutdown.assert_awaited_once()


# --------------------------------------------------------------------------- #
# 4. embedded vs owned process
# --------------------------------------------------------------------------- #


class TestOwnedProcess:
    @pytest.mark.parametrize(
        "platform,declared,owned",
        [
            ("android", "", False),
            ("ios", "", False),
            ("unknown", "server", False),
            ("linux", "laptop", False),  # ciris-agent desktop / the client's spawn (node fold)
            ("macos", "laptop", False),
            ("linux", "server", True),  # ciris-server / main.py in a container
            ("windows", "server", True),
            ("linux", "", True),  # bare main.py: the node fold declares server
        ],
    )
    def test_agent_owns_process(self, monkeypatch, platform, declared, owned):
        from ciris_engine.logic.utils import platform_detection

        monkeypatch.setattr(platform_detection, "get_platform_name", lambda: platform)
        monkeypatch.setattr(device_class, "is_android", lambda: platform == "android")
        monkeypatch.setattr(device_class, "is_ios", lambda: platform == "ios")
        monkeypatch.setenv(device_class.DEVICE_CLASS_ENV, declared)
        assert device_class.agent_owns_process() is owned

    @pytest.mark.asyncio
    async def test_owned_headless_process_gets_a_bounded_exit(self, monkeypatch):
        """Owned process: no immediate exit; after the grace, a normal interrupt, then a hard stop."""
        shutdown_manager.reset_global_shutdown_service()
        monkeypatch.setattr(device_class, "agent_owns_process", lambda: True)
        monkeypatch.setattr(shutdown_service_module, "OWNED_PROCESS_EXIT_GRACE_SECONDS", 0.05)
        interrupt = Mock()
        terminate = Mock()
        monkeypatch.setattr("_thread.interrupt_main", interrupt)
        monkeypatch.setattr("ciris_engine.logic.utils.hard_kill.terminate_immediately", terminate)
        monkeypatch.setattr(sys, "exit", _forbidden)
        try:
            svc = shutdown_manager.get_global_shutdown_service()
            await svc.emergency_shutdown("owned", timeout_seconds=1)
            interrupt.assert_not_called()  # nothing ends the process synchronously
            deadline = time.monotonic() + 5
            while not terminate.called and time.monotonic() < deadline:
                time.sleep(0.01)
            interrupt.assert_called_once()
            terminate.assert_called_once()
        finally:
            shutdown_manager.reset_global_shutdown_service()

    @pytest.mark.asyncio
    async def test_owned_exit_can_be_disarmed(self, monkeypatch):
        shutdown_manager.reset_global_shutdown_service()
        monkeypatch.setattr(device_class, "agent_owns_process", lambda: True)
        monkeypatch.setattr(shutdown_service_module, "OWNED_PROCESS_EXIT_GRACE_SECONDS", 0.1)
        interrupt = Mock()
        monkeypatch.setattr("_thread.interrupt_main", interrupt)
        try:
            svc = shutdown_manager.get_global_shutdown_service()
            await svc.emergency_shutdown("owned", timeout_seconds=1)
            svc.cancel_owned_process_exit()
            time.sleep(0.3)
            interrupt.assert_not_called()
        finally:
            shutdown_manager.reset_global_shutdown_service()

    @pytest.mark.asyncio
    async def test_non_global_instance_still_reaches_the_loop(self, embedded_host, global_shutdown_spy):
        """A stray ShutdownService instance routes its emergency to the global one."""
        stray = shutdown_service_module.ShutdownService()
        assert stray is not shutdown_manager.get_global_shutdown_service()
        await stray.emergency_shutdown("stray", timeout_seconds=1)
        global_shutdown_spy.assert_called_once()
        assert shutdown_manager.is_global_shutdown_requested()
        assert shutdown_manager.get_global_shutdown_service().is_force_shutdown()
