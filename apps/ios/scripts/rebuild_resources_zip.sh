#!/bin/bash
# Rebuild Resources.zip for iOS app deployment
#
# This is the CANONICAL script for creating Resources.zip. Always use this
# instead of ad-hoc zip commands to avoid missing directories.
#
# What it does:
#   1. Syncs latest ciris_engine + ciris_adapters from repo (default, skip with --no-sync)
#   2. Removes desktop-only files that shouldn't be on iOS
#   3. Cleans __pycache__ and .pyc files
#   4. Validates all 3 required directories exist (app, app_packages, python)
#   5. Creates Resources.zip with all contents
#   6. Optionally bumps CFBundleVersion in Info.plist
#
# Usage:
#   ./rebuild_resources_zip.sh                  # Sync source from repo + rebuild zip (DEFAULT)
#   ./rebuild_resources_zip.sh --bump           # Sync + rebuild + bump build number
#   ./rebuild_resources_zip.sh --no-sync        # Skip sync, just rebuild zip from current Resources/
#   ./rebuild_resources_zip.sh --no-sync --bump # Rebuild without sync + bump build number
#
# NOTE: Sync is ALWAYS on by default to prevent stale files in Resources/.
# Use --no-sync only if you know Resources/ is already up to date.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IOS_APP_DIR="$(dirname "$SCRIPT_DIR")"
CIRIS_ROOT="$(dirname "$(dirname "$IOS_APP_DIR")")"
RESOURCES_DIR="$IOS_APP_DIR/Resources"
INFO_PLIST="$IOS_APP_DIR/iosApp/Info.plist"

# Parse flags — sync is ON by default
SYNC=true
BUMP=false
for arg in "$@"; do
    case "$arg" in
        --no-sync) SYNC=false ;;
        --sync)    SYNC=true ;;  # Kept for backwards compat (already default)
        --bump)    BUMP=true ;;
        *)         echo "Unknown flag: $arg"; echo "Usage: $0 [--no-sync] [--bump]"; exit 1 ;;
    esac
done

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

step() { echo -e "${BLUE}==> $1${NC}"; }
ok()   { echo -e "${GREEN}  + $1${NC}"; }
warn() { echo -e "${YELLOW}  ! $1${NC}"; }
fail() { echo -e "${RED}  x $1${NC}"; exit 1; }

echo ""
echo "========================================"
echo "  Rebuild Resources.zip"
echo "========================================"
echo ""

# -----------------------------------------------------------
# Step 1: Validate Resources/ directory
# -----------------------------------------------------------
step "Validating Resources directory..."

[ -d "$RESOURCES_DIR" ] || fail "Resources directory not found at $RESOURCES_DIR"

MISSING=""
[ -d "$RESOURCES_DIR/app" ]          || MISSING="$MISSING app"
[ -d "$RESOURCES_DIR/app_packages" ] || MISSING="$MISSING app_packages"
[ -d "$RESOURCES_DIR/python" ]       || MISSING="$MISSING python"

if [ -n "$MISSING" ]; then
    fail "Missing required directories in Resources/:$MISSING\n  Run prepare_python_bundle.sh first to populate from BeeWare build."
fi
ok "All 3 required directories present (app, app_packages, python)"

# -----------------------------------------------------------
# Step 2: Optionally sync source from repo
# -----------------------------------------------------------
if [ "$SYNC" = true ]; then
    step "Syncing source from repo..."

    # Sync ciris_engine (exclude desktop-only dirs)
    rsync -a --delete \
        --exclude='__pycache__' \
        --exclude='gui_static' \
        --exclude='desktop_app' \
        --exclude='desktop_launcher.py' \
        --exclude='cli.py' \
        "$CIRIS_ROOT/ciris_engine/" "$RESOURCES_DIR/app/ciris_engine/"
    ok "ciris_engine synced"

    # Sync ciris_adapters
    rsync -a --delete --exclude='__pycache__' \
        "$CIRIS_ROOT/ciris_adapters/" "$RESOURCES_DIR/app/ciris_adapters/"
    ok "ciris_adapters synced"

    # Sync ciris_ios (if source exists)
    CIRIS_IOS_SRC="$CIRIS_ROOT/ios/CirisiOS/src/ciris_ios"
    if [ -d "$CIRIS_IOS_SRC" ]; then
        rsync -a --exclude='__pycache__' \
            "$CIRIS_IOS_SRC/" "$RESOURCES_DIR/app/ciris_ios/"
        ok "ciris_ios synced"
    fi

    # Sync guides
    for guide in CIRIS_COMPREHENSIVE_GUIDE.md CIRIS_COMPREHENSIVE_GUIDE_MOBILE.md; do
        if [ -f "$CIRIS_ROOT/$guide" ]; then
            cp "$CIRIS_ROOT/$guide" "$RESOURCES_DIR/app/"
            ok "$guide copied"
        fi
    done
