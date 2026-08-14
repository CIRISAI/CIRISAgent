"""Long-jump upgrade recovery: legacy `wa_cert` rows must reach the live store.

Context: pre-2.9.0 `authentication_store` took an explicit `db_path` and the
caller passed the AUDIT database, so `wa_cert` rows live in `ciris_audit.db`.
From 2.9.0 the store reads the persist engine (`cirislens_wa_cert`, main DB).
An agent upgraded straight from 2.7.x boots GREEN with both listeners at 200
and zero incidents, while the pre-existing owner cannot log in — a READ-PATH
mismatch, not data loss.

The contract these tests lock:
  1. legacy rows import, `password_hash` byte-for-byte intact
  2. a second pass imports nothing
  3. an absent legacy DB is a no-op, not an error
  4. a row already in the destination is never overwritten
  5. the migration never raises out to the caller
"""

import base64
import sqlite3
from typing import Any, Dict, List, Optional
from unittest.mock import patch

import pytest

from ciris_engine.logic.persistence.stores import wa_cert_legacy_migration as migration
from ciris_engine.schemas.services.authority_core import WACertificate

# A real PBKDF2 base64(salt||key) shape: 32-byte salt + 32-byte key = 88 b64 chars.
REAL_HASH = base64.b64encode(bytes(range(32)) + bytes(range(32, 64))).decode()

OWNER_ID = "wa-2026-08-14-078CA6"
AUTHORITY_ID = "wa-2026-08-14-2F77D1"
OBSERVER_ID = "wa-2026-08-14-84F137"


LEGACY_DDL = """
CREATE TABLE wa_cert (
  wa_id              TEXT PRIMARY KEY,
  name               TEXT NOT NULL,
  role               TEXT CHECK(role IN ('root','authority','observer')),
  pubkey             TEXT NOT NULL,
  jwt_kid            TEXT NOT NULL UNIQUE,
  password_hash      TEXT,
  api_key_hash       TEXT,
  oauth_provider     TEXT,
  oauth_external_id  TEXT,
  oauth_links_json   TEXT,
  veilid_id          TEXT,
  auto_minted        INTEGER DEFAULT 0,
  parent_wa_id       TEXT,
  parent_signature   TEXT,
  scopes_json        TEXT NOT NULL,
  custom_permissions_json TEXT,
  adapter_id         TEXT,
  adapter_name       TEXT,
  adapter_metadata_json TEXT,
  token_type         TEXT DEFAULT 'standard',
  created            TEXT NOT NULL,
  last_login         TEXT,
  active             INTEGER DEFAULT 1,
  FOREIGN KEY (parent_wa_id) REFERENCES wa_cert(wa_id)
)
"""


def _legacy_row(
    wa_id: str = OWNER_ID,
    name: str = "jeff",
    role: str = "root",
    password_hash: Optional[str] = REAL_HASH,
    parent_wa_id: Optional[str] = None,
    active: int = 1,
    adapter_id: Optional[str] = None,
) -> Dict[str, Any]:
    """One row shaped exactly like the 2.7.x fixture."""
    suffix = wa_id[-6:].lower()
    return {
        "wa_id": wa_id,
        "name": name,
        "role": role,
        "pubkey": "pobo8itVDw9o_ULToxiWasdFLePdvzYVH3QRHtkyAHo",
        "jwt_kid": f"wa-jwt-{suffix}",
        "password_hash": password_hash,
        "api_key_hash": None,
        "oauth_provider": None,
        "oauth_external_id": None,
        "oauth_links_json": None,
        "veilid_id": None,
        "auto_minted": 0,
        "parent_wa_id": parent_wa_id,
        "parent_signature": None,
        "scopes_json": '["read:any", "write:any"]',
        "custom_permissions_json": None,
        "adapter_id": adapter_id,
        "adapter_name": None,
        "adapter_metadata_json": None,
        "token_type": "standard",
        "created": "2026-08-14T19:56:41.039056+00:00",
        "last_login": None,
        "active": active,
    }


def _write_legacy_db(path: str, rows: List[Dict[str, Any]]) -> None:
    conn = sqlite3.connect(path)
    try:
        conn.execute(LEGACY_DDL)
        for row in rows:
            cols = ", ".join(row.keys())
            marks = ", ".join("?" for _ in row)
            conn.execute(f"INSERT INTO wa_cert ({cols}) VALUES ({marks})", tuple(row.values()))
        conn.commit()
    finally:
        conn.close()


