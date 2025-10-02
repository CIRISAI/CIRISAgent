"""Tests for linking and unlinking OAuth accounts via the users API routes."""

import os
import tempfile
from datetime import datetime, timezone

import pytest

from ciris_engine.logic.adapters.api.routes.users import (
    LinkOAuthAccountRequest,
    link_oauth_account,
    unlink_oauth_account,
)
from ciris_engine.logic.adapters.api.services.auth_service import APIAuthService
from ciris_engine.logic.services.infrastructure.authentication import AuthenticationService
from ciris_engine.logic.services.lifecycle.time import TimeService
from ciris_engine.schemas.api.auth import AuthContext, UserRole
from ciris_engine.schemas.runtime.api import APIRole
from ciris_engine.schemas.services.authority_core import WACertificate, WARole


@pytest.mark.asyncio
async def test_link_and_unlink_oauth_account_route():
    # Set up authentication service with temporary database
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        db_path = tmp.name

    time_service = TimeService()
    auth_service = AuthenticationService(db_path=db_path, time_service=time_service, key_dir=None)
    await auth_service.start()

    try:
        private_key, public_key = auth_service.generate_keypair()
        wa = WACertificate(
            wa_id="wa-2025-06-24-API0A1",
            name="API User",
            role=WARole.AUTHORITY,
            pubkey=auth_service._encode_public_key(public_key),
            jwt_kid="api-user-kid",
            scopes_json='["read:any"]',
            created_at=datetime.now(timezone.utc),
        )
        await auth_service._store_wa_certificate(wa)

        api_auth_service = APIAuthService(auth_service=auth_service)
        await api_auth_service._process_wa_record(wa)

        auth_context = AuthContext(
            user_id=wa.wa_id,
            role=UserRole.SYSTEM_ADMIN,
            permissions=set(),
            api_key_id=None,
            session_id=None,
            authenticated_at=datetime.now(timezone.utc),
        )

        link_request = LinkOAuthAccountRequest(
            provider="google",
            external_id="google-foo",
            account_name="Google Foo",
            primary=True,
        )

        detail = await link_oauth_account(
            user_id=wa.wa_id,
            request=link_request,
            auth=auth_context,
            auth_service=api_auth_service,
        )

        assert any(acc.provider == "google" for acc in detail.linked_oauth_accounts)
        assert detail.linked_oauth_accounts[0].is_primary

        link_request = LinkOAuthAccountRequest(
            provider="discord",
            external_id="discord-bar",
            account_name="Discord Bar",
            metadata={"discriminator": "1234"},
            primary=False,
        )

        detail = await link_oauth_account(
            user_id=wa.wa_id,
            request=link_request,
            auth=auth_context,
            auth_service=api_auth_service,
        )

        assert any(acc.provider == "discord" for acc in detail.linked_oauth_accounts)

        detail = await unlink_oauth_account(
            user_id=wa.wa_id,
            provider="google",
            external_id="google-foo",
            auth=auth_context,
            auth_service=api_auth_service,
        )

        assert all(acc.provider != "google" for acc in detail.linked_oauth_accounts)

    finally:
        await auth_service.stop()
        os.unlink(db_path)
