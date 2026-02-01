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

# For App Store (Release) or any Device build, skip individual .framework bundles
# But we MUST copy lib-dynload to the app bundle where it will be code-signed
# Use PLATFORM_NAME which is more reliable than SDKROOT for device detection
if [ "$CONFIGURATION" = "Release" ] || [ "$PLATFORM_NAME" = "iphoneos" ] || [[ "$SDKROOT" == *"iphoneos"* ]]; then
    echo "Release/Device build - NOT embedding separate Python extension frameworks"
    echo "PLATFORM_NAME=$PLATFORM_NAME, SDKROOT=$SDKROOT, CONFIGURATION=$CONFIGURATION"

    # Only ensure shared.framework is properly set up (handled by Link KMP Shared Framework script)
    if [ -d "$FRAMEWORKS_DST/shared.framework" ]; then
        echo "shared.framework already embedded by Link KMP Shared Framework script"
        codesign --force --sign "$EXPANDED_CODE_SIGN_IDENTITY" --timestamp=none "$FRAMEWORKS_DST/shared.framework" 2>/dev/null || true
    fi

    # CRITICAL: For App Store, convert lib-dynload .so files to .framework bundles
    # Apple App Store rejects standalone .so files - they MUST be in framework format.
    # The .fwork redirect files in lib-dynload point to Frameworks/<module>.framework/<module>
    PYTHON_XCFRAMEWORK="${PROJECT_DIR}/Frameworks/Python.xcframework/ios-arm64"
    LIB_DYNLOAD_SRC="${PYTHON_XCFRAMEWORK}/lib/python3.10/lib-dynload"

    if [ -d "$LIB_DYNLOAD_SRC" ]; then
        echo "Converting lib-dynload .so files to frameworks for App Store..."

        # Count source files
        so_count=$(ls -1 "$LIB_DYNLOAD_SRC"/*.so 2>/dev/null | wc -l | tr -d ' ')
        echo "Found $so_count .so files to convert"

        # Create dylib-Info-template.plist if it doesn't exist
        DYLIB_PLIST="${BUILT_PRODUCTS_DIR}/${UNLOCALIZED_RESOURCES_FOLDER_PATH}/dylib-Info-template.plist"
        if [ ! -f "$DYLIB_PLIST" ]; then
            mkdir -p "$(dirname "$DYLIB_PLIST")"
            cat > "$DYLIB_PLIST" << 'PLIST_EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>en</string>
    <key>CFBundleExecutable</key>
    <string>EXECUTABLE_NAME</string>
    <key>CFBundleIdentifier</key>
    <string>BUNDLE_IDENTIFIER</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundlePackageType</key>
    <string>FMWK</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>MinimumOSVersion</key>
    <string>15.0</string>
</dict>
</plist>
PLIST_EOF
        fi

        # Convert each .so to a .framework
        for so_file in "$LIB_DYNLOAD_SRC"/*.so; do
            if [ -f "$so_file" ]; then
                # Get module name: _hashlib.cpython-310-iphoneos.so -> _hashlib
                so_basename=$(basename "$so_file")
                FRAMEWORK_NAME="${so_basename%.cpython-*}"
                FRAMEWORK_NAME="${FRAMEWORK_NAME%.so}"
                FRAMEWORK_DIR="$FRAMEWORKS_DST/${FRAMEWORK_NAME}.framework"
                BUNDLE_ID=$(echo "${PRODUCT_BUNDLE_IDENTIFIER}.stdlib.${FRAMEWORK_NAME}" | tr '_' '-')

                # Create framework structure
                mkdir -p "$FRAMEWORK_DIR"

                # Copy Info.plist and customize
                cp "$DYLIB_PLIST" "$FRAMEWORK_DIR/Info.plist"
                plutil -replace CFBundleExecutable -string "$FRAMEWORK_NAME" "$FRAMEWORK_DIR/Info.plist"
                plutil -replace CFBundleIdentifier -string "$BUNDLE_ID" "$FRAMEWORK_DIR/Info.plist"

                # Copy the binary as the framework executable
                cp "$so_file" "$FRAMEWORK_DIR/$FRAMEWORK_NAME"

                # Code sign the framework
                codesign --force --sign "$EXPANDED_CODE_SIGN_IDENTITY" \
                    ${OTHER_CODE_SIGN_FLAGS:-} \
                    -o runtime --timestamp=none \
                    --preserve-metadata=identifier,entitlements,flags \
                    --generate-entitlement-der \
                    "$FRAMEWORK_DIR" 2>/dev/null || true
            fi
        done

        # Count frameworks created
        stdlib_count=$(ls -1d "$FRAMEWORKS_DST"/*.framework 2>/dev/null | wc -l | tr -d ' ')
        echo "Created/updated stdlib frameworks (total frameworks: $stdlib_count)"
    else
        echo "WARNING: lib-dynload not found at $LIB_DYNLOAD_SRC"
    fi

    # CRITICAL: Add privacy manifests to OpenSSL-using frameworks
    # Apple requires PrivacyInfo.xcprivacy for any SDK using OpenSSL/BoringSSL
    PRIVACY_MANIFEST="${PROJECT_DIR}/PrivacyInfo.xcprivacy"
    if [ -f "$PRIVACY_MANIFEST" ]; then
        echo ""
        echo "Adding privacy manifests to OpenSSL-using frameworks..."
        OPENSSL_FRAMEWORKS=(
            "_hashlib"
            "_ssl"
            "cryptography.hazmat.bindings._openssl"
        )
        for fw_name in "${OPENSSL_FRAMEWORKS[@]}"; do
            fw_path="$FRAMEWORKS_DST/${fw_name}.framework"
            if [ -d "$fw_path" ]; then
                cp "$PRIVACY_MANIFEST" "$fw_path/PrivacyInfo.xcprivacy"
                echo "  Added PrivacyInfo.xcprivacy to ${fw_name}.framework"
            fi
        done
    else
        echo "WARNING: PrivacyInfo.xcprivacy not found at $PRIVACY_MANIFEST"
    fi

    # CRITICAL: Create .framework bundles for third-party native extensions
    # Python on iOS uses .fwork files to locate binaries in Frameworks/
    # The .fwork files point to Frameworks/<module>.framework/<module>
    APP_PACKAGES_NATIVE="${PROJECT_DIR}/app_packages_native"
    FRAMEWORKS_DST="${BUILT_PRODUCTS_DIR}/${FRAMEWORKS_FOLDER_PATH}"

    if [ -d "$APP_PACKAGES_NATIVE" ]; then
        echo ""
        echo "Creating .framework bundles for app_packages native modules..."
        mkdir -p "$FRAMEWORKS_DST"

        # Create dylib-Info-template.plist if it doesn't exist
        DYLIB_PLIST="${BUILT_PRODUCTS_DIR}/${UNLOCALIZED_RESOURCES_FOLDER_PATH}/dylib-Info-template.plist"
        if [ ! -f "$DYLIB_PLIST" ]; then
            mkdir -p "$(dirname "$DYLIB_PLIST")"
            cat > "$DYLIB_PLIST" << 'PLIST_EOF'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key>
    <string>en</string>
    <key>CFBundleExecutable</key>
    <string>EXECUTABLE_NAME</string>
    <key>CFBundleIdentifier</key>
    <string>BUNDLE_IDENTIFIER</string>
    <key>CFBundleInfoDictionaryVersion</key>
    <string>6.0</string>
    <key>CFBundlePackageType</key>
    <string>FMWK</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>MinimumOSVersion</key>
    <string>13.0</string>
</dict>
</plist>
PLIST_EOF
        fi

        # Function to create a framework from an .so file
        create_framework() {
            local SO_FILE="$1"
            local REL_PATH="$2"

            # Create framework name - strip ALL suffixes
            # E.g., "pydantic_core/_pydantic_core.cpython-310-iphoneos.so" -> "pydantic_core._pydantic_core"
            # E.g., "cryptography/hazmat/bindings/_openssl.abi3.so" -> "cryptography.hazmat.bindings._openssl"
            local MODULE_PATH="$REL_PATH"
            MODULE_PATH="${MODULE_PATH%.cpython-*}"    # Remove .cpython-310-iphoneos.so
            MODULE_PATH="${MODULE_PATH%.abi3.so}"      # Remove .abi3.so
            MODULE_PATH="${MODULE_PATH%.so}"           # Remove plain .so if any left
            local FRAMEWORK_NAME=$(echo "$MODULE_PATH" | tr '/' '.')
            local FRAMEWORK_DIR="$FRAMEWORKS_DST/${FRAMEWORK_NAME}.framework"
            local BUNDLE_ID=$(echo "${PRODUCT_BUNDLE_IDENTIFIER}.${FRAMEWORK_NAME}" | tr '_' '-')

            # Create framework structure
            mkdir -p "$FRAMEWORK_DIR"

            # Copy Info.plist and customize
            cp "$DYLIB_PLIST" "$FRAMEWORK_DIR/Info.plist"
            plutil -replace CFBundleExecutable -string "$FRAMEWORK_NAME" "$FRAMEWORK_DIR/Info.plist"
            plutil -replace CFBundleIdentifier -string "$BUNDLE_ID" "$FRAMEWORK_DIR/Info.plist"

            # Copy the binary
            cp "$SO_FILE" "$FRAMEWORK_DIR/$FRAMEWORK_NAME"

            # Code sign the framework
            codesign --force --sign "$EXPANDED_CODE_SIGN_IDENTITY" \
                ${OTHER_CODE_SIGN_FLAGS:-} \
                -o runtime --timestamp=none \
                --preserve-metadata=identifier,entitlements,flags \
                --generate-entitlement-der \
                "$FRAMEWORK_DIR" 2>/dev/null || true

            echo "  Created: ${FRAMEWORK_NAME}.framework"
        }

        # Find all .so files and create frameworks
        FRAMEWORK_COUNT=0
        find "$APP_PACKAGES_NATIVE" -name "*.so" -type f | while read so_file; do
            # Get relative path
            rel_path="${so_file#$APP_PACKAGES_NATIVE/}"
            create_framework "$so_file" "$rel_path"
            FRAMEWORK_COUNT=$((FRAMEWORK_COUNT + 1))
        done

        # Count frameworks created
        ACTUAL_COUNT=$(find "$FRAMEWORKS_DST" -maxdepth 1 -name "*.framework" -type d | wc -l | tr -d ' ')
        echo "Created $ACTUAL_COUNT app_packages native frameworks"
    else
        echo "No app_packages_native directory found (skipping)"
    fi

    echo ""
    echo "Device build setup complete"
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
