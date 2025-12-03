#!/bin/bash
# deploy-debug.sh - Build debug APK with release signing and deploy to device
#
# Debug builds allow run-as access while release signing enables OAuth.
# This script handles:
#   - Web asset synchronization to all required locations
#   - Debug APK build with Gradle
#   - Device connection verification
#   - APK installation and app launch
#
# Usage:
#   ./deploy-debug.sh                    # Full rebuild and deploy
#   ./deploy-debug.sh --skip-build       # Use existing APK
#   ./deploy-debug.sh --skip-web         # Skip web asset copy
#   ./deploy-debug.sh --clear-data       # Clear app data after install
#   ./deploy-debug.sh --verify           # Verify APK contents

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ANDROID_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(dirname "$ANDROID_DIR")"

# Package info
PACKAGE="ai.ciris.mobile"
ACTIVITY="$PACKAGE/.MainActivity"

# Paths
GUI_STATIC_DIR="$PROJECT_ROOT/android_gui_static"
ASSETS_DIR="$ANDROID_DIR/app/src/main/assets/public"
PYTHON_GUI_DIR="$ANDROID_DIR/app/src/main/python/android_gui_static"
APK_PATH="$ANDROID_DIR/app/build/outputs/apk/debug/app-debug.apk"

# Colors for output
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
log_step()    { echo -e "${CYAN}[STEP]${NC} $1"; }

# Find ADB with multiple fallback locations
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

# Parse arguments
SKIP_BUILD=false
SKIP_WEB=false
CLEAR_DATA=false
VERIFY_APK=false

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
        --verify)
            VERIFY_APK=true
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --skip-build    Skip gradle build, use existing APK"
            echo "  --skip-web      Skip web asset copy (use existing assets)"
            echo "  --clear-data    Clear app data after install"
            echo "  --verify        Verify APK contents before deploy"
            echo "  --help          Show this help message"
            echo ""
            echo "Web assets are copied from:"
            echo "  $GUI_STATIC_DIR"
            echo ""
            echo "To rebuild web assets, run:"
            echo "  $SCRIPT_DIR/full-rebuild.sh --skip-web"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Header
echo ""
echo -e "${CYAN}============================================================${NC}"
echo -e "${CYAN}  CIRIS Android Debug Deploy${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""

# Find ADB first
if ! ADB=$(find_adb); then
    log_error "ADB not found. Please set ANDROID_HOME or install Android SDK."
    exit 1
fi
log_info "ADB: $ADB"

# Verify device connection early
log_step "Checking device connection..."
if ! "$ADB" devices | grep -w "device" | grep -v "List" > /dev/null; then
    log_error "No device connected. Please connect a device or start an emulator."
    echo ""
    echo "Available devices:"
    "$ADB" devices
    exit 1
fi

DEVICE=$("$ADB" devices | grep -w "device" | grep -v "List" | head -1 | cut -f1)
DEVICE_MODEL=$("$ADB" shell getprop ro.product.model 2>/dev/null | tr -d '\r' || echo "Unknown")
log_success "Device: $DEVICE ($DEVICE_MODEL)"

# Ensure Java 17
export JAVA_HOME="${JAVA_HOME:-/usr/lib/jvm/java-17-openjdk-amd64}"
if [[ ! -d "$JAVA_HOME" ]]; then
    log_error "Java 17 not found at $JAVA_HOME"
    exit 1
fi
log_info "Java: $JAVA_HOME"

cd "$ANDROID_DIR"

