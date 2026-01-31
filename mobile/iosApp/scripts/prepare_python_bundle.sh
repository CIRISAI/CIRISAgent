#!/bin/bash
# Prepare Python bundle for KMP iOS app
# This script copies the Python stdlib, CIRIS source, and packages from the BeeWare build
# EXCLUDES web GUI static files (Next.js) which are not needed for mobile
#
# Usage: ./prepare_python_bundle.sh [device|simulator]
# Default: simulator

set -e

BUILD_TYPE="${1:-simulator}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IOS_APP_DIR="$(dirname "$SCRIPT_DIR")"
CIRIS_ROOT="$(dirname "$(dirname "$IOS_APP_DIR")")"

# Source directories from BeeWare build
BEEWARE_APP="/Users/macmini/CIRISAgent/ios/CirisiOS/build/ciris_ios/ios/xcode/build/Debug-iphonesimulator/Ciris iOS.app"
PYTHON_XCF="/Users/macmini/CIRISAgent/ios/CirisiOS/build/ciris_ios/ios/xcode/Support/Python.xcframework"

# Target directory in iosApp
RESOURCES_DIR="$IOS_APP_DIR/Resources"

echo "=== Preparing Python Bundle for KMP iOS ($BUILD_TYPE) ==="
echo "Source: $BEEWARE_APP"
echo "Target: $RESOURCES_DIR"

# Check if BeeWare build exists
if [ ! -d "$BEEWARE_APP" ]; then
    echo "Error: BeeWare app not found at $BEEWARE_APP"
    echo "Please run 'cd $CIRIS_ROOT/ios && briefcase build iOS' first"
    exit 1
fi

# Create Resources directory
mkdir -p "$RESOURCES_DIR"

# Copy Python stdlib
echo "Copying Python stdlib..."
rm -rf "$RESOURCES_DIR/python"
cp -R "$BEEWARE_APP/python" "$RESOURCES_DIR/"

