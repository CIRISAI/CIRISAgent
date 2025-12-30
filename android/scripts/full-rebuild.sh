#!/bin/bash
# full-rebuild.sh - Complete Android build from scratch
#
# Handles:
#   1. Web assets rebuild from local CIRISGUI-Android
#   2. Copies to all 3 required locations
#   3. Optionally builds pydantic-core wheels for all architectures
#   4. Builds debug or release APK/AAB
#   5. Optionally deploys to connected device
#
# Usage:
#   ./full-rebuild.sh                    # Full debug build
#   ./full-rebuild.sh --release          # Full release build
#   ./full-rebuild.sh --skip-wheels      # Skip pydantic wheel builds
#   ./full-rebuild.sh --deploy           # Build and deploy to device
#   ./full-rebuild.sh --aab              # Build AAB for Play Store

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ANDROID_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(dirname "$ANDROID_DIR")"

# Configuration
BUILD_TYPE="debug"
BUILD_WHEELS="false"
DEPLOY_AFTER="false"
CLEAR_DATA="false"
OUTPUT_FORMAT="apk"
SKIP_WEB="false"

# Paths
WEB_BUILD_DIR="$ANDROID_DIR/.web-build/CIRISGUI-Android"
AGUI_DIR="$WEB_BUILD_DIR/apps/agui"
GUI_STATIC_DIR="$PROJECT_ROOT/android_gui_static"
ASSETS_DIR="$ANDROID_DIR/app/src/main/assets/public"
PYTHON_GUI_DIR="$ANDROID_DIR/app/src/main/python/android_gui_static"
WHEELS_DIR="$ANDROID_DIR/app/wheels"
PYTHON_SRC_DIR="$ANDROID_DIR/app/src/main/python"
MAIN_CIRIS_ENGINE="$PROJECT_ROOT/ciris_engine"
MAIN_MODULAR_SERVICES="$PROJECT_ROOT/ciris_adapters"

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
log_step()    { echo -e "${CYAN}[STEP]${NC} $1"; }

print_header() {
    echo ""
    echo -e "${CYAN}============================================================${NC}"
    echo -e "${CYAN}  $1${NC}"
    echo -e "${CYAN}============================================================${NC}"
    echo ""
}

# Parse arguments
parse_args() {
    while [[ $# -gt 0 ]]; do
        case $1 in
            --release)
                BUILD_TYPE="release"
                shift
                ;;
            --debug)
                BUILD_TYPE="debug"
                shift
                ;;
            --aab)
                OUTPUT_FORMAT="aab"
                BUILD_TYPE="release"
                shift
                ;;
            --wheels)
                BUILD_WHEELS="true"
                shift
                ;;
            --skip-wheels)
                BUILD_WHEELS="false"
                shift
                ;;
            --skip-web)
                SKIP_WEB="true"
                shift
                ;;
            --deploy)
                DEPLOY_AFTER="true"
                shift
                ;;
            --clear-data)
                CLEAR_DATA="true"
                shift
                ;;
            --help|-h)
                echo "Usage: $0 [options]"
                echo ""
                echo "Build Options:"
                echo "  --release       Build release APK (default: debug)"
                echo "  --debug         Build debug APK"
                echo "  --aab           Build AAB for Play Store (implies --release)"
                echo "  --skip-web      Skip web asset rebuild (use existing android_gui_static)"
                echo ""
                echo "Wheel Options:"
                echo "  --wheels        Build pydantic-core wheels for all architectures"
                echo "  --skip-wheels   Skip wheel builds (default)"
                echo ""
                echo "Deploy Options:"
                echo "  --deploy        Deploy to connected device after build"
                echo "  --clear-data    Clear app data after deploy"
                echo ""
                echo "Examples:"
                echo "  $0                          # Full debug build"
                echo "  $0 --release --deploy       # Release build and deploy"
                echo "  $0 --wheels --release       # Build wheels + release APK"
                echo "  $0 --aab                    # Build AAB for Play Store"
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done
}

# Find Java 17 with multiple fallback locations
find_java() {
    local java_paths=(
        "/usr/lib/jvm/java-17-openjdk-amd64"
        "/usr/lib/jvm/java-17-openjdk"
        "/snap/android-studio/current/jbr"
        "$JAVA_HOME"
    )

    for java_path in "${java_paths[@]}"; do
        if [[ -n "$java_path" && -x "$java_path/bin/java" ]]; then
            echo "$java_path"
            return 0
        fi
    done

    return 1
}

