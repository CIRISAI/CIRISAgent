#!/bin/bash
# CIRIS Installation Verification Script
#
# Validates CIRIS installations across deployment methods:
# - install.sh
# - wheel (pip install)
# - APK (Android)
# - Docker
#
# Usage:
#   ./verify_install.sh [OPTIONS]
#
# Options:
#   -u, --url URL          Base URL (default: http://localhost:8080)
#   -v, --version VERSION  Expected version to match
#   -t, --timeout SECONDS  Request timeout (default: 10)
#   --skip-auth            Skip authentication check
#   --skip-interaction     Skip agent interaction check
#   --json                 Output JSON format
#   -q, --quiet            Minimal output
#   -h, --help             Show this help
#
# Exit Codes:
#   0 - All checks passed
#   1 - Health check failed (server not running)
#   2 - Version mismatch
#   3 - Setup wizard issue
#   4 - Authentication failed
#   5 - Agent interaction failed

set -euo pipefail

# ============================================================================
# Configuration
# ============================================================================

DEFAULT_URL="http://localhost:8080"
DEFAULT_TIMEOUT=10
VERSION=""
SKIP_AUTH=false
SKIP_INTERACTION=false
JSON_OUTPUT=false
QUIET=false

# Colors (disabled for JSON output)
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

# Results storage for JSON output
declare -A RESULTS
RESULTS[health]="pending"
RESULTS[version]="pending"
RESULTS[setup]="pending"
RESULTS[auth]="pending"
RESULTS[interaction]="pending"

# ============================================================================
# Utility Functions
# ============================================================================

disable_colors() {
    RED=''
    GREEN=''
    YELLOW=''
    BLUE=''
    CYAN=''
    BOLD=''
    RESET=''
}

log_info() {
    if [ "$QUIET" = false ] && [ "$JSON_OUTPUT" = false ]; then
        echo -e "${BLUE}[INFO]${RESET} $1"
    fi
}

log_success() {
    if [ "$QUIET" = false ] && [ "$JSON_OUTPUT" = false ]; then
        echo -e "${GREEN}[PASS]${RESET} $1"
    fi
}

log_warn() {
    if [ "$QUIET" = false ] && [ "$JSON_OUTPUT" = false ]; then
        echo -e "${YELLOW}[WARN]${RESET} $1"
    fi
}

log_error() {
    if [ "$JSON_OUTPUT" = false ]; then
        echo -e "${RED}[FAIL]${RESET} $1" >&2
    fi
}

show_usage() {
    cat << EOF
CIRIS Installation Verification Script

Usage: $(basename "$0") [OPTIONS]

Options:
  -u, --url URL          Base URL (default: $DEFAULT_URL)
  -v, --version VERSION  Expected version to match
  -t, --timeout SECONDS  Request timeout (default: $DEFAULT_TIMEOUT)
  --skip-auth            Skip authentication check
  --skip-interaction     Skip agent interaction check
  --json                 Output JSON format
  -q, --quiet            Minimal output
  -h, --help             Show this help

Exit Codes:
  0 - All checks passed
  1 - Health check failed (server not running)
  2 - Version mismatch
  3 - Setup wizard issue
  4 - Authentication failed
  5 - Agent interaction failed

Examples:
  $(basename "$0")                          # Check localhost:8080
  $(basename "$0") -u http://192.168.1.10:8080
  $(basename "$0") -v 1.7.8 --json
  $(basename "$0") --skip-interaction -t 30
EOF
}

# Check if command exists
command_exists() {
    command -v "$1" &> /dev/null
}

# HTTP request with timeout
http_get() {
    local url="$1"
    local timeout="${2:-$DEFAULT_TIMEOUT}"

    if command_exists curl; then
        curl -s -f --connect-timeout "$timeout" --max-time "$timeout" "$url" 2>/dev/null
    elif command_exists wget; then
        wget -q -O - --timeout="$timeout" "$url" 2>/dev/null
    else
        echo "Error: Neither curl nor wget found" >&2
        return 1
    fi
}

