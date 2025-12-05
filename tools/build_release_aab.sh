#!/bin/bash
# Build Release AAB for Google Play Store
# This script produces a signed AAB bundle with arm64-v8a support

set -e  # Exit on any error

# Configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
ANDROID_DIR="$PROJECT_ROOT/android"
OUTPUT_DIR="$ANDROID_DIR/app/build/outputs/bundle/release"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  CIRIS Mobile Release AAB Builder${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Step 1: Check prerequisites
echo -e "${YELLOW}[1/6] Checking prerequisites...${NC}"

# Check if we're in the right directory
if [ ! -f "$ANDROID_DIR/build.gradle" ]; then
    echo -e "${RED}ERROR: Cannot find android/build.gradle${NC}"
    echo "Please run this script from the CIRISAgent root directory"
    exit 1
fi

# Check for keystore (matches gradle signingConfigs.release.storeFile)
KEYSTORE_PATH="/home/emoore/ciris-release-key.jks"
if [ ! -f "$KEYSTORE_PATH" ]; then
    echo -e "${RED}ERROR: Release keystore not found at $KEYSTORE_PATH${NC}"
    echo ""
    echo "To create a keystore, run:"
    echo "  keytool -genkey -v -keystore $KEYSTORE_PATH \\"
    echo "    -keyalg RSA -keysize 2048 -validity 10000 \\"
    echo "    -alias ciris-release-key"
    exit 1
fi

# Set Java 17 (required for Android build)
if [ -d "/usr/lib/jvm/java-17-openjdk-amd64" ]; then
    export JAVA_HOME="/usr/lib/jvm/java-17-openjdk-amd64"
    echo -e "${GREEN}  ✓ Using Java 17: $JAVA_HOME${NC}"
else
    echo -e "${RED}ERROR: Java 17 not found at /usr/lib/jvm/java-17-openjdk-amd64${NC}"
    exit 1
fi

echo -e "${GREEN}  ✓ Prerequisites OK${NC}"

# Step 2: Update static GUI assets
echo ""
echo -e "${YELLOW}[2/6] Updating static GUI assets...${NC}"
if [ -d "$PROJECT_ROOT/android_gui_static" ]; then
    # Copy static files to Android assets
    rm -rf "$ANDROID_DIR/app/src/main/assets/public"
    cp -r "$PROJECT_ROOT/android_gui_static" "$ANDROID_DIR/app/src/main/assets/public"
    echo -e "${GREEN}  ✓ Static GUI assets updated${NC}"
else
    echo -e "${YELLOW}  ⚠ android_gui_static not found, skipping${NC}"
fi

# Step 3: Clean previous builds
echo ""
echo -e "${YELLOW}[3/6] Cleaning previous builds...${NC}"
cd "$ANDROID_DIR"
./gradlew clean --quiet
echo -e "${GREEN}  ✓ Clean complete${NC}"

# Step 4: Build the release AAB
echo ""
echo -e "${YELLOW}[4/6] Building release AAB (this may take a few minutes)...${NC}"
echo "  Building for architectures: arm64-v8a, armeabi-v7a, x86_64"

# Build release bundle (signing config in build.gradle)
./gradlew bundleRelease --warning-mode=none

if [ ! -f "$OUTPUT_DIR/app-release.aab" ]; then
    echo -e "${RED}ERROR: AAB build failed - output file not found${NC}"
    exit 1
fi

echo -e "${GREEN}  ✓ AAB build complete${NC}"

# Step 5: Verify the AAB
echo ""
echo -e "${YELLOW}[5/6] Verifying AAB...${NC}"

AAB_FILE="$OUTPUT_DIR/app-release.aab"
AAB_SIZE=$(du -h "$AAB_FILE" | cut -f1)

echo "  AAB file: $AAB_FILE"
echo "  Size: $AAB_SIZE"

# Check AAB contents
if command -v bundletool &> /dev/null; then
    echo "  Architectures included:"
    bundletool dump manifest --bundle="$AAB_FILE" 2>/dev/null | grep -i "native" || true
else
    echo -e "${YELLOW}  ⚠ bundletool not installed - skipping detailed verification${NC}"
    echo "  Install with: brew install bundletool (macOS) or download from GitHub"
fi

echo -e "${GREEN}  ✓ Verification complete${NC}"

# Step 6: Copy to project root with version
echo ""
echo -e "${YELLOW}[6/6] Finalizing...${NC}"

# Get version from build.gradle
VERSION_NAME=$(grep "versionName" "$ANDROID_DIR/app/build.gradle" | head -1 | sed 's/.*"\(.*\)".*/\1/')
VERSION_CODE=$(grep "versionCode" "$ANDROID_DIR/app/build.gradle" | head -1 | sed 's/[^0-9]*//g')

FINAL_AAB="$PROJECT_ROOT/ciris-mobile-v${VERSION_NAME}.aab"
cp "$AAB_FILE" "$FINAL_AAB"

echo -e "${GREEN}  ✓ Final AAB: $FINAL_AAB${NC}"

# Summary
echo ""
echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}  BUILD SUCCESSFUL!${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""
echo "  Version: $VERSION_NAME (code: $VERSION_CODE)"
echo "  Output:  $FINAL_AAB"
echo "  Size:    $AAB_SIZE"
echo ""
echo "Next steps:"
echo "  1. Test locally with bundletool:"
echo "     bundletool build-apks --bundle=$FINAL_AAB --output=test.apks"
echo ""
echo "  2. Upload to Google Play Console:"
echo "     https://play.google.com/console"
echo ""
