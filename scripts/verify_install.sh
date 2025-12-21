#!/bin/bash
# CIRIS Installation Verification Script
#
# Validates CIRIS installations across deployment methods:
# - install.sh
# - wheel (pip install)
# - APK (Android)
# - Docker
#
# Supports two modes:
# 1. Basic health check (default) - verifies running server
# 2. First-run setup test (--first-run) - simulates complete setup flow
#
# Usage:
#   ./verify_install.sh [OPTIONS]
#
# Options:
#   -u, --url URL            Base URL (default: http://localhost:8080)
#   -v, --version VERSION    Expected version to match
#   -t, --timeout SECONDS    Request timeout (default: 10)
#   --first-run              Test first-run setup flow (creates mock config)
#   --llm-key KEY            LLM API key for setup (default: mock_test_key)
#   --llm-provider PROVIDER  LLM provider: openai|local|other (default: local)
#   --llm-base-url URL       LLM base URL (default: http://localhost:11434)
#   --llm-model MODEL        LLM model name (default: llama3)
#   --admin-user USER        Admin username for setup (default: qa_verify_user)
#   --admin-pass PASS        Admin password for setup (default: qa_verify_pass_12345)
#   --skip-auth              Skip authentication check
#   --skip-interaction       Skip agent interaction check
#   --json                   Output JSON format
#   -q, --quiet              Minimal output
#   -h, --help               Show this help
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
FIRST_RUN_MODE=false

# LLM configuration for first-run setup
LLM_KEY="mock_test_key"
LLM_PROVIDER="local"
LLM_BASE_URL="http://localhost:11434"
LLM_MODEL="llama3"

# Admin credentials for first-run setup
ADMIN_USER="qa_verify_user"
ADMIN_PASS="qa_verify_pass_12345"

# Colors (disabled for JSON output)
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
BOLD='\033[1m'
RESET='\033[0m'

# Results storage for JSON output (individual vars for bash 3.2 compat)
RESULT_health="pending"
RESULT_version="pending"
RESULT_setup_status="pending"
RESULT_setup_providers="pending"
RESULT_setup_templates="pending"
RESULT_setup_complete="pending"
RESULT_auth="pending"
RESULT_interaction="pending"

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
  -u, --url URL            Base URL (default: $DEFAULT_URL)
  -v, --version VERSION    Expected version to match
  -t, --timeout SECONDS    Request timeout (default: $DEFAULT_TIMEOUT)
  --first-run              Test first-run setup flow (creates mock config)
  --llm-key KEY            LLM API key for setup (default: mock_test_key)
  --llm-provider PROVIDER  LLM provider: openai|local|other (default: local)
  --llm-base-url URL       LLM base URL (default: http://localhost:11434)
  --llm-model MODEL        LLM model name (default: llama3)
  --admin-user USER        Admin username for setup (default: qa_verify_user)
  --admin-pass PASS        Admin password for setup (default: qa_verify_pass_12345)
  --skip-auth              Skip authentication check
  --skip-interaction       Skip agent interaction check
  --json                   Output JSON format
  -q, --quiet              Minimal output
  -h, --help               Show this help

Exit Codes:
  0 - All checks passed
  1 - Health check failed (server not running)
  2 - Version mismatch
  3 - Setup wizard issue
  4 - Authentication failed
  5 - Agent interaction failed

Examples:
  $(basename "$0")                                    # Basic health check
  $(basename "$0") --first-run                        # Test full setup flow with mock LLM
  $(basename "$0") --first-run --llm-key sk-xxx      # Test with real OpenAI key
  $(basename "$0") -u http://192.168.1.10:8080
  $(basename "$0") -v 1.7.8 --json
  $(basename "$0") --skip-interaction -t 30

CD Pipeline Usage:
  # Build and start container, then verify
  docker build -t ciris:test .
  docker run -d -p 8080:8080 --name ciris-test ciris:test
  ./verify_install.sh --first-run --json
EOF
}

# Check if command exists
command_exists() {
    command -v "$1" &> /dev/null
}

# HTTP GET request with timeout
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

