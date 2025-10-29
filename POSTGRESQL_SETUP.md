# PostgreSQL Setup Instructions for CIRIS Agent

This guide explains how to set up PostgreSQL as the database backend for CIRIS Agent.

## Prerequisites

- PostgreSQL installed and running
- sudo access to your system

## Quick Setup (Recommended)

### Step 1: Run the Setup Script

```bash
sudo ./tools/database/setup_postgres_sudo.sh ciris_test_db ciris_test ciris_test_password
```

**Arguments:**
- `ciris_test_db` - Main database name
- `ciris_test` - PostgreSQL username
- `ciris_test_password` - Password for the user

For production, use different credentials:
```bash
sudo ./tools/database/setup_postgres_sudo.sh ciris_db ciris_user your_secure_password
```

### Step 2: Set Environment Variable

```bash
export CIRIS_DB_URL='postgresql://ciris_test:ciris_test_password@localhost:5432/ciris_test_db'
```

### Step 3: Run CIRIS

```bash
python main.py --adapter cli --mock-llm
```

That's it! CIRIS will now use PostgreSQL for all data storage.

---

## What the Setup Script Does

The script automatically:

1. ✅ Checks if PostgreSQL is running (starts it if needed)
2. ✅ Creates the database user with appropriate permissions
3. ✅ Creates three databases:
   - **Main database** (`ciris_test_db`) - Core CIRIS data
   - **Secrets database** (`ciris_test_db_secrets`) - Encrypted secrets storage
   - **Auth database** (`ciris_test_db_auth`) - Authentication data
4. ✅ Runs any pending migrations
5. ✅ Tests all database connections
6. ✅ Displays the connection string for CIRIS

---

## Manual Setup (Advanced)

If you prefer to set up manually or need more control:

### 1. Create PostgreSQL User

```bash
sudo -u postgres psql
```

```sql
CREATE USER ciris_test WITH PASSWORD 'ciris_test_password';
ALTER USER ciris_test CREATEDB;
\q
```

### 2. Create Databases

```bash
sudo -u postgres psql <<EOF
CREATE DATABASE ciris_test_db OWNER ciris_test;
CREATE DATABASE ciris_test_db_secrets OWNER ciris_test;
CREATE DATABASE ciris_test_db_auth OWNER ciris_test;
GRANT ALL PRIVILEGES ON DATABASE ciris_test_db TO ciris_test;
GRANT ALL PRIVILEGES ON DATABASE ciris_test_db_secrets TO ciris_test;
GRANT ALL PRIVILEGES ON DATABASE ciris_test_db_auth TO ciris_test;
EOF
```

### 3. Test Connection

```bash
PGPASSWORD=ciris_test_password psql -h localhost -U ciris_test -d ciris_test_db -c "SELECT 1"
```

---

## Database Architecture

CIRIS uses three separate PostgreSQL databases:

```
postgresql://user:pass@host:port/ciris_db          ← Main database (set via CIRIS_DB_URL)
                                     ├── _secrets   ← Automatically derived
                                     └── _auth      ← Automatically derived
```

**Why three databases?**
- **Security isolation**: Secrets are stored in a separate database
- **Auth separation**: Authentication data is isolated from application data
- **Easier backups**: You can backup each database independently

You only need to specify the **main database** in `CIRIS_DB_URL`. CIRIS automatically:
- Connects to `{main_db}_secrets` for secrets storage
- Connects to `{main_db}_auth` for authentication

---

## Configuration

### Environment Variables

```bash
# Required - tells CIRIS to use PostgreSQL
export CIRIS_DB_URL='postgresql://username:password@host:port/database_name'

# Optional - override default host/port
export CIRIS_DB_URL='postgresql://ciris_test:ciris_test_password@192.168.1.100:5433/ciris_test_db'

# Passwords with special characters (@, {, }, [, ], etc.) are supported
# Both formats work (URL-encoded or non-encoded):
export CIRIS_DB_URL='postgresql://user:p@ss{w}rd[123]@localhost:5432/db'           # Non-encoded
export CIRIS_DB_URL='postgresql://user:p%40ss%7Bw%7Drd%5B123%5D@localhost:5432/db' # URL-encoded
```

### Configuration File

Alternatively, add to `config/essential.yaml`:

```yaml
database:
  database_url: "postgresql://ciris_test:ciris_test_password@localhost:5432/ciris_test_db"
```

**Note:** Environment variable takes precedence over config file.

---

