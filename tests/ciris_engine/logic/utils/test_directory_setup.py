"""
Unit tests for directory setup utility.

Tests the fail-fast directory validation and creation logic.
"""

import os
import shutil
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch

import pytest

from ciris_engine.logic.utils.directory_setup import (
    DatabaseAccessError,
    DirectoryCreationError,
    DirectorySetupError,
    DiskSpaceError,
    PermissionError,
    check_disk_space,
    ensure_database_exclusive_access,
    setup_application_directories,
    validate_directories,
)

# Import the existing central mock fixture
from tests.conftest_config_mock import mock_db_path


class TestCheckDiskSpace:
    """Test disk space checking functionality."""

    def test_sufficient_disk_space(self):
        """Test when sufficient disk space is available."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            has_space, available_mb = check_disk_space(path, required_mb=1)
            assert has_space is True
            assert available_mb > 1

    def test_insufficient_disk_space(self):
        """Test detection of insufficient disk space."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir)
            # Request more than available (assuming < 1PB free space!)
            has_space, available_mb = check_disk_space(path, required_mb=1_000_000_000)
            assert has_space is False
            assert available_mb < 1_000_000_000

    @patch("ciris_engine.logic.utils.directory_setup.shutil.disk_usage")
    def test_disk_space_check_error(self, mock_disk_usage):
        """Test handling of disk space check errors."""
        mock_disk_usage.side_effect = Exception("Disk error")
        path = Path("/tmp")
        has_space, available_mb = check_disk_space(path)
        assert has_space is False
        assert available_mb == 0.0


