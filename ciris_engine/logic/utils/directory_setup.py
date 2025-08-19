"""
Centralized directory setup for CIRIS.

Ensures all required directories exist with correct permissions
before the application starts. FAILS FAST with clear error messages.
"""

import os
import shutil
import sys
from pathlib import Path
from typing import Dict, Optional, Tuple


class DirectorySetupError(Exception):
    """Base exception for directory setup failures."""

    pass


class PermissionError(DirectorySetupError):
    """Raised when directory permissions are incorrect and cannot be fixed."""

    pass


class DiskSpaceError(DirectorySetupError):
    """Raised when insufficient disk space is available."""

    pass


class DirectoryCreationError(DirectorySetupError):
    """Raised when a directory cannot be created."""

    pass


def check_disk_space(path: Path, required_mb: int = 100) -> Tuple[bool, float]:
    """
    Check if sufficient disk space is available.

    Args:
        path: Path to check disk space for
        required_mb: Required space in megabytes (default 100MB)

    Returns:
        Tuple of (has_enough_space, available_mb)
    """
    try:
        stat = shutil.disk_usage(path if path.exists() else path.parent)
        available_mb = stat.free / (1024 * 1024)
        return available_mb >= required_mb, available_mb
    except Exception as e:
        # If we can't check disk space, assume it's insufficient
        print(f"ERROR: Cannot check disk space: {e}")
        return False, 0.0


def setup_application_directories(
    base_dir: Optional[Path] = None,
    user_id: Optional[int] = None,
    group_id: Optional[int] = None,
    fail_fast: bool = True,
) -> None:
    """
    Set up all required application directories with correct permissions.

    FAILS FAST with clear error messages if directories cannot be created
    or permissions cannot be set correctly.

    Args:
        base_dir: Base directory for the application (defaults to current working directory)
        user_id: User ID to own the directories (defaults to current user)
        group_id: Group ID to own the directories (defaults to current group)
        fail_fast: If True, exit immediately on any error (default True)

    Raises:
        DirectorySetupError: If any directory setup fails
    """
    if base_dir is None:
        base_dir = Path.cwd()

    if user_id is None:
        user_id = os.getuid()

    if group_id is None:
        group_id = os.getgid()

    # First, check disk space
    has_space, available_mb = check_disk_space(base_dir)
    if not has_space:
        error_msg = f"INSUFFICIENT DISK SPACE: Only {available_mb:.1f}MB available. MINIMUM 100MB REQUIRED - EXITING"
        print(f"CRITICAL ERROR: {error_msg}", file=sys.stderr)
        if fail_fast:
            sys.exit(1)
        raise DiskSpaceError(error_msg)

    # Define directories and their required permissions
    # 0o755 = rwxr-xr-x (readable by all, writable by owner)
    # 0o700 = rwx------ (only owner can read/write/execute)
    directories: Dict[str, int] = {
        "data": 0o755,  # Database files
        "data_archive": 0o755,  # Archived thoughts/tasks
        "logs": 0o755,  # Log files
        "audit_keys": 0o700,  # Sensitive audit keys - restricted!
        "config": 0o755,  # Configuration files
        ".secrets": 0o700,  # Secrets storage - restricted!
    }

    for dir_name, mode in directories.items():
        dir_path = base_dir / dir_name

        try:
            # Create directory if it doesn't exist
            if not dir_path.exists():
                dir_path.mkdir(parents=True, mode=mode)
                print(f"✓ Created directory: {dir_path} with mode {oct(mode)}")

                # Verify creation
                if not dir_path.exists():
                    error_msg = f"UNABLE TO CREATE DIRECTORY {dir_path} - CHECK FILESYSTEM"
                    print(f"CRITICAL ERROR: {error_msg}", file=sys.stderr)
                    if fail_fast:
                        sys.exit(1)
                    raise DirectoryCreationError(error_msg)
            else:
                # Directory exists, check permissions
                current_mode = dir_path.stat().st_mode & 0o777
                if current_mode != mode:
                    try:
                        dir_path.chmod(mode)
                        print(f"✓ Fixed permissions for {dir_path}: {oct(current_mode)} -> {oct(mode)}")
                    except Exception as perm_error:
                        error_msg = f"WRONG PERMS on {dir_path}: Has {oct(current_mode)}, needs {oct(mode)} - CANNOT FIX - EXITING"
                        print(f"CRITICAL ERROR: {error_msg}", file=sys.stderr)
                        print(f"  Details: {perm_error}", file=sys.stderr)
                        if fail_fast:
                            sys.exit(1)
                        raise PermissionError(error_msg)

            # Test write access
            test_file = dir_path / ".write_test"
            try:
                test_file.touch()
                test_file.unlink()
            except Exception as write_error:
                error_msg = f"CANNOT WRITE TO {dir_path} - CHECK OWNERSHIP AND PERMISSIONS"
                print(f"CRITICAL ERROR: {error_msg}", file=sys.stderr)
                print(f"  Current owner: uid={dir_path.stat().st_uid}, gid={dir_path.stat().st_gid}", file=sys.stderr)
                print(f"  Current perms: {oct(dir_path.stat().st_mode & 0o777)}", file=sys.stderr)
                print(f"  Running as: uid={user_id}, gid={group_id}", file=sys.stderr)
                print(f"  Error: {write_error}", file=sys.stderr)
                if fail_fast:
                    sys.exit(1)
                raise PermissionError(error_msg)

            # Try to fix ownership if needed (will fail gracefully if not root)
            current_stat = dir_path.stat()
            if current_stat.st_uid != user_id or current_stat.st_gid != group_id:
                try:
                    os.chown(dir_path, user_id, group_id)
                    print(
                        f"✓ Fixed ownership for {dir_path}: {current_stat.st_uid}:{current_stat.st_gid} -> {user_id}:{group_id}"
                    )
                except Exception:
                    # Not fatal if we can't change ownership as long as we can write
                    print(f"  Warning: Cannot change ownership of {dir_path} (need root), but write access confirmed")

        except (DirectorySetupError, SystemExit):
            raise  # Re-raise our own exceptions and exits
        except Exception as e:
            error_msg = f"UNEXPECTED ERROR setting up {dir_path}: {e}"
            print(f"CRITICAL ERROR: {error_msg}", file=sys.stderr)
            if fail_fast:
                sys.exit(1)
            raise DirectorySetupError(error_msg)

    print("✓ All directories successfully configured")