# For device builds, replace lib-dynload with device-specific .so files
if [ "$BUILD_TYPE" = "device" ]; then
    echo "Device build: Using device-specific lib-dynload..."
    DEVICE_DYNLOAD="$PYTHON_XCF/ios-arm64/lib/python3.10/lib-dynload"

    if [ -d "$DEVICE_DYNLOAD" ]; then
        # Remove simulator .fwork stubs
        rm -rf "$RESOURCES_DIR/python/lib/python3.10/lib-dynload"
        mkdir -p "$RESOURCES_DIR/python/lib/python3.10/lib-dynload"

        # Copy device .so files (these have proper encryption info for App Store)
        for so_file in "$DEVICE_DYNLOAD"/*.so; do
            if [ -f "$so_file" ]; then
                # Rename from -iphoneos.so to match what Python expects
                base=$(basename "$so_file")
                # Python on iOS looks for .cpython-310.so or the platform-specific name
                cp "$so_file" "$RESOURCES_DIR/python/lib/python3.10/lib-dynload/"
            fi
        done
        echo "  Copied $(ls "$RESOURCES_DIR/python/lib/python3.10/lib-dynload/" | wc -l | tr -d ' ') device extensions"
    else
        echo "WARNING: Device lib-dynload not found at $DEVICE_DYNLOAD"
    fi
fi

# Copy app code (CIRIS source) - EXCLUDING gui_static directories
echo "Copying CIRIS source code (excluding web GUI)..."
rm -rf "$RESOURCES_DIR/app"
mkdir -p "$RESOURCES_DIR/app"

# Copy each directory, excluding gui_static
for dir in "$BEEWARE_APP/app/"*; do
    dirname=$(basename "$dir")

    # Skip ios_gui_static entirely - it's the Next.js web GUI
    if [ "$dirname" = "ios_gui_static" ]; then
        echo "  Skipping ios_gui_static (Next.js web GUI - not needed for mobile)"
        continue
    fi

    if [ -d "$dir" ]; then
        echo "  Copying $dirname..."
        # Use rsync to exclude gui_static subdirectories
        rsync -a --exclude='gui_static' --exclude='__pycache__' "$dir" "$RESOURCES_DIR/app/"
    else
        cp "$dir" "$RESOURCES_DIR/app/"
    fi
done

# Copy app_packages (third-party packages)
echo "Copying third-party packages..."
rm -rf "$RESOURCES_DIR/app_packages"

if [ "$BUILD_TYPE" = "device" ]; then
    # For device, use device-specific packages if available
    DEVICE_PACKAGES="$BEEWARE_APP/../../../CirisiOS/app_packages.iphoneos"
    if [ -d "$DEVICE_PACKAGES" ]; then
        cp -R "$DEVICE_PACKAGES" "$RESOURCES_DIR/app_packages"
        echo "  Using device-specific app_packages"
    else
        cp -R "$BEEWARE_APP/app_packages" "$RESOURCES_DIR/"
    fi
else
    cp -R "$BEEWARE_APP/app_packages" "$RESOURCES_DIR/"
fi

# Overlay latest CIRIS source from main repo (includes any fixes not in BeeWare build)
echo "Overlaying latest ciris_engine from main repo..."
rsync -a --exclude='__pycache__' --exclude='gui_static' "$CIRIS_ROOT/ciris_engine/" "$RESOURCES_DIR/app/ciris_engine/"

echo "Overlaying latest ciris_adapters from main repo..."
rsync -a --exclude='__pycache__' "$CIRIS_ROOT/ciris_adapters/" "$RESOURCES_DIR/app/ciris_adapters/"

# Remove any __pycache__ directories
echo "Cleaning up __pycache__ directories..."
find "$RESOURCES_DIR" -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

# For simulator builds, copy Python native module frameworks
if [ "$BUILD_TYPE" = "simulator" ]; then
    FRAMEWORKS_DIR="$IOS_APP_DIR/Frameworks"
    echo ""
    echo "Copying Python native module frameworks (simulator)..."
    mkdir -p "$FRAMEWORKS_DIR"

    # Copy all native extension frameworks from BeeWare build
    NATIVE_MODULES_COUNT=0
    for framework in "$BEEWARE_APP/Frameworks/"*.framework; do
        if [ -d "$framework" ]; then
            framework_name=$(basename "$framework")
            # Skip Python.framework - we handle that separately
            if [ "$framework_name" != "Python.framework" ]; then
                cp -R "$framework" "$FRAMEWORKS_DIR/"
                NATIVE_MODULES_COUNT=$((NATIVE_MODULES_COUNT + 1))
            fi
        fi
    done
    echo "  Copied $NATIVE_MODULES_COUNT native module frameworks"
else
    echo ""
    echo "Device build: NOT copying separate Python extension frameworks"
    echo "Extensions are loaded from Python.xcframework"
fi

# Also copy Python.xcframework if it exists and isn't already there
FRAMEWORKS_DIR="$IOS_APP_DIR/Frameworks"
if [ ! -d "$FRAMEWORKS_DIR/Python.xcframework" ]; then
    if [ -d "$PYTHON_XCF" ]; then
        echo "Copying Python.xcframework..."
        mkdir -p "$FRAMEWORKS_DIR"
        cp -R "$PYTHON_XCF" "$FRAMEWORKS_DIR/"
    fi
fi

# Calculate sizes
PYTHON_SIZE=$(du -sh "$RESOURCES_DIR/python" 2>/dev/null | cut -f1)
APP_SIZE=$(du -sh "$RESOURCES_DIR/app" 2>/dev/null | cut -f1)
PACKAGES_SIZE=$(du -sh "$RESOURCES_DIR/app_packages" 2>/dev/null | cut -f1)
TOTAL_SIZE=$(du -sh "$RESOURCES_DIR" 2>/dev/null | cut -f1)

echo ""
echo "=== Bundle Complete ($BUILD_TYPE) ==="
echo "Python stdlib: $PYTHON_SIZE"
echo "CIRIS source:  $APP_SIZE"
echo "Packages:      $PACKAGES_SIZE"
echo "TOTAL:         $TOTAL_SIZE"
echo ""
echo "Resources prepared at: $RESOURCES_DIR"
echo ""
echo "Next steps:"
echo "  1. Regenerate Resources.zip: cd Resources && zip -q -r ../Resources.zip . && cd .."
echo "  2. Regenerate Xcode project: xcodegen generate"
echo "  3. Build: xcodebuild ..."