## Switching Between SQLite and PostgreSQL

CIRIS automatically detects the database type from the connection string:

### Use SQLite (default):
```bash
unset CIRIS_DB_URL  # Uses data/ciris.db
python main.py --adapter cli
```

### Use PostgreSQL:
```bash
export CIRIS_DB_URL='postgresql://ciris_test:ciris_test_password@localhost:5432/ciris_test_db'
python main.py --adapter cli
```

No code changes needed - CIRIS handles the dialect translation automatically!

---

## Troubleshooting

### "permission denied to create database"

The user needs CREATEDB privilege:
```bash
sudo -u postgres psql -c "ALTER USER ciris_test CREATEDB;"
```

### "database does not exist"

Run the setup script or manually create the databases as shown above.

### "password authentication failed"

Check your connection string:
- Username is correct
- Password is correct (check for special characters that need URL encoding)
- PostgreSQL is configured to accept password authentication

Edit `/etc/postgresql/*/main/pg_hba.conf`:
```
# Add this line for local connections:
host    all             all             127.0.0.1/32            md5
```

Then restart PostgreSQL:
```bash
sudo systemctl restart postgresql
```

### "connection refused"

PostgreSQL might not be running:
```bash
sudo systemctl status postgresql
sudo systemctl start postgresql
```

---

## Migration from SQLite to PostgreSQL

To migrate existing SQLite data to PostgreSQL:

1. **Backup your SQLite database:**
   ```bash
   cp data/ciris.db data/ciris.db.backup
   ```

2. **Set up PostgreSQL** (follow steps above)

3. **Note:** There is currently no automatic migration tool. You'll start fresh with PostgreSQL.

---

## Production Recommendations

### Security

1. **Use strong passwords:**
   ```bash
   # Generate a strong password
   openssl rand -base64 32
   ```

2. **Restrict database access:**
   ```sql
   -- Connect only from localhost
   REVOKE ALL ON DATABASE ciris_db FROM PUBLIC;
   GRANT CONNECT ON DATABASE ciris_db TO ciris_user;
   ```

3. **Enable SSL connections:**
   ```bash
   export CIRIS_DB_URL='postgresql://user:pass@host:5432/db?sslmode=require'
   ```

### Performance

1. **Adjust PostgreSQL settings** in `/etc/postgresql/*/main/postgresql.conf`:
   ```
   shared_buffers = 256MB
   effective_cache_size = 1GB
   maintenance_work_mem = 64MB
   ```

2. **Enable connection pooling** (future feature)

### Backups

```bash
# Backup all three databases
pg_dump -h localhost -U ciris_test ciris_test_db > backup_main.sql
pg_dump -h localhost -U ciris_test ciris_test_db_secrets > backup_secrets.sql
pg_dump -h localhost -U ciris_test ciris_test_db_auth > backup_auth.sql

# Restore
psql -h localhost -U ciris_test ciris_test_db < backup_main.sql
psql -h localhost -U ciris_test ciris_test_db_secrets < backup_secrets.sql
psql -h localhost -U ciris_test ciris_test_db_auth < backup_auth.sql
```

---

## Testing

Verify your setup:

```bash
# 1. Set environment
export CIRIS_DB_URL='postgresql://ciris_test:ciris_test_password@localhost:5432/ciris_test_db'

# 2. Run CIRIS with timeout
python main.py --adapter cli --mock-llm --timeout 10

# 3. Check logs
tail -f logs/latest.log
```

Expected output:
```
✓ Database initialized at postgresql://ciris_test:...
✓ Database integrity verified
✓ Phase database completed successfully
```

---

## Support

If you encounter issues:

1. Check the logs: `logs/incidents_latest.log`
2. Verify PostgreSQL is running: `sudo systemctl status postgresql`
3. Test connection manually: `psql -h localhost -U ciris_test -d ciris_test_db`
4. Review this guide for troubleshooting steps

---

## Summary

**Quick commands for testing:**

```bash
# Setup (one time)
sudo ./tools/database/setup_postgres_sudo.sh ciris_test_db ciris_test ciris_test_password

# Run CIRIS with PostgreSQL
export CIRIS_DB_URL='postgresql://ciris_test:ciris_test_password@localhost:5432/ciris_test_db'
python main.py --adapter cli --mock-llm

# Switch back to SQLite
unset CIRIS_DB_URL
python main.py --adapter cli
```

That's it! You now have CIRIS running on PostgreSQL. 🎉
