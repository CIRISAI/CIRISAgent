#!/bin/bash
# CIRIS iOS GUI Build Script
# Builds CIRISGUI web assets and packages them for iOS app
#
# Usage:
#   ./build-gui.sh                    # Clone and build from CIRISGUI-Standalone
#   ./build-gui.sh --local-gui PATH   # Use local CIRISGUI repo
#   ./build-gui.sh --skip-web         # Skip npm build (use existing assets)

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IOS_DIR="$(dirname "$SCRIPT_DIR")"
PROJECT_ROOT="$(dirname "$IOS_DIR")"

# Configuration
CIRISGUI_REPO="${CIRISGUI_REPO:-https://github.com/CIRISAI/CIRISGUI-Standalone.git}"
CIRISGUI_BRANCH="${CIRISGUI_BRANCH:-main}"
CIRISGUI_LOCAL_PATH="${CIRISGUI_LOCAL_PATH:-}"
SKIP_WEB_BUILD="${SKIP_WEB_BUILD:-false}"

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
        --local-gui)
            CIRISGUI_LOCAL_PATH="$2"
            shift 2
            ;;
        --branch)
            CIRISGUI_BRANCH="$2"
            shift 2
            ;;
        --skip-web)
            SKIP_WEB_BUILD="true"
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [options]"
            echo ""
            echo "Options:"
            echo "  --local-gui PATH  Path to local CIRISGUI repo"
            echo "  --branch NAME     Git branch to use (default: main)"
            echo "  --skip-web        Skip npm build, use existing assets"
            echo "  --help            Show this help"
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
echo -e "${CYAN}  CIRIS iOS GUI Build${NC}"
echo -e "${CYAN}============================================================${NC}"
echo ""

# Check requirements
check_requirements() {
    log_step "Checking requirements..."

    if ! command -v node &> /dev/null; then
        log_error "Node.js is required but not installed"
        log_info "Install with: brew install node"
        exit 1
    fi

    if ! command -v npm &> /dev/null; then
        log_error "npm is required but not installed"
        exit 1
    fi

    NODE_VER=$(node --version)
    log_info "Node.js: $NODE_VER"
    log_success "Requirements OK"
}

# Get CIRISGUI source
get_web_source() {
    log_step "Getting CIRISGUI source..."

    WORK_DIR="$IOS_DIR/.web-build"
    mkdir -p "$WORK_DIR"

    if [ -n "$CIRISGUI_LOCAL_PATH" ] && [ -d "$CIRISGUI_LOCAL_PATH" ]; then
        log_info "Using local CIRISGUI: $CIRISGUI_LOCAL_PATH"

        # Auto-detect if path is root repo or apps/agui directly
        if [ -d "$CIRISGUI_LOCAL_PATH/apps/agui" ]; then
            WEB_SOURCE="$CIRISGUI_LOCAL_PATH/apps/agui"
        elif [ -f "$CIRISGUI_LOCAL_PATH/package.json" ]; then
            WEB_SOURCE="$CIRISGUI_LOCAL_PATH"
        else
            log_error "Could not find Next.js app in: $CIRISGUI_LOCAL_PATH"
            exit 1
        fi
    else
        log_info "Cloning CIRISGUI from $CIRISGUI_REPO (branch: $CIRISGUI_BRANCH)"

        if [ -d "$WORK_DIR/CIRISGUI-Standalone" ]; then
            cd "$WORK_DIR/CIRISGUI-Standalone"
            git fetch origin
            git checkout "$CIRISGUI_BRANCH"
            git pull origin "$CIRISGUI_BRANCH" || true
            cd "$PROJECT_ROOT"
        else
            git clone --branch "$CIRISGUI_BRANCH" --depth 1 "$CIRISGUI_REPO" "$WORK_DIR/CIRISGUI-Standalone"
        fi

        # Check structure
        if [ -d "$WORK_DIR/CIRISGUI-Standalone/apps/agui" ]; then
            WEB_SOURCE="$WORK_DIR/CIRISGUI-Standalone/apps/agui"
        else
            WEB_SOURCE="$WORK_DIR/CIRISGUI-Standalone"
        fi
    fi

    if [ ! -f "$WEB_SOURCE/package.json" ]; then
        log_error "package.json not found in: $WEB_SOURCE"
        exit 1
    fi

    log_success "Web source: $WEB_SOURCE"
}

# Build web assets
build_web_assets() {
    if [ "$SKIP_WEB_BUILD" = "true" ]; then
        log_step "Skipping web build (--skip-web)"
        return
    fi

    log_step "Building web assets..."

    cd "$WEB_SOURCE"

    # Install dependencies
    log_info "Installing npm dependencies..."
    npm ci 2>/dev/null || npm install

    # Build Next.js static export
    log_info "Building Next.js app (this may take a minute)..."
    npm run build

    # Check for output
    if [ -d "$WEB_SOURCE/out" ]; then
        OUT_DIR="$WEB_SOURCE/out"
    elif [ -d "$WEB_SOURCE/dist" ]; then
        OUT_DIR="$WEB_SOURCE/dist"
    elif [ -d "$WEB_SOURCE/.next/static" ]; then
        log_error "Found .next but no 'out' directory. Ensure next.config.js has output: 'export'"
        exit 1
    else
        log_error "Build output not found. Expected 'out' or 'dist' directory."
        exit 1
    fi

    log_success "Web assets built: $OUT_DIR"
}

# Copy web assets to iOS
copy_web_assets() {
    log_step "Copying web assets to iOS..."

    # Determine output directory
    if [ -d "$WEB_SOURCE/out" ]; then
        OUT_DIR="$WEB_SOURCE/out"
    elif [ -d "$WEB_SOURCE/dist" ]; then
        OUT_DIR="$WEB_SOURCE/dist"
    else
        log_error "No build output found"
        exit 1
    fi

    # iOS GUI static directory
    IOS_GUI_DIR="$IOS_DIR/ios_gui_static"

    # Clean and copy
    rm -rf "$IOS_GUI_DIR"
    mkdir -p "$IOS_GUI_DIR"
    cp -r "$OUT_DIR/"* "$IOS_GUI_DIR/"

    # Count files
    FILE_COUNT=$(find "$IOS_GUI_DIR" -type f | wc -l | tr -d ' ')
    log_success "Copied $FILE_COUNT files to $IOS_GUI_DIR"

    # Also copy to Briefcase app sources
    BRIEFCASE_GUI="$IOS_DIR/CirisiOS/src/ios_gui_static"
    rm -rf "$BRIEFCASE_GUI"
    mkdir -p "$BRIEFCASE_GUI"
    cp -r "$OUT_DIR/"* "$BRIEFCASE_GUI/"
    log_success "Copied to Briefcase sources: $BRIEFCASE_GUI"
}

# Summary
show_summary() {
    echo ""
    echo -e "${CYAN}============================================================${NC}"
    echo -e "${CYAN}  GUI Build Complete${NC}"
    echo -e "${CYAN}============================================================${NC}"
    echo ""
    echo "Assets location: $IOS_DIR/ios_gui_static/"
    echo ""
    echo "Next steps:"
    echo "  1. Run: ./ios/scripts/full-rebuild.sh --skip-wheels"
    echo "  2. Deploy: ./ios/scripts/deploy-ios.sh"
    echo ""
}

# Main
main() {
    check_requirements
    get_web_source
    build_web_assets
    copy_web_assets
    show_summary
}

main
