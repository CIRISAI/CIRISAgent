#!/usr/bin/env python3
"""
Reset admin password utility for CIRIS.

Usage:
    python tools/reset_admin_password.py [new_password]

If no password is provided, a secure random password will be generated.
"""

import argparse
import asyncio
import getpass
import secrets
import sqlite3
import string
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    import bcrypt
except ImportError:
    print("Error: bcrypt not installed. Run: pip install bcrypt")
    sys.exit(1)

from ciris_engine.logic.config import get_sqlite_db_full_path


def generate_secure_password(length: int = 16) -> str:
    """Generate a cryptographically secure random password."""
    # Use a mix of letters, digits, and special characters
    alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_+=[]{}|;:,.<>?"
    password = "".join(secrets.choice(alphabet) for _ in range(length))
    return password


def hash_password(password: str) -> str:
    """Hash a password using bcrypt."""
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def update_admin_password(password: str, db_path: str = None) -> bool:
    """Update the admin password in the database."""
    if db_path is None:
        # Use ciris_engine.db, NOT ciris_auth.db!
        db_path = get_sqlite_db_full_path()  # This returns /app/data/ciris_engine.db

    # Hash the new password
    password_hash = hash_password(password)

    try:
        # Connect to database
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # Check if wa_cert table exists
        cursor.execute(
            """
            SELECT name FROM sqlite_master
            WHERE type='table' AND name='wa_cert'
        """
        )

        if not cursor.fetchone():
            print("❌ wa_cert table does not exist in database")
            print(f"   Database path: {db_path}")
            print("\n   This tool is for production databases only.")
            print("   For local development, use environment variables:")
            print("   export ADMIN_USERNAME=admin")
            print("   export ADMIN_PASSWORD=your_password")
            return False

        # First check if admin user exists in wa_cert table
        cursor.execute(
            """
            SELECT wa_id, name FROM wa_cert
            WHERE name = 'admin'
        """
        )

        admin_row = cursor.fetchone()

        if admin_row:
            wa_id = admin_row[0]
            print(f"Found admin user with WA ID: {wa_id}")

            # Update the password hash
            cursor.execute(
                """
                UPDATE wa_cert
                SET password_hash = ?
                WHERE wa_id = ?
            """,
                (password_hash, wa_id),
            )

            if cursor.rowcount > 0:
                conn.commit()
                print(f"✅ Successfully updated password for admin (WA ID: {wa_id})")
                return True
            else:
                print("❌ Failed to update password - no rows affected")
                return False
        else:
            print("❌ Admin user not found in database")
            print("\nAttempting to create admin user...")

            # Create admin user
            import uuid
            from datetime import datetime, timezone

            wa_id = f"wa-admin-{uuid.uuid4().hex[:8]}"
            now = datetime.now(timezone.utc).isoformat()

            cursor.execute(
                """
                INSERT INTO wa_cert (
                    wa_id, name, role, pubkey, jwt_kid,
                    password_hash, scopes_json, created, auto_minted,
                    adapter_name, active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
                (
                    wa_id,
                    "admin",
                    "root",  # System admin role (lowercase)
                    "",  # Empty pubkey is OK for password auth
                    f"admin-{secrets.token_hex(4)}",  # JWT key ID
                    password_hash,
                    '["*"]',  # All permissions
                    now,
                    0,  # Not auto-minted
                    "manual",  # Adapter name
                    1,  # Active
                ),
            )

            if cursor.rowcount > 0:
                conn.commit()
                print(f"✅ Created admin user with WA ID: {wa_id}")
                print(f"✅ Password set successfully")
                return True
            else:
                print("❌ Failed to create admin user")
                return False

    except sqlite3.Error as e:
        print(f"❌ Database error: {e}")
        return False
    except Exception as e:
        print(f"❌ Unexpected error: {e}")
        import traceback

        traceback.print_exc()
        return False
    finally:
        if conn:
            conn.close()


def verify_password(username: str, password: str, db_path: str = None) -> bool:
    """Verify that the password works."""
    if db_path is None:
        # Use ciris_engine.db, NOT ciris_auth.db!
        db_path = get_sqlite_db_full_path()  # This returns /app/data/ciris_engine.db

    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            SELECT password_hash FROM wa_cert
            WHERE name = ?
        """,
            (username,),
        )

        row = cursor.fetchone()
        if row and row[0]:
            password_hash = row[0]
            return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))

        return False
    except Exception as e:
        print(f"Error verifying password: {e}")
        return False
    finally:
        if conn:
            conn.close()


def main():
    parser = argparse.ArgumentParser(description="Reset admin password for CIRIS")
    parser.add_argument("password", nargs="?", help="New password (will prompt if not provided)")
    parser.add_argument("--generate", action="store_true", help="Generate a random secure password")
    parser.add_argument("--db-path", help="Path to database (default: auto-detect)")
    parser.add_argument("--verify-only", action="store_true", help="Only verify current password")

    args = parser.parse_args()

    if args.verify_only:
        # Verify mode
        password = getpass.getpass("Enter password to verify: ")
        if verify_password("admin", password, args.db_path):
            print("✅ Password is correct!")
            sys.exit(0)
        else:
            print("❌ Password is incorrect or admin user not found")
            sys.exit(1)

    # Determine the new password
    if args.generate:
        new_password = generate_secure_password()
        print(f"Generated secure password: {new_password}")
        print("⚠️  SAVE THIS PASSWORD - it will not be shown again!")
    elif args.password:
        new_password = args.password
    else:
        # Prompt for password
        while True:
            new_password = getpass.getpass("Enter new admin password: ")
            if len(new_password) < 12:
                print("❌ Password must be at least 12 characters")
                continue
            confirm = getpass.getpass("Confirm new password: ")
            if new_password != confirm:
                print("❌ Passwords do not match")
                continue
            break

    # Update the password
    print(f"\nUpdating admin password in database...")
    if update_admin_password(new_password, args.db_path):
        print("\n✅ Password reset successful!")

        # Verify it works
        print("\nVerifying new password...")
        if verify_password("admin", new_password, args.db_path):
            print("✅ Password verification successful!")
        else:
            print("⚠️  Warning: Password was updated but verification failed")
    else:
        print("\n❌ Password reset failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
