#!/bin/bash
# Script to cross-compile binary wheels for iOS
# Requirements: macOS with Xcode, Rust, Python 3.10, Briefcase (for Python.xcframework)
# Usage: ./ios/scripts/build_wheels.sh

set -e

# Configuration
PYTHON_VER="3.10"
PYDANTIC_CORE_VER="2.23.4"
TARGET="aarch64-apple-ios"
BASE_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
OUTPUT_DIR="$BASE_DIR/ios/wheels"
PYTHON_FRAMEWORK="$BASE_DIR/ios/CirisiOS/build/ciris_ios/ios/xcode/Support/Python.xcframework/ios-arm64/Python.framework"

mkdir -p "$OUTPUT_DIR"

echo "=== iOS Wheel Builder ==="
echo "Target: $TARGET"
echo "Output: $OUTPUT_DIR"
echo "Python Framework: $PYTHON_FRAMEWORK"

# Check prerequisites
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo "Error: This script must be run on macOS."
    exit 1
fi

if [ ! -d "$PYTHON_FRAMEWORK" ]; then
    echo "Error: Python.xcframework not found. Run 'briefcase create iOS' first."
    echo "Expected at: $PYTHON_FRAMEWORK"
    exit 1
fi

if ! command -v rustup &> /dev/null; then
    echo "Error: Rustup not found. Please install Rust."
    exit 1
fi

if ! command -v maturin &> /dev/null; then
    echo "Installing maturin..."
    pip3.10 install maturin
fi

# Get iOS SDK path
IOS_SDK=$(xcrun --sdk iphoneos --show-sdk-path)
echo "iOS SDK: $IOS_SDK"

# Ensure Rust target is installed
echo "Checking Rust target..."
rustup target add $TARGET

# Set up cross-compilation environment
export SDKROOT="$IOS_SDK"
export CARGO_BUILD_TARGET="$TARGET"

# Create PyO3 cross-compilation config file
PYO3_CONFIG_FILE="$BASE_DIR/ios/pyo3-ios-config.txt"
cat > "$PYO3_CONFIG_FILE" << EOF
implementation=CPython
version=3.10
shared=false
abi3=false
lib_name=Python
lib_dir=$PYTHON_FRAMEWORK
pointer_width=64
build_flags=
suppress_build_script_link_lines=true
ext_suffix=.cpython-310-iphoneos.so
executable=/opt/homebrew/bin/python3.10
EOF

# PyO3 cross-compilation settings
export PYO3_CONFIG_FILE
export PYO3_CROSS=1
export PYO3_CROSS_LIB_DIR="$PYTHON_FRAMEWORK/lib/python3.10"
export PYO3_CROSS_PYTHON_VERSION="$PYTHON_VER"
export PYO3_PYTHON="python3.10"
export _PYTHON_SYSCONFIGDATA_NAME="_sysconfigdata__ios_arm64-iphoneos"

# Compiler flags for iOS
export CC="$(xcrun --sdk iphoneos --find clang)"
export CXX="$(xcrun --sdk iphoneos --find clang++)"
export AR="$(xcrun --sdk iphoneos --find ar)"
export CFLAGS="-target arm64-apple-ios -isysroot $IOS_SDK -miphoneos-version-min=13.0"
export CXXFLAGS="$CFLAGS"
export LDFLAGS="-target arm64-apple-ios -isysroot $IOS_SDK -miphoneos-version-min=13.0 -F$PYTHON_FRAMEWORK/.. -framework Python"

# Cargo config for iOS linking
# -undefined dynamic_lookup allows Python symbols to be resolved at runtime
export CARGO_TARGET_AARCH64_APPLE_IOS_LINKER="$CC"
export CARGO_TARGET_AARCH64_APPLE_IOS_RUSTFLAGS="-C link-arg=-isysroot -C link-arg=$IOS_SDK -C link-arg=-miphoneos-version-min=13.0 -C link-arg=-undefined -C link-arg=dynamic_lookup"

echo ""
echo "=== Environment ==="
echo "SDKROOT=$SDKROOT"
echo "PYO3_CROSS_LIB_DIR=$PYO3_CROSS_LIB_DIR"
echo "CC=$CC"
echo ""

# Build pydantic-core
echo "--- Building pydantic-core $PYDANTIC_CORE_VER ---"
WORK_DIR=$(mktemp -d)
echo "Work dir: $WORK_DIR"

# Clean up on exit
cleanup() {
    echo "Cleaning up..."
    rm -rf "$WORK_DIR"
}
trap cleanup EXIT

cd "$WORK_DIR"
echo "Cloning pydantic-core..."
git clone --depth 1 --branch "v$PYDANTIC_CORE_VER" https://github.com/pydantic/pydantic-core.git .

echo "Building with Maturin for iOS..."
# Build without interpreter detection - we're cross-compiling
maturin build \
    --release \
    --target $TARGET \
    --out "$OUTPUT_DIR" \
    --skip-auditwheel \
    2>&1 || {
        echo ""
        echo "=== Build failed. Trying alternative approach... ==="
        echo ""
        # Try building just the Rust library with cargo
        cargo build --release --target $TARGET --lib
        echo "Cargo build succeeded. Manual wheel packaging may be needed."
        exit 1
    }

echo ""
echo "=== Build Complete ==="
echo "Wheels available in: $OUTPUT_DIR"
ls -l "$OUTPUT_DIR"

# Also build for iOS Simulator (arm64)
echo ""
echo "--- Building pydantic-core for iOS Simulator ---"
SIM_TARGET="aarch64-apple-ios-sim"
rustup target add $SIM_TARGET

SIM_SDK=$(xcrun --sdk iphonesimulator --show-sdk-path)
export SDKROOT="$SIM_SDK"
export CARGO_BUILD_TARGET="$SIM_TARGET"
export CARGO_TARGET_AARCH64_APPLE_IOS_SIM_LINKER="$(xcrun --sdk iphonesimulator --find clang)"
export CARGO_TARGET_AARCH64_APPLE_IOS_SIM_RUSTFLAGS="-C link-arg=-isysroot -C link-arg=$SIM_SDK -C link-arg=-mios-simulator-version-min=13.0 -C link-arg=-undefined -C link-arg=dynamic_lookup"

# Update config for simulator
cat > "$PYO3_CONFIG_FILE" << EOF
implementation=CPython
version=3.10
shared=false
abi3=false
lib_name=Python
lib_dir=$PYTHON_FRAMEWORK
pointer_width=64
build_flags=
suppress_build_script_link_lines=true
ext_suffix=.cpython-310-iphonesimulator.so
executable=/opt/homebrew/bin/python3.10
EOF

WORK_DIR=$(mktemp -d)
cd "$WORK_DIR"
git clone --depth 1 --branch "v$PYDANTIC_CORE_VER" https://github.com/pydantic/pydantic-core.git .

maturin build \
    --release \
    --target $SIM_TARGET \
    --out "$OUTPUT_DIR" \
    --skip-auditwheel

echo "Simulator wheel built!"
rm -rf "$WORK_DIR"