def validate_directories(base_dir: Optional[Path] = None) -> bool:
    """
    Validate that all required directories exist and are writable.

    This is a lighter-weight check suitable for production where
    directories should already exist.

    Args:
        base_dir: Base directory for the application

    Returns:
        True if all directories are valid

    Raises:
        DirectorySetupError: If validation fails
    """
    if base_dir is None:
        base_dir = Path.cwd()

    # Check disk space first
    has_space, available_mb = check_disk_space(base_dir)
    if not has_space:
        error_msg = f"INSUFFICIENT DISK SPACE: Only {available_mb:.1f}MB available. MINIMUM 100MB REQUIRED - EXITING"
        print(f"CRITICAL ERROR: {error_msg}", file=sys.stderr)
        raise DiskSpaceError(error_msg)

    required_dirs = ["data", "data_archive", "logs", "audit_keys", "config"]

    for dir_name in required_dirs:
        dir_path = base_dir / dir_name

        # Check existence
        if not dir_path.exists():
            error_msg = f"REQUIRED DIRECTORY MISSING: {dir_path} - EXITING"
            print(f"CRITICAL ERROR: {error_msg}", file=sys.stderr)
            raise DirectoryCreationError(error_msg)

        # Check if it's actually a directory
        if not dir_path.is_dir():
            error_msg = f"PATH EXISTS BUT IS NOT A DIRECTORY: {dir_path} - EXITING"
            print(f"CRITICAL ERROR: {error_msg}", file=sys.stderr)
            raise DirectorySetupError(error_msg)

        # Check write access
        test_file = dir_path / ".write_test"
        try:
            test_file.touch()
            test_file.unlink()
        except Exception as e:
            error_msg = f"CANNOT WRITE TO DIRECTORY: {dir_path} - CHECK PERMISSIONS"
            print(f"CRITICAL ERROR: {error_msg}", file=sys.stderr)
            print(f"  Error: {e}", file=sys.stderr)
            raise PermissionError(error_msg)

    print("✓ All directories validated successfully")
    return True


if __name__ == "__main__":
    # Run setup when executed directly
    import argparse

    parser = argparse.ArgumentParser(description="CIRIS Directory Setup")
    parser.add_argument(
        "--validate-only", action="store_true", help="Only validate existing directories (for production)"
    )
    parser.add_argument("--no-fail-fast", action="store_true", help="Continue on errors instead of exiting")
    args = parser.parse_args()

    try:
        if args.validate_only:
            print("Validating CIRIS application directories...")
            validate_directories()
        else:
            print("Setting up CIRIS application directories...")
            setup_application_directories(fail_fast=not args.no_fail_fast)

        print("\n✓ SUCCESS: All directories properly configured!")
    except DirectorySetupError as e:
        print(f"\n✗ FAILED: {e}", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"\n✗ UNEXPECTED ERROR: {e}", file=sys.stderr)
        sys.exit(1)
