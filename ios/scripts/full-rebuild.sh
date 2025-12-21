#!/bin/bash
# CIRIS iOS Full Rebuild Script
# Performs a complete rebuild from scratch including pydantic-core wheels
#
# Usage:
#   ./full-rebuild.sh              # Full rebuild everything
#   ./full-rebuild.sh --skip-wheels # Rebuild app but not wheels

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IOS_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(dirname "$IOS_DIR")"
CIRISIOS_DIR="$IOS_DIR/CirisiOS"

# Configuration
SKIP_WHEELS="false"

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
        --skip-wheels)
            SKIP_WHEELS="true"
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --skip-wheels   Skip pydantic-core wheel rebuild"
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
echo -e "${CYAN}  CIRIS iOS Full Rebuild${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""

START_TIME=$(date +%s)

# Step 1: Clean everything
log_step "1/5 Cleaning previous builds..."
rm -rf "$CIRISIOS_DIR/build"
rm -rf "$CIRISIOS_DIR/logs"
rm -rf "$IOS_DIR/pyo3-ios-config.txt"
log_success "Clean complete"

# Step 2: Build pydantic-core wheels
if [[ "$SKIP_WHEELS" != "true" ]]; then
    log_step "2/5 Building pydantic-core wheels..."
    rm -rf "$IOS_DIR/wheels"
    mkdir -p "$IOS_DIR/wheels"
    "$SCRIPT_DIR/build_wheels.sh"
    log_success "Wheels built"
else
    log_step "2/5 Skipping wheel build (--skip-wheels)"
    if [[ ! -f "$IOS_DIR/wheels/"*"iphoneos.whl" ]]; then
        log_error "No wheels found! Remove --skip-wheels to build them."
        exit 1
    fi
fi

# Step 3: Sync source code
log_step "3/5 Syncing source code..."
"$SCRIPT_DIR/prepare_source.sh"
log_success "Source synced"

# Step 4: Create iOS project
log_step "4/5 Creating iOS project..."
cd "$CIRISIOS_DIR"
briefcase create iOS
log_success "iOS project created"

# Step 5: Build iOS app
log_step "5/5 Building iOS app..."
briefcase build iOS
log_success "iOS app built"

# Calculate time
END_TIME=$(date +%s)
DURATION=$((END_TIME - START_TIME))
MINUTES=$((DURATION / 60))
SECONDS=$((DURATION % 60))

# Summary
echo ""
echo -e "${CYAN}============================================================${NC}"
echo -e "${CYAN}  Full Rebuild Complete${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""
echo "Build time: ${MINUTES}m ${SECONDS}s"
echo ""
echo "Artifacts:"
echo "  Wheels:  $IOS_DIR/wheels/"
ls -la "$IOS_DIR/wheels/"*.whl 2>/dev/null | awk '{print "           " $NF " (" $5 ")"}'
echo ""
echo "  App:     $CIRISIOS_DIR/build/ciris_ios/ios/xcode/"
echo ""
echo "Next steps:"
echo "  Deploy to simulator:  $SCRIPT_DIR/deploy-ios.sh"
echo "  Open in Xcode:        open $CIRISIOS_DIR/build/ciris_ios/ios/xcode/Ciris\\ iOS.xcodeproj"
echo ""
