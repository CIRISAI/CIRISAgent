"""
Comprehensive test suite for key_migration.py.

Tests cover:
- MigrationResult dataclass
- AuditEntry dataclass
- AuditKeyMigration class methods
- Backup/restore functionality
- Database operations
"""

import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from ciris_engine.logic.audit.key_migration import (
    AuditEntry,
    AuditKeyMigration,
    MigrationResult,
    migrate_audit_key_to_ed25519,
)


class MockTimeService:
    """Mock time service for testing."""

    def __init__(self):
        self.current_time = datetime(2024, 6, 15, 12, 0, 0, tzinfo=timezone.utc)

    def now_iso(self) -> str:
        """Return current mock time as ISO string."""
        return self.current_time.isoformat()


class MockUnifiedKey:
    """Mock unified signing key for testing."""

    def __init__(self, key_id: str = "agent-test123456"):
        self.key_id = key_id
        self.public_key_base64 = "dGVzdHB1YmxpY2tleWJhc2U2NA=="

    def sign(self, data: bytes) -> bytes:
        """Mock sign - return deterministic signature."""
        return b"mocksignature" + data[:20]

    def verify(self, data: bytes, signature: bytes) -> bool:
        """Mock verify - check if signature matches our mock format."""
        expected = b"mocksignature" + data[:20]
        return signature == expected


@pytest.fixture
def mock_time_service():
    """Create mock time service."""
    return MockTimeService()


@pytest.fixture
def temp_db():
    """Create temporary database with audit tables."""
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name

    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    # Create audit_entries table
    cursor.execute(
        """
        CREATE TABLE audit_entries (
            sequence_number INTEGER PRIMARY KEY,
            entry_hash TEXT NOT NULL,
            previous_hash TEXT NOT NULL,
            signature TEXT NOT NULL,
            key_id TEXT NOT NULL,
            timestamp TEXT NOT NULL,
            event_type TEXT NOT NULL,
            event_data TEXT
        )
    """
    )

    # Create audit_signing_keys table
    cursor.execute(
        """
        CREATE TABLE audit_signing_keys (
            key_id TEXT PRIMARY KEY,
            public_key TEXT NOT NULL,
            algorithm TEXT NOT NULL,
            key_size INTEGER NOT NULL,
            created_at TEXT NOT NULL,
            revoked_at TEXT
        )
    """
    )

    conn.commit()
    conn.close()

    yield db_path
    Path(db_path).unlink(missing_ok=True)


@pytest.fixture
def temp_key_dir():
    """Create temporary key directory."""
    with tempfile.TemporaryDirectory() as temp_dir:
        yield Path(temp_dir)