# Find Android SDK with multiple fallback locations
find_android_sdk() {
    local sdk_paths=(
        "$ANDROID_HOME"
        "$HOME/Android/Sdk"
        "/opt/android-sdk"
        "/usr/lib/android-sdk"
    )

    for sdk_path in "${sdk_paths[@]}"; do
        if [[ -n "$sdk_path" && -d "$sdk_path/platform-tools" ]]; then
            echo "$sdk_path"
            return 0
        fi
    done

    return 1
}

# Setup keystore environment variables
setup_keystore() {
    local keystore_paths=(
        "$HOME/ciris-release-key.jks"
        "$ANDROID_DIR/ciris-release-key.jks"
        "$PROJECT_ROOT/ciris-release-key.jks"
    )

    local keystore_path=""
    for path in "${keystore_paths[@]}"; do
        if [[ -f "$path" ]]; then
            keystore_path="$path"
            break
        fi
    done

    if [[ -z "$keystore_path" ]]; then
        log_error "Release keystore not found. Checked:"
        for path in "${keystore_paths[@]}"; do
            echo "  - $path"
        done
        echo ""
        echo "Create a keystore with:"
        echo "  keytool -genkeypair -v -keystore ~/ciris-release-key.jks -keyalg RSA -keysize 2048 -validity 10000 -alias ciris-key"
        return 1
    fi

    export CIRIS_KEYSTORE_PATH="$keystore_path"

    # Set default password if not already set
    if [[ -z "$CIRIS_KEYSTORE_PASSWORD" ]]; then
        export CIRIS_KEYSTORE_PASSWORD="${CIRIS_KEYSTORE_PASSWORD:-changeme123}"
    fi
    if [[ -z "$CIRIS_KEY_PASSWORD" ]]; then
        export CIRIS_KEY_PASSWORD="${CIRIS_KEY_PASSWORD:-$CIRIS_KEYSTORE_PASSWORD}"
    fi

    log_info "Keystore: $keystore_path"
    return 0
}

# Check requirements
check_requirements() {
    log_step "Checking requirements..."

    local errors=0

    # Check Node.js (only needed if building web assets)
    if [ "$SKIP_WEB" != "true" ]; then
        if ! command -v node &> /dev/null; then
            log_error "Node.js not found (required for web build)"
            errors=$((errors + 1))
        else
            log_info "Node.js: $(node --version)"
        fi

        # Check npm
        if ! command -v npm &> /dev/null; then
            log_error "npm not found (required for web build)"
            errors=$((errors + 1))
        else
            log_info "npm: $(npm --version)"
        fi
    fi

    # Find and export Java
    if JAVA_HOME=$(find_java); then
        export JAVA_HOME
        log_info "Java: $JAVA_HOME"
    else
        log_error "Java 17 not found. Please install: sudo apt install openjdk-17-jdk"
        errors=$((errors + 1))
    fi

    # Find and export Android SDK
    if ANDROID_HOME=$(find_android_sdk); then
        export ANDROID_HOME
        log_info "Android SDK: $ANDROID_HOME"
    else
        log_error "Android SDK not found. Please set ANDROID_HOME or install Android Studio."
        errors=$((errors + 1))
    fi

    # Setup keystore
    if ! setup_keystore; then
        errors=$((errors + 1))
    fi

    # Check Android NDK (for wheels)
    if [ "$BUILD_WHEELS" = "true" ]; then
        if [ ! -d "${ANDROID_NDK_HOME:-$ANDROID_HOME/ndk}" ]; then
            log_error "Android NDK not found (required for --wheels)"
            errors=$((errors + 1))
        fi

        if ! command -v maturin &> /dev/null; then
            log_error "maturin not found (required for --wheels)"
            errors=$((errors + 1))
        fi

        if ! command -v rustup &> /dev/null; then
            log_error "rustup not found (required for --wheels)"
            errors=$((errors + 1))
        fi
    fi

    # Check web source exists
    if [ "$SKIP_WEB" != "true" ] && [ ! -d "$AGUI_DIR" ]; then
        log_warn "Web source not found at $AGUI_DIR"
        log_info "Will clone CIRISGUI-Android repository..."
    fi

    if [ $errors -gt 0 ]; then
        log_error "Requirements check failed with $errors errors"
        exit 1
    fi

    log_success "Requirements check passed"
}

