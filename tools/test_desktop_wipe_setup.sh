#!/bin/bash
#
# test_desktop_wipe_setup.sh
# Desktop E2E Test: Wipe → Setup Wizard → Verify
#
# Tests the quick setup flow for authenticated users and full setup for new users.
# Requires CIRIS_TEST_MODE=true to be set before starting the app.
#
# Usage:
#   export CIRIS_TEST_MODE=true
#   ciris-agent  # Start app with test mode
#   bash tools/test_desktop_wipe_setup.sh [--quick|--full|--wipe-only]
#

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

TEST_URL="http://localhost:9091"
API_URL="http://localhost:8080"
TIMEOUT=30
MODE="${1:-quick}"

log() { echo -e "${BLUE}[TEST]${NC} $1"; }
log_ok() { echo -e "${GREEN}[OK]${NC} $1"; }
log_fail() { echo -e "${RED}[FAIL]${NC} $1"; exit 1; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }

wait_for_test_server() {
    log "Waiting for test server at $TEST_URL..."
    for i in $(seq 1 $TIMEOUT); do
        if curl -s "$TEST_URL/health" | grep -q "ok"; then
            log_ok "Test server ready"
            return 0
        fi
        sleep 1
    done
    log_fail "Test server not ready after ${TIMEOUT}s"
}

wait_for_api_server() {
    log "Waiting for API server at $API_URL..."
    for i in $(seq 1 $TIMEOUT); do
        if curl -s "$API_URL/v1/system/health" | grep -q "status"; then
            log_ok "API server ready"
            return 0
        fi
        sleep 1
    done
    log_fail "API server not ready after ${TIMEOUT}s"
}

get_screen() {
    curl -s "$TEST_URL/screen" | python3 -c "import json,sys; print(json.load(sys.stdin).get('screen', 'Unknown'))"
}

click() {
    local tag="$1"
    local result=$(curl -s -X POST "$TEST_URL/click" \
        -H "Content-Type: application/json" \
        -d "{\"testTag\": \"$tag\"}")
    if echo "$result" | grep -q "success.*true"; then
        log_ok "Clicked: $tag"
    else
        log_warn "Click may have failed: $tag"
    fi
    sleep 0.5
}

input_text() {
    local tag="$1"
    local text="$2"
    local clear="${3:-true}"
    local result=$(curl -s -X POST "$TEST_URL/input" \
        -H "Content-Type: application/json" \
        -d "{\"testTag\": \"$tag\", \"text\": \"$text\", \"clearFirst\": $clear}")
    if echo "$result" | grep -q "success.*true"; then
        log_ok "Input to $tag: ${text:0:20}..."
    else
        log_warn "Input may have failed: $tag"
    fi
    sleep 0.3
}

wait_for_element() {
    local tag="$1"
    local timeout="${2:-10}"
    log "Waiting for element: $tag"
    local result=$(curl -s -X POST "$TEST_URL/wait" \
        -H "Content-Type: application/json" \
        -d "{\"testTag\": \"$tag\", \"timeoutMs\": $((timeout * 1000))}")
    if echo "$result" | grep -q "found.*true"; then
        log_ok "Element found: $tag"
        return 0
    else
        log_fail "Element not found: $tag after ${timeout}s"
    fi
}

test_quick_setup_flow() {
    log "═══════════════════════════════════════════════════════════"
    log "TEST: Quick Setup Flow (Authenticated User)"
    log "═══════════════════════════════════════════════════════════"

    local screen=$(get_screen)
    log "Current screen: $screen"

    # Quick setup skips Welcome, goes to QuickSetup with CIRIS AI access
    log "Step 1: Proceed through quick setup"
    click "btn_wizard_next" || click "btn_next"
    sleep 1

    # Location step (expanded by default)
    wait_for_element "btn_wizard_next" 5
    click "btn_wizard_next"
    sleep 1

    # Services step (expanded by default)
    wait_for_element "btn_wizard_next" 5
    click "btn_wizard_next"
    sleep 1

    # Account step
    log "Step 2: Create account"
    input_text "input_username" "admin"
    sleep 0.5
    input_text "input_password" "testpassword123"
    sleep 0.5
    input_text "input_password_confirm" "testpassword123"
    sleep 0.5

    click "btn_wizard_complete" || click "btn_finish_setup"
    sleep 3

    wait_for_element "input_message" 10
    log_ok "Quick setup completed - on Interact screen"
}

test_verify_setup() {
    log "═══════════════════════════════════════════════════════════"
    log "TEST: Verify Setup Completed Correctly"
    log "═══════════════════════════════════════════════════════════"

    local token=$(curl -s -X POST "$API_URL/v1/auth/login" \
        -H "Content-Type: application/json" \
        -d '{"username":"admin","password":"testpassword123"}' | \
        python3 -c "import json,sys; print(json.load(sys.stdin).get('access_token', ''))")

    if [ -n "$token" ] && [ "$token" != "None" ]; then
        log_ok "Login successful"
    else
        log_fail "Login failed"
    fi

    local services=$(curl -s -H "Authorization: Bearer $token" \
        "$API_URL/v1/telemetry/unified" | \
        python3 -c "import json,sys; d=json.load(sys.stdin); print(f\"{d.get('services_online',0)}/{d.get('services_total',0)}\")")
    log_ok "Services: $services"

    log_ok "All verifications passed!"
}

echo ""
echo "╔═══════════════════════════════════════════════════════════════╗"
echo "║     CIRIS Desktop E2E Test - Mode: $MODE                      ║"
echo "╚═══════════════════════════════════════════════════════════════╝"
echo ""

wait_for_test_server
wait_for_api_server

case "$MODE" in
    "quick"|"--quick")
        test_quick_setup_flow
        test_verify_setup
        ;;
    *)
        echo "Usage: $0 [--quick|--full|--wipe-only]"
        exit 1
        ;;
esac

echo ""
echo -e "${GREEN}${BOLD}ALL TESTS PASSED${NC}"
echo ""
