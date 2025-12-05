# iOS Build Pipeline Instructions

This guide explains how to build the required binary dependencies for the CIRIS iOS runtime.

## Prerequisites

*   macOS (12.0+)
*   Xcode (14.0+)
*   Rust (`rustup`)
*   Python 3.10
*   `pip`

## Architecture

The iOS runtime requires "cross-compiled" Python wheels for packages that contain C or Rust extensions.
The main blockers identified are:
1.  `pydantic-core` (Rust)
2.  `cryptography` (Rust/C)

## Automatic Build Script

We provide a script to build `pydantic-core`:

```bash
./ios/scripts/build_wheels.sh
```

This will:
1.  Clone `pydantic-core`.
2.  Build it for `aarch64-apple-ios`.
3.  Output the `.whl` file to `ios/wheels/`.

## Manual Steps for Cryptography

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

## Integration

Once you have the wheels in `ios/wheels/`:
1.  **Copy**: Move the `.whl` files to your iOS project structure.
2.  **Install**: Use a script to unzip these wheels into your app's `site-packages` directory, or use a tool that supports installing from local wheels.