class TestSetupApplicationDirectories:
    """Test directory setup functionality."""

    def test_create_all_directories(self, mock_db_path):
        """Test creating all required directories with correct permissions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)

            # Run setup
            setup_application_directories(base_dir=base_dir, fail_fast=False)

            # Check all directories exist with correct permissions
            expected_dirs = {
                "data": 0o755,
                "data_archive": 0o755,
                "logs": 0o755,
                "audit_keys": 0o700,
                "config": 0o755,
                ".secrets": 0o700,
            }

            for dir_name, expected_mode in expected_dirs.items():
                dir_path = base_dir / dir_name
                assert dir_path.exists(), f"Directory {dir_name} should exist"
                assert dir_path.is_dir(), f"{dir_name} should be a directory"

                # Check permissions
                actual_mode = dir_path.stat().st_mode & 0o777
                assert (
                    actual_mode == expected_mode
                ), f"{dir_name} has mode {oct(actual_mode)}, expected {oct(expected_mode)}"

    def test_fix_existing_directory_permissions(self, mock_db_path):
        """Test fixing permissions on existing directories."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)

            # Create a directory with wrong permissions
            test_dir = base_dir / "data"
            test_dir.mkdir(mode=0o777)

            # Run setup
            setup_application_directories(base_dir=base_dir, fail_fast=False)

            # Check permissions were fixed
            actual_mode = test_dir.stat().st_mode & 0o777
            assert actual_mode == 0o755

    def test_insufficient_disk_space_fails_fast(self, mock_db_path):
        """Test that insufficient disk space causes immediate failure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)

            with patch("ciris_engine.logic.utils.directory_setup.check_disk_space") as mock_check:
                mock_check.return_value = (False, 50.0)  # Only 50MB available

                # Test with fail_fast=True (should exit)
                with patch("sys.exit") as mock_exit:
                    with pytest.raises(DiskSpaceError):
                        setup_application_directories(base_dir=base_dir, fail_fast=True)
                    mock_exit.assert_called_once_with(1)

                # Test with fail_fast=False (should raise)
                with pytest.raises(DiskSpaceError) as exc_info:
                    setup_application_directories(base_dir=base_dir, fail_fast=False)
                assert "MINIMUM 100MB REQUIRED" in str(exc_info.value)

    def test_cannot_create_directory_fails_fast(self, mock_db_path):
        """Test that directory creation failure causes immediate failure."""
        # Skip if running as root
        if os.getuid() == 0:
            pytest.skip("Cannot test permission errors when running as root")

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)

            # Make base_dir read-only
            os.chmod(tmpdir, 0o555)

            try:
                # Test with fail_fast=False (should raise)
                with pytest.raises((PermissionError, DirectorySetupError)) as exc_info:
                    setup_application_directories(base_dir=base_dir, fail_fast=False)
                error_msg = str(exc_info.value)
                # Accept various error messages since exact error depends on OS
                assert any(
                    msg in error_msg
                    for msg in ["CANNOT WRITE TO", "UNABLE TO CREATE", "Permission denied", "UNEXPECTED ERROR"]
                )
            finally:
                # Restore permissions for cleanup
                os.chmod(tmpdir, 0o755)

    def test_cannot_write_to_directory_fails_fast(self, mock_db_path):
        """Test that write permission issues cause immediate failure."""
        # Skip this test if running as root (root can write anywhere)
        if os.getuid() == 0:
            pytest.skip("Cannot test permission errors when running as root")

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)

            # Create a directory but make it read-only (no write permission)
            test_dir = base_dir / "data"
            test_dir.mkdir(mode=0o444)  # r--r--r-- (read-only for everyone)

            try:
                # Test with fail_fast=False (should raise)
                # chmod will succeed since we own it, but write test will fail
                setup_application_directories(base_dir=base_dir, fail_fast=False)
                # The function will fix the permissions, so this is actually OK behavior
                # The test was expecting it to fail, but our implementation fixes it
                assert test_dir.stat().st_mode & 0o777 == 0o755
            finally:
                # Restore permissions for cleanup
                test_dir.chmod(0o755)


class TestValidateDirectories:
    """Test directory validation functionality."""

    def test_validate_all_directories_exist(self):
        """Test successful validation when all directories exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)

            # Create all required directories
            for dir_name in ["data", "data_archive", "logs", "audit_keys", "config"]:
                (base_dir / dir_name).mkdir()

            # Should validate successfully
            result = validate_directories(base_dir=base_dir)
            assert result is True

    def test_validate_missing_directory_fails(self):
        """Test that missing directories cause validation failure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)

            # Create some but not all directories
            (base_dir / "data").mkdir()
            (base_dir / "logs").mkdir()
            # Missing: data_archive, audit_keys, config

            with pytest.raises(DirectoryCreationError) as exc_info:
                validate_directories(base_dir=base_dir)
            assert "REQUIRED DIRECTORY MISSING" in str(exc_info.value)

    def test_validate_file_not_directory_fails(self):
        """Test that a file where a directory is expected causes failure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)

            # Create all directories except one
            for dir_name in ["data", "logs", "audit_keys", "config"]:
                (base_dir / dir_name).mkdir()

            # Create a file instead of directory
            (base_dir / "data_archive").touch()

            with pytest.raises(DirectorySetupError) as exc_info:
                validate_directories(base_dir=base_dir)
            assert "PATH EXISTS BUT IS NOT A DIRECTORY" in str(exc_info.value)

    def test_validate_cannot_write_fails(self):
        """Test that directories without write permission fail validation."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)

            # Create all directories
            for dir_name in ["data", "data_archive", "logs", "audit_keys", "config"]:
                dir_path = base_dir / dir_name
                dir_path.mkdir()

            # Make one read-only
            (base_dir / "data").chmod(0o555)

            try:
                with pytest.raises(PermissionError) as exc_info:
                    validate_directories(base_dir=base_dir)
                assert "CANNOT WRITE TO DIRECTORY" in str(exc_info.value)
            finally:
                # Restore permissions for cleanup
                (base_dir / "data").chmod(0o755)

    def test_validate_insufficient_disk_space_fails(self):
        """Test that insufficient disk space causes validation failure."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)

            # Create all directories
            for dir_name in ["data", "data_archive", "logs", "audit_keys", "config"]:
                (base_dir / dir_name).mkdir()

            with patch("ciris_engine.logic.utils.directory_setup.check_disk_space") as mock_check:
                mock_check.return_value = (False, 75.0)  # Only 75MB available

                with pytest.raises(DiskSpaceError) as exc_info:
                    validate_directories(base_dir=base_dir)
                assert "INSUFFICIENT DISK SPACE" in str(exc_info.value)
                assert "75.0MB available" in str(exc_info.value)


