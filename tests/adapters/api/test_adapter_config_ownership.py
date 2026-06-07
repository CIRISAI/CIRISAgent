"""
Regression tests for CIRISAgent#848 — adapter configuration status must not leak
collected_config (which holds oauth_tokens) to non-owners.
"""

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from ciris_engine.logic.adapters.api.routes.system import adapter_config
from ciris_engine.schemas.api.auth import AuthContext
from ciris_engine.schemas.api.auth import Permission, UserRole


def _auth(user_id: str, role: UserRole = UserRole.ADMIN) -> AuthContext:
    return AuthContext(
        user_id=user_id,
        role=role,
        permissions=set(Permission),
        authenticated_at=datetime.now(timezone.utc),
    )


def _session(user_id: str):
    session = MagicMock()
    session.session_id = "sess_1"
    session.adapter_type = "discord"
    session.status = MagicMock(value="in_progress")
    session.current_step_index = 0
    session.collected_config = {"oauth_tokens": {"access_token": "SECRET"}}
    session.created_at = datetime.now(timezone.utc)
    session.updated_at = datetime.now(timezone.utc)
    session.user_id = user_id
    return session


@pytest.mark.asyncio
async def test_non_owner_admin_is_forbidden():
    """#848: an ADMIN who is not the session owner gets 403, not the tokens."""
    config_service = MagicMock()
    config_service.get_session.return_value = _session(user_id="alice")

    with patch.object(adapter_config, "get_adapter_config_service", return_value=config_service):
        with pytest.raises(HTTPException) as exc:
            await adapter_config.get_configuration_status(
                session_id="sess_1", request=MagicMock(), auth=_auth("bob")
            )
    assert exc.value.status_code == 403


@pytest.mark.asyncio
async def test_owner_is_allowed():
    """The session owner can read their own config."""
    config_service = MagicMock()
    session = _session(user_id="alice")
    config_service.get_session.return_value = session
    # Minimal manifest so the response builds past the ownership gate.
    manifest = MagicMock()
    manifest.steps = []
    config_service._adapter_manifests = {"discord": manifest}

    with patch.object(adapter_config, "get_adapter_config_service", return_value=config_service):
        result = await adapter_config.get_configuration_status(
            session_id="sess_1", request=MagicMock(), auth=_auth("alice")
        )
    assert result.data.collected_config == session.collected_config


@pytest.mark.asyncio
async def test_setup_wizard_bypasses_ownership():
    """During first-run setup there are no real users — setup context may read."""
    config_service = MagicMock()
    session = _session(user_id="alice")
    config_service.get_session.return_value = session
    manifest = MagicMock()
    manifest.steps = []
    config_service._adapter_manifests = {"discord": manifest}

    with patch.object(adapter_config, "get_adapter_config_service", return_value=config_service):
        result = await adapter_config.get_configuration_status(
            session_id="sess_1", request=MagicMock(), auth=_auth("setup_wizard")
        )
    assert result.data.session_id == "sess_1"
