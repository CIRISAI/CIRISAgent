"""
Unit tests for the password reset utility.
"""

import sqlite3

# Import the functions from the tool
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import bcrypt
import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "tools"))
from reset_admin_password import generate_secure_password, hash_password, update_admin_password, verify_password


class TestPasswordResetUtility:
    """Test suite for password reset utility functions."""

    def test_generate_secure_password(self):
        """Test secure password generation."""
        # Test default length
        password = generate_secure_password()
        assert len(password) == 16
        assert any(c.isalpha() for c in password)
        assert any(c.isdigit() for c in password)

        # Test custom length
        password = generate_secure_password(24)
        assert len(password) == 24

        # Test uniqueness
        password1 = generate_secure_password()
        password2 = generate_secure_password()
        assert password1 != password2

    def test_hash_password(self):
        """Test password hashing."""
        password = "test_password_123"
        hashed = hash_password(password)

        # Check it's a valid bcrypt hash
        assert hashed.startswith("$2b$")
        assert len(hashed) == 60

        # Verify the hash works
        assert bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))

        # Different passwords produce different hashes
        hashed2 = hash_password("different_password")
        assert hashed != hashed2

    def test_update_admin_password_no_table(self, tmp_path):
        """Test updating password when wa_cert table doesn't exist."""
        db_path = tmp_path / "test.db"

        # Create empty database
        conn = sqlite3.connect(db_path)
        conn.close()

        # Should fail gracefully
        result = update_admin_password("new_password", str(db_path))
        assert result is False

    def test_update_admin_password_existing_user(self, tmp_path):
        """Test updating password for existing admin user."""
        db_path = tmp_path / "test.db"

        # Create database with wa_cert table and admin user
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE wa_cert (
                wa_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                role TEXT,
                pubkey TEXT NOT NULL,
                jwt_kid TEXT NOT NULL,
                password_hash TEXT,
                scopes_json TEXT NOT NULL,
                created TEXT NOT NULL,
                auto_minted INTEGER DEFAULT 0,
                adapter_name TEXT,
                active INTEGER DEFAULT 1
            )
        """
        )

        # Insert admin user with old password
        old_hash = hash_password("old_password")
        cursor.execute(
            """
            INSERT INTO wa_cert (wa_id, name, role, pubkey, jwt_kid, password_hash,
                                scopes_json, created, adapter_name)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            ("wa-admin-test", "admin", "root", "", "test-kid", old_hash, '["*"]', "2024-01-01T00:00:00", "manual"),
        )
        conn.commit()
        conn.close()

        # Update password
        result = update_admin_password("new_password", str(db_path))
        assert result is True

        # Verify new password works
        assert verify_password("admin", "new_password", str(db_path))
        assert not verify_password("admin", "old_password", str(db_path))

    def test_update_admin_password_create_new(self, tmp_path):
        """Test creating new admin user when none exists."""
        db_path = tmp_path / "test.db"

        # Create database with wa_cert table but no admin
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE wa_cert (
                wa_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                role TEXT,
                pubkey TEXT NOT NULL,
                jwt_kid TEXT NOT NULL,
                password_hash TEXT,
                scopes_json TEXT NOT NULL,
                created TEXT NOT NULL,
                auto_minted INTEGER DEFAULT 0,
                adapter_name TEXT,
                active INTEGER DEFAULT 1
            )
        """
        )
        conn.commit()
        conn.close()

        # Should create new admin user
        result = update_admin_password("admin_password", str(db_path))
        assert result is True

        # Verify admin was created and password works
        assert verify_password("admin", "admin_password", str(db_path))

        # Check admin user exists in database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT wa_id, name, role FROM wa_cert WHERE name = 'admin'")
        row = cursor.fetchone()
        assert row is not None
        assert row[1] == "admin"
        assert row[2] == "root"
        conn.close()

    def test_verify_password(self, tmp_path):
        """Test password verification."""
        db_path = tmp_path / "test.db"

        # Create database with admin user
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE wa_cert (
                wa_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                password_hash TEXT
            )
        """
        )

        password = "test_password_123"
        hashed = hash_password(password)
        cursor.execute(
            """
            INSERT INTO wa_cert (wa_id, name, password_hash)
            VALUES (?, ?, ?)
        """,
            ("wa-admin-test", "admin", hashed),
        )
        conn.commit()
        conn.close()

        # Test correct password
        assert verify_password("admin", password, str(db_path))

        # Test incorrect password
        assert not verify_password("admin", "wrong_password", str(db_path))

        # Test non-existent user
        assert not verify_password("nonexistent", password, str(db_path))

    def test_verify_password_no_hash(self, tmp_path):
        """Test verification when user has no password hash."""
        db_path = tmp_path / "test.db"

        # Create database with admin user but no password
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE wa_cert (
                wa_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                password_hash TEXT
            )
        """
        )
        cursor.execute(
            """
            INSERT INTO wa_cert (wa_id, name, password_hash)
            VALUES (?, ?, ?)
        """,
            ("wa-admin-test", "admin", None),
        )
        conn.commit()
        conn.close()

        # Should return False
        assert not verify_password("admin", "any_password", str(db_path))

    @patch("reset_admin_password.get_sqlite_db_full_path")
    def test_default_db_path(self, mock_get_path):
        """Test that default database path is used when not specified."""
        mock_get_path.return_value = "/app/data/ciris_engine.db"

        # Create a mock database to avoid actual file operations
        with patch("sqlite3.connect") as mock_connect:
            mock_conn = MagicMock()
            mock_cursor = MagicMock()
            mock_conn.cursor.return_value = mock_cursor
            mock_connect.return_value = mock_conn

            # Mock table doesn't exist
            mock_cursor.fetchone.return_value = None

            result = update_admin_password("password")

            # Should use the default path
            mock_get_path.assert_called_once()
            assert result is False
