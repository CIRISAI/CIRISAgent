"""Root signing is retired in the agent (2026-11-08).

The agent no longer accepts a root-key-signed emergency shutdown or mints a
Wise Authority from a root signature. The emergency halt is the accord halt the
server serves; the WA seat comes from the node's owner. These locks fail if
either surface, or the single-key Ed25519 signing code behind it, comes back.
"""

import importlib

import pytest

from ciris_engine.logic.adapters.api.app import create_app


def _route_paths() -> set[str]:
    app = create_app()
    return {getattr(r, "path", "") for r in app.routes}


def test_signed_emergency_and_mint_routes_are_not_mounted() -> None:
    paths = _route_paths()
    for gone in ("/emergency/shutdown", "/emergency/test", "/v1/users/{user_id}/mint-wa", "/v1/users/wa/key-check"):
        assert gone not in paths, gone
    # Positive control: the ordinary shutdown route the app's button uses is still there.
    assert "/v1/system/shutdown" in paths


@pytest.mark.parametrize(
    "module",
    [
        "ciris_engine.logic.adapters.api.routes.emergency",
        "ciris_engine.logic.adapters.api.endpoints.emergency",
        "ciris_engine.logic.accord.authorities",
        "ciris_engine.schemas.services.shutdown",
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