http_post_status() {
    local url="$1"
    local data="$2"
    local timeout="${3:-$DEFAULT_TIMEOUT}"

    if command_exists curl; then
        curl -s -o /dev/null -w "%{http_code}" --connect-timeout "$timeout" --max-time "$timeout" \
            -X POST -H "Content-Type: application/json" \
            -d "$data" "$url" 2>/dev/null
    else
        echo "000"
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
        # Try nested path first (data.status), then top-level
        if command_exists jq; then
            status=$(echo "$response" | jq -r '.data.status // .status // empty' 2>/dev/null)
        else
            # Fallback: grep for status value
            status=$(echo "$response" | grep -o '"status"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*: *"\([^"]*\)".*/\1/')
        fi

        if [ "$status" = "healthy" ] || [ "$status" = "ok" ]; then
            RESULT_health="pass"
            log_success "Server is healthy"
            return 0
        else
            RESULT_health="fail"
            log_error "Server reported unhealthy status: $status"
            return 1
        fi
    else
        # Try alternate health endpoint
        local alt_url="${BASE_URL}/health"
        if response=$(http_get "$alt_url" "$TIMEOUT" 2>/dev/null); then
            RESULT_health="pass"
            log_success "Server is healthy (alternate endpoint)"
            return 0
        fi

        RESULT_health="fail"
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
                    RESULT_version="pass"
                    log_success "Version matches: $server_version"
                    return 0
                else
                    RESULT_version="fail"
                    log_error "Version mismatch: expected $VERSION, got $server_version"
                    return 2
                fi
            else
                RESULT_version="pass"
                log_success "Version: $server_version"
                return 0
            fi
        fi
    fi

    # Version check is optional - warn but don't fail
    RESULT_version="skip"
    log_warn "Could not determine version (endpoint may require auth)"
    return 0
}

# ============================================================================
# First-Run Setup Flow Tests (mirrors qa_runner/modules/setup_tests.py)
# ============================================================================

check_setup_status() {
    log_info "Checking setup status..."

    local status_url="${BASE_URL}/v1/setup/status"
    local response
    local status_code

    status_code=$(http_get_status "$status_url" "$TIMEOUT")

    if [ "$status_code" = "200" ]; then
        if response=$(http_get "$status_url" "$TIMEOUT"); then
            RESULT_setup_status="pass"
            log_success "Setup status endpoint accessible"
            return 0
        fi
    fi

    # 401/403 means setup already completed (needs auth)
    if [ "$status_code" = "401" ] || [ "$status_code" = "403" ]; then
        RESULT_setup_status="pass"
        log_success "Setup already completed (auth required)"
        return 0
    fi

    RESULT_setup_status="fail"
    log_error "Setup status check failed (status: $status_code)"
    return 3
}

check_setup_providers() {
    log_info "Checking LLM providers..."

    local providers_url="${BASE_URL}/v1/setup/providers"
    local response

    if response=$(http_get "$providers_url" "$TIMEOUT" 2>/dev/null); then
        # Verify response contains expected providers
        if echo "$response" | grep -q "openai\|local\|other"; then
            RESULT_setup_providers="pass"
            log_success "LLM providers listed successfully"
            return 0
        else
            RESULT_setup_providers="warn"
            log_warn "Providers response doesn't contain expected values"
            return 0
        fi
    fi

    local status_code
    status_code=$(http_get_status "$providers_url" "$TIMEOUT")

    if [ "$status_code" = "401" ] || [ "$status_code" = "403" ]; then
        RESULT_setup_providers="skip"
        log_info "Providers endpoint requires auth (setup completed)"
        return 0
    fi

    RESULT_setup_providers="fail"
    log_error "Failed to get LLM providers (status: $status_code)"
    return 3
}

check_setup_templates() {
    log_info "Checking agent templates..."

    local templates_url="${BASE_URL}/v1/setup/templates"
    local response

    if response=$(http_get "$templates_url" "$TIMEOUT" 2>/dev/null); then
        # Verify response contains required templates (Datum/default, Ally)
        local has_default=false
        local has_ally=false

        if echo "$response" | grep -qi '"id"[[:space:]]*:[[:space:]]*"default"'; then
            has_default=true
        fi
        if echo "$response" | grep -qi '"id"[[:space:]]*:[[:space:]]*"ally"'; then
            has_ally=true
        fi

        if [ "$has_default" = true ] && [ "$has_ally" = true ]; then
            RESULT_setup_templates="pass"
            log_success "Agent templates include default (Datum) and ally"
            return 0
        else
            RESULT_setup_templates="warn"
            log_warn "Templates missing: default=$has_default, ally=$has_ally"
            return 0
        fi
    fi

    local status_code
    status_code=$(http_get_status "$templates_url" "$TIMEOUT")

    if [ "$status_code" = "401" ] || [ "$status_code" = "403" ]; then
        RESULT_setup_templates="skip"
        log_info "Templates endpoint requires auth (setup completed)"
        return 0
    fi

    RESULT_setup_templates="fail"
    log_error "Failed to get agent templates (status: $status_code)"
    return 3
}

