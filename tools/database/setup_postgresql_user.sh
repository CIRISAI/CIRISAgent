#!/bin/bash
# PostgreSQL Database Setup Script for CIRIS Agent (User Mode)
#
# This script creates derivative databases using an existing PostgreSQL user
# with CREATEDB privilege. Use this when you don't have postgres superuser access.
#
# Usage:
#   ./setup_postgresql_user.sh [database_name] [username] [password]
#
# Examples:
#   ./setup_postgresql_user.sh ciris_test_db ciris_test ciris_test_password
#   ./setup_postgresql_user.sh ciris_db ciris_user mypassword

set -e  # Exit on error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

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
    echo -e "${BLUE}Checking PostgreSQL connection...${NC}"
    if ! pg_isready -h "$DB_HOST" -p "$DB_PORT" > /dev/null 2>&1; then
        echo -e "${RED}✗ PostgreSQL is not running or not accessible at $DB_HOST:$DB_PORT${NC}"
        echo -e "${YELLOW}Please start PostgreSQL and try again.${NC}"
        exit 1
    fi
    echo -e "${GREEN}✓ PostgreSQL is running${NC}"
}

# Function to check if database exists
db_exists() {
    local dbname=$1
    PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -tAc \
        "SELECT 1 FROM pg_database WHERE datname='$dbname'" 2>/dev/null | grep -q 1
}

# Check PostgreSQL connection
check_postgres

# Test user credentials
echo ""
echo -e "${BLUE}Testing user credentials...${NC}"
if ! PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres -c "SELECT 1" > /dev/null 2>&1; then
    echo -e "${RED}✗ Failed to authenticate as user '$DB_USER'${NC}"
    echo -e "${YELLOW}Please check your username and password.${NC}"
    exit 1
fi
echo -e "${GREEN}✓ User '$DB_USER' authenticated successfully${NC}"

# Check if main database exists
echo ""
echo -e "${BLUE}Checking main database...${NC}"
if db_exists "$DB_NAME"; then
    echo -e "${GREEN}✓ Main database '$DB_NAME' exists${NC}"
else
    echo -e "${YELLOW}Creating main database '$DB_NAME'...${NC}"
    PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres <<EOF
CREATE DATABASE $DB_NAME OWNER $DB_USER;
EOF
    echo -e "${GREEN}✓ Database '$DB_NAME' created${NC}"
fi

# Create secrets database
echo ""
echo -e "${BLUE}Creating secrets database...${NC}"
if db_exists "$SECRETS_DB"; then
    echo -e "${YELLOW}✓ Database '$SECRETS_DB' already exists${NC}"
else
    PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres <<EOF
CREATE DATABASE $SECRETS_DB OWNER $DB_USER;
EOF
    echo -e "${GREEN}✓ Database '$SECRETS_DB' created${NC}"
fi

# Create auth database
echo ""
echo -e "${BLUE}Creating auth database...${NC}"
if db_exists "$AUTH_DB"; then
    echo -e "${YELLOW}✓ Database '$AUTH_DB' already exists${NC}"
else
    PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d postgres <<EOF
CREATE DATABASE $AUTH_DB OWNER $DB_USER;
EOF
    echo -e "${GREEN}✓ Database '$AUTH_DB' created${NC}"
fi

# Run migrations on main database
echo ""
echo -e "${BLUE}Running PostgreSQL migrations on main database...${NC}"
MIGRATION_DIR="ciris_engine/logic/persistence/db/migrations/postgresql"
if [ -d "$MIGRATION_DIR" ]; then
    for migration in "$MIGRATION_DIR"/*.sql; do
        if [ -f "$migration" ]; then
            migration_name=$(basename "$migration")
            echo -e "${BLUE}  Applying $migration_name...${NC}"
            PGPASSWORD="$DB_PASSWORD" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" -f "$migration" > /dev/null 2>&1 || {
                echo -e "${YELLOW}  ⚠ Migration may have already been applied: $migration_name${NC}"
            }
        fi
    done
    echo -e "${GREEN}✓ Migrations applied to main database${NC}"
else
    echo -e "${YELLOW}⚠ No migration directory found at $MIGRATION_DIR${NC}"
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

# Display connection string
echo ""
echo -e "${GREEN}========================================${NC}"
echo -e "${GREEN}Setup Complete!${NC}"
echo -e "${GREEN}========================================${NC}"
echo ""
echo -e "${YELLOW}Connection String:${NC}"
echo "  postgresql://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME"
echo ""
echo -e "${YELLOW}Environment Variable:${NC}"
echo "  export CIRIS_DB_URL='postgresql://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME'"
echo ""
echo -e "${YELLOW}To start CIRIS with PostgreSQL:${NC}"
echo "  export CIRIS_DB_URL='postgresql://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME'"
echo "  python main.py --adapter cli --mock-llm"
echo ""
