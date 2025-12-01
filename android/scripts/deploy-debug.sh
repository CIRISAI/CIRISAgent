#!/bin/bash
# deploy-debug.sh - Build debug APK with release signing and deploy to device
# Debug builds allow run-as access while release signing enables OAuth

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ANDROID_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(dirname "$ANDROID_DIR")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Find ADB
find_adb() {
    # Check common locations
    local adb_paths=(
        "/mnt/c/Users/moore/AppData/Local/Android/Sdk/platform-tools/adb.exe"
        "/mnt/c/Users/*/AppData/Local/Android/Sdk/platform-tools/adb.exe"
        "$ANDROID_HOME/platform-tools/adb"
        "$HOME/Android/Sdk/platform-tools/adb"
        "$(which adb 2>/dev/null)"
    )

    for adb in "${adb_paths[@]}"; do
        # Handle glob patterns
        for expanded in $adb; do
            if [[ -x "$expanded" ]]; then
                echo "$expanded"
                return 0
            fi
        done
    done

    log_error "ADB not found. Please set ANDROID_HOME or install Android SDK."
    exit 1
}

ADB=$(find_adb)
log_info "Using ADB: $ADB"

# Ensure Java 17
export JAVA_HOME="${JAVA_HOME:-/usr/lib/jvm/java-17-openjdk-amd64}"
if [[ ! -d "$JAVA_HOME" ]]; then
    log_error "Java 17 not found at $JAVA_HOME"
    exit 1
fi
log_info "Using Java: $JAVA_HOME"

# Parse arguments
SKIP_BUILD=false
SKIP_WEB=false
CLEAR_DATA=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --skip-build)
            SKIP_BUILD=true
            shift
            ;;
        --skip-web)
            SKIP_WEB=true
            shift
            ;;
        --clear-data)
            CLEAR_DATA=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --skip-build    Skip gradle build, use existing APK"
            echo "  --skip-web      Skip web asset copy (faster rebuild)"
            echo "  --clear-data    Clear app data after install"
            echo "  --help          Show this help message"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

cd "$ANDROID_DIR"

# Copy web assets if not skipping
if [[ "$SKIP_WEB" != "true" && "$SKIP_BUILD" != "true" ]]; then
    log_info "Copying web assets..."
    if [[ -d "$PROJECT_ROOT/android_gui_static" ]]; then
        rm -rf app/src/main/python/android_gui_static
        cp -r "$PROJECT_ROOT/android_gui_static" app/src/main/python/
        rm -rf app/src/main/assets/public
        cp -r "$PROJECT_ROOT/android_gui_static" app/src/main/assets/public
        log_success "Web assets copied"
    else
        log_warn "android_gui_static not found, skipping web assets"
    fi
fi

# Build debug APK
APK_PATH="app/build/outputs/apk/debug/app-debug.apk"

if [[ "$SKIP_BUILD" != "true" ]]; then
    log_info "Building debug APK with release signing..."
    ./gradlew assembleDebug --warning-mode=none

    if [[ ! -f "$APK_PATH" ]]; then
        log_error "Build failed - APK not found at $APK_PATH"
        exit 1
    fi
    log_success "Build complete: $APK_PATH"
else
    if [[ ! -f "$APK_PATH" ]]; then
        log_error "No existing APK found at $APK_PATH"
        exit 1
    fi
    log_info "Using existing APK: $APK_PATH"
fi

# Check device connection
log_info "Checking device connection..."
if ! "$ADB" devices | grep -q "device$"; then
    log_error "No device connected. Please connect a device or start an emulator."
    exit 1
fi

DEVICE=$("$ADB" devices | grep "device$" | head -1 | cut -f1)
log_success "Device connected: $DEVICE"

# Install APK
log_info "Installing APK..."
"$ADB" install -r "$APK_PATH"
log_success "APK installed"

# Clear data if requested
if [[ "$CLEAR_DATA" == "true" ]]; then
    log_info "Clearing app data..."
    "$ADB" shell pm clear ai.ciris.mobile
    log_success "App data cleared"
fi

# Clear logcat
log_info "Clearing logcat..."
"$ADB" logcat -c

# Launch app
log_info "Launching app..."
"$ADB" shell am start -n ai.ciris.mobile/.MainActivity

log_success "App launched!"
echo ""
echo "============================================================"
echo "DEBUG BUILD DEPLOYED"
echo "============================================================"
echo ""
echo "View Python logs:"
echo "  $ADB logcat 'python.stdout:*' 'python.stderr:*' '*:S'"
echo ""
echo "Read on-device logs (debug build allows run-as):"
echo "  $ADB shell 'run-as ai.ciris.mobile cat /data/data/ai.ciris.mobile/files/ciris/logs/latest.log'"
echo ""
echo "Read incidents log:"
echo "  $ADB shell 'run-as ai.ciris.mobile cat /data/data/ai.ciris.mobile/files/ciris/logs/incidents_latest.log'"
echo ""
echo "============================================================"
