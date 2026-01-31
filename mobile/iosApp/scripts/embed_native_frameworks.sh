#!/bin/bash
# Embed and code-sign Python native module frameworks
# This script copies all .framework directories from the project's Frameworks directory
# into the app bundle, fixes their Info.plist for App Store compliance, and code-signs them
#
# Fixes applied:
# - CFBundlePackageType: APPL -> FMWK (framework, not application)
# - MinimumOSVersion: matches app's deployment target
# - Strips x86_64 simulator architecture for Release builds

set -e

# Only process if frameworks exist
FRAMEWORKS_SRC="${PROJECT_DIR}/Frameworks"
FRAMEWORKS_DST="${BUILT_PRODUCTS_DIR}/${FRAMEWORKS_FOLDER_PATH}"
MIN_IOS_VERSION="15.0"

if [ ! -d "$FRAMEWORKS_SRC" ]; then
    echo "No Frameworks directory found at $FRAMEWORKS_SRC"
    exit 0
fi

echo "Copying native Python frameworks to $FRAMEWORKS_DST..."
mkdir -p "$FRAMEWORKS_DST"

# Copy each framework (except Python.xcframework which is handled by Xcode)
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

echo "Copied $count native module frameworks"

# Fix Info.plist in each framework for App Store compliance
echo "Fixing framework Info.plist files for App Store..."
fixed=0
for framework in "$FRAMEWORKS_DST"/*.framework; do
    if [ -d "$framework" ]; then
        plist="$framework/Info.plist"
        if [ -f "$plist" ]; then
            # Fix CFBundlePackageType: APPL -> FMWK
            /usr/libexec/PlistBuddy -c "Set :CFBundlePackageType FMWK" "$plist" 2>/dev/null || true

            # Fix MinimumOSVersion to match app
            /usr/libexec/PlistBuddy -c "Set :MinimumOSVersion $MIN_IOS_VERSION" "$plist" 2>/dev/null || \
                /usr/libexec/PlistBuddy -c "Add :MinimumOSVersion string $MIN_IOS_VERSION" "$plist" 2>/dev/null || true

            # Add CFBundleSupportedPlatforms if missing
            /usr/libexec/PlistBuddy -c "Set :CFBundleSupportedPlatforms:0 iPhoneOS" "$plist" 2>/dev/null || true

            fixed=$((fixed + 1))
        fi
    fi
done
echo "Fixed Info.plist in $fixed frameworks"

# For Release builds targeting device, strip x86_64 (simulator) architecture
if [ "$CONFIGURATION" = "Release" ] || [[ "$SDKROOT" == *"iphoneos"* ]]; then
    echo "Release/Device build - stripping x86_64 from frameworks..."
    stripped=0
    for framework in "$FRAMEWORKS_DST"/*.framework; do
        if [ -d "$framework" ]; then
            fname=$(basename "$framework" .framework)
            binary="$framework/$fname"

            if [ -f "$binary" ]; then
                # Check if it's a fat binary with x86_64
                if lipo -info "$binary" 2>/dev/null | grep -q "x86_64"; then
                    echo "  Stripping x86_64: $fname"

                    # Extract arm64 only
                    lipo -extract arm64 "$binary" -output "${binary}.arm64" 2>/dev/null || \
                        lipo -thin arm64 "$binary" -output "${binary}.arm64" 2>/dev/null || {
                            echo "  Warning: Could not strip $fname"
                            continue
                        }

                    mv "${binary}.arm64" "$binary"
                    stripped=$((stripped + 1))
                fi
            fi
        fi
    done
    echo "Stripped x86_64 from $stripped frameworks"
fi

# Code sign all frameworks
if [ "$count" -gt 0 ]; then
    echo "Code signing native frameworks..."
    for framework in "$FRAMEWORKS_DST"/*.framework; do
        if [ -d "$framework" ]; then
            codesign --force --sign "$EXPANDED_CODE_SIGN_IDENTITY" --timestamp=none "$framework" 2>/dev/null || true
        fi
    done
    echo "Code signing complete"
fi
