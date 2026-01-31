#!/bin/bash
# Embed and code-sign Python native module frameworks
#
# NOTE: For App Store builds, we do NOT embed individual Python extension frameworks.
# The extensions are already inside Python.xcframework with proper encryption info.
# Embedding separate .framework bundles causes App Store validation failures
# ("binary not built with Apple's linker").
#
# This script only handles the shared.framework (KMP) which IS properly built.

set -e

FRAMEWORKS_SRC="${PROJECT_DIR}/Frameworks"
FRAMEWORKS_DST="${BUILT_PRODUCTS_DIR}/${FRAMEWORKS_FOLDER_PATH}"

echo "Embed Native Frameworks script running..."
echo "Configuration: $CONFIGURATION"
echo "SDK: $SDKROOT"

# For App Store (Release) or any Device build, skip Python extension frameworks entirely
# They're already in Python.xcframework with proper encryption info
# Use PLATFORM_NAME which is more reliable than SDKROOT for device detection
if [ "$CONFIGURATION" = "Release" ] || [ "$PLATFORM_NAME" = "iphoneos" ] || [[ "$SDKROOT" == *"iphoneos"* ]]; then
    echo "Release/Device build - NOT embedding separate Python extension frameworks"
    echo "PLATFORM_NAME=$PLATFORM_NAME, SDKROOT=$SDKROOT, CONFIGURATION=$CONFIGURATION"
    echo "Python extensions are loaded from Python.xcframework"

    # Only ensure shared.framework is properly set up (handled by Link KMP Shared Framework script)
    if [ -d "$FRAMEWORKS_DST/shared.framework" ]; then
        echo "shared.framework already embedded by Link KMP Shared Framework script"
        codesign --force --sign "$EXPANDED_CODE_SIGN_IDENTITY" --timestamp=none "$FRAMEWORKS_DST/shared.framework" 2>/dev/null || true
    fi

    echo "Skipping Python extension frameworks for App Store compliance"
    exit 0
fi

# For Debug/Simulator builds, embed frameworks for easier debugging
echo "Debug/Simulator build - embedding Python extension frameworks..."

if [ ! -d "$FRAMEWORKS_SRC" ]; then
    echo "No Frameworks directory found at $FRAMEWORKS_SRC"
    exit 0
fi

mkdir -p "$FRAMEWORKS_DST"

count=0
for framework in "$FRAMEWORKS_SRC"/*.framework; do
    if [ -d "$framework" ]; then
        name=$(basename "$framework")
        # Skip Python.xcframework slices and shared.framework (already handled)
        if [[ "$name" != "Python.framework" && "$name" != "shared.framework" ]]; then
            cp -R "$framework" "$FRAMEWORKS_DST/"
            count=$((count + 1))
        fi
    fi
done

echo "Copied $count native module frameworks for simulator"

# Code sign all frameworks for simulator
if [ "$count" -gt 0 ]; then
    echo "Code signing native frameworks..."
    for framework in "$FRAMEWORKS_DST"/*.framework; do
        if [ -d "$framework" ]; then
            codesign --force --sign - --timestamp=none "$framework" 2>/dev/null || true
        fi
    done
    echo "Code signing complete"
fi
