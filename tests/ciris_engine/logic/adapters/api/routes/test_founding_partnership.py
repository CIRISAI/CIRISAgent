"""Tests for founding partnership creation during setup wizard.

Verifies that _create_founding_partnership() correctly creates a PARTNERED
consent GraphNode for the setup user, mirroring the pattern from
_handle_partnership_accept() in partnership.py.

The founding partnership embodies "configured consistency, not bypassed
safeguards" — the Ally template's identity IS partnership, so creating the
PARTNERED record at setup is the same principle as skipping wakeup ceremony.
"""

import json
import os
import tempfile
from datetime import datetime, timezone
from unittest.mock import patch

import pytest

from ciris_engine.logic import persistence
from ciris_engine.logic.persistence import initialize_database
from ciris_engine.logic.persistence.db import core
from ciris_engine.logic.persistence.db.core import get_db_connection


@pytest.fixture
def test_db():
    """Create a temporary test database for each test."""
    fd, db_path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    os.chmod(db_path, 0o666)

    initialize_database(db_path)

    original_test_db_path = core._test_db_path
    core._test_db_path = db_path

    original_db_path = persistence._db_path if hasattr(persistence, "_db_path") else None
    persistence._db_path = db_path

    if hasattr(persistence, "_init_db"):
        persistence._init_db()

    yield db_path

    try:
        os.unlink(db_path)
    except OSError:
        pass

    core._test_db_path = original_test_db_path
    if original_db_path:
        persistence._db_path = original_db_path
        if hasattr(persistence, "_init_db"):
            persistence._init_db()