# Ensure web source exists
ensure_web_source() {
    if [ "$SKIP_WEB" = "true" ]; then
        log_info "Skipping web source check (--skip-web)"
        return
    fi

    log_step "Ensuring web source exists..."

    if [ ! -d "$AGUI_DIR" ]; then
        log_info "Cloning CIRISGUI-Android repository..."
        mkdir -p "$WEB_BUILD_DIR"
        git clone --branch main --depth 1 https://github.com/CIRISAI/CIRISGUI-Android.git "$WEB_BUILD_DIR"
    else
        log_info "Web source found at $AGUI_DIR"

        # Update if it's a git repo
        if [ -d "$WEB_BUILD_DIR/.git" ]; then
            log_info "Updating web source..."
            cd "$WEB_BUILD_DIR"
            git fetch origin main
            git reset --hard origin/main
            cd "$PROJECT_ROOT"
        fi
    fi

    log_success "Web source ready"
}

# Build web assets
build_web_assets() {
    if [ "$SKIP_WEB" = "true" ]; then
        log_info "Skipping web build (--skip-web)"
        return
    fi

    print_header "Building Web Assets"

    cd "$AGUI_DIR"

    log_step "Installing npm dependencies..."
    npm ci || npm install

    log_step "Building Next.js static export..."
    npm run build

    if [ ! -d "$AGUI_DIR/out" ]; then
        log_error "Build failed - 'out' directory not found"
        exit 1
    fi

    local file_count
    file_count=$(find "$AGUI_DIR/out" -type f | wc -l)
    log_success "Web build complete: $file_count files"

    cd "$PROJECT_ROOT"
}

# Copy web assets to all 3 locations
copy_web_assets() {
    print_header "Copying Web Assets"

    local source_dir
    if [ "$SKIP_WEB" = "true" ]; then
        source_dir="$GUI_STATIC_DIR"
        if [ ! -d "$source_dir" ]; then
            log_error "android_gui_static not found - cannot skip web build"
            exit 1
        fi
        log_info "Using existing android_gui_static"
    else
        source_dir="$AGUI_DIR/out"
    fi

    # Location 1: android_gui_static (project root)
    log_step "Copying to android_gui_static..."
    # Only clear and copy if source is different from destination (not --skip-web)
    if [ "$source_dir" != "$GUI_STATIC_DIR" ]; then
        rm -rf "$GUI_STATIC_DIR"
        mkdir -p "$GUI_STATIC_DIR"
        cp -r "$source_dir/"* "$GUI_STATIC_DIR/"
    fi
    local count1
    count1=$(find "$GUI_STATIC_DIR" -type f | wc -l)
    log_info "  -> $count1 files"

    # Location 2: Android assets/public (for WebView)
    log_step "Copying to app/src/main/assets/public..."
    rm -rf "$ASSETS_DIR"
    mkdir -p "$(dirname "$ASSETS_DIR")"
    cp -r "$GUI_STATIC_DIR" "$ASSETS_DIR"
    local count2
    count2=$(find "$ASSETS_DIR" -type f | wc -l)
    log_info "  -> $count2 files"

    # Location 3: Python sources (for Chaquopy/Python server)
    log_step "Copying to app/src/main/python/android_gui_static..."
    rm -rf "$PYTHON_GUI_DIR"
    mkdir -p "$PYTHON_GUI_DIR"
    cp -r "$GUI_STATIC_DIR/"* "$PYTHON_GUI_DIR/"
    local count3
    count3=$(find "$PYTHON_GUI_DIR" -type f | wc -l)
    log_info "  -> $count3 files"

    log_success "Web assets copied to all 3 locations"
}

# Sync Python sources from main repo
sync_python_sources() {
    print_header "Syncing Python Sources from Main Repo"

    # Sync ciris_engine
    log_step "Syncing ciris_engine..."
    if [ -d "$MAIN_CIRIS_ENGINE" ]; then
        rm -rf "$PYTHON_SRC_DIR/ciris_engine"
        cp -r "$MAIN_CIRIS_ENGINE" "$PYTHON_SRC_DIR/ciris_engine"
        # Remove __pycache__ directories
        find "$PYTHON_SRC_DIR/ciris_engine" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
        local count1
        count1=$(find "$PYTHON_SRC_DIR/ciris_engine" -name "*.py" | wc -l)
        log_info "  -> $count1 Python files"
    else
        log_error "Main ciris_engine not found at $MAIN_CIRIS_ENGINE"
        exit 1
    fi

    # Sync ciris_adapters
    log_step "Syncing ciris_adapters..."
    if [ -d "$MAIN_MODULAR_SERVICES" ]; then
        rm -rf "$PYTHON_SRC_DIR/ciris_adapters"
        cp -r "$MAIN_MODULAR_SERVICES" "$PYTHON_SRC_DIR/ciris_adapters"
        # Remove __pycache__ directories
        find "$PYTHON_SRC_DIR/ciris_adapters" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
        local count2
        count2=$(find "$PYTHON_SRC_DIR/ciris_adapters" -name "*.py" | wc -l)
        log_info "  -> $count2 Python files"
    else
        log_warn "ciris_adapters not found at $MAIN_MODULAR_SERVICES - skipping"
    fi

    log_success "Python sources synced from main repo"
}

