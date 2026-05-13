#!/bin/bash
# Full rebuild and deploy iOS app to simulator
#
# Usage:
#   ./rebuild_and_deploy.sh                # Full rebuild (prepare + zip + xcodegen + build + deploy)
#   ./rebuild_and_deploy.sh --quick        # Quick: overlay source + zip + build + deploy (skip prepare_python_bundle)
#   ./rebuild_and_deploy.sh --source-only  # Fastest: overlay source + zip + deploy (skip xcodebuild, hot-swap zip)
#
# This script:
#   1. Overlays latest ciris_engine + ciris_verify source into Resources/
#   2. Recreates Resources.zip
#   3. Regenerates Xcode project (xcodegen)
#   4. Builds with xcodebuild
#   5. Terminates old app on simulator
#   6. Installs and launches new build

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IOS_APP_DIR="$(dirname "$SCRIPT_DIR")"
CIRIS_ROOT="$(dirname "$(dirname "$IOS_APP_DIR")")"
RESOURCES_DIR="$IOS_APP_DIR/Resources"

MODE="${1:-full}"
SIMULATOR_NAME="iPhone 17 Pro"

# Shared rsync exclusions for iOS Resources — mirrors Android build.gradle excludes
# These reduce zip size and avoid shipping docs/tests/dev artifacts to the device
IOS_RSYNC_EXCLUDES=(
    --exclude='__pycache__'
    --exclude='.pytest_cache'
    --exclude='*.pyc'
    --exclude='*.pyo'
    --exclude='gui_static'
    --exclude='desktop_app'
    --exclude='android_gui_static'
    --exclude='README*'
    --exclude='*.md'
    --exclude='examples/'
    --exclude='tests/'
    --exclude='adapters/discord'
)
DEVICE_UUID="A53DA92F-972A-5A28-86E3-E6E86E02EE79"
IS_DEVICE=false
if [ "$MODE" = "--device" ]; then
    IS_DEVICE=true
    MODE="--quick"
fi

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

step() { echo -e "${BLUE}==> $1${NC}"; }
ok()   { echo -e "${GREEN}  ✓ $1${NC}"; }
warn() { echo -e "${YELLOW}  ⚠ $1${NC}"; }
fail() { echo -e "${RED}  ✗ $1${NC}"; exit 1; }

echo ""
echo "================================================"
echo "  CIRIS iOS Rebuild & Deploy"
echo "  Mode: $MODE"
echo "================================================"
echo ""

# Step 0: Verify prerequisites
step "Checking prerequisites..."
command -v xcodegen >/dev/null 2>&1 || fail "xcodegen not found. Install: brew install xcodegen"
command -v xcodebuild >/dev/null 2>&1 || fail "xcodebuild not found. Install Xcode."
[ -d "$RESOURCES_DIR" ] || fail "Resources directory not found at $RESOURCES_DIR"

# Preflight: Resources sanity checks
step "Preflight: Resources validation..."

# Check for desktop_app JAR (98MB+ of dead weight on iOS)
if [ -d "$RESOURCES_DIR/app/ciris_engine/desktop_app" ]; then
    JAR_SIZE=$(du -sm "$RESOURCES_DIR/app/ciris_engine/desktop_app" 2>/dev/null | cut -f1)
    warn "desktop_app/ found in Resources (${JAR_SIZE}MB) — removing (not needed on iOS)"
    rm -rf "$RESOURCES_DIR/app/ciris_engine/desktop_app"
    ok "Removed desktop_app/"
fi

# Check for gui_static (Next.js web GUI — not needed on iOS)
if [ -d "$RESOURCES_DIR/app/ciris_engine/gui_static" ]; then
    warn "gui_static/ found in Resources — removing (not needed on iOS)"
    rm -rf "$RESOURCES_DIR/app/ciris_engine/gui_static"
    ok "Removed gui_static/"
fi

# Clean __pycache__
find "$RESOURCES_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null
ok "Cleaned __pycache__"

# Verify kmp_main.py exists (required for Python runtime to start)
if [ ! -f "$RESOURCES_DIR/app/ciris_ios/kmp_main.py" ]; then
    fail "kmp_main.py missing from Resources/app/ciris_ios/ — Python runtime will not start"
fi
ok "kmp_main.py present"

