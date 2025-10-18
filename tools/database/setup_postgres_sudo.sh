#!/bin/bash
# PostgreSQL Database Setup Script for CIRIS Agent (Sudo Mode)
#
# This script creates the necessary PostgreSQL databases for CIRIS Agent
# using sudo to authenticate as the postgres system user.
#
# Usage:
#   sudo ./setup_postgres_sudo.sh [database_name] [username] [password]
#
# Examples:
#   sudo ./setup_postgres_sudo.sh ciris_test_db ciris_test ciris_test_password
#   sudo ./setup_postgres_sudo.sh ciris_db ciris_user mypassword

set -e  # Exit on error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Check if running as root/sudo
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}✗ This script must be run with sudo${NC}"
    echo "Usage: sudo $0 [database_name] [username] [password]"
    exit 1
fi

# Default values
DEFAULT_DB_NAME="ciris_db"
DEFAULT_USER="ciris_user"
DEFAULT_PASSWORD="ciris_password"
DEFAULT_HOST="localhost"
DEFAULT_PORT="5432"

# Parse arguments
DB_NAME="${1:-$DEFAULT_DB_NAME}"
DB_USER="${2:-$DEFAULT_USER}"
DB_PASSWORD="${3:-$DEFAULT_PASSWORD}"
DB_HOST="${4:-$DEFAULT_HOST}"
DB_PORT="${5:-$DEFAULT_PORT}"

