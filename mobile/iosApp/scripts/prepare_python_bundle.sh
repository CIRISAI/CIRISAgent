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

    # Copy device-specific sysconfigdata (required for sysconfig/distutils)
    DEVICE_SYSCONFIG="$PYTHON_XCF/ios-arm64/lib/python3.10/_sysconfigdata__ios_arm64-iphoneos.py"
    if [ -f "$DEVICE_SYSCONFIG" ]; then
        echo "Device build: Copying device sysconfigdata..."
        cp "$DEVICE_SYSCONFIG" "$RESOURCES_DIR/python/lib/python3.10/"
        echo "  Copied _sysconfigdata__ios_arm64-iphoneos.py"
    else
        echo "WARNING: Device sysconfigdata not found at $DEVICE_SYSCONFIG"
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

# Directory to store .so files for framework embedding (device builds only)
NATIVE_MODULES_DIR="$IOS_APP_DIR/app_packages_native"
rm -rf "$NATIVE_MODULES_DIR"

if [ "$BUILD_TYPE" = "device" ]; then
    # For device, use device-specific packages and replace .so with .fwork
    DEVICE_PACKAGES="$BEEWARE_APP/../../../CirisiOS/app_packages.iphoneos"
    if [ -d "$DEVICE_PACKAGES" ]; then
        echo "  Processing device-specific app_packages..."
        mkdir -p "$NATIVE_MODULES_DIR"

        # Copy packages, but replace .so files with .fwork placeholders
        cp -R "$DEVICE_PACKAGES" "$RESOURCES_DIR/app_packages"

        # Find all .so files and convert to .fwork
        SO_COUNT=0
        find "$RESOURCES_DIR/app_packages" -name "*.so" -type f | while read so_file; do
            # Get the relative path from app_packages
            rel_path="${so_file#$RESOURCES_DIR/app_packages/}"

            # Create the framework name
            # Remove ALL suffixes: .cpython-310-iphoneos.so, .abi3.so, etc.
            # E.g., "pydantic_core/_pydantic_core.cpython-310-iphoneos.so" -> "pydantic_core/_pydantic_core"
            # E.g., "cryptography/hazmat/bindings/_openssl.abi3.so" -> "cryptography/hazmat/bindings/_openssl"
            module_path="$rel_path"
            module_path="${module_path%.cpython-*}"    # Remove .cpython-310-iphoneos.so
            module_path="${module_path%.abi3.so}"      # Remove .abi3.so
            module_path="${module_path%.so}"           # Remove plain .so if any left
            framework_name=$(echo "$module_path" | tr '/' '.')

            # Create .fwork content pointing to the framework
            fwork_path="${so_file%.so}.fwork"
            echo "Frameworks/${framework_name}.framework/${framework_name}" > "$fwork_path"

            # Copy .so to native modules directory for later framework embedding
            # Preserve directory structure
            so_dest_dir="$NATIVE_MODULES_DIR/$(dirname "$rel_path")"
            mkdir -p "$so_dest_dir"
            cp "$so_file" "$so_dest_dir/"

            # Remove the original .so
            rm "$so_file"

            SO_COUNT=$((SO_COUNT + 1))
        done

        # Count results
        FWORK_COUNT=$(find "$RESOURCES_DIR/app_packages" -name "*.fwork" | wc -l | tr -d ' ')
        echo "  Created $FWORK_COUNT .fwork placeholders"
        echo "  Native modules saved to: $NATIVE_MODULES_DIR"
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

# Overlay ciris_ios from source (includes kmp_main.py which is not in BeeWare build)
echo "Overlaying ciris_ios from source (includes kmp_main.py)..."
rsync -a --exclude='__pycache__' "$CIRIS_ROOT/ios/CirisiOS/src/ciris_ios/" "$RESOURCES_DIR/app/ciris_ios/"

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
