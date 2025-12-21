#!/bin/bash
# CIRIS iOS Log Collector
# Pulls logs from iOS simulator or device
#
# Usage:
#   ./pull-logs-ios.sh              # Pull logs to /tmp/ciris-ios-logs/
#   ./pull-logs-ios.sh --live       # Live tail the simulator logs
#   ./pull-logs-ios.sh /path/to/    # Pull to specific directory

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_DIR="/tmp/ciris-ios-logs"
LIVE_MODE="false"
DEVICE_UDID=""

# App info
BUNDLE_ID="ai.ciris.ciris-ios"
APP_NAME="Ciris iOS"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info()    { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error()   { echo -e "${RED}[ERROR]${NC} $1"; }

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --live)
            LIVE_MODE="true"
            shift
            ;;
        -d|--device)
            DEVICE_UDID="$2"
            shift 2
            ;;
        --help|-h)
            echo "Usage: $0 [options] [output_dir]"
            echo ""
            echo "Options:"
            echo "  --live           Live tail the logs"
            echo "  -d, --device     Specific device UDID"
            echo "  --help           Show this help"
            echo ""
            echo "Output directory default: /tmp/ciris-ios-logs/"
            exit 0
            ;;
        *)
            if [[ -d "$1" ]] || [[ "$1" == /* ]]; then
                OUTPUT_DIR="$1"
            fi
            shift
            ;;
    esac
done

# Header
echo -e "${CYAN}============================================================${NC}"
echo -e "${CYAN}  CIRIS iOS Log Collector${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""

# Find booted simulator
get_booted_simulator() {
    xcrun simctl list devices | grep "Booted" | head -1 | sed 's/.*(\([A-F0-9-]*\)).*/\1/'
}

# Get device UDID if not specified
if [[ -z "$DEVICE_UDID" ]]; then
    DEVICE_UDID=$(get_booted_simulator)
    if [[ -z "$DEVICE_UDID" ]]; then
        log_error "No booted simulator found. Start a simulator first."
        echo ""
        echo "Available simulators:"
        xcrun simctl list devices available | grep -E "iPhone|iPad" | head -10
        exit 1
    fi
fi

# Get device name
DEVICE_NAME=$(xcrun simctl list devices | grep "$DEVICE_UDID" | sed 's/ (.*//;s/^[[:space:]]*//')
log_info "Device: $DEVICE_NAME"
log_info "UDID: $DEVICE_UDID"

# Find app container
APP_CONTAINER=$(xcrun simctl get_app_container "$DEVICE_UDID" "$BUNDLE_ID" data 2>/dev/null || echo "")

if [[ -z "$APP_CONTAINER" ]]; then
    log_warn "App not installed or container not found"
    log_info "Will collect system logs only"
fi

# Live mode
if [[ "$LIVE_MODE" == "true" ]]; then
    log_info "Live tailing logs... (Ctrl+C to stop)"
    echo ""

    # Use log stream for simulator
    xcrun simctl spawn "$DEVICE_UDID" log stream \
        --predicate 'subsystem CONTAINS "ai.ciris" OR process CONTAINS "python" OR process CONTAINS "Ciris"' \
        --style compact
    exit 0
fi

# Create output directory
OUTPUT_DIR="$OUTPUT_DIR/$TIMESTAMP"
mkdir -p "$OUTPUT_DIR"
log_info "Output: $OUTPUT_DIR"
echo ""

# Collect device info
log_info "Collecting device info..."
{
    echo "=== Device Info ==="
    echo "Name: $DEVICE_NAME"
    echo "UDID: $DEVICE_UDID"
    echo "Date: $(date)"
    echo ""

    echo "=== Simulator State ==="
    xcrun simctl list devices | grep "$DEVICE_UDID"
    echo ""

    if [[ -n "$APP_CONTAINER" ]]; then
        echo "=== App Container ==="
        echo "$APP_CONTAINER"
        echo ""

        echo "=== App Files ==="
        ls -la "$APP_CONTAINER/" 2>/dev/null || echo "Not accessible"
        echo ""

        echo "=== Documents ==="
        ls -la "$APP_CONTAINER/Documents/" 2>/dev/null || echo "Empty or not accessible"
        echo ""

        echo "=== Library ==="
        ls -la "$APP_CONTAINER/Library/" 2>/dev/null || echo "Empty or not accessible"
    fi
} > "$OUTPUT_DIR/device_info.txt" 2>&1
log_success "  device_info.txt"

# Collect system log
log_info "Collecting system logs..."
xcrun simctl spawn "$DEVICE_UDID" log show \
    --predicate 'subsystem CONTAINS "ai.ciris" OR process CONTAINS "python" OR process CONTAINS "Ciris"' \
    --style compact \
    --last 1h \
    > "$OUTPUT_DIR/system_log.txt" 2>&1 || true
log_success "  system_log.txt"

# Collect Python-specific logs
log_info "Collecting Python logs..."
xcrun simctl spawn "$DEVICE_UDID" log show \
    --predicate 'process CONTAINS "python"' \
    --style compact \
    --last 1h \
    > "$OUTPUT_DIR/python_log.txt" 2>&1 || true
log_success "  python_log.txt"

# Collect crash logs
log_info "Collecting crash logs..."
CRASH_DIR="$HOME/Library/Logs/DiagnosticReports"
if [[ -d "$CRASH_DIR" ]]; then
    mkdir -p "$OUTPUT_DIR/crashes"
    find "$CRASH_DIR" -name "*Ciris*" -mtime -1 -exec cp {} "$OUTPUT_DIR/crashes/" \; 2>/dev/null || true
    find "$CRASH_DIR" -name "*python*" -mtime -1 -exec cp {} "$OUTPUT_DIR/crashes/" \; 2>/dev/null || true
    crash_count=$(find "$OUTPUT_DIR/crashes" -type f 2>/dev/null | wc -l)
    log_success "  crashes/ ($crash_count files)"
else
    log_info "  No crash logs found"
fi

# Copy app data if accessible
if [[ -n "$APP_CONTAINER" && -d "$APP_CONTAINER" ]]; then
    log_info "Copying app data..."

    # Copy Documents
    if [[ -d "$APP_CONTAINER/Documents" ]]; then
        mkdir -p "$OUTPUT_DIR/Documents"
        cp -r "$APP_CONTAINER/Documents/"* "$OUTPUT_DIR/Documents/" 2>/dev/null || true
        doc_count=$(find "$OUTPUT_DIR/Documents" -type f 2>/dev/null | wc -l)
        log_success "  Documents/ ($doc_count files)"
    fi

    # Copy logs directory if exists
    if [[ -d "$APP_CONTAINER/Documents/logs" ]]; then
        mkdir -p "$OUTPUT_DIR/logs"
        cp -r "$APP_CONTAINER/Documents/logs/"* "$OUTPUT_DIR/logs/" 2>/dev/null || true
        log_count=$(find "$OUTPUT_DIR/logs" -type f 2>/dev/null | wc -l)
        log_success "  logs/ ($log_count files)"
    fi

    # Copy databases
    mkdir -p "$OUTPUT_DIR/databases"
    find "$APP_CONTAINER" -name "*.db" -exec cp {} "$OUTPUT_DIR/databases/" \; 2>/dev/null || true
    find "$APP_CONTAINER" -name "*.sqlite" -exec cp {} "$OUTPUT_DIR/databases/" \; 2>/dev/null || true
    db_count=$(find "$OUTPUT_DIR/databases" -type f 2>/dev/null | wc -l)
    log_success "  databases/ ($db_count files)"
fi

# Summary
echo ""
echo -e "${CYAN}============================================================${NC}"
echo -e "${CYAN}  Collection Complete${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""
echo "Files saved to: $OUTPUT_DIR"
echo ""
echo "Contents:"
find "$OUTPUT_DIR" -type f -exec ls -lh {} \; 2>/dev/null | awk '{print "  " $9 " (" $5 ")"}'
echo ""
echo "Quick analysis:"
echo "  grep -i error $OUTPUT_DIR/python_log.txt | tail -20"
echo "  grep -i exception $OUTPUT_DIR/system_log.txt | tail -20"
echo ""
