#!/bin/bash
# Setup script for nginx management with CIRISManager
# This script prepares the nginx configuration directory and ensures
# CIRISManager can manage nginx configurations dynamically.

set -e

# Configuration
NGINX_CONFIG_DIR="${NGINX_CONFIG_DIR:-/home/ciris/nginx}"
NGINX_CONTAINER="${NGINX_CONTAINER:-ciris-nginx}"
CIRIS_USER="${CIRIS_USER:-ciris}"
USE_CURRENT_USER="${USE_CURRENT_USER:-false}"  # Set to true to use current user instead

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

log "Setting up nginx management for CIRISManager..."

# Check if we should use current user
if [ "$USE_CURRENT_USER" = "true" ]; then
    CIRIS_USER=$(whoami)
    log "Using current user: $CIRIS_USER"
else
    # Check if ciris user exists
    if ! id "$CIRIS_USER" &>/dev/null; then
        error "User '$CIRIS_USER' does not exist!"
        error "Please run: sudo ./deployment/create-ciris-user.sh"
        error "Or set USE_CURRENT_USER=true to use current user"
        exit 1
    fi
fi

# Step 1: Create nginx config directory
log "Creating nginx configuration directory..."
if [ "$USE_CURRENT_USER" = "true" ]; then
    mkdir -p "$NGINX_CONFIG_DIR"
else
    sudo mkdir -p "$NGINX_CONFIG_DIR"
fi

# Step 2: Set ownership so CIRISManager can write configs
log "Setting directory ownership to $CIRIS_USER..."
if [ "$USE_CURRENT_USER" = "true" ]; then
    # Already owned by current user
    log "Directory owned by current user"
else
    sudo chown -R "$CIRIS_USER:$CIRIS_USER" "$NGINX_CONFIG_DIR"
fi

# Step 3: Generate initial nginx config if CIRISManager is installed
CIRIS_AGENT_PATH="${CIRIS_AGENT_PATH:-$(pwd)}"
if command -v python3 >/dev/null 2>&1 && [ -f "$CIRIS_AGENT_PATH/ciris_manager/nginx_manager.py" ]; then
    log "Generating initial nginx configuration..."
    
    # Create a simple Python script to generate initial config
    cat > /tmp/generate_initial_nginx.py << EOF
#!/usr/bin/env python3
import sys
sys.path.insert(0, '$CIRIS_AGENT_PATH')

from ciris_manager.nginx_manager import NginxManager
from ciris_manager.docker_discovery import DockerAgentDiscovery

# Initialize managers
nginx_manager = NginxManager(config_dir='$NGINX_CONFIG_DIR')
discovery = DockerAgentDiscovery()

# Discover current agents
print("Discovering agents...")
agents = discovery.discover_agents()
print(f"Found {len(agents)} agents")

# Generate and save nginx config
print("Generating nginx configuration...")
success = nginx_manager.update_config(agents)

if success:
    print("✓ Nginx configuration generated successfully")
else:
    print("✗ Failed to generate nginx configuration")
    sys.exit(1)
EOF

    # Run the generation script
    if [ "$USE_CURRENT_USER" = "true" ]; then
        python3 /tmp/generate_initial_nginx.py || {
            warn "Failed to generate initial nginx config"
            warn "CIRISManager will generate it on first run"
        }
    else
        sudo -u "$CIRIS_USER" python3 /tmp/generate_initial_nginx.py || {
            warn "Failed to generate initial nginx config"
            warn "CIRISManager will generate it on first run"
        }
    fi
    rm -f /tmp/generate_initial_nginx.py
else
    warn "CIRISManager not found at $CIRIS_AGENT_PATH - nginx config will be generated on first run"
fi

# Step 4: Check if nginx container is using the volume mount
log "Checking nginx container configuration..."
if docker inspect "$NGINX_CONTAINER" >/dev/null 2>&1; then
    # Check if the container has the correct volume mount
    if docker inspect "$NGINX_CONTAINER" | grep -q "$NGINX_CONFIG_DIR/nginx.conf:/etc/nginx/nginx.conf"; then
        log "✓ Nginx container is correctly configured with volume mount"
        
        # Test nginx config if container is running
        if docker exec "$NGINX_CONTAINER" nginx -t >/dev/null 2>&1; then
            log "✓ Nginx configuration is valid"
        else
            warn "Nginx configuration validation failed"
            docker exec "$NGINX_CONTAINER" nginx -t
        fi
    else
        error "Nginx container is not using the managed config volume!"
        error "Please update your docker-compose.yml to mount:"
        error "  $NGINX_CONFIG_DIR/nginx.conf:/etc/nginx/nginx.conf:ro"
    fi
else
    warn "Nginx container not found - will be configured on first start"
fi

# Step 5: Show configuration summary
log "Configuration Summary:"
echo "  - Config directory: $NGINX_CONFIG_DIR"
echo "  - Config file: $NGINX_CONFIG_DIR/nginx.conf"
echo "  - Owner: $CIRIS_USER"
echo "  - Container: $NGINX_CONTAINER"

# Step 6: Instructions for docker-compose
if [ ! -f "$NGINX_CONFIG_DIR/nginx.conf" ]; then
    warn "No nginx.conf found yet"
    log "Next steps:"
    echo "  1. Ensure CIRISManager is running"
    echo "  2. CIRISManager will generate nginx.conf on startup"
    echo "  3. Start nginx container with the volume mount"
else
    log "Next steps:"
    echo "  1. Ensure your docker-compose.yml mounts the nginx config:"
    echo "     volumes:"
    echo "       - $NGINX_CONFIG_DIR/nginx.conf:/etc/nginx/nginx.conf:ro"
    echo "  2. Restart nginx container if needed:"
    echo "     docker-compose up -d nginx"
fi

log "Setup complete!"