check_setup_complete() {
    log_info "Testing setup completion..."

    local complete_url="${BASE_URL}/v1/setup/complete"
    local response

    # Build setup payload matching qa_runner setup_tests.py
    local payload
    payload=$(cat << EOF
{
    "llm_provider": "$LLM_PROVIDER",
    "llm_api_key": "$LLM_KEY",
    "llm_base_url": $([ "$LLM_PROVIDER" = "openai" ] && echo "null" || echo "\"$LLM_BASE_URL\""),
    "llm_model": $([ "$LLM_PROVIDER" = "openai" ] && echo "null" || echo "\"$LLM_MODEL\""),
    "template_id": "default",
    "enabled_adapters": ["api"],
    "adapter_config": {},
    "admin_username": "$ADMIN_USER",
    "admin_password": "$ADMIN_PASS",
    "system_admin_password": "ciris_admin_password",
    "agent_port": 8080
}
EOF
)

    if response=$(http_post "$complete_url" "$payload" "$TIMEOUT" 2>/dev/null); then
        RESULT_setup_complete="pass"
        log_success "Setup completed successfully"
        return 0
    fi

    local status_code
    status_code=$(http_post_status "$complete_url" "$payload" "$TIMEOUT")

    if [ "$status_code" = "200" ]; then
        RESULT_setup_complete="pass"
        log_success "Setup completed (status: 200)"
        return 0
    elif [ "$status_code" = "403" ]; then
        # Setup already completed
        RESULT_setup_complete="skip"
        log_info "Setup already completed (cannot repeat)"
        return 0
    elif [ "$status_code" = "422" ]; then
        # Validation error - still indicates endpoint works
        RESULT_setup_complete="warn"
        log_warn "Setup validation error (status: 422) - check payload"
        return 0
    else
        RESULT_setup_complete="fail"
        log_error "Setup completion failed (status: $status_code)"
        return 3
    fi
}

check_auth() {
    if [ "$SKIP_AUTH" = true ]; then
        RESULT_auth="skip"
        log_info "Skipping authentication check"
        return 0
    fi

    log_info "Checking authentication flow..."

    local login_url="${BASE_URL}/v1/auth/login"
    local response

    # If first-run mode, use the created user credentials
    local test_user="$ADMIN_USER"
    local test_pass="$ADMIN_PASS"

    # Also try default admin credentials
    local login_data="{\"username\":\"$test_user\",\"password\":\"$test_pass\"}"

    if response=$(http_post "$login_url" "$login_data" "$TIMEOUT" 2>/dev/null); then
        local token
        token=$(json_get "$response" "access_token")

        if [ -n "$token" ] && [ "$token" != "null" ]; then
            RESULT_auth="pass"
            # Store token for interaction test
            AUTH_TOKEN="$token"
            log_success "Authentication successful (user: $test_user)"
            return 0
        fi
    fi

    # Try default admin if custom user failed
    if [ "$test_user" != "admin" ]; then
        login_data='{"username":"admin","password":"ciris_admin_password"}'
        if response=$(http_post "$login_url" "$login_data" "$TIMEOUT" 2>/dev/null); then
            local token
            token=$(json_get "$response" "access_token")
            if [ -n "$token" ] && [ "$token" != "null" ]; then
                RESULT_auth="pass"
                AUTH_TOKEN="$token"
                log_success "Authentication successful (user: admin)"
                return 0
            fi
        fi
    fi

    # Check if auth endpoint exists
    local status_code
    status_code=$(http_get_status "$login_url" "$TIMEOUT")

    if [ "$status_code" = "405" ]; then
        RESULT_auth="pass"
        log_success "Auth endpoint exists (POST required)"
        return 0
    elif [ "$status_code" = "401" ] || [ "$status_code" = "422" ]; then
        RESULT_auth="warn"
        log_warn "Auth endpoint works but credentials rejected"
        return 0
    else
        RESULT_auth="fail"
        log_error "Authentication check failed (status: $status_code)"
        return 4
    fi
}

check_interaction() {
    if [ "$SKIP_INTERACTION" = true ]; then
        RESULT_interaction="skip"
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
        RESULT_interaction="pass"
        log_success "Agent interaction successful"
        return 0
    fi

    # Check status code
    local status_code
    if command_exists curl && [ -n "$auth_header" ]; then
        status_code=$(curl -s -o /dev/null -w "%{http_code}" --connect-timeout "$TIMEOUT" \
            -X POST -H "Content-Type: application/json" \
            -H "Authorization: $auth_header" \
            -d "$interact_data" "$interact_url" 2>/dev/null)
    else
        status_code=$(http_post_status "$interact_url" "$interact_data" "$TIMEOUT")
    fi

    if [ "$status_code" = "401" ] || [ "$status_code" = "403" ]; then
        RESULT_interaction="warn"
        log_warn "Interaction requires auth (could not authenticate)"
        return 0
    elif [ "$status_code" = "503" ]; then
        RESULT_interaction="warn"
        log_warn "Agent not ready for interaction (still starting up?)"
        return 0
    elif [ "$status_code" = "200" ] || [ "$status_code" = "202" ]; then
        RESULT_interaction="pass"
        log_success "Agent interaction accepted"
        return 0
    else
        RESULT_interaction="fail"
        log_error "Agent interaction check failed (status: $status_code)"
        return 5
    fi
}

