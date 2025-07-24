#!/bin/bash
# Create ciris user for managing CIRIS services
# This script creates a dedicated user for running CIRISManager and managing configurations

set -e

# Configuration
CIRIS_USER="${CIRIS_USER:-ciris}"
CIRIS_HOME="${CIRIS_HOME:-/home/ciris}"
CIRIS_SHELL="${CIRIS_SHELL:-/bin/bash}"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1"
}

error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1"
}

# Check if running with sudo
if [ "$EUID" -ne 0 ]; then 
    error "This script must be run with sudo"
    echo "Usage: sudo $0"
    exit 1
fi

log "Creating CIRIS user and environment..."

# Check if user already exists
if id "$CIRIS_USER" &>/dev/null; then
    warn "User '$CIRIS_USER' already exists"
    log "Skipping user creation"
else
    # Create the user
    log "Creating user '$CIRIS_USER'..."
    useradd -m -s "$CIRIS_SHELL" -d "$CIRIS_HOME" "$CIRIS_USER" || {
        error "Failed to create user"
        exit 1
    }
    log "✓ User created successfully"
fi

# Create necessary directories
log "Creating directory structure..."
directories=(
    "$CIRIS_HOME/CIRISAgent"
    "$CIRIS_HOME/nginx"
    "$CIRIS_HOME/shared/oauth"
    "$CIRIS_HOME/.ciris"
    "$CIRIS_HOME/.config/ciris-manager"
    "/var/log/ciris"
    "/var/run/ciris"
    "/etc/ciris-manager/agents"
)

for dir in "${directories[@]}"; do
    if [ ! -d "$dir" ]; then
        mkdir -p "$dir"
        chown "$CIRIS_USER:$CIRIS_USER" "$dir"
        log "✓ Created $dir"
    else
        log "  Directory exists: $dir"
    fi
done

# Set permissions
log "Setting permissions..."
chmod 750 "$CIRIS_HOME"
chmod 755 "$CIRIS_HOME/nginx"
chmod 700 "$CIRIS_HOME/.ciris"
chmod 755 "/var/log/ciris"
chmod 755 "/var/run/ciris"

# Add current user to ciris group (for shared access)
CURRENT_USER="${SUDO_USER:-$USER}"
if [ -n "$CURRENT_USER" ] && [ "$CURRENT_USER" != "root" ]; then
    log "Adding $CURRENT_USER to $CIRIS_USER group..."
    usermod -a -G "$CIRIS_USER" "$CURRENT_USER" || {
        warn "Failed to add $CURRENT_USER to $CIRIS_USER group"
    }
    log "Note: You may need to log out and back in for group changes to take effect"
fi

# Create sudoers entry for docker commands (optional)
SUDOERS_FILE="/etc/sudoers.d/ciris-docker"
if [ ! -f "$SUDOERS_FILE" ]; then
    log "Creating sudoers entry for docker commands..."
    cat > "$SUDOERS_FILE" << EOF
# Allow ciris user to run docker commands without password
$CIRIS_USER ALL=(ALL) NOPASSWD: /usr/bin/docker, /usr/bin/docker-compose
EOF
    chmod 440 "$SUDOERS_FILE"
    log "✓ Sudoers entry created"
fi

# Summary
log "User setup complete!"
echo
echo "Created/configured:"
echo "  - User: $CIRIS_USER"
echo "  - Home: $CIRIS_HOME"
echo "  - Groups: $(groups $CIRIS_USER | cut -d: -f2)"
echo
echo "Next steps:"
echo "  1. Clone CIRISAgent repo to $CIRIS_HOME/CIRISAgent"
echo "  2. Run deployment/setup-nginx-management.sh"
echo "  3. Configure CIRISManager"
echo
echo "To switch to ciris user:"
echo "  sudo su - $CIRIS_USER"