@pytest.fixture
def populated_db(temp_db):
    """Create database with test entries and RSA key."""
    conn = sqlite3.connect(temp_db)
    cursor = conn.cursor()

    # Add RSA signing key
    cursor.execute(
        """
        INSERT INTO audit_signing_keys (key_id, public_key, algorithm, key_size, created_at)
        VALUES ('rsa-oldkey123', 'old_public_key', 'rsa_2048', 2048, '2024-01-01T00:00:00Z')
    """
    )

    # Add audit entries
    previous_hash = "GENESIS"
    for i in range(1, 6):
        entry_hash = f"hash_{i}"
        cursor.execute(
            """
            INSERT INTO audit_entries
            (sequence_number, entry_hash, previous_hash, signature, key_id, timestamp, event_type, event_data)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                i,
                entry_hash,
                previous_hash,
                f"signature_{i}",
                "rsa-oldkey123",
                f"2024-01-0{i}T12:00:00Z",
                "test_event",
                f'{{"action": "test_{i}"}}',
            ),
        )
        previous_hash = entry_hash

    conn.commit()
    conn.close()

    return temp_db


class TestMigrationResult:
    """Test MigrationResult dataclass."""

    def test_default_values(self):
        """Test MigrationResult default values."""
        result = MigrationResult(success=False, message="test")

        assert result.success is False
        assert result.message == "test"
        assert result.entries_migrated == 0
        assert result.old_key_id is None
        assert result.new_key_id is None
        assert result.backup_path is None
        assert result.errors == []

    def test_with_all_values(self):
        """Test MigrationResult with all values set."""
        result = MigrationResult(
            success=True,
            message="Migration complete",
            entries_migrated=100,
            old_key_id="old-key",
            new_key_id="new-key",
            backup_path="/backups/backup1",
            errors=["warning1"],
        )

        assert result.success is True
        assert result.entries_migrated == 100
        assert result.old_key_id == "old-key"
        assert result.new_key_id == "new-key"
        assert result.backup_path == "/backups/backup1"
        assert result.errors == ["warning1"]


class TestAuditEntry:
    """Test AuditEntry dataclass."""

    def test_create_entry(self):
        """Test creating AuditEntry."""
        entry = AuditEntry(
            sequence_number=1,
            entry_hash="hash123",
            previous_hash="GENESIS",
            signature="sig123",
            key_id="key-abc",
            timestamp="2024-06-15T12:00:00Z",
            event_type="test",
            event_data='{"key": "value"}',
        )

        assert entry.sequence_number == 1
        assert entry.entry_hash == "hash123"
        assert entry.previous_hash == "GENESIS"
        assert entry.signature == "sig123"
        assert entry.key_id == "key-abc"
        assert entry.timestamp == "2024-06-15T12:00:00Z"
        assert entry.event_type == "test"
        assert entry.event_data == '{"key": "value"}'


class TestAuditKeyMigration:
    """Test AuditKeyMigration class."""

    def test_init(self, temp_db, temp_key_dir, mock_time_service):
        """Test initialization."""
        migration = AuditKeyMigration(temp_db, str(temp_key_dir), mock_time_service)

        assert migration.db_path == Path(temp_db)
        assert migration.key_path == Path(temp_key_dir)
        assert migration.time_service == mock_time_service
        assert migration._backup_path is None

    def test_get_current_key_info_no_key(self, temp_db, temp_key_dir, mock_time_service):
        """Test getting key info when no key exists."""
        migration = AuditKeyMigration(temp_db, str(temp_key_dir), mock_time_service)

        result = migration._get_current_key_info()
        assert result is None

    def test_get_current_key_info_with_rsa_key(self, populated_db, temp_key_dir, mock_time_service):
        """Test getting key info with existing RSA key."""
        migration = AuditKeyMigration(populated_db, str(temp_key_dir), mock_time_service)

        result = migration._get_current_key_info()
        assert result is not None
        key_id, algorithm = result
        assert key_id == "rsa-oldkey123"
        assert algorithm == "rsa_2048"

    def test_load_all_entries(self, populated_db, temp_key_dir, mock_time_service):
        """Test loading all audit entries."""
        migration = AuditKeyMigration(populated_db, str(temp_key_dir), mock_time_service)

        entries = migration._load_all_entries()

        assert len(entries) == 5
        assert entries[0].sequence_number == 1
        assert entries[0].previous_hash == "GENESIS"
        assert entries[-1].sequence_number == 5

    def test_load_all_entries_empty(self, temp_db, temp_key_dir, mock_time_service):
        """Test loading entries from empty database."""
        migration = AuditKeyMigration(temp_db, str(temp_key_dir), mock_time_service)

        entries = migration._load_all_entries()
        assert entries == []

    def test_resign_entries(self, populated_db, temp_key_dir, mock_time_service):
        """Test re-signing entries with new key."""
        migration = AuditKeyMigration(populated_db, str(temp_key_dir), mock_time_service)
        entries = migration._load_all_entries()
        mock_key = MockUnifiedKey()

        migrated = migration._resign_entries(entries, mock_key)

        assert len(migrated) == 5
        # All entries should have new key_id
        for entry in migrated:
            assert entry.key_id == mock_key.key_id
        # Hash chain should be maintained
        assert migrated[0].previous_hash == "GENESIS"
        for i in range(1, len(migrated)):
            assert migrated[i].previous_hash == migrated[i - 1].entry_hash

    def test_update_database(self, populated_db, temp_key_dir, mock_time_service):
        """Test updating database with migrated entries."""
        migration = AuditKeyMigration(populated_db, str(temp_key_dir), mock_time_service)
        entries = migration._load_all_entries()
        mock_key = MockUnifiedKey()
        migrated = migration._resign_entries(entries, mock_key)

        # Update database
        migration._update_database(migrated)

        # Verify changes
        conn = sqlite3.connect(populated_db)
        cursor = conn.cursor()
        cursor.execute("SELECT key_id FROM audit_entries WHERE sequence_number = 1")
        result = cursor.fetchone()
        conn.close()

        assert result[0] == mock_key.key_id

    def test_register_ed25519_key(self, temp_db, temp_key_dir, mock_time_service):
        """Test registering new Ed25519 key."""
        migration = AuditKeyMigration(temp_db, str(temp_key_dir), mock_time_service)
        mock_key = MockUnifiedKey()

        migration._register_ed25519_key(mock_key)

        # Verify key was registered
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT algorithm, key_size FROM audit_signing_keys WHERE key_id = ?", (mock_key.key_id,))
        result = cursor.fetchone()
        conn.close()

        assert result is not None
        assert result[0] == "ed25519"
        assert result[1] == 256

    def test_register_ed25519_key_idempotent(self, temp_db, temp_key_dir, mock_time_service):
        """Test registering same key twice is idempotent."""
        migration = AuditKeyMigration(temp_db, str(temp_key_dir), mock_time_service)
        mock_key = MockUnifiedKey()

        # Register twice - should not raise
        migration._register_ed25519_key(mock_key)
        migration._register_ed25519_key(mock_key)

        # Verify only one entry
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM audit_signing_keys WHERE key_id = ?", (mock_key.key_id,))
        count = cursor.fetchone()[0]
        conn.close()

        assert count == 1

    def test_archive_old_key(self, populated_db, temp_key_dir, mock_time_service):
        """Test archiving old RSA key."""
        migration = AuditKeyMigration(populated_db, str(temp_key_dir), mock_time_service)

        migration._archive_old_key("rsa-oldkey123")

        # Verify key was marked as revoked/migrated
        conn = sqlite3.connect(populated_db)
        cursor = conn.cursor()
        cursor.execute("SELECT revoked_at FROM audit_signing_keys WHERE key_id = ?", ("rsa-oldkey123",))
        result = cursor.fetchone()
        conn.close()

        assert result is not None
        assert "MIGRATED_TO_ED25519" in result[0]

    def test_create_backup(self, populated_db, temp_key_dir, mock_time_service):
        """Test backup creation."""
        migration = AuditKeyMigration(populated_db, str(temp_key_dir), mock_time_service)

        backup_path = migration._create_backup()

        assert backup_path.exists()
        # Should have database backup
        assert (backup_path / Path(populated_db).name).exists()
        # Should have keys directory
        assert (backup_path / "keys").exists()

        # Cleanup
        import shutil

        shutil.rmtree(backup_path)

    def test_verify_chain_integrity_valid(self, populated_db, temp_key_dir, mock_time_service):
        """Test chain integrity verification with valid chain."""
        migration = AuditKeyMigration(populated_db, str(temp_key_dir), mock_time_service)
        entries = migration._load_all_entries()
        mock_key = MockUnifiedKey()
        migrated = migration._resign_entries(entries, mock_key)
        migration._update_database(migrated)

        result = migration._verify_chain_integrity(mock_key)
        assert result is True


class TestMigrateToEd25519:
    """Test the main migration method."""

    @pytest.mark.asyncio
    async def test_migrate_no_existing_key(self, temp_db, temp_key_dir, mock_time_service):
        """Test migration when no RSA key exists."""
        migration = AuditKeyMigration(temp_db, str(temp_key_dir), mock_time_service)

        result = await migration.migrate_to_ed25519(backup=False)

        assert result.success is False
        assert "No existing RSA key" in result.message

    @pytest.mark.asyncio
    async def test_migrate_already_ed25519(self, temp_db, temp_key_dir, mock_time_service):
        """Test migration when already using Ed25519."""
        # Add Ed25519 key
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO audit_signing_keys (key_id, public_key, algorithm, key_size, created_at)
            VALUES ('agent-ed25519key', 'pubkey', 'ed25519', 256, '2024-01-01T00:00:00Z')
        """
        )
        conn.commit()
        conn.close()

        migration = AuditKeyMigration(temp_db, str(temp_key_dir), mock_time_service)

        result = await migration.migrate_to_ed25519(backup=False)

        assert result.success is True
        assert "Already using Ed25519" in result.message

    @pytest.mark.asyncio
    async def test_migrate_empty_entries(self, temp_db, temp_key_dir, mock_time_service):
        """Test migration with no audit entries."""
        # Add RSA key but no entries
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO audit_signing_keys (key_id, public_key, algorithm, key_size, created_at)
            VALUES ('rsa-key', 'pubkey', 'rsa_2048', 2048, '2024-01-01T00:00:00Z')
        """
        )
        conn.commit()
        conn.close()

        migration = AuditKeyMigration(temp_db, str(temp_key_dir), mock_time_service)

        with patch("ciris_engine.logic.audit.signing_protocol.get_unified_signing_key", return_value=MockUnifiedKey()):
            result = await migration.migrate_to_ed25519(backup=False)

        assert result.success is True
        assert result.entries_migrated == 0
        assert "No audit entries" in result.message

    @pytest.mark.asyncio
    async def test_migrate_with_entries(self, populated_db, temp_key_dir, mock_time_service):
        """Test full migration with entries."""
        migration = AuditKeyMigration(populated_db, str(temp_key_dir), mock_time_service)
        mock_key = MockUnifiedKey()

        with patch("ciris_engine.logic.audit.signing_protocol.get_unified_signing_key", return_value=mock_key):
            result = await migration.migrate_to_ed25519(backup=False, verify_after=False)

        assert result.success is True
        assert result.entries_migrated == 5
        assert result.old_key_id == "rsa-oldkey123"
        assert result.new_key_id == mock_key.key_id


class TestConvenienceFunction:
    """Test the convenience function."""

    @pytest.mark.asyncio
    async def test_migrate_audit_key_to_ed25519(self, temp_db, temp_key_dir, mock_time_service):
        """Test convenience function creates migration and runs it."""
        # Add RSA key
        conn = sqlite3.connect(temp_db)
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO audit_signing_keys (key_id, public_key, algorithm, key_size, created_at)
            VALUES ('rsa-key', 'pubkey', 'rsa_2048', 2048, '2024-01-01T00:00:00Z')
        """
        )
        conn.commit()
        conn.close()

        with patch("ciris_engine.logic.audit.signing_protocol.get_unified_signing_key", return_value=MockUnifiedKey()):
            result = await migrate_audit_key_to_ed25519(temp_db, str(temp_key_dir), mock_time_service, backup=False)

        assert isinstance(result, MigrationResult)
