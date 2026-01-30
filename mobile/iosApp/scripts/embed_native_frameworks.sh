#!/bin/bash
# Embed and code-sign Python native module frameworks
# This script copies all .framework directories from the project's Frameworks directory
# into the app bundle and code-signs them

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
