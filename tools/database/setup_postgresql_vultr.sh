#!/bin/bash
# PostgreSQL Database Setup Script for CIRIS Agent (Vultr Managed Database)
#
# This script sets up CIRIS databases on a Vultr managed PostgreSQL cluster.
#
# Prerequisites:
#   1. Create a dedicated user 'ciris_user' in the Vultr console with CREATEDB privilege
#   2. Download the SSL certificate from Vultr dashboard
#   3. Note the VPC IP address from Vultr dashboard
#
# Usage:
#   ./setup_postgresql_vultr.sh [database_name] [username] [password] [host] [port] [cert_path]
#
# Examples:
#   # Using VPC IP (recommended for production)
#   ./setup_postgresql_vultr.sh ciris_db ciris_user 'your_password' \
#       10.2.96.5 16751 ~/vultr-ca-certificate.crt
#
#   # Using public host (for external access)
#   ./setup_postgresql_vultr.sh ciris_db ciris_user 'your_password' \
#       public-vultr-prod-xxx.vultrdb.com 16751 ~/vultr-ca-certificate.crt

set -e  # Exit on error

# Color codes for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Default values (update these for your Vultr cluster)
DEFAULT_DB_NAME="ciris_db"
DEFAULT_USER="ciris_user"
DEFAULT_PASSWORD=""  # Must be provided
DEFAULT_HOST=""      # Must be provided (VPC IP or public host)
DEFAULT_PORT="16751"
DEFAULT_CERT_PATH="$HOME/vultr-ca-certificate.crt"

# Parse arguments
DB_NAME="${1:-$DEFAULT_DB_NAME}"
DB_USER="${2:-$DEFAULT_USER}"
DB_PASSWORD="${3:-$DEFAULT_PASSWORD}"
DB_HOST="${4:-$DEFAULT_HOST}"
DB_PORT="${5:-$DEFAULT_PORT}"
CERT_PATH="${6:-$DEFAULT_CERT_PATH}"

# Derivative database names
SECRETS_DB="${DB_NAME}_secrets"
AUTH_DB="${DB_NAME}_auth"

# Validation
if [ -z "$DB_PASSWORD" ]; then
    echo -e "${RED}✗ Error: Database password is required${NC}"
    echo "Usage: $0 [database_name] [username] PASSWORD [host] [port] [cert_path]"
    exit 1
fi

if [ -z "$DB_HOST" ]; then
    echo -e "${RED}✗ Error: Database host is required${NC}"
    echo "Usage: $0 [database_name] [username] [password] HOST [port] [cert_path]"
    echo ""
    echo -e "${YELLOW}Get your VPC IP from Vultr dashboard:${NC}"
    echo "  Products -> PostgreSQL -> cirispostgres -> VPC Network"
    exit 1
fi

if [ ! -f "$CERT_PATH" ]; then
    echo -e "${RED}✗ Error: SSL certificate not found at: $CERT_PATH${NC}"
    echo ""
    echo -e "${YELLOW}Download the certificate from Vultr dashboard:${NC}"
    echo "  Products -> PostgreSQL -> cirispostgres -> Connection Details"
    echo "  Click 'Download Signed Certificate'"
    exit 1
