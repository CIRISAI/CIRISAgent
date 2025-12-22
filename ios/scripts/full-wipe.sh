#!/bin/bash
# CIRIS iOS Full Wipe Script
# Removes all build artifacts, caches, and generated files
#
# Usage:
#   ./full-wipe.sh              # Wipe everything
#   ./full-wipe.sh --keep-wheels # Keep pydantic-core wheels

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IOS_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(dirname "$IOS_DIR")"
CIRISIOS_DIR="$IOS_DIR/CirisiOS"

# Configuration
KEEP_WHEELS="false"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

log_info()    { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn()    { echo -e "${YELLOW}[WARN]${NC} $1"; }

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --keep-wheels)
            KEEP_WHEELS="true"
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --keep-wheels   Don't delete pydantic-core wheels"
            echo "  --help          Show this help"
            exit 0
            ;;
        *)
            shift
            ;;
    esac
done

echo ""
echo -e "${CYAN}============================================================${NC}"
echo -e "${CYAN}  CIRIS iOS Full Wipe${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""

# Remove Briefcase build
if [[ -d "$CIRISIOS_DIR/build" ]]; then
    log_info "Removing Briefcase build..."
    rm -rf "$CIRISIOS_DIR/build"
fi

# Remove logs
if [[ -d "$CIRISIOS_DIR/logs" ]]; then
    log_info "Removing Briefcase logs..."
    rm -rf "$CIRISIOS_DIR/logs"
fi

# Remove synced source
log_info "Removing synced source code..."
rm -rf "$CIRISIOS_DIR/src/ciris_engine"
rm -rf "$CIRISIOS_DIR/src/ciris_adapters"
rm -rf "$CIRISIOS_DIR/src/ciris_sdk"

# Remove PyO3 config
if [[ -f "$IOS_DIR/pyo3-ios-config.txt" ]]; then
    log_info "Removing PyO3 config..."
    rm -f "$IOS_DIR/pyo3-ios-config.txt"
fi

# Remove wheels (unless --keep-wheels)
if [[ "$KEEP_WHEELS" != "true" ]]; then
    if [[ -d "$IOS_DIR/wheels" ]]; then
        log_info "Removing pydantic-core wheels..."
        rm -rf "$IOS_DIR/wheels"
    fi
else
    log_warn "Keeping wheels (--keep-wheels)"
fi

# Remove Python cache
log_info "Removing Python cache..."
find "$CIRISIOS_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$CIRISIOS_DIR" -name "*.pyc" -delete 2>/dev/null || true

echo ""
echo -e "${GREEN}Wipe complete!${NC}"
echo ""
echo "To rebuild:"
echo "  $SCRIPT_DIR/full-rebuild.sh"
echo ""