# Build pydantic-core wheels
build_wheels() {
    if [ "$BUILD_WHEELS" != "true" ]; then
        log_info "Skipping wheel builds (use --wheels to enable)"
        return
    fi

    print_header "Building Pydantic-Core Wheels"

    if [ -x "$SCRIPT_DIR/build-pydantic-wheels.sh" ]; then
        "$SCRIPT_DIR/build-pydantic-wheels.sh"
    else
        log_error "build-pydantic-wheels.sh not found or not executable"
        exit 1
    fi

    # Verify wheels exist
    local wheel_count
    wheel_count=$(find "$WHEELS_DIR" -name "pydantic_core*.whl" 2>/dev/null | wc -l)
    if [ "$wheel_count" -lt 3 ]; then
        log_warn "Expected 3 wheels (arm64, armv7, x86_64), found $wheel_count"
    else
        log_success "All 3 architecture wheels built"
    fi

    ls -la "$WHEELS_DIR/"*.whl 2>/dev/null || true
}

# Build Android APK/AAB
build_android() {
    print_header "Building Android ($BUILD_TYPE, format: $OUTPUT_FORMAT)"

    cd "$ANDROID_DIR"

    log_step "Running Gradle build..."

    if [ "$BUILD_TYPE" = "release" ]; then
        if [ "$OUTPUT_FORMAT" = "aab" ]; then
            ./gradlew clean bundleRelease --warning-mode=none
            OUTPUT_PATH="$ANDROID_DIR/app/build/outputs/bundle/release/app-release.aab"
        else
            ./gradlew clean assembleRelease --warning-mode=none
            OUTPUT_PATH="$ANDROID_DIR/app/build/outputs/apk/release/app-release.apk"
        fi
    else
        ./gradlew clean assembleDebug --warning-mode=none
        OUTPUT_PATH="$ANDROID_DIR/app/build/outputs/apk/debug/app-debug.apk"
    fi

    if [ ! -f "$OUTPUT_PATH" ]; then
        log_error "Build failed - output not found: $OUTPUT_PATH"
        exit 1
    fi

    # Get file size
    local size_mb
    size_mb=$(du -m "$OUTPUT_PATH" | cut -f1)
    log_success "Build complete: $OUTPUT_PATH ($size_mb MB)"

    # Copy to outputs directory
    mkdir -p "$ANDROID_DIR/build/outputs"
    cp "$OUTPUT_PATH" "$ANDROID_DIR/build/outputs/"

    cd "$PROJECT_ROOT"
}

# Validate APK contents
validate_build() {
    if [ "$OUTPUT_FORMAT" = "aab" ]; then
        log_info "Skipping validation for AAB"
        return
    fi

    log_step "Validating APK contents..."

    # Check for _next directory
    local next_count
    next_count=$(unzip -l "$OUTPUT_PATH" 2>/dev/null | grep -c "assets/public/_next" || true)
    if [ "$next_count" -lt 10 ]; then
        log_error "APK missing _next assets! Found only $next_count files."
        exit 1
    fi
    log_info "  _next assets: $next_count files"

    # Check for setup page
    local setup_chunk
    setup_chunk=$(unzip -l "$OUTPUT_PATH" 2>/dev/null | grep "app/setup/page-" | head -1 || true)
    if [ -z "$setup_chunk" ]; then
        log_warn "Setup page chunk not found in APK"
    else
        log_info "  Setup page: found"
    fi

    # Check for Python sources
    local python_count
    python_count=$(unzip -l "$OUTPUT_PATH" 2>/dev/null | grep -c "assets/chaquopy" || true)
    if [ "$python_count" -lt 100 ]; then
        log_warn "Python assets may be incomplete ($python_count files)"
    else
        log_info "  Python assets: $python_count files"
    fi

    log_success "APK validation passed"
}