class FakeDestination:
    """Stand-in for the persist-backed authentication_store.

    Mirrors the two behaviors the migration relies on: `list_wa_certificates`
    returns active certs, and `store_wa_certificate` REFUSES to overwrite an
    existing wa_id (the real store raises ValueError there).
    """

    def __init__(self, seed: Optional[List[WACertificate]] = None) -> None:
        self.certs: Dict[str, WACertificate] = {c.wa_id: c for c in (seed or [])}
        self.store_calls: List[str] = []

    def list_wa_certificates(self, active_only: bool) -> List[WACertificate]:
        return list(self.certs.values())

    def store_wa_certificate(self, wa: WACertificate) -> None:
        self.store_calls.append(wa.wa_id)
        if wa.wa_id in self.certs:
            raise ValueError(f"WA certificate {wa.wa_id} already exists")
        self.certs[wa.wa_id] = wa


@pytest.fixture
def dest() -> FakeDestination:
    return FakeDestination()


STORE = "ciris_engine.logic.persistence.stores.authentication_store"


def _run_with_store(
    legacy_paths: List[str], list_impl: Any, store_impl: Any
) -> migration.WACertMigrationResult:
    """Run the migration against explicit legacy paths and a stubbed store."""
    with patch.object(migration, "_candidate_legacy_paths", return_value=legacy_paths), patch(
        f"{STORE}.list_wa_certificates", side_effect=list_impl
    ), patch(f"{STORE}.store_wa_certificate", side_effect=store_impl):
        return migration.migrate_legacy_wa_certificates(None)


def _run(legacy_paths: List[str], dest: FakeDestination) -> migration.WACertMigrationResult:
    """Run the migration against explicit legacy paths and a fake destination."""
    return _run_with_store(legacy_paths, dest.list_wa_certificates, dest.store_wa_certificate)


# --------------------------------------------------------------------------- #
# 1. Legacy rows import, hash intact                                           #
# --------------------------------------------------------------------------- #


class TestImportsLegacyRows:
    def test_rows_import_with_hash_byte_for_byte(self, tmp_path, dest):
        legacy = str(tmp_path / "ciris_audit.db")
        _write_legacy_db(legacy, [_legacy_row()])

        result = _run([legacy], dest)

        assert result.found == 1
        assert result.imported == 1
        assert result.imported_ids == [OWNER_ID]
        assert dest.certs[OWNER_ID].name == "jeff"
        # The whole point: an altered hash means the owner still can't log in.
        assert dest.certs[OWNER_ID].password_hash == REAL_HASH

    def test_full_fixture_shape_imports_every_active_row(self, tmp_path, dest):
        legacy = str(tmp_path / "ciris_audit.db")
        _write_legacy_db(
            legacy,
            [
                _legacy_row(),
                _legacy_row(AUTHORITY_ID, "CIRIS System Authority", "authority", None, parent_wa_id=OWNER_ID),
                _legacy_row(OBSERVER_ID, "cirisverify_observer", "observer", None, adapter_id="cirisverify_default"),
            ],
        )

        result = _run([legacy], dest)

        assert result.imported == 3
        assert set(dest.certs) == {OWNER_ID, AUTHORITY_ID, OBSERVER_ID}
        assert dest.certs[AUTHORITY_ID].parent_wa_id == OWNER_ID

    def test_parent_is_inserted_before_child(self, tmp_path, dest):
        """The destination declares an FK on parent_wa_id — order matters."""
        legacy = str(tmp_path / "ciris_audit.db")
        # Child listed FIRST in the legacy table, to prove we reorder.
        _write_legacy_db(
            legacy,
            [
                _legacy_row(AUTHORITY_ID, "CIRIS System Authority", "authority", None, parent_wa_id=OWNER_ID),
                _legacy_row(),
            ],
        )

        _run([legacy], dest)

        assert dest.store_calls.index(OWNER_ID) < dest.store_calls.index(AUTHORITY_ID)

    def test_revoked_rows_are_not_resurrected(self, tmp_path, dest):
        """store_wa_certificate always writes active=True; importing a revoked
        row would silently un-revoke it."""
        legacy = str(tmp_path / "ciris_audit.db")
        _write_legacy_db(legacy, [_legacy_row(active=0)])

        result = _run([legacy], dest)

        assert result.imported == 0
        assert result.skipped_inactive == 1
        assert dest.certs == {}

    def test_same_file_twice_is_scanned_once(self, tmp_path, dest):
        """audit and main configured to the same path must not double-import."""
        legacy = str(tmp_path / "ciris_engine.db")
        _write_legacy_db(legacy, [_legacy_row()])

        # Bypass the patch on _candidate_legacy_paths to exercise real dedup.
        with patch(
            "ciris_engine.logic.config.db_paths.get_audit_db_full_path", return_value=legacy
        ), patch("ciris_engine.logic.config.db_paths.get_sqlite_db_full_path", return_value=legacy):
            paths = migration._candidate_legacy_paths(None)

        assert paths == [legacy]

        result = _run(paths, dest)
        assert result.found == 1
        assert result.imported == 1


