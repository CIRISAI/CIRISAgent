#!/bin/bash
# Embed and code-sign Python native module frameworks
# This script copies all .framework directories from the project's Frameworks directory
# into the app bundle and code-signs them
#
# For Release builds, also strips x86_64 (simulator) architecture for App Store

set -e

# Only process if frameworks exist
FRAMEWORKS_SRC="${PROJECT_DIR}/Frameworks"
FRAMEWORKS_DST="${BUILT_PRODUCTS_DIR}/${FRAMEWORKS_FOLDER_PATH}"

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