http_get_status() {
    local url="$1"
    local timeout="${2:-$DEFAULT_TIMEOUT}"

    if command_exists curl; then
        curl -s -o /dev/null -w "%{http_code}" --connect-timeout "$timeout" --max-time "$timeout" "$url" 2>/dev/null
    elif command_exists wget; then
        wget -q --spider --timeout="$timeout" "$url" 2>&1 | grep -o '[0-9]\{3\}' | head -1 || echo "000"
    else
        echo "000"
    fi
}

http_post() {
    local url="$1"
    local data="$2"
    local timeout="${3:-$DEFAULT_TIMEOUT}"
    local auth_header="${4:-}"

    if command_exists curl; then
        if [ -n "$auth_header" ]; then
            curl -s -f --connect-timeout "$timeout" --max-time "$timeout" \
                -X POST -H "Content-Type: application/json" \
                -H "Authorization: $auth_header" \
                -d "$data" "$url" 2>/dev/null
        else
            curl -s -f --connect-timeout "$timeout" --max-time "$timeout" \
                -X POST -H "Content-Type: application/json" \
                -d "$data" "$url" 2>/dev/null
        fi
    elif command_exists wget; then
        if [ -n "$auth_header" ]; then
            wget -q -O - --timeout="$timeout" \
                --header="Content-Type: application/json" \
                --header="Authorization: $auth_header" \
                --post-data="$data" "$url" 2>/dev/null
        else
            wget -q -O - --timeout="$timeout" \
                --header="Content-Type: application/json" \
                --post-data="$data" "$url" 2>/dev/null
        fi
    else
        return 1
    fi
}

# Extract JSON field (minimal jq alternative)
json_get() {
    local json="$1"
    local field="$2"

    if command_exists jq; then
        echo "$json" | jq -r ".$field // empty" 2>/dev/null
    else
        # Fallback: basic grep/sed extraction (handles simple cases)
        echo "$json" | grep -o "\"$field\"[[:space:]]*:[[:space:]]*\"[^\"]*\"" | sed 's/.*: *"\([^"]*\)".*/\1/' | head -1
    fi
}

# ============================================================================
# Verification Checks
# ============================================================================

check_health() {
    log_info "Checking server health..."

    local health_url="${BASE_URL}/v1/system/health"
    local response

    if response=$(http_get "$health_url" "$TIMEOUT"); then
        local status
        status=$(json_get "$response" "status")

        if [ "$status" = "healthy" ] || [ "$status" = "ok" ]; then
            RESULTS[health]="pass"
            log_success "Server is healthy"
            return 0
        else
            RESULTS[health]="fail"
            log_error "Server reported unhealthy status: $status"
            return 1
        fi
    else
        # Try alternate health endpoint
        local alt_url="${BASE_URL}/health"
        if response=$(http_get "$alt_url" "$TIMEOUT" 2>/dev/null); then
            RESULTS[health]="pass"
            log_success "Server is healthy (alternate endpoint)"
            return 0
        fi

        RESULTS[health]="fail"
        log_error "Server health check failed - is CIRIS running at $BASE_URL?"
        return 1
    fi
}

check_version() {
    log_info "Checking version..."

    local version_url="${BASE_URL}/v1/agent/status"
    local response

    if response=$(http_get "$version_url" "$TIMEOUT" 2>/dev/null); then
        local server_version
        server_version=$(json_get "$response" "version")

        if [ -z "$server_version" ]; then
            # Try alternate extraction for nested response
            server_version=$(echo "$response" | grep -o '"version"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*: *"\([^"]*\)".*/\1/' | head -1)
        fi

        if [ -n "$server_version" ]; then
            if [ -n "$VERSION" ]; then
                if [ "$server_version" = "$VERSION" ]; then
                    RESULTS[version]="pass"
                    log_success "Version matches: $server_version"
                    return 0
                else
                    RESULTS[version]="fail"
                    log_error "Version mismatch: expected $VERSION, got $server_version"
                    return 2
                fi
            else
                RESULTS[version]="pass"
                log_success "Version: $server_version"
                return 0
            fi
        fi
    fi

    # Version check is optional - warn but don't fail
    RESULTS[version]="skip"
    log_warn "Could not determine version (endpoint may require auth)"
    return 0
}