# --------------------------------------------------------------------------- #
# 2. Idempotent — a second pass imports nothing                                #
# --------------------------------------------------------------------------- #


class TestIdempotent:
    def test_second_run_imports_nothing(self, tmp_path, dest):
        legacy = str(tmp_path / "ciris_audit.db")
        _write_legacy_db(legacy, [_legacy_row(), _legacy_row(OBSERVER_ID, "observer1", "observer", None)])

        first = _run([legacy], dest)
        assert first.imported == 2

        second = _run([legacy], dest)
        assert second.found == 2
        assert second.imported == 0
        assert second.skipped_existing == 2
        assert second.imported_ids == []
        # Destination untouched, hash still the original.
        assert dest.certs[OWNER_ID].password_hash == REAL_HASH


# --------------------------------------------------------------------------- #
# 3. Absent legacy DB is a no-op, not an error                                 #
# --------------------------------------------------------------------------- #


class TestAbsentLegacyDatabase:
    def test_missing_file_is_a_noop(self, tmp_path, dest):
        result = _run([str(tmp_path / "does_not_exist.db")], dest)

        assert result.error is None
        assert result.found == 0
        assert result.imported == 0
        assert dest.certs == {}

    def test_missing_file_is_not_created(self, tmp_path, dest):
        """A plain sqlite3.connect would CREATE the file, turning 'fresh
        install' into 'empty legacy database on disk forever'."""
        missing = tmp_path / "does_not_exist.db"
        _run([str(missing)], dest)
        assert not missing.exists()

    def test_database_without_wa_cert_table_is_a_noop(self, tmp_path, dest):
        legacy = tmp_path / "ciris_audit.db"
        conn = sqlite3.connect(str(legacy))
        conn.execute("CREATE TABLE audit_log (id INTEGER PRIMARY KEY)")
        conn.commit()
        conn.close()

        result = _run([str(legacy)], dest)

        assert result.error is None
        assert result.found == 0
        assert result.imported == 0

    def test_empty_wa_cert_table_is_a_noop(self, tmp_path, dest):
        legacy = str(tmp_path / "ciris_audit.db")
        _write_legacy_db(legacy, [])

        result = _run([legacy], dest)

        assert result.error is None
        assert result.imported == 0

    def test_postgres_dsn_is_skipped(self):
        with patch(
            "ciris_engine.logic.config.db_paths.get_audit_db_full_path",
            return_value="postgresql://u:p@h:5432/db_auth",
        ), patch(
            "ciris_engine.logic.config.db_paths.get_sqlite_db_full_path",
            return_value="postgresql://u:p@h:5432/db",
        ):
            assert migration._candidate_legacy_paths(None) == []


# --------------------------------------------------------------------------- #
# 4. An existing destination row is never overwritten                          #
# --------------------------------------------------------------------------- #


class TestNeverOverwrites:
    def test_existing_row_is_left_alone(self, tmp_path):
        """A live cert with a NEWER password must survive an older legacy row."""
        live = WACertificate(
            wa_id=OWNER_ID,
            name="jeff",
            role="root",
            pubkey="live-pubkey",
            jwt_kid="wa-jwt-live",
            password_hash="NEWER-HASH-DO-NOT-CLOBBER",
            scopes_json='["read:any"]',
            created_at="2026-08-20T00:00:00+00:00",
        )
        dest = FakeDestination([live])

        legacy = str(tmp_path / "ciris_audit.db")
        _write_legacy_db(legacy, [_legacy_row()])

        result = _run([legacy], dest)

        assert result.imported == 0
        assert result.skipped_existing == 1
        assert dest.certs[OWNER_ID].password_hash == "NEWER-HASH-DO-NOT-CLOBBER"
        assert dest.certs[OWNER_ID].jwt_kid == "wa-jwt-live"

    def test_jwt_kid_collision_is_not_imported(self, tmp_path):
        """jwt_kid is UNIQUE in the destination; a colliding legacy row must
        not be pushed at it."""
        live = WACertificate(
            wa_id="wa-2026-08-20-AAAAAA",
            name="live",
            role="root",
            pubkey="live-pubkey",
            jwt_kid="wa-jwt-078ca6",  # same kid the legacy owner row carries
            scopes_json="[]",
            created_at="2026-08-20T00:00:00+00:00",
        )
        dest = FakeDestination([live])

        legacy = str(tmp_path / "ciris_audit.db")
        _write_legacy_db(legacy, [_legacy_row()])

        result = _run([legacy], dest)

        assert result.imported == 0
        assert result.skipped_existing == 1
        assert OWNER_ID not in dest.certs

    def test_inactive_destination_row_is_not_revived(self, tmp_path):
        """A destination row that exists but is inactive won't appear in the
        active-only listing; the store's own ValueError must be honored."""
        dest = FakeDestination()
        # Seed directly so it is NOT in list_wa_certificates' output.
        hidden = WACertificate(
            wa_id=OWNER_ID,
            name="jeff",
            role="root",
            pubkey="p",
            jwt_kid="wa-jwt-hidden",
            scopes_json="[]",
            created_at="2026-08-20T00:00:00+00:00",
        )

        legacy = str(tmp_path / "ciris_audit.db")
        _write_legacy_db(legacy, [_legacy_row()])

        def _refuse(wa: WACertificate) -> None:
            raise ValueError("already exists")

        result = _run_with_store([legacy], lambda active_only: [], _refuse)

        assert result.imported == 0
        assert result.skipped_existing == 1
        assert hidden.wa_id == OWNER_ID  # sanity: same id we tried to import


