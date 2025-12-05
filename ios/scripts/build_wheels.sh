#!/bin/bash
# Script to cross-compile binary wheels for iOS
# Requirements: macOS with Xcode, Rust, Python 3.10
# Usage: ./ios/scripts/build_wheels.sh

set -e

# Configuration
PYTHON_VER="3.10"
PYDANTIC_CORE_VER="2.23.4"
TARGET="aarch64-apple-ios"
BASE_DIR="$(pwd)"
OUTPUT_DIR="$BASE_DIR/ios/wheels"

mkdir -p "$OUTPUT_DIR"

echo "=== iOS Wheel Builder ==="
echo "Target: $TARGET"
echo "Output: $OUTPUT_DIR"

# Check prerequisites
if [[ "$OSTYPE" != "darwin"* ]]; then
    echo "Warning: This script is intended to be run on macOS. Cross-compilation from Linux/Windows is experimental."
fi

if ! command -v rustup &> /dev/null; then
    echo "Error: Rustup not found. Please install Rust."
    exit 1
fi

if ! command -v maturin &> /dev/null; then
    echo "Installing maturin..."
    pip install maturin
fi

# Ensure target is installed
echo "Checking Rust target..."
rustup target add $TARGET

# Build pydantic-core
# Note: Pydantic V2 relies on pydantic-core. We build the core wheel, which pydantic will use.
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

echo "Building with Maturin..."
# We use --interpreter to specify the python version for the wheel metadata
# On macOS, this requires the iOS SDKs to be available in the path/SDKs
maturin build --target $TARGET --release --out "$OUTPUT_DIR" --interpreter python$PYTHON_VER

echo "=== Build Complete ==="
echo "Wheels available in: $OUTPUT_DIR"
ls -l "$OUTPUT_DIR"