check_setup_wizard() {
    log_info "Checking setup wizard accessibility..."

    local setup_url="${BASE_URL}/v1/setup/status"
    local status_code

    status_code=$(http_get_status "$setup_url" "$TIMEOUT")

    # 200 = setup available, 401/403 = auth required (normal), 404 = not found
    if [ "$status_code" = "200" ] || [ "$status_code" = "401" ] || [ "$status_code" = "403" ]; then
        RESULTS[setup]="pass"
        log_success "Setup wizard endpoint accessible (status: $status_code)"
        return 0
    elif [ "$status_code" = "404" ]; then
        RESULTS[setup]="warn"
        log_warn "Setup wizard endpoint not found (may be disabled after setup)"
        return 0
    else
        RESULTS[setup]="fail"
        log_error "Setup wizard check failed (status: $status_code)"
        return 3
    fi
}

check_auth() {
    if [ "$SKIP_AUTH" = true ]; then
        RESULTS[auth]="skip"
        log_info "Skipping authentication check"
        return 0
    fi

    log_info "Checking authentication flow..."

    local login_url="${BASE_URL}/v1/auth/login"
    local response

    # Try login with default credentials
    local login_data='{"username":"admin","password":"ciris_admin_password"}'

    if response=$(http_post "$login_url" "$login_data" "$TIMEOUT" 2>/dev/null); then
        local token
        token=$(json_get "$response" "access_token")

        if [ -n "$token" ] && [ "$token" != "null" ]; then
            RESULTS[auth]="pass"
            # Store token for interaction test
            AUTH_TOKEN="$token"
            log_success "Authentication successful"
            return 0
        fi
    fi

    # Check if auth endpoint exists but credentials are wrong
    local status_code
    status_code=$(http_get_status "$login_url" "$TIMEOUT")

    if [ "$status_code" = "401" ] || [ "$status_code" = "422" ]; then
        RESULTS[auth]="warn"
        log_warn "Auth endpoint works but default credentials rejected (expected if changed)"
        return 0
    elif [ "$status_code" = "405" ]; then
        # Method not allowed - try to check if endpoint exists
        RESULTS[auth]="pass"
        log_success "Auth endpoint exists (POST required)"
        return 0
    else
        RESULTS[auth]="fail"
        log_error "Authentication check failed (status: $status_code)"
        return 4
    fi
}

check_interaction() {
    if [ "$SKIP_INTERACTION" = true ]; then
        RESULTS[interaction]="skip"
        log_info "Skipping agent interaction check"
        return 0
    fi

    log_info "Checking agent interaction..."

    local interact_url="${BASE_URL}/v1/agent/interact"
    local response
    local auth_header=""

    if [ -n "${AUTH_TOKEN:-}" ]; then
        auth_header="Bearer $AUTH_TOKEN"
    fi

    local interact_data='{"message":"ping","channel_id":"verify_test"}'

    if response=$(http_post "$interact_url" "$interact_data" "$TIMEOUT" "$auth_header" 2>/dev/null); then
        # Any successful response means interaction works
        RESULTS[interaction]="pass"
        log_success "Agent interaction successful"
        return 0
    fi

    # Check status code
    local status_code
    status_code=$(http_get_status "$interact_url" "$TIMEOUT")

    if [ "$status_code" = "401" ] || [ "$status_code" = "403" ]; then
        RESULTS[interaction]="warn"
        log_warn "Interaction requires auth (could not authenticate with defaults)"
        return 0
    elif [ "$status_code" = "503" ]; then
        RESULTS[interaction]="warn"
        log_warn "Agent not ready for interaction (still starting up?)"
        return 0
    else
        RESULTS[interaction]="fail"
        log_error "Agent interaction check failed (status: $status_code)"
        return 5
    fi
}

# ============================================================================
# Output Functions
# ============================================================================