fi

# -----------------------------------------------------------
# Step 3: Remove desktop-only files that shouldn't be on iOS
# -----------------------------------------------------------
step "Cleaning desktop-only files..."

CLEANED=0
for item in \
    "$RESOURCES_DIR/app/ciris_engine/desktop_app" \
    "$RESOURCES_DIR/app/ciris_engine/desktop_launcher.py" \
    "$RESOURCES_DIR/app/ciris_engine/gui_static" \
    "$RESOURCES_DIR/app/ciris_engine/cli.py" \
    "$RESOURCES_DIR/app/ios_gui_static"; do
    if [ -e "$item" ]; then
        rm -rf "$item"
        ok "Removed $(basename "$item")"
        CLEANED=$((CLEANED + 1))
    fi
done
[ "$CLEANED" -eq 0 ] && ok "No desktop-only files found (clean)"

# -----------------------------------------------------------
# Step 4: Clean __pycache__ and .pyc
# -----------------------------------------------------------
step "Cleaning __pycache__ and .pyc files..."
PYCACHE_COUNT=$(find "$RESOURCES_DIR" -type d -name "__pycache__" 2>/dev/null | wc -l | tr -d ' ')
find "$RESOURCES_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
find "$RESOURCES_DIR" -name "*.pyc" -delete 2>/dev/null || true
ok "Removed $PYCACHE_COUNT __pycache__ directories"

# -----------------------------------------------------------
# Step 5: Build Resources.zip
# -----------------------------------------------------------
step "Building Resources.zip..."

cd "$RESOURCES_DIR"
rm -f "$IOS_APP_DIR/Resources.zip"
zip -q -r "$IOS_APP_DIR/Resources.zip" .
cd "$IOS_APP_DIR"

ZIP_SIZE=$(du -sh Resources.zip | cut -f1)
FILE_COUNT=$(unzip -l Resources.zip | tail -1 | awk '{print $2}')

ok "Resources.zip created: $ZIP_SIZE, $FILE_COUNT files"

# Sanity check: zip should contain files from all 3 dirs
APP_COUNT=$(unzip -l Resources.zip | grep -c "^ .* app/" || true)
PKG_COUNT=$(unzip -l Resources.zip | grep -c "^ .* app_packages/" || true)
PY_COUNT=$(unzip -l Resources.zip | grep -c "^ .* python/" || true)

echo ""
echo "  Contents:"
echo "    app/          : $APP_COUNT files"
echo "    app_packages/ : $PKG_COUNT files"
echo "    python/       : $PY_COUNT files"

if [ "$PKG_COUNT" -lt 100 ]; then
    warn "app_packages has very few files ($PKG_COUNT) - expected 2000+. Was prepare_python_bundle.sh run?"
fi
if [ "$PY_COUNT" -lt 100 ]; then
    warn "python stdlib has very few files ($PY_COUNT) - expected 2000+. Was prepare_python_bundle.sh run?"
fi

# -----------------------------------------------------------
# Step 6: Optionally bump build number
# -----------------------------------------------------------
if [ "$BUMP" = true ]; then
    step "Bumping CFBundleVersion in Info.plist..."

    if [ ! -f "$INFO_PLIST" ]; then
        warn "Info.plist not found at $INFO_PLIST"
    else
        CURRENT=$(/usr/libexec/PlistBuddy -c "Print :CFBundleVersion" "$INFO_PLIST" 2>/dev/null)
        NEW=$((CURRENT + 1))
        /usr/libexec/PlistBuddy -c "Set :CFBundleVersion $NEW" "$INFO_PLIST"
        ok "CFBundleVersion: $CURRENT -> $NEW"
    fi
fi

# -----------------------------------------------------------
# Done
# -----------------------------------------------------------
echo ""
echo -e "${GREEN}========================================"
echo "  Resources.zip ready"
echo "========================================${NC}"
echo ""
echo "  Next: build and deploy"
echo "    cd mobile && ./gradlew :shared:linkDebugFrameworkIosArm64"
echo "    cd iosApp && xcodebuild -project iosApp.xcodeproj -scheme iosApp \\"
echo "      -sdk iphoneos -configuration Debug -destination 'generic/platform=iOS' \\"
echo "      -allowProvisioningUpdates -quiet build"
echo ""
