#!/bin/bash
# CIRIS iOS Build Script
# Builds the iOS app using Briefcase
#
# Usage:
#   ./build-ios.sh                    # Build for simulator (debug)
#   ./build-ios.sh --device           # Build for physical device
#   ./build-ios.sh --release          # Build release version
#   ./build-ios.sh --skip-wheels      # Skip pydantic-core wheel build

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IOS_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(dirname "$IOS_DIR")"
CIRISIOS_DIR="$IOS_DIR/CirisiOS"

# Configuration
BUILD_TARGET="simulator"  # simulator or device
BUILD_TYPE="debug"
SKIP_WHEELS="false"
SKIP_SOURCE="false"

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

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --device)
            BUILD_TARGET="device"
            shift
            ;;
        --simulator)
            BUILD_TARGET="simulator"
            shift
            ;;
        --release)
            BUILD_TYPE="release"
            shift
            ;;
        --debug)
            BUILD_TYPE="debug"
            shift
            ;;
        --skip-wheels)
            SKIP_WHEELS="true"
            shift
            ;;
        --skip-source)
            SKIP_SOURCE="true"
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --device        Build for physical iOS device"
            echo "  --simulator     Build for iOS Simulator (default)"
            echo "  --release       Build release version"
            echo "  --debug         Build debug version (default)"
            echo "  --skip-wheels   Skip pydantic-core wheel build"
            echo "  --skip-source   Skip source code sync"
            echo "  --help          Show this help"
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
echo -e "${CYAN}  CIRIS iOS Build${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""
log_info "Target: $BUILD_TARGET"
log_info "Type: $BUILD_TYPE"

# Check requirements
log_step "Checking requirements..."

if ! command -v briefcase &> /dev/null; then
    log_error "Briefcase not found. Install with: pip install briefcase"
    exit 1
fi

if ! command -v xcodebuild &> /dev/null; then
    log_error "Xcode not found. Please install Xcode from the App Store."
    exit 1
fi

log_success "Requirements satisfied"

# Build pydantic-core wheels if needed
if [[ "$SKIP_WHEELS" != "true" ]]; then
    if [[ ! -f "$IOS_DIR/wheels/pydantic_core"*"iphoneos.whl" ]] || \
       [[ ! -f "$IOS_DIR/wheels/pydantic_core"*"iphonesimulator.whl" ]]; then
        log_step "Building pydantic-core wheels for iOS..."
        "$SCRIPT_DIR/build_wheels.sh"
        log_success "Wheels built"
    else
        log_info "Wheels already exist, skipping build"
    fi
else
    log_info "Skipping wheel build (--skip-wheels)"
fi

# Sync source code
if [[ "$SKIP_SOURCE" != "true" ]]; then
    log_step "Syncing source code..."
    "$SCRIPT_DIR/prepare_source.sh"
    log_success "Source synced"
else
    log_info "Skipping source sync (--skip-source)"
fi

# Change to project directory
cd "$CIRISIOS_DIR"

# Clean previous build
log_step "Cleaning previous build..."
rm -rf build/

# Create iOS project
log_step "Creating iOS project with Briefcase..."
briefcase create iOS

# Build iOS app
log_step "Building iOS app..."
briefcase build iOS

# Summary
echo ""
echo -e "${CYAN}============================================================${NC}"
echo -e "${CYAN}  Build Complete${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""
echo "App location: $CIRISIOS_DIR/build/ciris_ios/ios/xcode/"
echo ""
echo "Next steps:"
echo "  Run in simulator:  $SCRIPT_DIR/deploy-ios.sh"
echo "  Run on device:     $SCRIPT_DIR/deploy-ios.sh --device"
echo "  Open in Xcode:     open $CIRISIOS_DIR/build/ciris_ios/ios/xcode/Ciris\\ iOS.xcodeproj"
echo ""