# Detect if running in WSL2
is_wsl() {
    if [[ -f /proc/version ]]; then
        grep -qi "microsoft\|wsl" /proc/version 2>/dev/null && return 0
    fi
    [[ -d /mnt/c/Windows ]] && return 0
    return 1
}

# Find ADB with environment-aware fallback locations
find_adb() {
    local adb_paths=()

    if is_wsl; then
        # WSL2: Prefer Windows ADB for USB device access
        adb_paths=(
            "/mnt/c/Users/moore/AppData/Local/Android/Sdk/platform-tools/adb.exe"
            "/mnt/c/Users/*/AppData/Local/Android/Sdk/platform-tools/adb.exe"
            "/mnt/c/Program Files/Android/Android Studio/platform-tools/adb.exe"
            "$ANDROID_HOME/platform-tools/adb"
            "$HOME/Android/Sdk/platform-tools/adb"
            "$(which adb 2>/dev/null)"
        )
    else
        # Native Linux: Prefer Linux ADB
        adb_paths=(
            "$ANDROID_HOME/platform-tools/adb"
            "$HOME/Android/Sdk/platform-tools/adb"
            "/opt/android-sdk/platform-tools/adb"
            "/usr/lib/android-sdk/platform-tools/adb"
            "/usr/bin/adb"
            "$(which adb 2>/dev/null)"
        )
    fi

    for adb in "${adb_paths[@]}"; do
        # Handle glob patterns (e.g., /mnt/c/Users/*)
        for expanded in $adb; do
            if [[ -x "$expanded" ]]; then
                echo "$expanded"
                return 0
            fi
        done
    done

    return 1
}

# Deploy to device
deploy_to_device() {
    if [ "$DEPLOY_AFTER" != "true" ]; then
        return
    fi

    print_header "Deploying to Device"

    local ADB
    if ! ADB=$(find_adb); then
        log_error "ADB not found - cannot deploy"
        exit 1
    fi
    log_info "Using ADB: $ADB"

    # Check device
    if ! "$ADB" devices | grep -q "device$"; then
        log_error "No device connected"
        exit 1
    fi

    local device
    device=$("$ADB" devices | grep "device$" | head -1 | cut -f1)
    log_info "Device: $device"

    # Install
    log_step "Installing APK..."
    "$ADB" install -r "$OUTPUT_PATH"

    # Clear data if requested
    if [ "$CLEAR_DATA" = "true" ]; then
        log_step "Clearing app data..."
        "$ADB" shell pm clear ai.ciris.mobile
    fi

    # Launch
    log_step "Launching app..."
    "$ADB" logcat -c
    "$ADB" shell am start -n ai.ciris.mobile/.MainActivity

    log_success "Deployed to device!"

    echo ""
    echo "View logs:"
    echo "  $ADB logcat 'python.stdout:*' 'python.stderr:*' '*:S'"
    echo ""
    echo "Pull device logs:"
    echo "  $SCRIPT_DIR/pull-device-logs.sh"
}

# Print summary
print_summary() {
    print_header "Build Summary"

    echo "Build type:    $BUILD_TYPE"
    echo "Output format: $OUTPUT_FORMAT"
    echo "Output:        $OUTPUT_PATH"
    echo ""
    echo "Web assets:"
    echo "  - $GUI_STATIC_DIR"
    echo "  - $ASSETS_DIR"
    echo "  - $PYTHON_GUI_DIR"
    echo ""

    if [ "$BUILD_WHEELS" = "true" ]; then
        echo "Wheels built in: $WHEELS_DIR"
        ls "$WHEELS_DIR/"*.whl 2>/dev/null | while read wheel; do
            echo "  - $(basename "$wheel")"
        done
        echo ""
    fi

    if [ "$DEPLOY_AFTER" = "true" ]; then
        echo "Deployed: Yes"
    fi
}

# Main
main() {
    parse_args "$@"

    print_header "CIRIS Android Full Rebuild"

    log_info "Build type:    $BUILD_TYPE"
    log_info "Output format: $OUTPUT_FORMAT"
    log_info "Build wheels:  $BUILD_WHEELS"
    log_info "Skip web:      $SKIP_WEB"
    log_info "Deploy after:  $DEPLOY_AFTER"
    echo ""

    check_requirements
    ensure_web_source
    build_web_assets
    copy_web_assets
    sync_python_sources
    build_wheels
    build_android
    validate_build
    deploy_to_device
    print_summary

    log_success "Full rebuild complete!"
}

main "$@"