fi

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}CIRIS PostgreSQL Setup (Vultr Managed)${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo -e "${YELLOW}Configuration:${NC}"
echo "  Host: $DB_HOST"
echo "  Port: $DB_PORT"
echo "  User: $DB_USER"
echo "  SSL Certificate: $CERT_PATH"
echo "  Main Database: $DB_NAME"
echo "  Secrets Database: $SECRETS_DB"
echo "  Auth Database: $AUTH_DB"
echo ""

# Function to check if PostgreSQL is accessible
check_postgres() {
    echo -e "${BLUE}Checking PostgreSQL connection...${NC}"
    if ! pg_isready -h "$DB_HOST" -p "$DB_PORT" > /dev/null 2>&1; then
        echo -e "${RED}✗ PostgreSQL is not accessible at $DB_HOST:$DB_PORT${NC}"
        echo -e "${YELLOW}Please verify:${NC}"
        echo "  1. VPC IP address is correct"
        echo "  2. Your machine is on the same VPC network"
        echo "  3. Firewall rules allow PostgreSQL connections"
        exit 1
    fi
    echo -e "${GREEN}✓ PostgreSQL is accessible${NC}"
}

# Function to check if database exists
db_exists() {
    local dbname=$1
    PGSSLMODE=require PGSSLROOTCERT="$CERT_PATH" PGPASSWORD="$DB_PASSWORD" \
        psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d defaultdb -tAc \
        "SELECT 1 FROM pg_database WHERE datname='$dbname'" 2>/dev/null | grep -q 1
}

# Function to execute psql with SSL
psql_ssl() {
    PGSSLMODE=require PGSSLROOTCERT="$CERT_PATH" PGPASSWORD="$DB_PASSWORD" \
        psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" "$@"
}

# Check PostgreSQL connection
check_postgres

# Test user credentials
echo ""
echo -e "${BLUE}Testing user credentials...${NC}"
if ! psql_ssl -d defaultdb -c "SELECT 1" > /dev/null 2>&1; then
    echo -e "${RED}✗ Failed to authenticate as user '$DB_USER'${NC}"
    echo ""
    echo -e "${YELLOW}Please create the user in Vultr console:${NC}"
    echo "  1. Go to Products -> PostgreSQL -> cirispostgres -> Users"
    echo "  2. Click 'Add User'"
    echo "  3. Username: $DB_USER"
    echo "  4. Set a strong password"
    echo "  5. Grant CREATEDB privilege if possible"
    exit 1
fi
echo -e "${GREEN}✓ User '$DB_USER' authenticated successfully${NC}"

# Create main database
echo ""
echo -e "${BLUE}Creating main database...${NC}"
if db_exists "$DB_NAME"; then
    echo -e "${YELLOW}✓ Database '$DB_NAME' already exists${NC}"
else
    psql_ssl -d defaultdb <<EOF
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
    psql_ssl -d defaultdb <<EOF
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
    psql_ssl -d defaultdb <<EOF
CREATE DATABASE $AUTH_DB OWNER $DB_USER;
EOF
    echo -e "${GREEN}✓ Database '$AUTH_DB' created${NC}"
fi

# Run migrations on main database
echo ""
echo -e "${BLUE}Running PostgreSQL migrations on main database...${NC}"
MIGRATION_DIR="ciris_engine/logic/persistence/db/migrations/postgres"
if [ -d "$MIGRATION_DIR" ]; then
    for migration in "$MIGRATION_DIR"/*.sql; do
        if [ -f "$migration" ]; then
            migration_name=$(basename "$migration")
            echo -e "${BLUE}  Applying $migration_name...${NC}"
            psql_ssl -d "$DB_NAME" -f "$migration" > /dev/null 2>&1 || {
                echo -e "${YELLOW}  ⚠ Migration may have already been applied: $migration_name${NC}"
            }
        fi
    done
    echo -e "${GREEN}✓ Migrations applied to main database${NC}"
else
    echo -e "${YELLOW}⚠ No migration directory found at $MIGRATION_DIR${NC}"
    echo -e "${YELLOW}  (Tables will be created on first run)${NC}"
fi

# Test connections
echo ""
echo -e "${BLUE}Testing database connections...${NC}"

# Test main database
if psql_ssl -d "$DB_NAME" -c "SELECT 1" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Main database connection successful${NC}"
else
    echo -e "${RED}✗ Failed to connect to main database${NC}"
    exit 1
fi

# Test secrets database
if psql_ssl -d "$SECRETS_DB" -c "SELECT 1" > /dev/null 2>&1; then
    echo -e "${GREEN}✓ Secrets database connection successful${NC}"
else
    echo -e "${RED}✗ Failed to connect to secrets database${NC}"
    exit 1
fi

# Test auth database
if psql_ssl -d "$AUTH_DB" -c "SELECT 1" > /dev/null 2>&1; then
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
echo -e "${YELLOW}Connection String (with SSL):${NC}"
echo "  postgresql://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME?sslmode=require"
echo ""
echo -e "${YELLOW}Environment Variables:${NC}"
echo "  export CIRIS_DB_URL='postgresql://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME?sslmode=require'"
echo "  export PGSSLROOTCERT='$CERT_PATH'"
echo ""
echo -e "${YELLOW}To start CIRIS with Vultr PostgreSQL:${NC}"
echo "  export CIRIS_DB_URL='postgresql://$DB_USER:$DB_PASSWORD@$DB_HOST:$DB_PORT/$DB_NAME?sslmode=require'"
echo "  export PGSSLROOTCERT='$CERT_PATH'"
echo "  python main.py --adapter cli --mock-llm"
echo ""
echo -e "${BLUE}Note: Using VPC IP ($DB_HOST) provides better performance and security${NC}"
echo -e "${BLUE}      than the public host for production deployments.${NC}"
echo ""
