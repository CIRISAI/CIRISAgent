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

## Selected iOS Architecture: BeeWare Briefcase

After evaluation, we have selected **BeeWare Briefcase** as the foundation for the iOS build.

*   **Runtime**: Uses **Python-Apple-support**, a pre-compiled Python framework for iOS.
*   **Packaging**: **Briefcase** handles the creation of the Xcode project, signing, and bundling of the Python environment.
*   **Interop**: Initial validation uses **Toga** (BeeWare's UI toolkit) to ensure the runtime works. Future iterations can use **PythonKit** or the Python C-API for deep integration with a native Swift UI.

### Critical Dependency Strategy

The main challenge remains binary extensions (`pydantic` and `cryptography`).

1.  **`pydantic-core` (Rust)**:
    *   **Solution**: We have implemented a custom build script (`ios/scripts/build_wheels.sh`) that uses `maturin` to cross-compile this dependency for `aarch64-apple-ios`.
    *   **Status**: Automated script available.

2.  **`cryptography` (Rust/C)**:
    *   **Solution**: Requires manual compilation against an iOS-built OpenSSL.
    *   **Status**: Manual instructions provided in `docs/IOS_BUILD_INSTRUCTIONS.md`.

## Implementation Status

We have established the following infrastructure for the iOS runtime:

| Component | Path | Status |
| :--- | :--- | :--- |
| **Build Pipeline** | `ios/scripts/build_wheels.sh` | **Done.** Automates `pydantic-core` cross-compilation. |
| **Project Scaffold** | `ios/CirisiOS/` | **Done.** BeeWare Briefcase project configured for CIRIS. |
| **Source Sync** | `ios/scripts/prepare_source.sh` | **Done.** Copies `ciris_engine` and services into the app bundle. |
| **Verification App** | `ios/CirisiOS/src/ciris_ios/app.py` | **Done.** A test harness to verify `pydantic` and `cryptography` loading. |

## Next Steps

To finalize the "100% on device" iOS implementation:

1.  **Execute Build Pipeline (on macOS)**:
    *   Run `ios/scripts/build_wheels.sh` to generate the `pydantic-core` wheel.
    *   Manually build `cryptography` (requires OpenSSL setup).
    *   Place wheels in `ios/wheels/`.

2.  **Build & Run Simulator**:
    *   Run `./ios/scripts/prepare_source.sh` to populate the source code.
    *   Run `briefcase run iOS` to launch the verification app in the Simulator.
    *   **Success Criteria**: The app launches and displays the versions of Pydantic and Cryptography without crashing.

3.  **Native Integration**:
    *   Once the runtime is verified, modify the Briefcase template (or export the Xcode project) to expose the CIRIS engine to Swift code, replacing the Toga UI with the native iOS interface.

## Conclusion

**Is an equivalent to Chaquopy available?**
**No.** However, **BeeWare Briefcase** provides a viable alternative workflow.

**Can we implement 100% on device?**
**Yes.** We have scaffolded the necessary pipeline to cross-compile the required dependencies. The path forward involves executing these build scripts on a macOS machine and verifying the runtime in the Simulator. The "hard part" (automating the Rust build for Pydantic) has been scripted.
