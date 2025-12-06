#!/bin/bash
# pull-device-logs.sh - Pull logs and relevant files from Android device
#
# Collects:
#   - Python logs (latest.log, incidents_latest.log)
#   - Database files (.db)
#   - Shared preferences
#   - Logcat output
#   - App info and storage usage
#
# Usage:
#   ./pull-device-logs.sh              # Pull to /tmp/ciris-device-logs/
#   ./pull-device-logs.sh /path/to/    # Pull to specified directory
#   ./pull-device-logs.sh --live       # Live tail the logs

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
OUTPUT_DIR="/tmp/ciris-device-logs"
LIVE_MODE="false"
DEVICE=""

# Package and paths
PACKAGE="ai.ciris.mobile"
APP_DATA="/data/data/$PACKAGE"
APP_FILES="$APP_DATA/files"
LOGS_DIR="$APP_FILES/ciris/logs"
PREFS_DIR="$APP_DATA/shared_prefs"

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

# Parse args
while [[ $# -gt 0 ]]; do
    case $1 in
        -s)
            DEVICE="$2"
            shift 2
            ;;
        --live)
            LIVE_MODE="true"
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [options] [output_dir]"
            echo ""
            echo "Arguments:"
            echo "  output_dir     Directory to save logs (default: /tmp/ciris-device-logs)"
            echo ""
            echo "Options:"
            echo "  -s DEVICE      Specify device (like adb -s)"
            echo "  --live         Live tail the Python logs"
            echo "  --help         Show this help"
            echo ""
            echo "Files collected:"
            echo "  - Python logs:       latest.log, incidents_latest.log, etc."
            echo "  - Database files:    *.db (SQLite databases)"
            echo "  - Shared prefs:      *.xml (app preferences)"
            echo "  - Logcat:            python.stdout, python.stderr"
            echo "  - App info:          storage usage, version, etc."
            exit 0
            ;;
        *)
            OUTPUT_DIR="$1"
            shift
            ;;
    esac
done

# Find ADB
find_adb() {
    local adb_paths=(
        "/mnt/c/Users/moore/AppData/Local/Android/Sdk/platform-tools/adb.exe"
        "/mnt/c/Users/*/AppData/Local/Android/Sdk/platform-tools/adb.exe"
        "$ANDROID_HOME/platform-tools/adb"
        "$HOME/Android/Sdk/platform-tools/adb"
        "$(which adb 2>/dev/null)"
    )

    for adb in "${adb_paths[@]}"; do
        for expanded in $adb; do
            if [[ -x "$expanded" ]]; then
                echo "$expanded"
                return 0
            fi
        done
    done

    return 1
}

