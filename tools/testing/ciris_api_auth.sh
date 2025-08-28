#!/bin/bash
# CIRIS API Authentication and Environment Setup Script
# This script handles authentication and sets up environment variables for easy API interaction

# Default values
API_HOST="${CIRIS_API_HOST:-localhost}"
API_PORT="${CIRIS_API_PORT:-8080}"
API_BASE_URL="http://${API_HOST}:${API_PORT}"

# Colors for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to print colored output
print_status() {
    echo -e "${GREEN}[✓]${NC} $1"
}

print_error() {
    echo -e "${RED}[✗]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[!]${NC} $1"
}

# Function to check if API is accessible
check_api() {
    if curl -s -f "${API_BASE_URL}/v1/system/health" > /dev/null 2>&1; then
        return 0
    else
        return 1
    fi
}

# Function to authenticate and get token
authenticate() {
    local username="${1:-admin}"
    local password="${2:-ciris_admin_password}"

    print_status "Authenticating with CIRIS API at ${API_BASE_URL}..."

    response=$(curl -s -X POST "${API_BASE_URL}/v1/auth/login" \
        -H "Content-Type: application/json" \
        -d "{\"username\": \"${username}\", \"password\": \"${password}\"}")

    # Check if response contains access_token
    if echo "$response" | grep -q "access_token"; then
        token=$(echo "$response" | jq -r '.access_token')
        export CIRIS_TOKEN="$token"
        print_status "Authentication successful!"
        print_status "Token stored in CIRIS_TOKEN environment variable"
        return 0
    else
        print_error "Authentication failed!"
        echo "$response" | jq . 2>/dev/null || echo "$response"
        return 1
    fi
}

# Function to make authenticated API calls
ciris_api() {
    if [ -z "$CIRIS_TOKEN" ]; then
        print_error "No authentication token found. Please run: source ciris_api_auth.sh"
        return 1
    fi

    local method="${1:-GET}"
    local endpoint="$2"
    local data="$3"

    local curl_args=(
        -X "$method"
        -H "Authorization: Bearer $CIRIS_TOKEN"
        -H "Content-Type: application/json"
    )

    if [ -n "$data" ]; then
        curl_args+=(-d "$data")
    fi

    curl -s "${curl_args[@]}" "${API_BASE_URL}${endpoint}" | jq .
}

# Function to interact with the agent
ciris_interact() {
    local message="$1"
    local channel="${2:-api_${API_HOST}_${API_PORT}}"

    if [ -z "$message" ]; then
        print_error "Usage: ciris_interact \"message\" [channel_id]"
        return 1
    fi

    ciris_api POST "/v1/agent/interact" "{\"message\": \"$message\", \"channel_id\": \"$channel\"}"
}

# Function to send mock LLM commands
ciris_mock() {
    local command="$1"
    shift
    local args="$*"

    if [ -z "$command" ]; then
        print_warning "Available mock commands:"
        echo "  speak <message>     - Make the agent speak"
        echo "  recall <query>      - Recall memories"
        echo "  memorize <content>  - Store a memory"
        echo "  ponder <thought>    - Ponder a thought"
        echo "  tool <name> <args>  - Execute a tool"
        echo "  observe <channel>   - Observe a channel"
        echo "  defer <reason>      - Defer action"
        echo "  reject <reason>     - Reject action"
        echo "  forget <memory_id>  - Forget a memory"
        echo "  task_complete       - Complete current task"
        return 1
    fi

    local full_command="\$${command}"
    if [ -n "$args" ]; then
        full_command="${full_command} ${args}"
    fi

    ciris_interact "$full_command"
}

# Function to check system health
ciris_health() {
    ciris_api GET "/v1/system/health"
}

# Function to get audit entries
ciris_audit() {
    local limit="${1:-10}"
    ciris_api GET "/v1/audit/entries?limit=$limit"
}

# Main execution
main() {
    print_status "CIRIS API Authentication Script"
    echo "================================"

    # Check if API is accessible
    if ! check_api; then
        print_error "Cannot reach CIRIS API at ${API_BASE_URL}"
        print_warning "Make sure the container is running: docker-compose -f docker-compose-api-mock.yml up -d"
        return 1
    fi

    print_status "API is accessible at ${API_BASE_URL}"

    # Check if already authenticated
    if [ -n "$CIRIS_TOKEN" ]; then
        print_warning "Existing token found. Testing validity..."
        if ciris_api GET "/v1/system/health" > /dev/null 2>&1; then
            print_status "Existing token is valid"
            return 0
        else
            print_warning "Existing token is invalid. Re-authenticating..."
        fi
    fi

    # Authenticate
    if authenticate; then
        echo ""
        print_status "Environment ready! Available commands:"
        echo "  ciris_interact \"message\"  - Send a message to the agent"
        echo "  ciris_mock <cmd> [args]   - Send mock LLM commands"
        echo "  ciris_health              - Check system health"
        echo "  ciris_audit [limit]       - Get audit entries"
        echo "  ciris_api <METHOD> <path> [data] - Make raw API calls"
        echo ""
        print_status "Example: ciris_mock speak \"Hello from mock LLM!\""
    else
        return 1
    fi
}

# Only run main if script is being sourced (not executed)
if [ "${BASH_SOURCE[0]}" = "${0}" ]; then
    print_warning "This script should be sourced, not executed:"
    echo "  source $0"
    exit 1
else
    main
fi
