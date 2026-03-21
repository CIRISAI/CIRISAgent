"""Tests for founding partnership startup migration.

Verifies that migrate_founding_partnerships() correctly backfills PARTNERED
consent GraphNodes for pre-existing ROOT Wise Authorities from earlier
releases that were created before the founding partnership feature (2.2.9).
"""

import json
import os
import tempfile
from unittest.mock import AsyncMock, MagicMock, patch

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


def _count_consent_nodes(db_path: str) -> int:
    """Count all consent graph nodes in the DB."""
    with get_db_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT COUNT(*) as cnt FROM graph_nodes WHERE node_id LIKE 'consent/%'"
        )
        return cursor.fetchone()["cnt"]


class _MockWA:
    """Mock Wise Authority certificate."""

    def __init__(self, name: str, role: str = "root"):
        from ciris_engine.schemas.services.authority_core import WARole

        self.name = name
        self.wa_id = f"wa-{name}"
        self.role = WARole(role)


def _make_runtime(was: list | None = None, auth_available: bool = True) -> MagicMock:
    """Build a mock runtime with configurable auth_service."""
    runtime = MagicMock()

    if not auth_available:
        runtime.service_initializer.auth_service = None
        return runtime

    auth_service = AsyncMock()
    auth_service.list_was = AsyncMock(return_value=was or [])
    runtime.service_initializer.auth_service = auth_service
    return runtime


