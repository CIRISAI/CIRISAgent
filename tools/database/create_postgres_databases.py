#!/usr/bin/env python3
"""
Create PostgreSQL derivative databases for CIRIS Agent.

This script creates the _secrets and _auth databases needed by CIRIS
when using PostgreSQL. It connects as a superuser to create the databases.

Usage:
    python tools/database/create_postgres_databases.py <main_db_name> <db_user> <superuser> <superuser_password>

Example:
    python tools/database/create_postgres_databases.py ciris_test_db ciris_test postgres mypassword
"""

import sys
import psycopg2
from psycopg2 import sql

def create_databases(main_db, db_user, superuser, superuser_password, host="localhost", port=5432):
    """Create derivative databases for CIRIS."""

    secrets_db = f"{main_db}_secrets"
    auth_db = f"{main_db}_auth"

    print(f"Creating PostgreSQL databases for CIRIS Agent")
    print(f"  Main database: {main_db}")
    print(f"  Secrets database: {secrets_db}")
    print(f"  Auth database: {auth_db}")
    print()

    # Connect to postgres database as superuser
    try:
        conn = psycopg2.connect(
            host=host,
            port=port,
            user=superuser,
            password=superuser_password,
            database="postgres"
        )
        conn.autocommit = True
        cursor = conn.cursor()

        print("✓ Connected to PostgreSQL")

        # Check if databases exist
        cursor.execute("SELECT datname FROM pg_database WHERE datname IN (%s, %s, %s)",
                      (main_db, secrets_db, auth_db))
        existing = {row[0] for row in cursor.fetchall()}

        # Create main database if needed
        if main_db not in existing:
            print(f"Creating main database: {main_db}")
            cursor.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(
                sql.Identifier(main_db),
                sql.Identifier(db_user)
            ))
            print(f"✓ Created {main_db}")
        else:
            print(f"✓ Main database {main_db} already exists")

        # Create secrets database
        if secrets_db not in existing:
            print(f"Creating secrets database: {secrets_db}")
            cursor.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(
                sql.Identifier(secrets_db),
                sql.Identifier(db_user)
            ))
            print(f"✓ Created {secrets_db}")
        else:
            print(f"✓ Secrets database {secrets_db} already exists")

        # Create auth database
        if auth_db not in existing:
            print(f"Creating auth database: {auth_db}")
            cursor.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(
                sql.Identifier(auth_db),
                sql.Identifier(db_user)
            ))
            print(f"✓ Created {auth_db}")
        else:
            print(f"✓ Auth database {auth_db} already exists")

        cursor.close()
        conn.close()

        print()
        print("✓ All databases ready!")
        print()
        print(f"Connection string: postgresql://{db_user}:<password>@{host}:{port}/{main_db}")
        print()

        return True

    except psycopg2.Error as e:
        print(f"✗ Error: {e}")
        return False

if __name__ == "__main__":
    if len(sys.argv) < 5:
        print("Usage: python create_postgres_databases.py <main_db> <db_user> <superuser> <superuser_password>")
        print("Example: python create_postgres_databases.py ciris_test_db ciris_test postgres mypassword")
        sys.exit(1)

    main_db = sys.argv[1]
    db_user = sys.argv[2]
    superuser = sys.argv[3]
    superuser_password = sys.argv[4]

    success = create_databases(main_db, db_user, superuser, superuser_password)
    sys.exit(0 if success else 1)