# --------------------------------------------------------------------------- #
# 5. The migration never raises out to the caller                              #
# --------------------------------------------------------------------------- #


class TestNeverRaises:
    def test_destination_store_exploding_does_not_raise(self, tmp_path, dest):
        legacy = str(tmp_path / "ciris_audit.db")
        _write_legacy_db(legacy, [_legacy_row()])

        def _explode(active_only: bool) -> List[WACertificate]:
            raise RuntimeError("persist engine not initialized")

        result = _run_with_store([legacy], _explode, dest.store_wa_certificate)

        assert result.error is not None
        assert result.imported == 0

    def test_single_row_write_failure_does_not_abort_the_rest(self, tmp_path):
        dest = FakeDestination()
        calls = {"n": 0}

        def flaky(wa: WACertificate) -> None:
            calls["n"] += 1
            if wa.wa_id == OWNER_ID:
                raise sqlite3.IntegrityError("FOREIGN KEY constraint failed")
            dest.certs[wa.wa_id] = wa

        legacy = str(tmp_path / "ciris_audit.db")
        _write_legacy_db(legacy, [_legacy_row(), _legacy_row(OBSERVER_ID, "obs", "observer", None)])

        result = _run_with_store([legacy], lambda active_only: [], flaky)

        assert result.imported == 1
        assert result.imported_ids == [OBSERVER_ID]
        assert result.skipped_unreadable == 1

    def test_corrupt_row_is_skipped_not_fatal(self, tmp_path, dest):
        """A wa_id that isn't a classic WA id fails WACertificate validation."""
        legacy = str(tmp_path / "ciris_audit.db")
        bad = _legacy_row(wa_id="wa-root-node-lowercase-thing", name="node-owner", password_hash=None)
        _write_legacy_db(legacy, [bad, _legacy_row()])

        result = _run([legacy], dest)

        assert result.found == 2
        assert result.skipped_unreadable == 1
        assert result.imported == 1
        assert list(dest.certs) == [OWNER_ID]

    def test_unreadable_file_does_not_raise(self, tmp_path, dest):
        junk = tmp_path / "ciris_audit.db"
        junk.write_bytes(b"this is not a sqlite database at all, not even close")

        result = _run([str(junk)], dest)

        assert result.error is None
        assert result.imported == 0

    def test_config_resolution_failure_does_not_raise(self, dest):
        with patch(
            "ciris_engine.logic.config.db_paths.get_audit_db_full_path",
            side_effect=RuntimeError("no config service"),
        ), patch(
            "ciris_engine.logic.config.db_paths.get_sqlite_db_full_path",
            side_effect=RuntimeError("no config service"),
        ):
            result = migration.migrate_legacy_wa_certificates(None)

        assert result.error is None
        assert result.imported == 0


# --------------------------------------------------------------------------- #
# Boot hook: the service initializer must survive a broken migration           #
# --------------------------------------------------------------------------- #


class TestBootHookIsNonFatal:
    def test_initializer_swallows_migration_import_failure(self):
        from ciris_engine.logic.runtime.service_initializer import ServiceInitializer

        init = ServiceInitializer.__new__(ServiceInitializer)
        init.essential_config = None  # type: ignore[attr-defined]

        with patch.object(
            migration, "migrate_legacy_wa_certificates", side_effect=RuntimeError("boom")
        ):
            # Must not propagate — an agent that won't start is worse than
            # one whose owner must re-run setup.
            init._recover_stranded_wa_certificates()

    def test_initializer_invokes_the_migration(self):
        from ciris_engine.logic.runtime.service_initializer import ServiceInitializer

        init = ServiceInitializer.__new__(ServiceInitializer)
        init.essential_config = None  # type: ignore[attr-defined]

        with patch.object(migration, "migrate_legacy_wa_certificates") as mock_migrate:
            init._recover_stranded_wa_certificates()

        mock_migrate.assert_called_once()
