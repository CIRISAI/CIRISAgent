#!/bin/bash
# Build pydantic-core wheels for all Android architectures
# This script cross-compiles pydantic-core for Android using Rust/maturin
#
# Prerequisites:
#   - Rust toolchain with Android targets
#   - Android NDK 26.1.10909125
#   - maturin (pip install maturin)
#   - pydantic-core source

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WHEELS_DIR="$SCRIPT_DIR/../app/wheels"
BUILD_DIR="/tmp/pydantic-core-build"
PYDANTIC_VERSION="2.23.4"

# Colors for output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

log() { echo -e "${GREEN}[BUILD]${NC} $1"; }
warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
error() { echo -e "${RED}[ERROR]${NC} $1"; exit 1; }

# Setup Rust environment
export RUSTUP_HOME="${RUSTUP_HOME:-$HOME/.rustup}"
export CARGO_HOME="${CARGO_HOME:-$HOME/.cargo}"
export PATH="$CARGO_HOME/bin:$PATH"

# Android NDK configuration
export ANDROID_NDK_HOME="${ANDROID_NDK_HOME:-/home/emoore/Android/Sdk/ndk/26.1.10909125}"
export NDK_TOOLCHAIN="$ANDROID_NDK_HOME/toolchains/llvm/prebuilt/linux-x86_64/bin"

if [ ! -d "$ANDROID_NDK_HOME" ]; then
    error "Android NDK not found at $ANDROID_NDK_HOME"
fi

if ! command -v maturin &> /dev/null; then
    error "maturin not found. Install with: pip install maturin"
fi

if ! command -v rustup &> /dev/null; then
    error "rustup not found. Install Rust from https://rustup.rs"
fi

# Common build flags
export CI=true
export PYO3_CROSS_PYTHON_VERSION="3.12"
export PYO3_CROSS_LIB_DIR=""
export RUSTFLAGS="-C link-arg=-Wl,--allow-shlib-undefined -C link-arg=-Wl,-z,lazy"

# Create PYO3 config file for Android
PYO3_CONFIG="/tmp/pyo3-config-android-cp312.txt"
cat > "$PYO3_CONFIG" << 'PYOCONFIG'
implementation=CPython
version=3.12
shared=true
abi3=false
lib_name=python3.12
lib_dir=
executable=python3
pointer_width=64
build_flags=
suppress_build_script_link_lines=true
PYOCONFIG
export PYO3_CONFIG_FILE="$PYO3_CONFIG"

# Download pydantic-core source if needed
setup_source() {
    if [ ! -d "$BUILD_DIR/pydantic_core-$PYDANTIC_VERSION" ]; then
        log "Downloading pydantic-core $PYDANTIC_VERSION source..."
        mkdir -p "$BUILD_DIR"
        cd "$BUILD_DIR"
        pip download --no-binary :all: --no-deps pydantic-core==$PYDANTIC_VERSION
        tar xzf pydantic_core-$PYDANTIC_VERSION.tar.gz
    fi
}

# Build for a specific target
build_target() {
    local target=$1
    local android_target=$2
    local wheel_suffix=$3

    log "Building for $target..."

    # Set target-specific environment
    export CC="$NDK_TOOLCHAIN/${android_target}24-clang"
    export CXX="$NDK_TOOLCHAIN/${android_target}24-clang++"
    export AR="$NDK_TOOLCHAIN/llvm-ar"

    # Set linker for cargo
    local cargo_target_upper=$(echo "$target" | tr '[:lower:]-' '[:upper:]_')
    export "CARGO_TARGET_${cargo_target_upper}_LINKER=$CC"

    # Add rust target if not present
    rustup target add "$target" 2>/dev/null || true

    cd "$BUILD_DIR/pydantic_core-$PYDANTIC_VERSION"
    rm -rf "target/$target" target/wheels

    maturin build --release --target "$target" -i python3 --skip-auditwheel

    # Find and copy the wheel
    local wheel=$(find target/wheels -name "*.whl" | head -1)
    if [ -n "$wheel" ]; then
        local dest_name="pydantic_core-${PYDANTIC_VERSION}-cp312-cp312-android_24_${wheel_suffix}.whl"
        cp "$wheel" "$WHEELS_DIR/$dest_name"
        log "Built: $dest_name"
    else
        warn "No wheel found for $target"
    fi
}

# Main build process
main() {
    log "=== Building pydantic-core wheels for Android ==="
    log "Version: $PYDANTIC_VERSION"
    log "NDK: $ANDROID_NDK_HOME"
    log "Output: $WHEELS_DIR"
    echo

    mkdir -p "$WHEELS_DIR"
    setup_source

    # Build for each architecture
    # Format: rust_target android_clang_prefix wheel_suffix

    log "--- Building x86_64 (emulator) ---"
    build_target "x86_64-linux-android" "x86_64-linux-android" "x86_64"

    log "--- Building ARM64 (real devices) ---"
    build_target "aarch64-linux-android" "aarch64-linux-android" "arm64_v8a"

    # Optional: Build for older 32-bit devices
    # log "--- Building ARMv7 (older devices) ---"
    # build_target "armv7-linux-androideabi" "armv7a-linux-androideabi" "armeabi_v7a"

    # log "--- Building x86 (older emulators) ---"
    # build_target "i686-linux-android" "i686-linux-android" "x86"

    echo
    log "=== Build Complete ==="
    log "Wheels in $WHEELS_DIR:"
    ls -la "$WHEELS_DIR"/*.whl 2>/dev/null || warn "No wheels found"
}

main "$@"