# Derivative database names
SECRETS_DB="${DB_NAME}_secrets"
AUTH_DB="${DB_NAME}_auth"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}CIRIS PostgreSQL Database Setup${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${YELLOW}Configuration:${NC}"
echo "  Host: $DB_HOST"
echo "  Port: $DB_PORT"
echo "  User: $DB_USER"
echo "  Main Database: $DB_NAME"
echo "  Secrets Database: $SECRETS_DB"
echo "  Auth Database: $AUTH_DB"
echo ""

# Function to check if PostgreSQL is running
check_postgres() {
    echo -e "${BLUE}Checking PostgreSQL service...${NC}"
    if ! systemctl is-active --quiet postgresql; then
        echo -e "${YELLOW}PostgreSQL is not running. Starting it...${NC}"
        systemctl start postgresql
        sleep 2
    fi

    if pg_isready -h "$DB_HOST" -p "$DB_PORT" > /dev/null 2>&1; then
        echo -e "${GREEN}✓ PostgreSQL is running${NC}"
    else
        echo -e "${RED}✗ PostgreSQL is not accessible at $DB_HOST:$DB_PORT${NC}"
        exit 1
    fi
}

# Function to execute SQL as postgres user
psql_as_postgres() {
    sudo -u postgres psql "$@"
}

# Function to check if user exists
user_exists() {
    local user=$1
    psql_as_postgres -tAc "SELECT 1 FROM pg_roles WHERE rolname='$user'" | grep -q 1
}

# Function to check if database exists
db_exists() {
    local dbname=$1
    psql_as_postgres -tAc "SELECT 1 FROM pg_database WHERE datname='$dbname'" | grep -q 1
}

# Check PostgreSQL
check_postgres

# Create user if it doesn't exist
echo ""
echo -e "${BLUE}Setting up database user...${NC}"
if user_exists "$DB_USER"; then
    echo -e "${YELLOW}✓ User '$DB_USER' already exists${NC}"
else
    psql_as_postgres <<EOF
CREATE USER $DB_USER WITH PASSWORD '$DB_PASSWORD';
ALTER USER $DB_USER CREATEDB;
EOF
    echo -e "${GREEN}✓ User '$DB_USER' created${NC}"
fi

# Create main database
echo ""
echo -e "${BLUE}Creating main database...${NC}"
if db_exists "$DB_NAME"; then
    echo -e "${YELLOW}✓ Database '$DB_NAME' already exists${NC}"
else
    psql_as_postgres <<EOF
CREATE DATABASE $DB_NAME OWNER $DB_USER;
GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;
EOF
    echo -e "${GREEN}✓ Database '$DB_NAME' created${NC}"
fi

# Create secrets database
echo ""
echo -e "${BLUE}Creating secrets database...${NC}"
if db_exists "$SECRETS_DB"; then
    echo -e "${YELLOW}✓ Database '$SECRETS_DB' already exists${NC}"
else
    psql_as_postgres <<EOF
CREATE DATABASE $SECRETS_DB OWNER $DB_USER;
GRANT ALL PRIVILEGES ON DATABASE $SECRETS_DB TO $DB_USER;
EOF
    echo -e "${GREEN}✓ Database '$SECRETS_DB' created${NC}"
fi

# Create auth database
echo ""
echo -e "${BLUE}Creating auth database...${NC}"
if db_exists "$AUTH_DB"; then
    echo -e "${YELLOW}✓ Database '$AUTH_DB' already exists${NC}"
else
    psql_as_postgres <<EOF
CREATE DATABASE $AUTH_DB OWNER $DB_USER;
GRANT ALL PRIVILEGES ON DATABASE $AUTH_DB TO $DB_USER;
EOF
    echo -e "${GREEN}✓ Database '$AUTH_DB' created${NC}"
fi

# Run migrations on main database if they exist
echo ""
echo -e "${BLUE}Checking for migrations...${NC}"
MIGRATION_DIR="ciris_engine/logic/persistence/db/migrations/postgresql"
if [ -d "$MIGRATION_DIR" ]; then
    echo -e "${BLUE}Running PostgreSQL migrations on main database...${NC}"
    for migration in "$MIGRATION_DIR"/*.sql; do
        if [ -f "$migration" ]; then
            migration_name=$(basename "$migration")
            echo -e "${BLUE}  Applying $migration_name...${NC}"
            PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$migration" > /dev/null 2>&1 || {
                echo -e "${YELLOW}  ⚠ Migration may have already been applied: $migration_name${NC}"
            }
        fi
    done
    echo -e "${GREEN}✓ Migrations applied${NC}"
else
    echo -e "${YELLOW}⚠ No migration directory found at $MIGRATION_DIR${NC}"
    echo -e "${YELLOW}  (This is normal - tables will be created on first run)${NC}"
fi

# Test connections
echo ""
echo -e "${BLUE}Testing database connections...${NC}"

# Test main database
if PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -c "SELECT 1" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Main database connection successful${NC}"
else
    echo -e "${RED}✗ Failed to connect to main database${NC}"
    exit 1
fi

# Test secrets database
if PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$SECRETS_DB" -c "SELECT 1" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Secrets database connection successful${NC}"
else
    echo -e "${RED}✗ Failed to connect to secrets database${NC}"
    exit 1
fi

# Test auth database
if PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$AUTH_DB" -c "SELECT 1" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Auth database connection successful${NC}"
else
    echo -e "${RED}✗ Failed to connect to auth database${NC}"
    exit 1
fi

# Display summary
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}✓ Setup Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${YELLOW}Databases created:${NC}"
echo "  • $DB_NAME (main)"
echo "  • $SECRETS_DB (secrets storage)"
echo "  • $AUTH_DB (authentication)"
echo ""
echo -e "${YELLOW}Connection String:${NC}"
echo "  postgresql://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME"
echo ""
echo -e "${YELLOW}To use with CIRIS Agent:${NC}"
echo "  1. Set the environment variable:"
echo "     export CIRIS_DB_URL='postgresql://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME'"
echo ""
echo "  2. Run CIRIS:"
echo "     python main.py --adapter cli --mock-llm"
echo ""
echo -e "${BLUE}Note: The derivative databases (_secrets and _auth) are automatically${NC}"
echo -e "${BLUE}      used by CIRIS based on the main database name.${NC}"
echo ""
