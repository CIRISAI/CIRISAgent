"""
Regression tests for CIRISAgent#847 — OAuth `state` CSRF tokens must be verified
server-side (single-use, TTL) instead of being a self-attesting blob that
provides no protection.
"""

import base64
import json
from unittest.mock import AsyncMock, Mock, patch

import pytest
from fastapi import HTTPException

from ciris_engine.logic.adapters.api.routes import auth


def test_state_is_single_use():
    """A registered csrf verifies exactly once; a replay is rejected."""
    token = "csrf-abc"
    auth._oauth_state_remember(token)
    assert auth._oauth_state_consume(token) is True
    assert auth._oauth_state_consume(token) is False  # replay


def test_unknown_state_rejected():
    assert auth._oauth_state_consume("never-issued") is False
    assert auth._oauth_state_consume(None) is False


def test_expired_state_rejected():
    token = "csrf-expired"
    auth._oauth_state_remember(token)
    # Force the stored entry to already be expired.
    with auth._oauth_states_lock:
        auth._oauth_pending_states[token] = 0.0
    assert auth._oauth_state_consume(token) is False


@pytest.mark.asyncio
async def test_callback_rejects_forged_state():
    """A well-formed state whose csrf we never issued is rejected with 400 —
    not processed. (No autouse bypass here, unlike the coverage suite.)"""
    forged = base64.urlsafe_b64encode(json.dumps({"csrf": "attacker-made-this-up"}).encode()).decode()

    mock_request = Mock()
    mock_request.app = Mock()
    mock_request.app.state = Mock()
    mock_auth_service = Mock()
    mock_auth_service._ensure_users_loaded = AsyncMock()

    with patch("ciris_engine.logic.adapters.api.routes.auth._load_oauth_config") as mock_config:
        mock_config.return_value = {"client_id": "id", "client_secret": "secret"}
        with pytest.raises(HTTPException) as exc:
            await auth.oauth_callback("google", "code", forged, mock_request, mock_auth_service)
    assert exc.value.status_code == 400
    assert "state" in exc.value.detail.lower()