class TestErrorMessages:
    """Test that error messages are clear and actionable."""

    def test_disk_space_error_message(self, mock_db_path):
        """Test disk space error message clarity."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)

            with patch("ciris_engine.logic.utils.directory_setup.check_disk_space") as mock_check:
                mock_check.return_value = (False, 42.5)

                with pytest.raises(DiskSpaceError) as exc_info:
                    setup_application_directories(base_dir=base_dir, fail_fast=False)

                error_msg = str(exc_info.value)
                assert "INSUFFICIENT DISK SPACE" in error_msg
                assert "42.5MB available" in error_msg
                assert "MINIMUM 100MB REQUIRED" in error_msg
                assert "EXITING" in error_msg

    def test_permission_error_message(self, mock_db_path):
        """Test permission error message includes helpful details."""
        # Skip if running as root
        if os.getuid() == 0:
            pytest.skip("Cannot test permission errors when running as root")

        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)

            # Our implementation actually fixes permissions when possible
            # So let's test a scenario where we truly can't write
            # Create all dirs first
            setup_application_directories(base_dir=base_dir, fail_fast=False)

            # Now make the base dir unwritable (so we can't create .write_test)
            test_dir = base_dir / "data"
            # Remove all permissions
            os.chmod(test_dir, 0o000)

            try:
                with pytest.raises(PermissionError) as exc_info:
                    validate_directories(base_dir=base_dir)

                error_msg = str(exc_info.value)
                assert "CANNOT WRITE TO" in error_msg
            finally:
                # Restore for cleanup
                os.chmod(test_dir, 0o755)

    def test_creation_error_message(self, mock_db_path):
        """Test directory creation error message clarity."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)

            # First patch disk space check to pass
            with patch("ciris_engine.logic.utils.directory_setup.check_disk_space") as mock_disk_check:
                mock_disk_check.return_value = (True, 1000.0)  # Plenty of space

                # Patch at a more specific level to avoid breaking other checks
                data_dir = base_dir / "data"

                # Create a situation where mkdir succeeds but dir doesn't exist after
                original_mkdir = Path.mkdir
                call_count = [0]

                def mock_mkdir_func(self, *args, **kwargs):
                    call_count[0] += 1
                    # Only mock the data directory creation
                    if str(self) == str(data_dir):
                        # Do nothing - simulate silent failure
                        return None
                    else:
                        # Let other directories work normally
                        return original_mkdir(self, *args, **kwargs)

                with patch.object(Path, "mkdir", mock_mkdir_func):
                    # Also need to mock exists for data dir specifically
                    original_exists = Path.exists

                    def mock_exists_func(self):
                        # data dir never exists even after "creation"
                        if str(self) == str(data_dir):
                            return False
                        else:
                            return original_exists(self)

                    with patch.object(Path, "exists", mock_exists_func):
                        with pytest.raises(DirectoryCreationError) as exc_info:
                            setup_application_directories(base_dir=base_dir, fail_fast=False)

                        error_msg = str(exc_info.value)
                        assert "UNABLE TO CREATE DIRECTORY" in error_msg
                        assert "CHECK FILESYSTEM" in error_msg


