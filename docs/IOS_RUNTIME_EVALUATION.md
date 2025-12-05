# iOS Runtime Evaluation for CIRIS Engine

## Executive Summary

There is **no direct drop-in equivalent to Chaquopy for iOS** that offers the same level of seamless integration (Gradle plugin, automatic dependency resolution, and Java/Kotlin interop) out of the box.

However, achieving the **"100% on device"** goal is **technically feasible**, provided you are willing to replicate the custom compilation engineering currently used for the Android implementation. The iOS ecosystem requires a more manual assembly of components to achieve the same result.

## Current Android Architecture (Reference)

The current Android implementation relies on **Chaquopy**, which handles:
1.  **Python Runtime**: Automatically bundles Python 3.10.
2.  **Interop**: Provides a Java API to access Python objects.
3.  **Dependencies**:
    *   Pure Python: Installed from PyPI.
    *   Binary Extensions (Rust/C): Chaquopy provides a repository of pre-built wheels.
    *   **Custom Binaries**: The project currently uses **manually cross-compiled wheels** for `pydantic-core` (Rust) placed in `android/app/wheels/`.

## iOS Options Evaluation

To achieve an equivalent setup on iOS, we must assemble the following components:

### 1. Python Runtime: **Python-Apple-support (BeeWare)**
*   **Description**: A build of Python (compiled as a framework) optimized for iOS/macOS.
*   **Role**: Replaces the Chaquopy runtime.
*   **Status**: Stable and widely used.

### 2. Interoperability: **PythonKit** (or Python-Apple-support's C-API)
*   **Description**: A Swift library that provides a bridge to Python. allows writing `let sys = Python.import("sys")` in Swift.
*   **Role**: Replaces Chaquopy's Java API.
*   **Status**: Mature, but requires manual setup in Xcode.

### 3. Dependency Management (The Main Challenge)
*   **Pure Python**: Can be installed into the app bundle using standard tools (`pip install -t ...`).
*   **Binary Extensions**: This is the critical bottleneck. iOS does not allow JIT compilation and has strict signing rules. All binary extensions must be:
    *   Compiled for `arm64` (device) and `x86_64/arm64` (simulator).
    *   Signed correctly.
    *   Linked as dynamic libraries or frameworks.

#### Critical Dependencies Analysis
*   **`pydantic` (requires `pydantic-core`)**:
    *   **Type**: Rust Extension.
    *   **Status**: **No public iOS wheels exist.**
    *   **Effort**: You must cross-compile `pydantic-core` for iOS using the Rust toolchain (`cargo build --target aarch64-apple-ios`). This mirrors the work already done for Android.
    *   **Risk**: High. [GitHub Issue #1170](https://github.com/pydantic/pydantic-core/issues/1170) indicates this is non-trivial and not officially supported.
*   **`cryptography`**:
    *   **Type**: Rust/C Extension.
    *   **Status**: **No public iOS wheels exist.**
    *   **Effort**: Requires cross-compilation. BeeWare's `mobile-forge` project has recipes, but they may need maintenance.

## Proposed iOS Stack

If the team decides to proceed, the recommended stack is:

1.  **Build System**: Custom script wrapping `pip` and `cargo` (for Rust).
2.  **Runtime**: **BeeWare's Python-Apple-support**.
3.  **Bridge**: **PythonKit** for Swift integration.
4.  **Process**:
    *   Create a `ios/wheels` directory (similar to `android/app/wheels`).
    *   Build `pydantic-core` and `cryptography` for iOS (arm64).
    *   Embed the Python framework and site-packages into the iOS App Bundle.

## Alternatives Considered

| Option | Pros | Cons | Verdict |
| :--- | :--- | :--- | :--- |
| **BeeWare (Briefcase)** | Full packaging solution. | Optimizes for Toga (UI), opaque build process for embedded use. | Good for referencing build recipes, but might be too heavy for just embedding a backend. |
| **Kivy (ios-deploy)** | Mature cross-platform tool. | Non-native UI focus. | Not suitable for "Native UI + Python Backend" architecture. |
| **Pyto / Pythonista** | Existing apps. | Closed source or not embeddable as a library. | Not viable for a standalone product. |

## Conclusion

**Is an equivalent to Chaquopy available?**
**No.** There is no single "add-plugin-and-run" solution for iOS that supports complex binary dependencies like Pydantic V2.

**Can we implement 100% on device?**
**Yes**, but it requires significant engineering investment to:
1.  Set up a cross-compilation pipeline for Rust/Python extensions (Pydantic, Cryptography) targeting iOS.
2.  Manually integrate the Python runtime and dependencies into the Xcode project.

**Recommendation:**
Proceed only if the team has resources to maintain custom builds of `pydantic-core` and `cryptography` for iOS. The architecture would mirror the Android one (using local wheels), but the setup cost is higher due to the lack of an ecosystem equivalent to Chaquopy.