# Copy web assets if not skipping
if [[ "$SKIP_WEB" != "true" && "$SKIP_BUILD" != "true" ]]; then
    log_step "Copying web assets to all locations..."

    if [[ ! -d "$GUI_STATIC_DIR" ]]; then
        log_error "android_gui_static not found at $GUI_STATIC_DIR"
        log_error "Run full-rebuild.sh first to build web assets"
        exit 1
    fi

    # Count source files
    local source_count
    source_count=$(find "$GUI_STATIC_DIR" -type f | wc -l)
    log_info "Source: $source_count files in android_gui_static"

    # Copy to Python sources (for Chaquopy)
    rm -rf "$PYTHON_GUI_DIR"
    mkdir -p "$PYTHON_GUI_DIR"
    cp -r "$GUI_STATIC_DIR/"* "$PYTHON_GUI_DIR/"
    local python_count
    python_count=$(find "$PYTHON_GUI_DIR" -type f | wc -l)
    log_info "  -> python/android_gui_static: $python_count files"

    # Copy to Android assets (for WebView)
    rm -rf "$ASSETS_DIR"
    mkdir -p "$(dirname "$ASSETS_DIR")"
    cp -r "$GUI_STATIC_DIR" "$ASSETS_DIR"
    local assets_count
    assets_count=$(find "$ASSETS_DIR" -type f | wc -l)
    log_info "  -> assets/public: $assets_count files"

    # Verify critical files exist
    if [[ ! -f "$ASSETS_DIR/index.html" ]]; then
        log_error "index.html missing from assets - web build incomplete"
        exit 1
    fi

    if [[ ! -d "$ASSETS_DIR/_next" ]]; then
        log_error "_next directory missing from assets - web build incomplete"
        exit 1
    fi

    log_success "Web assets copied and verified"
elif [[ "$SKIP_WEB" == "true" ]]; then
    log_info "Skipping web asset copy (--skip-web)"
fi

# Build debug APK
if [[ "$SKIP_BUILD" != "true" ]]; then
    log_step "Building debug APK..."
    ./gradlew assembleDebug --warning-mode=none

    if [[ ! -f "$APK_PATH" ]]; then
        log_error "Build failed - APK not found at $APK_PATH"
        exit 1
    fi

    # Get APK size
    apk_size=$(du -m "$APK_PATH" | cut -f1)
    log_success "Build complete: app-debug.apk ($apk_size MB)"
else
    if [[ ! -f "$APK_PATH" ]]; then
        log_error "No existing APK found at $APK_PATH"
        log_error "Run without --skip-build to build the APK"
        exit 1
    fi
    log_info "Using existing APK: $APK_PATH"
fi

# Verify APK if requested
if [[ "$VERIFY_APK" == "true" ]]; then
    log_step "Verifying APK contents..."

    local next_count
    next_count=$(unzip -l "$APK_PATH" 2>/dev/null | grep -c "assets/public/_next" || true)
    if [[ "$next_count" -lt 10 ]]; then
        log_error "APK missing _next assets (found $next_count, expected 100+)"
        exit 1
    fi
    log_info "  _next assets: $next_count files"

    local setup_chunk
    setup_chunk=$(unzip -l "$APK_PATH" 2>/dev/null | grep "app/setup/page-" | head -1 || true)
    if [[ -z "$setup_chunk" ]]; then
        log_warn "  Setup page chunk: NOT FOUND"
    else
        log_info "  Setup page chunk: found"
    fi

    log_success "APK verification passed"
fi

# Install APK
log_step "Installing APK..."
if ! "$ADB" install -r "$APK_PATH"; then
    log_error "Failed to install APK"
    exit 1
fi
log_success "APK installed"

# Clear data if requested
if [[ "$CLEAR_DATA" == "true" ]]; then
    log_step "Clearing app data..."
    "$ADB" shell pm clear "$PACKAGE"
    log_success "App data cleared"
fi

# Clear logcat and launch
log_step "Launching app..."
"$ADB" logcat -c
# Use monkey to launch - works better than am start with some devices
"$ADB" shell monkey -p "$PACKAGE" -c android.intent.category.LAUNCHER 1 > /dev/null 2>&1
log_success "App launched!"

# Print helpful commands
echo ""
echo -e "${CYAN}============================================================${NC}"
echo -e "${CYAN}  DEBUG BUILD DEPLOYED SUCCESSFULLY${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""
echo "View Python logs (live):"
echo "  $ADB logcat 'python.stdout:*' 'python.stderr:*' '*:S'"
echo ""
echo "Read latest log file (debug builds only):"
echo "  $ADB shell 'run-as $PACKAGE cat /data/data/$PACKAGE/files/ciris/logs/latest.log'"
echo ""
echo "Read incidents log:"
echo "  $ADB shell 'run-as $PACKAGE cat /data/data/$PACKAGE/files/ciris/logs/incidents_latest.log'"
echo ""
echo "Pull all device logs:"
echo "  $SCRIPT_DIR/pull-device-logs.sh"
echo ""
echo "Live tail logs:"
echo "  $SCRIPT_DIR/pull-device-logs.sh --live"
echo ""
echo -e "${CYAN}============================================================${NC}"
