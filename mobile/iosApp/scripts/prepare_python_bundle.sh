#!/bin/bash
# Prepare Python bundle for KMP iOS app
# This script copies the Python stdlib, CIRIS source, and packages from the BeeWare build

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IOS_APP_DIR="$(dirname "$SCRIPT_DIR")"
CIRIS_ROOT="$(dirname "$(dirname "$IOS_APP_DIR")")"

# Source directory from BeeWare build
BEEWARE_APP="/Users/macmini/CIRISAgent/ios/CirisiOS/build/ciris_ios/ios/xcode/build/Debug-iphonesimulator/Ciris iOS.app"

# Target directory in iosApp
RESOURCES_DIR="$IOS_APP_DIR/Resources"

echo "=== Preparing Python Bundle for KMP iOS ==="
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

# Copy app code (CIRIS source)
echo "Copying CIRIS source code..."
rm -rf "$RESOURCES_DIR/app"
cp -R "$BEEWARE_APP/app" "$RESOURCES_DIR/"

# Copy app_packages (third-party packages)
echo "Copying third-party packages..."
rm -rf "$RESOURCES_DIR/app_packages"
cp -R "$BEEWARE_APP/app_packages" "$RESOURCES_DIR/"

# Calculate sizes
PYTHON_SIZE=$(du -sh "$RESOURCES_DIR/python" 2>/dev/null | cut -f1)
APP_SIZE=$(du -sh "$RESOURCES_DIR/app" 2>/dev/null | cut -f1)
PACKAGES_SIZE=$(du -sh "$RESOURCES_DIR/app_packages" 2>/dev/null | cut -f1)

echo ""
echo "=== Bundle Complete ==="
echo "Python stdlib: $PYTHON_SIZE"
echo "CIRIS source:  $APP_SIZE"
echo "Packages:      $PACKAGES_SIZE"
echo ""
echo "Resources prepared at: $RESOURCES_DIR"
