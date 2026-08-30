#!/bin/bash
# Strip x86_64 (simulator) architecture from all Python frameworks
# Required for App Store submission - only arm64 (device) is allowed

set -e

FRAMEWORKS_DIR="${1:-$(dirname "$0")/../Frameworks}"

echo "Stripping x86_64 from frameworks in: $FRAMEWORKS_DIR"

count=0
for framework in "$FRAMEWORKS_DIR"/*.framework; do
    if [ -d "$framework" ]; then
        name=$(basename "$framework" .framework)
        binary="$framework/$name"

        if [ -f "$binary" ]; then
            # Check if it's a fat binary with x86_64
            if lipo -info "$binary" 2>/dev/null | grep -q "x86_64"; then
                echo "Stripping x86_64 from: $name"

                # Create arm64-only version
                lipo -extract arm64 "$binary" -output "${binary}.arm64" 2>/dev/null || {
                    # If extract fails, try thin instead
                    lipo -thin arm64 "$binary" -output "${binary}.arm64"
                }

                # Replace original with arm64-only
                mv "${binary}.arm64" "$binary"
                count=$((count + 1))
            fi
        fi
    fi
done

echo "Stripped x86_64 from $count frameworks"

# Also process Python.xcframework if present
PYTHON_XCF="$FRAMEWORKS_DIR/Python.xcframework"
if [ -d "$PYTHON_XCF" ]; then
    echo "Checking Python.xcframework..."

    # For device builds, we only need the ios-arm64 slice
    # The simulator slices (ios-arm64_x86_64-simulator) should not be included

    # Check if there's a device slice
    if [ -d "$PYTHON_XCF/ios-arm64" ]; then
        echo "Python.xcframework has ios-arm64 device slice - OK"
    else
        echo "WARNING: Python.xcframework missing ios-arm64 slice!"
    fi
fi

echo "Done!"