class TestMigrateFoundingPartnerships:
    """Tests for migrate_founding_partnerships()."""

    @pytest.mark.asyncio
    async def test_skips_first_run(self, test_db):
        """Should skip migration during first-run mode."""
        from ciris_engine.logic.runtime.config_migration import migrate_founding_partnerships

        runtime = _make_runtime(was=[_MockWA("alice")])

        with patch("ciris_engine.logic.setup.first_run.is_first_run", return_value=True):
            await migrate_founding_partnerships(runtime)

        # No consent node should be created
        assert _get_consent_node(test_db, "alice") is None

    @pytest.mark.asyncio
    async def test_skips_when_auth_service_unavailable(self, test_db):
        """Should skip gracefully when auth service is not available."""
        from ciris_engine.logic.runtime.config_migration import migrate_founding_partnerships

        runtime = _make_runtime(auth_available=False)

        with patch("ciris_engine.logic.setup.first_run.is_first_run", return_value=False):
            await migrate_founding_partnerships(runtime)

        assert _count_consent_nodes(test_db) == 0

    @pytest.mark.asyncio
    async def test_skips_when_no_root_was(self, test_db):
        """Should do nothing when there are no ROOT WAs."""
        from ciris_engine.logic.runtime.config_migration import migrate_founding_partnerships

        runtime = _make_runtime(was=[
            _MockWA("observer1", role="observer"),
            _MockWA("authority1", role="authority"),
        ])

        with patch("ciris_engine.logic.setup.first_run.is_first_run", return_value=False):
            await migrate_founding_partnerships(runtime)

        assert _count_consent_nodes(test_db) == 0

    @pytest.mark.asyncio
    async def test_backfills_single_root_wa(self, test_db):
        """Should create a PARTNERED consent node for a ROOT WA without one."""
        from ciris_engine.logic.runtime.config_migration import migrate_founding_partnerships

        runtime = _make_runtime(was=[_MockWA("alice")])

        with patch("ciris_engine.logic.setup.first_run.is_first_run", return_value=False):
            await migrate_founding_partnerships(runtime)

        node = _get_consent_node(test_db, "alice")
        assert node is not None
        attrs = json.loads(node["attributes_json"])
        assert attrs["stream"] == "partnered"
        assert attrs["founding_partnership"] is True
        assert attrs["partnership_approved"] is True

    @pytest.mark.asyncio
    async def test_backfills_multiple_root_was(self, test_db):
        """Should backfill all ROOT WAs that lack consent nodes."""
        from ciris_engine.logic.runtime.config_migration import migrate_founding_partnerships

        runtime = _make_runtime(was=[
            _MockWA("alice"),
            _MockWA("bob"),
            _MockWA("observer1", role="observer"),
        ])

        with patch("ciris_engine.logic.setup.first_run.is_first_run", return_value=False):
            await migrate_founding_partnerships(runtime)

        assert _get_consent_node(test_db, "alice") is not None
        assert _get_consent_node(test_db, "bob") is not None
        assert _get_consent_node(test_db, "observer1") is None  # Not ROOT

    @pytest.mark.asyncio
    async def test_skips_existing_consent_node(self, test_db):
        """Should not overwrite a consent node that already exists."""
        from ciris_engine.logic.adapters.api.routes.setup.complete import _create_founding_partnership
        from ciris_engine.logic.runtime.config_migration import migrate_founding_partnerships

        # Pre-create a consent node for alice
        _create_founding_partnership("alice")

        original_node = _get_consent_node(test_db, "alice")
        assert original_node is not None
        original_version = original_node["version"]

        runtime = _make_runtime(was=[_MockWA("alice")])

        with patch("ciris_engine.logic.setup.first_run.is_first_run", return_value=False):
            await migrate_founding_partnerships(runtime)

        # Node should still exist with same version (not re-created)
        node_after = _get_consent_node(test_db, "alice")
        assert node_after is not None
        assert node_after["version"] == original_version

    @pytest.mark.asyncio
    async def test_mixed_existing_and_new(self, test_db):
        """Should only backfill ROOT WAs that are missing consent nodes."""
        from ciris_engine.logic.adapters.api.routes.setup.complete import _create_founding_partnership
        from ciris_engine.logic.runtime.config_migration import migrate_founding_partnerships

        # Alice already has a consent node (from setup wizard in 2.2.9)
        _create_founding_partnership("alice")

        # Bob is a pre-existing ROOT user from before 2.2.9
        runtime = _make_runtime(was=[_MockWA("alice"), _MockWA("bob")])

        with patch("ciris_engine.logic.setup.first_run.is_first_run", return_value=False):
            await migrate_founding_partnerships(runtime)

        # Both should have consent nodes now
        assert _get_consent_node(test_db, "alice") is not None
        assert _get_consent_node(test_db, "bob") is not None

        # But only bob was newly created
        bob_attrs = json.loads(_get_consent_node(test_db, "bob")["attributes_json"])
        assert bob_attrs["founding_partnership"] is True

    @pytest.mark.asyncio
    async def test_idempotent_double_run(self, test_db):
        """Running the migration twice should be safe and idempotent."""
        from ciris_engine.logic.runtime.config_migration import migrate_founding_partnerships

        runtime = _make_runtime(was=[_MockWA("alice")])

        with patch("ciris_engine.logic.setup.first_run.is_first_run", return_value=False):
            await migrate_founding_partnerships(runtime)
            await migrate_founding_partnerships(runtime)

        # Should still be exactly one consent node
        assert _count_consent_nodes(test_db) == 1

    @pytest.mark.asyncio
    async def test_handles_list_was_error(self, test_db):
        """Should handle auth_service.list_was() errors gracefully."""
        from ciris_engine.logic.runtime.config_migration import migrate_founding_partnerships

        runtime = _make_runtime()
        runtime.service_initializer.auth_service.list_was = AsyncMock(
            side_effect=Exception("DB connection failed")
        )

        with patch("ciris_engine.logic.setup.first_run.is_first_run", return_value=False):
            # Should not raise
            await migrate_founding_partnerships(runtime)

        assert _count_consent_nodes(test_db) == 0

    @pytest.mark.asyncio
    async def test_handles_individual_creation_error(self, test_db):
        """Should continue backfilling other users if one fails."""
        from ciris_engine.logic.runtime.config_migration import migrate_founding_partnerships

        runtime = _make_runtime(was=[_MockWA("alice"), _MockWA("bob")])

        call_count = 0
        original_fn = None

        def _fail_on_alice(user_id: str) -> None:
            nonlocal call_count
            call_count += 1
            if user_id == "alice":
                raise RuntimeError("Simulated failure for alice")
            # Call the real function for bob
            original_fn(user_id)

        from ciris_engine.logic.adapters.api.routes.setup import complete as complete_mod

        original_fn = complete_mod._create_founding_partnership

        with patch("ciris_engine.logic.setup.first_run.is_first_run", return_value=False):
            with patch(
                "ciris_engine.logic.adapters.api.routes.setup.complete._create_founding_partnership",
                side_effect=_fail_on_alice,
            ):
                await migrate_founding_partnerships(runtime)

        # alice failed, bob succeeded
        assert _get_consent_node(test_db, "alice") is None
        assert _get_consent_node(test_db, "bob") is not None

    @pytest.mark.asyncio
    async def test_admin_user_gets_partnership(self, test_db):
        """The default 'admin' user should also get a founding partnership."""
        from ciris_engine.logic.runtime.config_migration import migrate_founding_partnerships

        runtime = _make_runtime(was=[_MockWA("admin")])

        with patch("ciris_engine.logic.setup.first_run.is_first_run", return_value=False):
            await migrate_founding_partnerships(runtime)

        node = _get_consent_node(test_db, "admin")
        assert node is not None
        attrs = json.loads(node["attributes_json"])
        assert attrs["stream"] == "partnered"


class TestMigrationCalledFromAdapterMigration:
    """Verify migrate_founding_partnerships is chained from migrate_adapter_configs_to_graph."""

    @pytest.mark.asyncio
    async def test_called_from_adapter_migration(self):
        """migrate_adapter_configs_to_graph should call migrate_founding_partnerships."""
        from ciris_engine.logic.runtime.config_migration import migrate_adapter_configs_to_graph

        runtime = MagicMock()
        runtime.service_initializer.config_service = MagicMock()
        runtime.adapter_configs = {}

        with patch(
            "ciris_engine.logic.runtime.config_migration.migrate_founding_partnerships"
        ) as mock_mfp:
            with patch(
                "ciris_engine.logic.runtime.config_migration.migrate_tickets_config_to_graph"
            ):
                with patch(
                    "ciris_engine.logic.runtime.config_migration.migrate_cognitive_state_behaviors_to_graph"
                ):
                    await migrate_adapter_configs_to_graph(runtime)

            mock_mfp.assert_called_once_with(runtime)