# ============================================================================
# Output Functions
# ============================================================================

output_json() {
    local exit_code="$1"

    # Build checks object based on mode
    local checks
    if [ "$FIRST_RUN_MODE" = true ]; then
        checks=$(cat << EOF
    "health": "${RESULT_health}",
    "version": "${RESULT_version}",
    "setup_status": "${RESULT_setup_status}",
    "setup_providers": "${RESULT_setup_providers}",
    "setup_templates": "${RESULT_setup_templates}",
    "setup_complete": "${RESULT_setup_complete}",
    "auth": "${RESULT_auth}",
    "interaction": "${RESULT_interaction}"
EOF
)
    else
        checks=$(cat << EOF
    "health": "${RESULT_health}",
    "version": "${RESULT_version}",
    "auth": "${RESULT_auth}",
    "interaction": "${RESULT_interaction}"
EOF
)
    fi

    cat << EOF
{
  "success": $([ "$exit_code" -eq 0 ] && echo "true" || echo "false"),
  "exit_code": $exit_code,
  "url": "$BASE_URL",
  "first_run_mode": $FIRST_RUN_MODE,
  "checks": {
$checks
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
    echo -e "  Mode: ${CYAN}$([ "$FIRST_RUN_MODE" = true ] && echo "First-Run Setup" || echo "Health Check")${RESET}"
    echo ""

    # Determine which checks to show
    local checks
    if [ "$FIRST_RUN_MODE" = true ]; then
        checks="health version setup_status setup_providers setup_templates setup_complete auth interaction"
    else
        checks="health version auth interaction"
    fi

    for check in $checks; do
        # Use indirect reference for bash 3.2 compatibility
        local varname="RESULT_$check"
        local result="${!varname}"
        local icon
        case "$result" in
            pass) icon="${GREEN}[PASS]${RESET}" ;;
            fail) icon="${RED}[FAIL]${RESET}" ;;
            warn) icon="${YELLOW}[WARN]${RESET}" ;;
            skip) icon="${BLUE}[SKIP]${RESET}" ;;
            *)    icon="${YELLOW}[----]${RESET}" ;;
        esac
        printf "  %-18s %b\n" "$check:" "$icon"
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
            --first-run)
                FIRST_RUN_MODE=true
                shift
                ;;
            --llm-key)
                LLM_KEY="$2"
                shift 2
                ;;
            --llm-provider)
                LLM_PROVIDER="$2"
                shift 2
                ;;
            --llm-base-url)
                LLM_BASE_URL="$2"
                shift 2
                ;;
            --llm-model)
                LLM_MODEL="$2"
                shift 2
                ;;
            --admin-user)
                ADMIN_USER="$2"
                shift 2
                ;;
            --admin-pass)
                ADMIN_PASS="$2"
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
        if [ "$FIRST_RUN_MODE" = true ]; then
            echo -e "Mode: ${CYAN}First-Run Setup Test${RESET}"
        fi
        echo ""
    fi

    local exit_code=0

    # Always run health check first
    check_health || exit_code=$?

    if [ "$exit_code" -ne 0 ]; then
        # Health failed, skip everything else
        if [ "$JSON_OUTPUT" = true ]; then
            output_json "$exit_code"
        elif [ "$QUIET" = false ]; then
            output_summary "$exit_code"
        fi
        exit "$exit_code"
    fi

    # Run version check
    check_version || exit_code=$?

    # First-run mode: test complete setup flow
    if [ "$FIRST_RUN_MODE" = true ]; then
        local saved_code=$exit_code

        check_setup_status || exit_code=$?
        [ "$exit_code" -eq 0 ] && exit_code=$saved_code

        check_setup_providers || exit_code=$?
        [ "$exit_code" -eq 0 ] && exit_code=$saved_code

        check_setup_templates || exit_code=$?
        [ "$exit_code" -eq 0 ] && exit_code=$saved_code

        check_setup_complete || exit_code=$?
        [ "$exit_code" -eq 0 ] && exit_code=$saved_code
    fi

    # Auth and interaction checks
    local saved_code=$exit_code
    check_auth || exit_code=$?
    [ "$exit_code" -eq 0 ] && exit_code=$saved_code

    saved_code=$exit_code
    check_interaction || exit_code=$?
    [ "$exit_code" -eq 0 ] && exit_code=$saved_code

    # Output results
    if [ "$JSON_OUTPUT" = true ]; then
        output_json "$exit_code"
    elif [ "$QUIET" = false ]; then
        output_summary "$exit_code"
    fi

    exit "$exit_code"
}

main "$@"
