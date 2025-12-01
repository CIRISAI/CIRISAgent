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

# Setup Rust environment (puccinialin location)
export RUSTUP_HOME="${RUSTUP_HOME:-$HOME/.cache/puccinialin/rustup}"
export CARGO_HOME="${CARGO_HOME:-$HOME/.cache/puccinialin/cargo}"
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
export PYO3_CROSS_PYTHON_VERSION="3.10"
export PYO3_CROSS_LIB_DIR=""

# Create PYO3 config file for Android
# suppress_build_script_link_lines=true allows building without libpython present at compile time
# We'll post-process the .so with patchelf to add the NEEDED entry for libpython3.10.so
PYO3_CONFIG="/tmp/pyo3-config-android-cp310.txt"
cat > "$PYO3_CONFIG" << 'PYOCONFIG'
implementation=CPython
version=3.10
shared=true
abi3=false
lib_name=python3.10
lib_dir=
executable=python3
pointer_width=64
build_flags=
suppress_build_script_link_lines=true
PYOCONFIG
export PYO3_CONFIG_FILE="$PYO3_CONFIG"

export RUSTFLAGS="-C link-arg=-Wl,--allow-shlib-undefined -C link-arg=-Wl,-z,lazy"

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
    local pointer_width=${4:-64}

    log "Building for $target (pointer_width=$pointer_width)..."

    # Create target-specific PYO3 config file
    local target_config="/tmp/pyo3-config-${target}.txt"
    cat > "$target_config" << PYOCONFIG
implementation=CPython
version=3.10
shared=true
abi3=false
lib_name=python3.10
lib_dir=
executable=python3
pointer_width=${pointer_width}
build_flags=
suppress_build_script_link_lines=true
PYOCONFIG
    export PYO3_CONFIG_FILE="$target_config"

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

    # Find and process the wheel
    local wheel=$(find target/wheels -name "*.whl" | head -1)
    if [ -n "$wheel" ]; then
        local dest_name="pydantic_core-${PYDANTIC_VERSION}-cp310-cp310-android_24_${wheel_suffix}.whl"

        # Post-process: add libpython3.10.so as NEEDED dependency
        log "Adding libpython3.10.so dependency to wheel..."
        local temp_dir=$(mktemp -d)
        unzip -q "$wheel" -d "$temp_dir"

        local so_file="$temp_dir/pydantic_core/_pydantic_core.so"
        if [ -f "$so_file" ]; then
            # Add NEEDED entry for libpython3.10.so
            patchelf --add-needed libpython3.10.so "$so_file"
            log "Added libpython3.10.so dependency"

            # Verify
            readelf -d "$so_file" | grep -i needed | head -5

            # Repackage wheel
            cd "$temp_dir"
            # Update RECORD with new hash
            rm -f pydantic_core-*.dist-info/RECORD
            find . -type f ! -name "RECORD" | while read f; do
                hash=$(sha256sum "$f" | cut -d' ' -f1 | xxd -r -p | base64 | tr -d '=')
                size=$(stat -c%s "$f")
                echo "${f#./},sha256=$hash,$size"
            done > pydantic_core-*.dist-info/RECORD
            echo "pydantic_core-*.dist-info/RECORD,," >> pydantic_core-*.dist-info/RECORD

            zip -q -r "$WHEELS_DIR/$dest_name" .
            cd "$BUILD_DIR/pydantic_core-$PYDANTIC_VERSION"
        else
            warn ".so file not found, copying wheel as-is"
            cp "$wheel" "$WHEELS_DIR/$dest_name"
        fi

        rm -rf "$temp_dir"
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
    build_target "x86_64-linux-android" "x86_64-linux-android" "x86_64" "64"

    log "--- Building ARM64 (real devices) ---"
    build_target "aarch64-linux-android" "aarch64-linux-android" "arm64_v8a" "64"

    # Build for 32-bit ARM devices
    log "--- Building ARMv7 (32-bit ARM devices) ---"
    build_target "armv7-linux-androideabi" "armv7a-linux-androideabi" "armeabi_v7a" "32"

    # log "--- Building x86 (older emulators) ---"
    # build_target "i686-linux-android" "i686-linux-android" "x86" "32"

    echo
    log "=== Build Complete ==="
    log "Wheels in $WHEELS_DIR:"
    ls -la "$WHEELS_DIR"/*.whl 2>/dev/null || warn "No wheels found"
}

main "$@"