# Main
main() {
    echo -e "${CYAN}============================================================${NC}"
    echo -e "${CYAN}  CIRIS Android Device Log Collector${NC}"
    echo -e "${CYAN}============================================================${NC}"
    echo ""

    # Find ADB
    if ! ADB=$(find_adb); then
        log_error "ADB not found"
        exit 1
    fi
    log_info "ADB: $ADB"

    # Check device
    if ! "$ADB" devices | grep -w "device" | grep -v "List" > /dev/null; then
        log_error "No device connected"
        exit 1
    fi

    # Use specified device or first available
    local device
    local ADB_DEVICE_FLAG=""
    if [ -n "$DEVICE" ]; then
        device="$DEVICE"
        ADB_DEVICE_FLAG="-s $DEVICE"
    else
        device=$("$ADB" devices | grep -w "device" | grep -v "List" | head -1 | cut -f1)
    fi
    log_info "Device: $device"

    # Create adb command function that includes device flag
    adb_cmd() {
        "$ADB" $ADB_DEVICE_FLAG "$@"
    }

    # Check if this is a debug build (run-as will work)
    if adb_cmd shell "run-as $PACKAGE ls" &>/dev/null; then
        CAN_RUN_AS="true"
        log_info "Debug build detected - full file access available"
    else
        CAN_RUN_AS="false"
        log_warn "Release build detected - limited file access (logcat only)"
    fi

    # Live mode - just tail the logs
    if [ "$LIVE_MODE" = "true" ]; then
        log_info "Live tailing Python logs... (Ctrl+C to stop)"
        echo ""
        if [ "$CAN_RUN_AS" = "true" ]; then
            adb_cmd shell "run-as $PACKAGE tail -f $LOGS_DIR/latest.log"
        else
            adb_cmd logcat -v time 'python.stdout:*' 'python.stderr:*' '*:S'
        fi
        exit 0
    fi

    # Create output directory
    OUTPUT_DIR="$OUTPUT_DIR/$TIMESTAMP"
    mkdir -p "$OUTPUT_DIR"
    log_info "Output directory: $OUTPUT_DIR"
    echo ""

    # 1. Get app info
    log_info "Collecting app info..."
    {
        echo "=== Device Info ==="
        adb_cmd shell getprop ro.product.model
        adb_cmd shell getprop ro.build.version.release
        echo ""

        echo "=== Package Info ==="
        adb_cmd shell dumpsys package $PACKAGE | grep -E "(versionName|versionCode|firstInstallTime|lastUpdateTime)"
        echo ""

        echo "=== Storage Usage ==="
        adb_cmd shell du -h "$APP_DATA" 2>/dev/null || echo "Not accessible"
        echo ""

        echo "=== Process Info ==="
        adb_cmd shell ps | grep -E "(python|ciris)" || echo "No CIRIS processes running"
    } > "$OUTPUT_DIR/app_info.txt" 2>&1
    log_success "  app_info.txt"

    # 2. Get logcat output
    log_info "Collecting logcat..."
    adb_cmd logcat -d -v time 'python.stdout:*' 'python.stderr:*' '*:S' > "$OUTPUT_DIR/logcat_python.txt" 2>&1
    log_success "  logcat_python.txt"

    adb_cmd logcat -d -v time 'AndroidRuntime:E' '*:S' > "$OUTPUT_DIR/logcat_crashes.txt" 2>&1
    log_success "  logcat_crashes.txt"

    # If we have run-as access, get more files
    if [ "$CAN_RUN_AS" = "true" ]; then
        # 3. Get Python log files
        log_info "Collecting Python logs..."
        mkdir -p "$OUTPUT_DIR/logs"

        local log_files=(
            "latest.log"
            "incidents_latest.log"
            "ciris.log"
        )

        for log_file in "${log_files[@]}"; do
            if adb_cmd shell "run-as $PACKAGE test -f $LOGS_DIR/$log_file" 2>/dev/null; then
                adb_cmd shell "run-as $PACKAGE cat $LOGS_DIR/$log_file" > "$OUTPUT_DIR/logs/$log_file" 2>&1
                log_success "  logs/$log_file"
            fi
        done

        # Get dated logs (last 3 days)
        for log_file in $(adb_cmd shell "run-as $PACKAGE ls -t $LOGS_DIR/*.log 2>/dev/null" | head -5); do
            log_file=$(echo "$log_file" | tr -d '\r')
            if [ -n "$log_file" ]; then
                local basename
                basename=$(basename "$log_file")
                adb_cmd shell "run-as $PACKAGE cat $log_file" > "$OUTPUT_DIR/logs/$basename" 2>&1
                log_success "  logs/$basename"
            fi
        done

        # 4. Get database files
        log_info "Collecting database files..."
        mkdir -p "$OUTPUT_DIR/databases"

        for db_file in $(adb_cmd shell "run-as $PACKAGE find $APP_FILES -name '*.db' 2>/dev/null" | tr -d '\r'); do
            if [ -n "$db_file" ]; then
                local basename
                basename=$(basename "$db_file")
                adb_cmd shell "run-as $PACKAGE cat $db_file" > "$OUTPUT_DIR/databases/$basename" 2>&1
                log_success "  databases/$basename"
            fi
        done

        # 5. Get shared preferences
        log_info "Collecting shared preferences..."
        mkdir -p "$OUTPUT_DIR/prefs"

        for pref_file in $(adb_cmd shell "run-as $PACKAGE ls $PREFS_DIR/*.xml 2>/dev/null" | tr -d '\r'); do
            if [ -n "$pref_file" ]; then
                local basename
                basename=$(basename "$pref_file")
                adb_cmd shell "run-as $PACKAGE cat $pref_file" > "$OUTPUT_DIR/prefs/$basename" 2>&1
                log_success "  prefs/$basename"
            fi
        done

        # 6. List files in app directory
        log_info "Collecting file listing..."
        adb_cmd shell "run-as $PACKAGE find $APP_FILES -type f 2>/dev/null" > "$OUTPUT_DIR/file_listing.txt" 2>&1
        log_success "  file_listing.txt"

    else
        log_warn "Skipping file collection (release build - use debug build for full access)"
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
    find "$OUTPUT_DIR" -type f -exec ls -lh {} \; | awk '{print "  " $9 " (" $5 ")"}'
    echo ""

    # Quick analysis hints
    echo "Quick analysis:"
    echo "  cat $OUTPUT_DIR/logs/incidents_latest.log | grep -i error"
    echo "  cat $OUTPUT_DIR/logs/latest.log | tail -100"
    echo "  sqlite3 $OUTPUT_DIR/databases/*.db '.tables'"
}

main "$@"
