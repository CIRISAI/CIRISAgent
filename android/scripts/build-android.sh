#!/bin/bash
# Unified Android Build Script
# Builds CIRISGUI-Android web assets and packages them into CIRISAgent Android app

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ANDROID_DIR="$(dirname "$SCRIPT_DIR")"
CIRISAGENT_DIR="$(dirname "$ANDROID_DIR")"

# Configuration
CIRISGUI_REPO="${CIRISGUI_REPO:-https://github.com/CIRISAI/CIRISGUI-Android.git}"
CIRISGUI_BRANCH="${CIRISGUI_BRANCH:-main}"
CIRISGUI_LOCAL_PATH="${CIRISGUI_LOCAL_PATH:-}"
BUILD_TYPE="${BUILD_TYPE:-debug}"
SKIP_WEB_BUILD="${SKIP_WEB_BUILD:-false}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Check for required tools
check_requirements() {
    log_info "Checking requirements..."

    if ! command -v node &> /dev/null; then
        log_error "Node.js is required but not installed"
        exit 1
    fi

    if ! command -v npm &> /dev/null; then
        log_error "npm is required but not installed"
        exit 1
    fi

    # Check for Java 17
    if [ -n "$JAVA_HOME" ]; then
        JAVA_VERSION=$("$JAVA_HOME/bin/java" -version 2>&1 | head -1 | cut -d'"' -f2 | cut -d'.' -f1)
    else
        JAVA_VERSION=$(java -version 2>&1 | head -1 | cut -d'"' -f2 | cut -d'.' -f1)
    fi

    if [ "$JAVA_VERSION" != "17" ] && [ "$JAVA_VERSION" != "21" ]; then
        log_warn "Java 17 or 21 recommended. Current: $JAVA_VERSION"
    fi

    log_info "Requirements check passed"
}

# Get CIRISGUI-Android source
get_web_source() {
    log_info "Getting CIRISGUI-Android web source..."

    WORK_DIR="$ANDROID_DIR/.web-build"
    mkdir -p "$WORK_DIR"

    if [ -n "$CIRISGUI_LOCAL_PATH" ] && [ -d "$CIRISGUI_LOCAL_PATH" ]; then
        log_info "Using local CIRISGUI-Android: $CIRISGUI_LOCAL_PATH"
        # Auto-detect if path is root repo or apps/agui directly
        if [ -d "$CIRISGUI_LOCAL_PATH/apps/agui" ]; then
            WEB_SOURCE="$CIRISGUI_LOCAL_PATH/apps/agui"
        elif [ -f "$CIRISGUI_LOCAL_PATH/package.json" ] && [ -f "$CIRISGUI_LOCAL_PATH/next.config.mjs" ]; then
            # Direct path to agui app
            WEB_SOURCE="$CIRISGUI_LOCAL_PATH"
        else
            log_error "Could not find Next.js app in: $CIRISGUI_LOCAL_PATH"
            log_error "Expected either apps/agui/ subdirectory or package.json + next.config.mjs"
            exit 1
        fi
    else
        log_info "Cloning CIRISGUI-Android from $CIRISGUI_REPO (branch: $CIRISGUI_BRANCH)"

        if [ -d "$WORK_DIR/CIRISGUI-Android" ]; then
            cd "$WORK_DIR/CIRISGUI-Android"
            git fetch origin
            git checkout "$CIRISGUI_BRANCH"
            git pull origin "$CIRISGUI_BRANCH"
            cd "$CIRISAGENT_DIR"
        else
            git clone --branch "$CIRISGUI_BRANCH" --depth 1 "$CIRISGUI_REPO" "$WORK_DIR/CIRISGUI-Android"
        fi

        WEB_SOURCE="$WORK_DIR/CIRISGUI-Android/apps/agui"
    fi

    if [ ! -d "$WEB_SOURCE" ]; then
        log_error "Web source directory not found: $WEB_SOURCE"
        exit 1
    fi

    log_info "Web source: $WEB_SOURCE"
}

# Build web assets
build_web_assets() {
    if [ "$SKIP_WEB_BUILD" = "true" ]; then
        log_info "Skipping web build (SKIP_WEB_BUILD=true)"
        return
    fi

    log_info "Building web assets..."

    cd "$WEB_SOURCE"

    # Install dependencies
    log_info "Installing npm dependencies..."
    npm ci || npm install

    # Build Next.js static export
    log_info "Building Next.js app..."
    npm run build

    if [ ! -d "$WEB_SOURCE/out" ]; then
        log_error "Build failed - 'out' directory not found"
        exit 1
    fi

    log_info "Web assets built successfully"
}

# Copy web assets to Android
copy_web_assets() {
    log_info "Copying web assets to Android..."

    ASSETS_DIR="$ANDROID_DIR/app/src/main/assets/public"

    # Clean previous assets
    rm -rf "$ASSETS_DIR"
    mkdir -p "$ASSETS_DIR"

    # Copy built web assets
    cp -r "$WEB_SOURCE/out/"* "$ASSETS_DIR/"

    # Count files
    FILE_COUNT=$(find "$ASSETS_DIR" -type f | wc -l)
    log_info "Copied $FILE_COUNT files to $ASSETS_DIR"
}

# Build Android APK
build_android() {
    log_info "Building Android APK ($BUILD_TYPE)..."

    cd "$ANDROID_DIR"

    # Set JAVA_HOME if Java 17 is available
    if [ -d "/usr/lib/jvm/java-17-openjdk-amd64" ]; then
        export JAVA_HOME="/usr/lib/jvm/java-17-openjdk-amd64"
        log_info "Using Java 17: $JAVA_HOME"
    fi

    # Clean and build
    if [ "$BUILD_TYPE" = "release" ]; then
        ./gradlew clean assembleRelease
        APK_PATH="$ANDROID_DIR/app/build/outputs/apk/release/app-release.apk"
    else
        ./gradlew clean assembleDebug
        APK_PATH="$ANDROID_DIR/app/build/outputs/apk/debug/app-debug.apk"
    fi

    if [ -f "$APK_PATH" ]; then
        log_info "APK built successfully: $APK_PATH"

        # Copy to output directory
        OUTPUT_DIR="$ANDROID_DIR/build/outputs"
        mkdir -p "$OUTPUT_DIR"
        cp "$APK_PATH" "$OUTPUT_DIR/"

        log_info "APK copied to: $OUTPUT_DIR/$(basename $APK_PATH)"
    else
        log_error "APK not found at expected path: $APK_PATH"
        exit 1
    fi
}

# Main
main() {
    log_info "=== CIRIS Android Unified Build ==="
    log_info "Build type: $BUILD_TYPE"

    check_requirements
    get_web_source
    build_web_assets
    copy_web_assets
    build_android

    log_info "=== Build Complete ==="
}

# Parse arguments
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
        --skip-web)
            SKIP_WEB_BUILD="true"
            shift
            ;;
        --local-gui)
            CIRISGUI_LOCAL_PATH="$2"
            shift 2
            ;;
        --branch)
            CIRISGUI_BRANCH="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --release       Build release APK"
            echo "  --debug         Build debug APK (default)"
            echo "  --skip-web      Skip web asset build"
            echo "  --local-gui     Path to local CIRISGUI-Android repo"
            echo "  --branch        CIRISGUI-Android branch to use"
            echo "  --help          Show this help"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

main