# Verify Resources total size is reasonable (<150MB uncompressed)
RESOURCES_SIZE_MB=$(du -sm "$RESOURCES_DIR" 2>/dev/null | cut -f1)
if [ "$RESOURCES_SIZE_MB" -gt 150 ]; then
    warn "Resources is ${RESOURCES_SIZE_MB}MB (expected <150MB) — check for bundled artifacts"
    du -sh "$RESOURCES_DIR"/app/*/ 2>/dev/null | sort -rh | head -5
fi
ok "Resources: ${RESOURCES_SIZE_MB}MB"

# Preflight: Framework validation
step "Preflight: Framework validation..."

# Check shared.framework exists and is the correct type
SHARED_FW_DIR="$CIRIS_ROOT/client/shared/build/bin"
if $IS_DEVICE; then
    FW_CHECK="$SHARED_FW_DIR/iosArm64/debugFramework/shared.framework/shared"
else
    FW_CHECK="$SHARED_FW_DIR/iosSimulatorArm64/debugFramework/shared.framework/shared"
fi

if [ -f "$FW_CHECK" ]; then
    FW_TYPE=$(file "$FW_CHECK")
    if echo "$FW_TYPE" | grep -q "ar archive"; then
        ok "shared.framework: STATIC archive (correct for isStatic=true)"
        # Verify project.yml handles static correctly
        if grep -q "FRAMEWORKS_FOLDER_PATH.*shared" "$IOS_APP_DIR/project.yml" && ! grep -q "ar archive" "$IOS_APP_DIR/project.yml"; then
            warn "project.yml may embed static archive in Frameworks/ — verify Link KMP script handles static detection"
        fi
    elif echo "$FW_TYPE" | grep -q "dynamically linked"; then
        ok "shared.framework: DYNAMIC library"
    else
        warn "shared.framework: unknown type — $FW_TYPE"
    fi
    FW_SIZE_MB=$(du -sm "$FW_CHECK" 2>/dev/null | cut -f1)
    if [ "$FW_SIZE_MB" -gt 350 ]; then
        warn "shared.framework is ${FW_SIZE_MB}MB — check if materialIconsExtended is included (should be removed, saves ~113MB)"
    fi
    ok "shared.framework: ${FW_SIZE_MB}MB"
else
    warn "shared.framework not built yet — will be built during KMP step"
fi

if $IS_DEVICE; then
    ok "Target: Physical device ($DEVICE_UUID)"
else
    # Check simulator is booted
    BOOTED_DEVICE=$(xcrun simctl list devices | grep "(Booted)" | head -1)
    if [ -z "$BOOTED_DEVICE" ]; then
        warn "No simulator booted. Booting $SIMULATOR_NAME..."
        xcrun simctl boot "$SIMULATOR_NAME" 2>/dev/null || true
        sleep 3
    fi
    DEVICE_ID=$(xcrun simctl list devices | grep "(Booted)" | grep -oE '[A-F0-9-]{36}' | head -1)
    ok "Simulator: $DEVICE_ID"
fi

# Step 1: Full prepare or quick overlay
if [ "$MODE" = "full" ] || [ "$MODE" = "--full" ]; then
    step "Running full prepare_python_bundle.sh..."
    bash "$SCRIPT_DIR/prepare_python_bundle.sh" simulator
    ok "Python bundle prepared"
elif [ "$MODE" = "--quick" ] || [ "$MODE" = "--source-only" ]; then
    step "Quick overlay: latest ciris_engine source..."

    # Overlay ciris_engine
    rsync -a --delete "${IOS_RSYNC_EXCLUDES[@]}" \
        "$CIRIS_ROOT/ciris_engine/" "$RESOURCES_DIR/app/ciris_engine/"
    ok "ciris_engine overlaid"

    # Overlay ciris_adapters
    rsync -a --delete "${IOS_RSYNC_EXCLUDES[@]}" \
        "$CIRIS_ROOT/ciris_adapters/" "$RESOURCES_DIR/app/ciris_adapters/"
    ok "ciris_adapters overlaid"

    # Overlay ciris_ios
    rsync -a --exclude='__pycache__' \
        "$CIRIS_ROOT/ios/CirisiOS/src/ciris_ios/" "$RESOURCES_DIR/app/ciris_ios/"
    ok "ciris_ios overlaid"

    # ciris_verify: managed by tools/update_ciris_verify.py — do NOT overlay
    # from local CIRISVerify repo (has stale dylib that overwrites version-matched one)
    ok "ciris_verify: using pre-staged bindings (managed by update_ciris_verify.py)"

    # Clean pycache
    find "$RESOURCES_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
    ok "Source overlay complete"
else
    step "Running full prepare_python_bundle.sh..."
    bash "$SCRIPT_DIR/prepare_python_bundle.sh" simulator
    ok "Python bundle prepared"
fi

# Step 2: Recreate Resources.zip
step "Creating Resources.zip..."
cd "$RESOURCES_DIR"
rm -f "$IOS_APP_DIR/Resources.zip"
zip -q -r "$IOS_APP_DIR/Resources.zip" .
cd "$IOS_APP_DIR"
ZIP_SIZE=$(du -sh Resources.zip | cut -f1)
ok "Resources.zip created ($ZIP_SIZE)"

# Step 3: Source-only mode skips build — just hot-swap the zip into the installed app
if [ "$MODE" = "--source-only" ]; then
    step "Source-only: hot-swapping Resources.zip into installed app..."

    APP_BUNDLE=$(xcrun simctl get_app_container booted ai.ciris.mobile 2>/dev/null || true)
    if [ -z "$APP_BUNDLE" ] || [ ! -d "$APP_BUNDLE" ]; then
        warn "App not installed. Falling back to full build."
        MODE="--quick"
    else
        # Kill the running app
        xcrun simctl terminate booted ai.ciris.mobile 2>/dev/null || true
        sleep 1

        # Replace the zip in the installed bundle
        cp "$IOS_APP_DIR/Resources.zip" "$APP_BUNDLE/iosApp.app/Resources.zip" 2>/dev/null || \
        cp "$IOS_APP_DIR/Resources.zip" "$APP_BUNDLE/Resources.zip" 2>/dev/null || \
        warn "Could not hot-swap zip. Falling back to full install."

        # Relaunch
        xcrun simctl launch booted ai.ciris.mobile
        ok "App relaunched with updated Resources.zip"

        echo ""
        echo -e "${GREEN}=== Deploy Complete (source-only) ===${NC}"
        echo "  Wait ~15s for Python runtime to start"
        echo "  Then: curl http://localhost:8080/v1/system/health"
        exit 0
    fi
fi

# Step 3.5: Build KMP shared framework
step "Building KMP shared framework..."
cd "$CIRIS_ROOT/client"
if $IS_DEVICE; then
    ./gradlew :shared:linkDebugFrameworkIosArm64 2>&1 | tail -3
else
    ./gradlew :shared:linkDebugFrameworkIosSimulatorArm64 2>&1 | tail -3
fi
ok "KMP framework built"
cd "$IOS_APP_DIR"

# Step 4: Regenerate Xcode project
step "Regenerating Xcode project (xcodegen)..."
xcodegen generate 2>&1 | tail -3
ok "Xcode project generated"

# Step 4.1: Verify static framework handling in generated project
# The Link KMP script in project.yml must detect static archives and NOT
# embed them in Frameworks/. If this check fails, the app won't install.
if ! grep -q "ar archive" "$IOS_APP_DIR/project.yml" 2>/dev/null; then
    warn "project.yml missing static framework detection — iOS install will fail"
    warn "The 'Link KMP Shared Framework' script must check for 'ar archive'"
    warn "and skip copying to Frameworks/ for static builds"
fi

# Step 4.5: Bump build number
step "Bumping CFBundleVersion..."
CURRENT_BUILD=$(grep -A1 CFBundleVersion iosApp/Info.plist | tail -1 | sed 's/.*<string>\(.*\)<\/string>/\1/')
NEXT_BUILD=$((CURRENT_BUILD + 1))
plutil -replace CFBundleVersion -string "$NEXT_BUILD" iosApp/Info.plist
ok "Build $CURRENT_BUILD → $NEXT_BUILD"

# Step 4.9: Always overlay latest source and rebuild Resources.zip
# This ensures the zip matches the repo, not a stale committed version
step "Syncing latest source into Resources..."
rsync -a --delete "${IOS_RSYNC_EXCLUDES[@]}" \
    "$CIRIS_ROOT/ciris_engine/" "$RESOURCES_DIR/app/ciris_engine/"
rsync -a --delete "${IOS_RSYNC_EXCLUDES[@]}" \
    "$CIRIS_ROOT/ciris_adapters/" "$RESOURCES_DIR/app/ciris_adapters/"
find "$RESOURCES_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
# Also strip READMEs from sdk and any other source that was synced earlier
find "$RESOURCES_DIR" -name "README*" -o -name "*.md" | xargs rm -f 2>/dev/null || true
find "$RESOURCES_DIR/app" -type d -name "examples" -exec rm -rf {} + 2>/dev/null || true
cd "$RESOURCES_DIR"
rm -f "$IOS_APP_DIR/Resources.zip"
zip -q -r "$IOS_APP_DIR/Resources.zip" .
cd "$IOS_APP_DIR"
ZIP_SIZE=$(du -sh Resources.zip | cut -f1)
ok "Resources.zip rebuilt ($ZIP_SIZE)"

# Step 5: Build
if $IS_DEVICE; then
    step "Building for device (this may take a minute)..."
    xcodebuild -project iosApp.xcodeproj -scheme iosApp \
        -sdk iphoneos -configuration Debug \
        -destination 'generic/platform=iOS' \
        -allowProvisioningUpdates \
        -quiet build 2>&1 | tail -5
else
    step "Building for simulator (this may take a minute)..."
    xcodebuild -project iosApp.xcodeproj -scheme iosApp \
        -sdk iphonesimulator \
        -destination "platform=iOS Simulator,name=$SIMULATOR_NAME" \
        -configuration Debug \
        -quiet build 2>&1 | tail -5
fi

if [ ${PIPESTATUS[0]} -ne 0 ]; then
    fail "Build failed! Run without -quiet for details."
fi
ok "Build succeeded"

# Step 6: Find the built app
if $IS_DEVICE; then
    APP_PATH=$(find ~/Library/Developer/Xcode/DerivedData/iosApp-* \
        -name "iosApp.app" -path "*Debug-iphoneos*" -not -path "*/Index.noindex/*" -type d 2>/dev/null | head -1)
else
    APP_PATH=$(find ~/Library/Developer/Xcode/DerivedData/iosApp-* \
        -name "iosApp.app" -path "*Debug-iphonesimulator*" -not -path "*/Index.noindex/*" -type d 2>/dev/null | head -1)
fi

if [ -z "$APP_PATH" ]; then
    fail "Could not find built iosApp.app in DerivedData"
fi
ok "Built app: $APP_PATH"

# Step 6.1: Verify shared.framework is NOT a static archive in Frameworks/
if [ -f "$APP_PATH/Frameworks/shared.framework/shared" ]; then
    if file "$APP_PATH/Frameworks/shared.framework/shared" | grep -q "ar archive"; then
        warn "FATAL: Static shared.framework found in Frameworks/ — iOS will reject install"
        warn "Removing it (linker already linked it via FRAMEWORK_SEARCH_PATHS)"
        rm -rf "$APP_PATH/Frameworks/shared.framework"
        ok "Removed static shared.framework from Frameworks/"
    fi
fi

# Step 7: Terminate old app
step "Terminating old app..."
if $IS_DEVICE; then
    xcrun devicectl device process terminate -d "$DEVICE_UUID" ai.ciris.mobile 2>/dev/null || true
else
    xcrun simctl terminate booted ai.ciris.mobile 2>/dev/null || true
    sleep 1
    APP_DATA_DIR=$(xcrun simctl get_app_container booted ai.ciris.mobile data 2>/dev/null || true)
    if [ -n "$APP_DATA_DIR" ] && [ -d "$APP_DATA_DIR/Documents/PythonResources" ]; then
        rm -rf "$APP_DATA_DIR/Documents/PythonResources"
        ok "Cleared cached PythonResources"
    fi
fi
ok "Old app terminated"

# Step 8: Install and launch
step "Installing and launching..."
if $IS_DEVICE; then
    xcrun devicectl device uninstall app -d "$DEVICE_UUID" ai.ciris.mobile 2>/dev/null || true
    sleep 1
    xcrun devicectl device install app -d "$DEVICE_UUID" "$APP_PATH" 2>&1 | tail -3
    ok "App installed"
    sleep 1
    xcrun devicectl device process launch -d "$DEVICE_UUID" ai.ciris.mobile 2>&1 | tail -2
    ok "App launched"
else
    xcrun simctl install booted "$APP_PATH"
    ok "App installed"
    APP_DATA_DIR=$(xcrun simctl get_app_container booted ai.ciris.mobile data 2>/dev/null || true)
    if [ -n "$APP_DATA_DIR" ] && [ -d "$APP_DATA_DIR/Documents/PythonResources" ]; then
        rm -rf "$APP_DATA_DIR/Documents/PythonResources"
        ok "Cleared cached PythonResources post-install"
    fi
    xcrun simctl launch booted ai.ciris.mobile
    ok "App launched"
fi

echo ""
echo -e "${GREEN}================================================${NC}"
echo -e "${GREEN}  Deploy Complete!${NC}"
echo -e "${GREEN}================================================${NC}"
echo ""
echo "  Wait ~15-20s for Python runtime to initialize"
echo "  Then check: curl http://localhost:8080/v1/system/health"
echo ""
echo "  Quick commands:"
echo "    # Pull logs"
echo "    python3 -m tools.qa_runner.modules.mobile pull-logs --platform ios"
echo ""
echo "    # Run E2E licensed agent test"
echo "    python3 -m tools.qa_runner.modules.mobile licensed-agent --wait --llm-provider openai --llm-key-file ~/.openai_key"
echo ""
