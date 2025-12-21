#!/bin/bash
# CIRIS iOS Deploy Script
# Deploys the iOS app to simulator or device
#
# Usage:
#   ./deploy-ios.sh                    # Run in simulator
#   ./deploy-ios.sh --device           # Run on physical device
#   ./deploy-ios.sh -d "iPhone 17 Pro" # Specific simulator
#   ./deploy-ios.sh --logs             # Show logs after launch

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IOS_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(dirname "$IOS_DIR")"
CIRISIOS_DIR="$IOS_DIR/CirisiOS"

# Configuration
BUILD_TARGET="simulator"
DEVICE_NAME=""
SHOW_LOGS="false"
SKIP_BUILD="false"

# App info
BUNDLE_ID="ai.ciris.ciris-ios"

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
        -d|--device-name)
            DEVICE_NAME="$2"
            shift 2
            ;;
        --logs)
            SHOW_LOGS="true"
            shift
            ;;
        --skip-build)
            SKIP_BUILD="true"
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --device           Deploy to physical iOS device"
            echo "  --simulator        Deploy to iOS Simulator (default)"
            echo "  -d, --device-name  Specific device/simulator name (e.g., 'iPhone 17 Pro')"
            echo "  --logs             Show Python logs after launch"
            echo "  --skip-build       Skip build step, use existing app"
            echo "  --help             Show this help"
            echo ""
            echo "Examples:"
            echo "  $0                           # Run in default simulator"
            echo "  $0 -d 'iPhone 17 Pro'       # Run in specific simulator"
            echo "  $0 --device                  # Deploy to connected iPhone"
            echo "  $0 --logs                    # Run and show Python logs"
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
echo -e "${CYAN}  CIRIS iOS Deploy${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""

cd "$CIRISIOS_DIR"

# Check if build exists
if [[ ! -d "build/ciris_ios/ios/xcode" ]]; then
    log_warn "No existing build found. Running build first..."
    "$SCRIPT_DIR/build-ios.sh"
fi

# Build command
BUILD_CMD="briefcase run iOS"

if [[ -n "$DEVICE_NAME" ]]; then
    BUILD_CMD="$BUILD_CMD -d '$DEVICE_NAME'"
fi

# Run the app
log_step "Launching CIRIS iOS..."

if [[ "$SHOW_LOGS" == "true" ]]; then
    log_info "App will launch and show Python logs (Ctrl+C to stop)"
    echo ""
    eval $BUILD_CMD
else
    # Run in background and capture output
    log_info "Launching app..."
    eval $BUILD_CMD &
    APP_PID=$!

    # Wait for app to launch
    sleep 5

    echo ""
    echo -e "${CYAN}============================================================${NC}"
    echo -e "${CYAN}  App Launched Successfully${NC}"
    echo -e "${CYAN}============================================================${NC}"
    echo ""
    echo "Useful commands:"
    echo ""
    echo "  View logs (live):"
    echo "    $SCRIPT_DIR/pull-logs-ios.sh --live"
    echo ""
    echo "  Pull all logs:"
    echo "    $SCRIPT_DIR/pull-logs-ios.sh"
    echo ""
    echo "  List simulators:"
    echo "    xcrun simctl list devices"
    echo ""
    echo "  Open Xcode project:"
    echo "    open $CIRISIOS_DIR/build/ciris_ios/ios/xcode/Ciris\\ iOS.xcodeproj"
    echo ""

    # Kill the background process since Briefcase stays running
    kill $APP_PID 2>/dev/null || true
fi
