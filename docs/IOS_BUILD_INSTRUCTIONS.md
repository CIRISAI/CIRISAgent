# iOS Build Pipeline Instructions

This guide explains how to build the required binary dependencies and run the CIRIS iOS runtime.

## Prerequisites

*   macOS (12.0+)
*   Xcode (14.0+)
*   Rust (`rustup`)
*   Python 3.10
*   `pip`
*   `briefcase` (`pip install briefcase`)

## Architecture

The iOS runtime requires "cross-compiled" Python wheels for packages that contain C or Rust extensions.
The main blockers identified are:
1.  `pydantic-core` (Rust)
2.  `cryptography` (Rust/C)

## Part 1: Building Dependencies

### Automatic Build Script (`pydantic-core`)

We provide a script to build `pydantic-core`:

```bash
./ios/scripts/build_wheels.sh
```

This will:
1.  Clone `pydantic-core`.
2.  Build it for `aarch64-apple-ios`.
3.  Output the `.whl` file to `ios/wheels/`.

### Manual Steps for Cryptography

Building `cryptography` for iOS is more complex as it depends on OpenSSL. We recommend using a recipe-based system like [kivy-ios](https://github.com/kivy/kivy-ios) or [BeeWare](https://beeware.org) tools if possible, but for manual builds:

1.  **Build OpenSSL for iOS**:
    You need static libraries for `libssl` and `libcrypto` compiled for `arm64-apple-ios`.
2.  **Build Cryptography**:
    ```bash
    # Example environment setup (paths vary based on your OpenSSL build)
    export OPENSSL_DIR=/path/to/ios/openssl
    export CFLAGS="-target arm64-apple-ios -miphoneos-version-min=12.0"
    export LDFLAGS="-target arm64-apple-ios -miphoneos-version-min=12.0 -L$OPENSSL_DIR/lib"

    # Build the wheel
    pip wheel cryptography==42.0.8 --no-deps --wheel-dir ios/wheels --no-binary cryptography
    ```

## Part 2: Running the iOS App

We use [BeeWare Briefcase](https://briefcase.readthedocs.io) to package and run the iOS application.

### Setup

1.  Prepare the source code (copies `ciris_engine` and `ciris_modular_services`):
    ```bash
    ./ios/scripts/prepare_source.sh
    ```

2.  (Important) Ensure you have built the wheels (see Part 1) and placed them in `ios/wheels`.
    *Note: Briefcase does not automatically pick up local wheels by default. You may need to manually install them into the generated Xcode project or use a custom Briefcase configuration to point to local pip sources.*

### Build and Run

1.  Navigate to the project directory:
    ```bash
    cd ios/CirisiOS
    ```

2.  Create the iOS app structure:
    ```bash
    briefcase create iOS
    ```

3.  Build the app:
    ```bash
    briefcase build iOS
    ```

4.  Run in Simulator:
    ```bash
    briefcase run iOS
    ```