output_json() {
    local exit_code="$1"

    cat << EOF
{
  "success": $([ "$exit_code" -eq 0 ] && echo "true" || echo "false"),
  "exit_code": $exit_code,
  "url": "$BASE_URL",
  "checks": {
    "health": "${RESULTS[health]}",
    "version": "${RESULTS[version]}",
    "setup": "${RESULTS[setup]}",
    "auth": "${RESULTS[auth]}",
    "interaction": "${RESULTS[interaction]}"
  }
}
EOF
}

output_summary() {
    local exit_code="$1"

    echo ""
    echo -e "${BOLD}========================================${RESET}"
    echo -e "${BOLD}  CIRIS Verification Summary${RESET}"
    echo -e "${BOLD}========================================${RESET}"
    echo ""
    echo -e "  URL: ${CYAN}$BASE_URL${RESET}"
    echo ""

    for check in health version setup auth interaction; do
        local result="${RESULTS[$check]}"
        local icon
        case "$result" in
            pass) icon="${GREEN}[PASS]${RESET}" ;;
            fail) icon="${RED}[FAIL]${RESET}" ;;
            warn) icon="${YELLOW}[WARN]${RESET}" ;;
            skip) icon="${BLUE}[SKIP]${RESET}" ;;
            *)    icon="${YELLOW}[????]${RESET}" ;;
        esac
        printf "  %-15s %b\n" "$check:" "$icon"
    done

    echo ""
    if [ "$exit_code" -eq 0 ]; then
        echo -e "  ${GREEN}${BOLD}All checks passed!${RESET}"
    else
        echo -e "  ${RED}${BOLD}Some checks failed (exit code: $exit_code)${RESET}"
    fi
    echo ""
}

# ============================================================================
# Main
# ============================================================================

main() {
    local BASE_URL="$DEFAULT_URL"
    local TIMEOUT="$DEFAULT_TIMEOUT"
    local AUTH_TOKEN=""

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            -u|--url)
                BASE_URL="$2"
                shift 2
                ;;
            -v|--version)
                VERSION="$2"
                shift 2
                ;;
            -t|--timeout)
                TIMEOUT="$2"
                shift 2
                ;;
            --skip-auth)
                SKIP_AUTH=true
                shift
                ;;
            --skip-interaction)
                SKIP_INTERACTION=true
                shift
                ;;
            --json)
                JSON_OUTPUT=true
                disable_colors
                shift
                ;;
            -q|--quiet)
                QUIET=true
                shift
                ;;
            -h|--help)
                show_usage
                exit 0
                ;;
            *)
                echo "Unknown option: $1" >&2
                show_usage
                exit 1
                ;;
        esac
    done

    # Remove trailing slash from URL
    BASE_URL="${BASE_URL%/}"

    if [ "$JSON_OUTPUT" = false ] && [ "$QUIET" = false ]; then
        echo ""
        echo -e "${BOLD}CIRIS Installation Verification${RESET}"
        echo -e "Checking: ${CYAN}$BASE_URL${RESET}"
        echo ""
    fi

    local exit_code=0

    # Run checks
    check_health || exit_code=$?

    if [ "$exit_code" -eq 0 ]; then
        check_version || exit_code=$?
    fi

    if [ "$exit_code" -eq 0 ] || [ "$exit_code" -eq 2 ]; then
        # Continue even if version mismatches
        local saved_code=$exit_code
        check_setup_wizard || exit_code=$?
        [ "$exit_code" -eq 0 ] && exit_code=$saved_code
    fi

    if [ "$exit_code" -eq 0 ] || [ "$exit_code" -eq 2 ]; then
        local saved_code=$exit_code
        check_auth || exit_code=$?
        [ "$exit_code" -eq 0 ] && exit_code=$saved_code
    fi

    if [ "$exit_code" -eq 0 ] || [ "$exit_code" -eq 2 ]; then
        local saved_code=$exit_code
        check_interaction || exit_code=$?
        [ "$exit_code" -eq 0 ] && exit_code=$saved_code
    fi

    # Output results
    if [ "$JSON_OUTPUT" = true ]; then
        output_json "$exit_code"
    elif [ "$QUIET" = false ]; then
        output_summary "$exit_code"
    fi

    exit "$exit_code"
}

main "$@"