def _get_consent_node(db_path: str, user_id: str) -> dict | None:
    """Read a consent graph node from the DB by user_id."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM graph_nodes WHERE node_id = ? AND scope = 'local'",
            (f"consent/{user_id}",),
        )
        row = cursor.fetchone()
        if row is None:
            return None
        return dict(row)


class TestCreateFoundingPartnership:
    """Tests for _create_founding_partnership()."""

    def test_creates_consent_node(self, test_db):
        """Founding partnership creates a consent GraphNode in the DB."""
        from ciris_engine.logic.adapters.api.routes.setup.complete import _create_founding_partnership

        _create_founding_partnership("alice")

        node = _get_consent_node(test_db, "alice")
        assert node is not None, "Consent node should exist after _create_founding_partnership"
        assert node["node_id"] == "consent/alice"

    def test_node_type_is_consent(self, test_db):
        """The node type should be CONSENT."""
        from ciris_engine.logic.adapters.api.routes.setup.complete import _create_founding_partnership

        _create_founding_partnership("bob")

        node = _get_consent_node(test_db, "bob")
        assert node is not None
        assert node["node_type"] == "consent"

    def test_node_scope_is_local(self, test_db):
        """The node scope should be LOCAL."""
        from ciris_engine.logic.adapters.api.routes.setup.complete import _create_founding_partnership

        _create_founding_partnership("carol")

        node = _get_consent_node(test_db, "carol")
        assert node is not None
        assert node["scope"] == "local"

    def test_stream_is_partnered(self, test_db):
        """The consent stream should be PARTNERED."""
        from ciris_engine.logic.adapters.api.routes.setup.complete import _create_founding_partnership

        _create_founding_partnership("dave")

        node = _get_consent_node(test_db, "dave")
        assert node is not None
        attrs = json.loads(node["attributes_json"])
        assert attrs["stream"] == "partnered"

    def test_categories_include_core_consent(self, test_db):
        """Should include INTERACTION, PREFERENCE, and IMPROVEMENT categories."""
        from ciris_engine.logic.adapters.api.routes.setup.complete import _create_founding_partnership

        _create_founding_partnership("eve")

        node = _get_consent_node(test_db, "eve")
        assert node is not None
        attrs = json.loads(node["attributes_json"])
        assert "interaction" in attrs["categories"]
        assert "preference" in attrs["categories"]
        assert "improvement" in attrs["categories"]

    def test_does_not_expire(self, test_db):
        """PARTNERED consent should not have an expiry date."""
        from ciris_engine.logic.adapters.api.routes.setup.complete import _create_founding_partnership

        _create_founding_partnership("frank")

        node = _get_consent_node(test_db, "frank")
        assert node is not None
        attrs = json.loads(node["attributes_json"])
        assert attrs["expires_at"] is None

    def test_partnership_approved_flag(self, test_db):
        """The partnership_approved flag should be True."""
        from ciris_engine.logic.adapters.api.routes.setup.complete import _create_founding_partnership

        _create_founding_partnership("grace")

        node = _get_consent_node(test_db, "grace")
        assert node is not None
        attrs = json.loads(node["attributes_json"])
        assert attrs["partnership_approved"] is True

    def test_founding_partnership_flag(self, test_db):
        """The founding_partnership flag distinguishes from bilateral consent flow."""
        from ciris_engine.logic.adapters.api.routes.setup.complete import _create_founding_partnership

        _create_founding_partnership("heidi")

        node = _get_consent_node(test_db, "heidi")
        assert node is not None
        attrs = json.loads(node["attributes_json"])
        assert attrs["founding_partnership"] is True

    def test_no_approval_task_id(self, test_db):
        """Founding partnership has no approval task — setup IS the consent act."""
        from ciris_engine.logic.adapters.api.routes.setup.complete import _create_founding_partnership

        _create_founding_partnership("ivan")

        node = _get_consent_node(test_db, "ivan")
        assert node is not None
        attrs = json.loads(node["attributes_json"])
        assert attrs["approval_task_id"] is None

    def test_updated_by_is_setup_wizard(self, test_db):
        """The node should be attributed to setup_wizard."""
        from ciris_engine.logic.adapters.api.routes.setup.complete import _create_founding_partnership

        _create_founding_partnership("judy")

        node = _get_consent_node(test_db, "judy")
        assert node is not None
        assert node["updated_by"] == "setup_wizard"

    def test_granted_at_is_recent(self, test_db):
        """The granted_at timestamp should be close to now."""
        from ciris_engine.logic.adapters.api.routes.setup.complete import _create_founding_partnership

        before = datetime.now(timezone.utc)
        _create_founding_partnership("karl")
        after = datetime.now(timezone.utc)

        node = _get_consent_node(test_db, "karl")
        assert node is not None
        attrs = json.loads(node["attributes_json"])
        granted = datetime.fromisoformat(attrs["granted_at"])
        assert before <= granted <= after

    def test_idempotent_call(self, test_db):
        """Calling twice for the same user should merge (not duplicate)."""
        from ciris_engine.logic.adapters.api.routes.setup.complete import _create_founding_partnership

        _create_founding_partnership("laura")
        _create_founding_partnership("laura")

        # Should still be exactly one node
        with get_db_connection(test_db) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) as cnt FROM graph_nodes WHERE node_id = ?",
                ("consent/laura",),
            )
            count = cursor.fetchone()["cnt"]
        assert count == 1

    def test_different_users_get_separate_nodes(self, test_db):
        """Each user gets their own consent node."""
        from ciris_engine.logic.adapters.api.routes.setup.complete import _create_founding_partnership

        _create_founding_partnership("mike")
        _create_founding_partnership("nancy")

        mike_node = _get_consent_node(test_db, "mike")
        nancy_node = _get_consent_node(test_db, "nancy")
        assert mike_node is not None
        assert nancy_node is not None
        assert mike_node["node_id"] != nancy_node["node_id"]

    def test_impact_score_starts_at_zero(self, test_db):
        """New founding partnership has zero impact score."""
        from ciris_engine.logic.adapters.api.routes.setup.complete import _create_founding_partnership

        _create_founding_partnership("oscar")

        node = _get_consent_node(test_db, "oscar")
        assert node is not None
        attrs = json.loads(node["attributes_json"])
        assert attrs["impact_score"] == 0.0
        assert attrs["attribution_count"] == 0


class TestFoundingPartnershipInSetupFlow:
    """Integration-style tests verifying the partnership is created during setup."""

    @pytest.mark.asyncio
    async def test_create_setup_users_calls_founding_partnership(self, test_db):
        """_create_setup_users should call _create_founding_partnership."""
        from ciris_engine.logic.adapters.api.routes.setup.complete import _create_setup_users
        from ciris_engine.logic.adapters.api.routes.setup.models import SetupCompleteRequest

        setup = SetupCompleteRequest(
            admin_username="test_setup_user",
            admin_password="TestPassword123!",
            llm_provider="openai",
            llm_api_key="sk-test",
            llm_model="gpt-4",
            template_id="ally",
            enabled_adapters=["api"],
        )

        with patch("ciris_engine.logic.adapters.api.routes.setup.complete._create_founding_partnership") as mock_fp:
            # AuthenticationService is imported inside the function body, so we
            # must patch it at the source module, not the complete module
            with patch(
                "ciris_engine.logic.services.infrastructure.authentication.service.AuthenticationService"
            ) as MockAuth:
                mock_auth_instance = MockAuth.return_value
                mock_auth_instance.start = _async_noop
                mock_auth_instance.stop = _async_noop
                mock_auth_instance.get_wa_by_oauth = _async_none
                mock_auth_instance.list_was = _async_empty_list
                mock_auth_instance.create_wa = _async_mock_wa_cert
                mock_auth_instance.hash_password = lambda p: "hashed"
                mock_auth_instance.update_wa = _async_noop
                mock_auth_instance.ensure_system_wa_exists = _async_system_wa

                await _create_setup_users(setup, test_db)

            # _create_founding_partnership is called with wa_cert.wa_id, not username
            # The mock returns wa_id = "wa-test-001"
            mock_fp.assert_called_once_with("wa-test-001")

    @pytest.mark.asyncio
    async def test_setup_flow_creates_actual_node(self, test_db):
        """Full setup flow actually persists the founding partnership node."""
        from ciris_engine.logic.adapters.api.routes.setup.complete import _create_setup_users
        from ciris_engine.logic.adapters.api.routes.setup.models import SetupCompleteRequest

        setup = SetupCompleteRequest(
            admin_username="real_setup_user",
            admin_password="TestPassword123!",
            llm_provider="openai",
            llm_api_key="sk-test",
            llm_model="gpt-4",
            template_id="ally",
            enabled_adapters=["api"],
        )

        with patch(
            "ciris_engine.logic.services.infrastructure.authentication.service.AuthenticationService"
        ) as MockAuth:
            mock_auth_instance = MockAuth.return_value
            mock_auth_instance.start = _async_noop
            mock_auth_instance.stop = _async_noop
            mock_auth_instance.get_wa_by_oauth = _async_none
            mock_auth_instance.list_was = _async_empty_list
            mock_auth_instance.create_wa = _async_mock_wa_cert
            mock_auth_instance.hash_password = lambda p: "hashed"
            mock_auth_instance.update_wa = _async_noop
            mock_auth_instance.ensure_system_wa_exists = _async_system_wa

            await _create_setup_users(setup, test_db)

        # Verify the node was actually persisted
        # The mock WA has wa_id = "wa-test-001", so node is at consent/wa-test-001
        node = _get_consent_node(test_db, "wa-test-001")
        assert node is not None, "Setup flow should create founding partnership node"
        attrs = json.loads(node["attributes_json"])
        assert attrs["stream"] == "partnered"
        assert attrs["founding_partnership"] is True
        assert attrs["partnership_approved"] is True


# -- Async helper stubs for mocking auth service --


async def _async_noop(*args, **kwargs):
    pass


async def _async_none(*args, **kwargs):
    return None


async def _async_empty_list(*args, **kwargs):
    return []


class _MockWACert:
    wa_id = "wa-test-001"
    name = "test_user"
    role = "ROOT"


async def _async_mock_wa_cert(*args, **kwargs):
    return _MockWACert()


async def _async_system_wa(*args, **kwargs):
    return "wa-system-001"
