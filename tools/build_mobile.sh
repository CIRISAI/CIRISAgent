#!/usr/bin/env bash
#
# Clean build for all CIRIS mobile platforms.
#
# Syncs Python code + localization, generates build secrets,
# rebuilds Resources.zip, and compiles KMP frameworks + desktop JAR.
#
# Usage:
#   tools/build_mobile.sh              # Full build (debug + release)
#   tools/build_mobile.sh debug        # Debug only
#   tools/build_mobile.sh release      # Release only
#   tools/build_mobile.sh ios-deploy   # Debug build + deploy to iPhone
#
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

step() { echo -e "${CYAN}▸ $1${NC}"; }
ok()   { echo -e "${GREEN}  ✓ $1${NC}"; }
warn() { echo -e "${YELLOW}  ⚠ $1${NC}"; }
fail() { echo -e "${RED}  ✗ $1${NC}"; exit 1; }

MODE="${1:-all}"  # all, debug, release, ios-deploy

# ============================================================================
# 1. Pre-flight checks
# ============================================================================
step "Pre-flight checks"

[[ -f "ciris_engine/constants.py" ]] || fail "Not in CIRISAgent project root"
[[ -d "mobile/shared" ]] || fail "mobile/shared not found"

# Version info
VERSION=$(grep 'CIRIS_VERSION = ' ciris_engine/constants.py | head -1 | sed 's/.*"\(.*\)".*/\1/')
ok "Project version: $VERSION"

# Check gradle
[[ -f "mobile/gradlew" ]] || fail "mobile/gradlew not found"

# ============================================================================
# 2. Generate build secrets
# ============================================================================
step "Generating build secrets"

python3 tools/generate_ios_secrets.py
if [[ ! -f "ciris_adapters/wallet/providers/_build_secrets.py" ]]; then
    fail "_build_secrets.py was not generated"
fi

# Verify the generated file has actual content (not empty getters)
if grep -q "data = \[\]" ciris_adapters/wallet/providers/_build_secrets.py; then
    warn "Some secrets are empty — check ~/.coinbase_paymaster_url and ~/.etherspot_android_key"
else
    ok "Build secrets generated with all keys"
fi

# ============================================================================
# 3. Sync Python code to iOS Resources
# ============================================================================
step "Syncing Python code to iOS Resources"

rsync -a --delete --exclude='__pycache__' --exclude='*.pyc' \
    ciris_engine/ mobile/iosApp/Resources/app/ciris_engine/
ok "ciris_engine synced"

rsync -a --delete --exclude='__pycache__' --exclude='*.pyc' \
    ciris_adapters/ mobile/iosApp/Resources/app/ciris_adapters/
ok "ciris_adapters synced"

# Ensure build secrets landed in Resources (rsync from source which has it)
if [[ ! -f "mobile/iosApp/Resources/app/ciris_adapters/wallet/providers/_build_secrets.py" ]]; then
    fail "_build_secrets.py missing from iOS Resources after sync"
fi
ok "Build secrets in iOS Resources"

# ============================================================================
# 4. Sync localization to all targets
# ============================================================================
step "Syncing localization files"

LANG_COUNT=$(ls localization/*.json 2>/dev/null | wc -l | tr -d ' ')
[[ "$LANG_COUNT" -gt 0 ]] || fail "No localization JSON files found in localization/"

cp localization/*.json mobile/iosApp/iosApp/localization/
cp localization/*.json mobile/iosApp/Resources/app/localization/
cp localization/*.json mobile/desktopApp/src/main/resources/localization/
cp localization/*.json mobile/shared/src/desktopMain/resources/localization/
cp localization/*.json mobile/androidApp/src/main/assets/localization/

ok "$LANG_COUNT language files synced to 5 targets"

# ============================================================================
# 5. Rebuild Resources.zip
# ============================================================================
step "Rebuilding Resources.zip"

cd mobile/iosApp
rm -f Resources.zip
cd Resources
zip -q -r ../Resources.zip .
cd ..

ZIP_SIZE=$(wc -c < Resources.zip | tr -d ' ')
[[ "$ZIP_SIZE" -gt 1000000 ]] || fail "Resources.zip suspiciously small: $ZIP_SIZE bytes"
ok "Resources.zip: $(echo "$ZIP_SIZE" | awk '{printf "%.1f MB", $1/1048576}')"

cd "$PROJECT_ROOT"

# ============================================================================
# 6. Build KMP frameworks
# ============================================================================
cd mobile

if [[ "$MODE" == "all" || "$MODE" == "debug" || "$MODE" == "ios-deploy" ]]; then
    step "Building debug iOS framework"
    ./gradlew :shared:linkDebugFrameworkIosArm64 --quiet 2>&1 | tail -1
    [[ -d "shared/build/bin/iosArm64/debugFramework/shared.framework" ]] || fail "Debug framework not built"
    ok "Debug iOS framework"
fi

if [[ "$MODE" == "all" || "$MODE" == "release" ]]; then
    step "Building release iOS framework"
    ./gradlew :shared:linkReleaseFrameworkIosArm64 --quiet 2>&1 | tail -1
    [[ -d "shared/build/bin/iosArm64/releaseFramework/shared.framework" ]] || fail "Release framework not built"
    ok "Release iOS framework"
fi

# ============================================================================
# 7. Build desktop JAR
# ============================================================================
if [[ "$MODE" == "all" || "$MODE" == "release" ]]; then
    step "Building desktop JAR"
    ./gradlew :desktopApp:packageUberJarForCurrentOS --quiet 2>&1 | tail -1
    JAR=$(find desktopApp/build/compose/jars -name "CIRIS-*.jar" 2>/dev/null | head -1)
    [[ -n "$JAR" ]] || fail "Desktop JAR not found"
    ok "Desktop JAR: $(basename "$JAR")"
fi

cd "$PROJECT_ROOT"

# ============================================================================
# 8. Optional: iOS deploy
# ============================================================================
if [[ "$MODE" == "ios-deploy" ]]; then
    step "Building iOS app (xcodebuild)"
    cd mobile/iosApp
    xcodebuild -project iosApp.xcodeproj -scheme iosApp \
        -sdk iphoneos -configuration Debug \
        -destination 'generic/platform=iOS' \
        -allowProvisioningUpdates -quiet build 2>&1 | tail -1

    APP_PATH=$(find ~/Library/Developer/Xcode/DerivedData/iosApp-* \
        -name "iosApp.app" -path "*Debug-iphoneos*" \
        -not -path "*/Index.noindex/*" 2>/dev/null | head -1)
    [[ -n "$APP_PATH" ]] || fail "iosApp.app not found in DerivedData"
    ok "Built: $(basename "$APP_PATH")"

    # Find device
    DEVICE_ID=$(xcrun devicectl list devices 2>/dev/null | grep "connected" | awk '{print $NF}' | head -1)
    if [[ -z "$DEVICE_ID" ]]; then
        warn "No connected iOS device found — skipping deploy"
    else
        step "Installing to device $DEVICE_ID"
        xcrun devicectl device install app -d "$DEVICE_ID" "$APP_PATH" 2>&1 | tail -1
        ok "Installed"

        step "Launching"
        xcrun devicectl device process launch -d "$DEVICE_ID" --terminate-existing ai.ciris.mobile 2>&1 | tail -1
        ok "Launched"
    fi
    cd "$PROJECT_ROOT"
fi

# ============================================================================
# Done
# ============================================================================
echo ""
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${GREEN}  Build complete: CIRIS $VERSION ($MODE)${NC}"
echo -e "${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
