"""Root signing is retired in the agent (2026-11-08).

The agent no longer accepts a root-key-signed emergency shutdown or mints a
Wise Authority from a root signature. Emergency shutdown stays, signed hybrid by
the seated WA (test_emergency_hybrid.py); the WA seat comes from the node's owner. These locks fail if
either surface, or the single-key Ed25519 signing code behind it, comes back.
"""

import importlib
import re

import pytest

from pathlib import Path

API = Path(__file__).resolve().parents[5] / "ciris_engine" / "logic" / "adapters" / "api"


def _route_sources() -> str:
    """Every route module's source, and app.py's mounting.

    These locks are about what the code mounts, so they read the code. Building
    the app was unreliable under CI: in-process a leaked include_router patch
    left an almost empty app, and even a fresh interpreter there produced one
    (CI 42747184825, 42758529473 shard 5), failing the positive controls and
    letting the "not mounted" asserts pass vacuously.
    """
    return "\n".join(f.read_text(encoding="utf-8") for f in sorted((API / "routes").rglob("*.py")))


def test_signed_emergency_and_mint_routes_are_not_mounted() -> None:
    routes, app_py = _route_sources(), (API / "app.py").read_text(encoding="utf-8")
    for gone in ('"/test"', "/mint-wa", "/wa/key-check"):
        assert gone not in routes, gone
    # Positive controls, so the scan can't pass on nothing: the ordinary shutdown
    # route and the hybrid-signed emergency route are both declared and mounted.
    shutdown = (API / "routes" / "system" / "shutdown.py").read_text(encoding="utf-8")
    assert re.search(r'@router\.post\(\s*"/shutdown"', shutdown)
    assert "router.include_router(shutdown.router)" in (API / "routes" / "system" / "__init__.py").read_text(encoding="utf-8")
    emergency = (API / "routes" / "emergency.py").read_text(encoding="utf-8")
    assert re.search(r'"/emergency/shutdown"|prefix="/emergency"', emergency)
    assert "app.include_router(emergency.router)" in app_py


@pytest.mark.parametrize(
    "module",
    [
        "ciris_engine.logic.adapters.api.endpoints.emergency",
        "ciris_engine.logic.accord.authorities",
        "ciris_engine.schemas.api.emergency",
        "ciris_sdk.resources.emergency",
    ],
)
def test_retired_modules_are_gone(module: str) -> None:
    with pytest.raises(ImportError):
        importlib.import_module(module)


def test_retired_signing_methods_are_gone() -> None:
    from ciris_engine.logic.adapters.api.services.auth_service import APIAuthService
    from ciris_engine.logic.services.infrastructure.authentication import AuthenticationService
    from ciris_engine.logic.services.runtime.control_service.service import RuntimeControlService

    assert not hasattr(APIAuthService, "verify_root_signature")
    assert not hasattr(RuntimeControlService, "handle_emergency_shutdown")
    for name in (
        "sign_task",
        "verify_task_signature",
        "sign_data",
        "rotate_keys",
        "import_portal_key",
        "_create_authority_token",
    ):
        assert not hasattr(AuthenticationService, name), name
    # Kept: budget grants verify on this path until the server ships a pen verb.
    assert hasattr(AuthenticationService, "_verify_signature")
    assert hasattr(AuthenticationService, "sign_as_wa")
