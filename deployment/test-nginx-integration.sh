#!/bin/bash
# Integration test for nginx management with CIRISManager
# This script tests the complete flow of nginx config generation and updates

set -e

# Configuration
NGINX_CONFIG_DIR="${NGINX_CONFIG_DIR:-/home/ciris/nginx}"
MANAGER_PORT="${MANAGER_PORT:-8888}"
TEST_MODE="${TEST_MODE:-false}"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log() {
    echo -e "${GREEN}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

info() {
    echo -e "${BLUE}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1"
}

warn() {
    echo -e "${YELLOW}[$(date '+%Y-%m-%d %H:%M:%S')] WARNING:${NC} $1"
}

error() {
    echo -e "${RED}[$(date '+%Y-%m-%d %H:%M:%S')] ERROR:${NC} $1"
}

# Function to check if service is running
check_service() {
    local service=$1
    local port=$2
    
    if curl -s -f "http://localhost:$port/health" >/dev/null 2>&1; then
        log "✓ $service is running on port $port"
        return 0
    else
        error "✗ $service is not accessible on port $port"
        return 1
    fi
}

# Function to get agent list from CIRISManager
get_agents() {
    curl -s "http://localhost:$MANAGER_PORT/manager/v1/agents" | jq -r '.agents[] | "\(.agent_id):\(.agent_name):\(.api_port)"' 2>/dev/null || echo ""
}

# Function to check nginx routes
check_nginx_route() {
    local route=$1
    local expected_response=$2
    
    response=$(curl -s -o /dev/null -w "%{http_code}" "http://localhost$route")
    if [ "$response" = "$expected_response" ]; then
        log "✓ Route $route returned $response"
        return 0
    else
        error "✗ Route $route returned $response (expected $expected_response)"
        return 1
    fi
}

log "Starting nginx integration test..."

# Step 1: Check prerequisites
info "Checking prerequisites..."

# Check if nginx config directory exists
if [ ! -d "$NGINX_CONFIG_DIR" ]; then
    error "Nginx config directory not found: $NGINX_CONFIG_DIR"
    error "Run ./deployment/setup-nginx-management.sh first"
    exit 1
fi

# Check if CIRISManager is running
if ! check_service "CIRISManager" "$MANAGER_PORT"; then
    error "CIRISManager not running"
    error "Start it with: python deployment/run-ciris-manager-api.py"
    exit 1
fi

# Step 2: Discover current agents
info "Discovering agents through CIRISManager..."
agents=$(get_agents)

if [ -z "$agents" ]; then
    warn "No agents found"
else
    log "Found agents:"
    echo "$agents" | while IFS=: read -r id name port; do
        echo "  - $name (ID: $id, Port: $port)"
    done
fi

# Step 3: Check nginx config file
info "Checking nginx configuration..."

if [ -f "$NGINX_CONFIG_DIR/nginx.conf" ]; then
    log "✓ Nginx config exists: $NGINX_CONFIG_DIR/nginx.conf"
    
    # Check config contents
    if grep -q "upstream gui" "$NGINX_CONFIG_DIR/nginx.conf"; then
        log "✓ GUI upstream found"
    else
        error "✗ GUI upstream missing"
    fi
    
    if grep -q "upstream manager" "$NGINX_CONFIG_DIR/nginx.conf"; then
        log "✓ Manager upstream found"
    else
        error "✗ Manager upstream missing"
    fi
    
    # Check for agent upstreams
    echo "$agents" | while IFS=: read -r id name port; do
        if grep -q "upstream agent_$id" "$NGINX_CONFIG_DIR/nginx.conf"; then
            log "✓ Agent upstream found: agent_$id"
        else
            error "✗ Agent upstream missing: agent_$id"
        fi
    done
else
    error "Nginx config not found!"
    error "CIRISManager should generate it on startup"
fi

# Step 4: Test nginx routes (if nginx is running)
if docker ps | grep -q ciris-nginx; then
    info "Testing nginx routes..."
    
    # Test health endpoint
    check_nginx_route "/health" "200"
    
    # Test manager route
    check_nginx_route "/manager/v1/health" "200"
    
    # Test agent routes
    echo "$agents" | while IFS=: read -r id name port; do
        check_nginx_route "/api/$id/v1/system/health" "200" || true
    done
    
    # Test default route (should go to datum if available)
    if echo "$agents" | grep -q "datum"; then
        check_nginx_route "/v1/system/health" "200" || true
    fi
else
    warn "Nginx container not running - skipping route tests"
fi

# Step 5: Test dynamic update (if in test mode)
if [ "$TEST_MODE" = "true" ]; then
    info "Testing dynamic configuration update..."
    
    # Force nginx config regeneration
    log "Triggering config regeneration..."
    curl -s "http://localhost:$MANAGER_PORT/manager/v1/agents" >/dev/null
    
    # Check if config was updated
    sleep 2
    if [ -f "$NGINX_CONFIG_DIR/nginx.conf.backup" ]; then
        log "✓ Backup file created"
    fi
    
    # Verify nginx reloaded
    if docker exec ciris-nginx nginx -t >/dev/null 2>&1; then
        log "✓ Nginx config is valid"
    else
        error "✗ Nginx config validation failed"
    fi
fi

# Summary
info "Test Summary:"
echo "  - Config directory: $NGINX_CONFIG_DIR"
echo "  - Manager accessible: $(check_service "CIRISManager" "$MANAGER_PORT" >/dev/null 2>&1 && echo "Yes" || echo "No")"
echo "  - Nginx config exists: $([ -f "$NGINX_CONFIG_DIR/nginx.conf" ] && echo "Yes" || echo "No")"
echo "  - Nginx running: $(docker ps | grep -q ciris-nginx && echo "Yes" || echo "No")"
echo "  - Agents found: $(echo "$agents" | grep -c ':')"

log "Integration test complete!"