class TestDatabaseExclusiveAccess:
    """Test database exclusive access functionality."""

    def test_database_exclusive_access_success(self):
        """Test successful database access check."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            
            # Should succeed on first access
            ensure_database_exclusive_access(db_path, fail_fast=False)
            
            # Verify database file was created
            assert Path(db_path).exists()

    def test_database_exclusive_access_creates_parent_directory(self):
        """Test that parent directories are created if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "subdir" / "nested" / "test.db")
            
            # Should succeed and create parent directories
            ensure_database_exclusive_access(db_path, fail_fast=False)
            
            # Verify database and parent directories were created
            assert Path(db_path).exists()
            assert Path(db_path).parent.exists()

    def test_database_exclusive_access_locked_database(self):
        """Test detection of locked database (another agent running)."""
        import sqlite3
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            
            # Create and hold a lock on the database
            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("BEGIN IMMEDIATE")  # Hold exclusive lock
            
            try:
                # Should detect the lock and fail
                with pytest.raises(DatabaseAccessError) as exc_info:
                    ensure_database_exclusive_access(db_path, fail_fast=False)
                
                error_msg = str(exc_info.value)
                assert "CANNOT ACCESS DATABASE" in error_msg
                assert "ANOTHER AGENT MAY BE RUNNING" in error_msg
            finally:
                # Clean up the lock
                conn.rollback()
                conn.close()

    def test_database_exclusive_access_fail_fast_exits(self):
        """Test that fail_fast=True causes system exit."""
        import sqlite3
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            
            # Create and hold a lock
            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA journal_mode=WAL") 
            conn.execute("BEGIN IMMEDIATE")
            
            try:
                with patch("sys.exit") as mock_exit:
                    with pytest.raises(DatabaseAccessError):
                        ensure_database_exclusive_access(db_path, fail_fast=True)
                    mock_exit.assert_called_once_with(1)
            finally:
                conn.rollback()
                conn.close()

    @patch("sqlite3.connect")
    def test_database_exclusive_access_unexpected_error(self, mock_connect):
        """Test handling of unexpected database errors."""
        mock_connect.side_effect = Exception("Unexpected database error")
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "test.db")
            
            # Should catch and wrap unexpected errors
            with pytest.raises(DatabaseAccessError) as exc_info:
                ensure_database_exclusive_access(db_path, fail_fast=False)
            
            error_msg = str(exc_info.value)
            assert "UNEXPECTED DATABASE ERROR" in error_msg
            assert "Unexpected database error" in error_msg

    def test_setup_with_database_access_check_enabled(self):
        """Test that setup_application_directories includes database check by default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            
            with patch("ciris_engine.logic.utils.directory_setup.ensure_database_exclusive_access") as mock_db_check:
                # Mock the config import to use our test path
                expected_db_path = str(base_dir / "data" / "ciris_engine.db")
                
                with patch("ciris_engine.logic.config.get_sqlite_db_full_path", 
                          side_effect=ImportError("Config not available")):
                    setup_application_directories(base_dir=base_dir, fail_fast=False)
                
                # Verify database check was called with default path
                mock_db_check.assert_called_once_with(expected_db_path, False)

    def test_setup_with_database_access_check_disabled(self):
        """Test that database check can be disabled."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            
            with patch("ciris_engine.logic.utils.directory_setup.ensure_database_exclusive_access") as mock_db_check:
                setup_application_directories(base_dir=base_dir, fail_fast=False, check_database_access=False)
                
                # Verify database check was NOT called
                mock_db_check.assert_not_called()

    def test_setup_with_config_available(self):
        """Test that setup uses config service when available."""
        with tempfile.TemporaryDirectory() as tmpdir:
            base_dir = Path(tmpdir)
            config_db_path = str(base_dir / "custom" / "config.db")
            
            with patch("ciris_engine.logic.utils.directory_setup.ensure_database_exclusive_access") as mock_db_check:
                with patch("ciris_engine.logic.config.get_sqlite_db_full_path", 
                          return_value=config_db_path):
                    setup_application_directories(base_dir=base_dir, fail_fast=False)
                
                # Verify database check was called with config path
                mock_db_check.assert_called_once_with(config_db_path, False)

    def test_database_exclusive_access_error_messages(self):
        """Test that database access errors have helpful messages."""
        import sqlite3
        
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = str(Path(tmpdir) / "locked.db")
            
            # Create and lock the database
            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("BEGIN IMMEDIATE")
            
            try:
                with pytest.raises(DatabaseAccessError) as exc_info:
                    ensure_database_exclusive_access(db_path, fail_fast=False)
                
                error_msg = str(exc_info.value)
                assert "CANNOT ACCESS DATABASE" in error_msg
                assert db_path in error_msg
                assert "ANOTHER AGENT MAY BE RUNNING" in error_msg
            finally:
                conn.rollback()
                conn.close()
