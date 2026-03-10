#!/usr/bin/env python3
"""
Update CIRISVerify binaries and Python bindings for Android and iOS.

Usage:
    python -m tools.update_ciris_verify [version]
    python -m tools.update_ciris_verify --local /path/to/CIRISVerify

Examples:
    python -m tools.update_ciris_verify 0.6.16
    python -m tools.update_ciris_verify                      # Uses latest release
    python -m tools.update_ciris_verify --local ../CIRISVerify  # From local build
    python -m tools.update_ciris_verify --local ../CIRISVerify --ios-only
    python -m tools.update_ciris_verify --local ../CIRISVerify --android-only
"""

import argparse
import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

# GitHub repo info
GITHUB_REPO = "CIRISAI/CIRISVerify"

# Project paths (relative to repo root)
REPO_ROOT = Path(__file__).parent.parent
MOBILE_ROOT = REPO_ROOT / "mobile"

# Android paths
JNI_LIBS_DIR = MOBILE_ROOT / "androidApp" / "src" / "main" / "jniLibs"

# Canonical FFI bindings location (used by both mobile and server)
FFI_BINDINGS_DIR = REPO_ROOT / "ciris_adapters" / "ciris_verify" / "ffi_bindings"

# Legacy path (deprecated - now synced from FFI_BINDINGS_DIR)
ANDROID_PYTHON_DIR = FFI_BINDINGS_DIR

# iOS paths
IOS_APP_DIR = MOBILE_ROOT / "iosApp"
IOS_FRAMEWORKS_DIR = IOS_APP_DIR / "Frameworks"
IOS_XCFRAMEWORK_DIR = IOS_FRAMEWORKS_DIR / "CIRISVerify.xcframework"
IOS_PYTHON_DIR = IOS_APP_DIR / "Resources" / "app_packages" / "ciris_verify"
IOS_ADAPTER_DIR = IOS_APP_DIR / "Resources" / "app" / "ciris_adapters" / "ciris_verify"
IOS_RESOURCES_ZIP = IOS_APP_DIR / "Resources.zip"
IOS_RESOURCES_DIR = IOS_APP_DIR / "Resources"
REPO_ADAPTER_DIR = REPO_ROOT / "ciris_adapters" / "ciris_verify"

# Android architectures mapping
ANDROID_ARCHS = {
    "arm64-v8a": "android/arm64-v8a/libciris_verify_ffi.so",
    "x86_64": "android/x86_64/libciris_verify_ffi.so",
    "armeabi-v7a": "android/armeabi-v7a/libciris_verify_ffi.so",
}

# iOS build targets
IOS_TARGETS = {
    "device": "aarch64-apple-ios",
    "simulator": "aarch64-apple-ios-sim",
}


def run_cmd(cmd: list[str], check: bool = True) -> subprocess.CompletedProcess:
    """Run a command and return the result."""
    print(f"  $ {' '.join(cmd)}")
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def get_latest_release_version() -> str:
    """Get the latest release version from GitHub."""
    print("Fetching latest release version...")
    result = run_cmd(["gh", "release", "view", "--repo", GITHUB_REPO, "--json", "tagName", "-q", ".tagName"])
    version = result.stdout.strip()
    if version.startswith("v"):
        version = version[1:]
    return version


def download_release(version: str, dest_dir: Path, platform: str = "android") -> Path:
    """Download a platform release tarball from GitHub.

    Args:
        version: Release version (e.g. "0.9.4").
        dest_dir: Directory to download into.
        platform: "android" or "ios".
    """
    tag = f"v{version}"

    asset_patterns = [
        f"ciris-verify-v{version}-{platform}.tar.gz",
        f"ciris-verify-{version}-{platform}.tar.gz",
    ]
    if platform == "android":
        asset_patterns.append("ciris-verify-ffi.tar.gz")

    for pattern in asset_patterns:
        print(f"Trying to download {pattern} from release {tag}...")
        run_cmd(
            ["gh", "release", "download", tag, "--repo", GITHUB_REPO, "--pattern", pattern, "--dir", str(dest_dir)],
            check=False,
        )

        for f in dest_dir.iterdir():
            if f.suffix == ".gz" and platform in f.name.lower():
                print(f"  Downloaded: {f.name}")
                return f
            elif f.name == "ciris-verify-ffi.tar.gz":
                print(f"  Downloaded: {f.name}")
                return f

    raise FileNotFoundError(f"Failed to download {platform} tarball from release {tag}")


def download_checksums(version: str, dest_dir: Path) -> Path:
    """Download SHA256SUMS from GitHub release."""
    tag = f"v{version}"
    print("Downloading SHA256SUMS...")
    run_cmd(
        ["gh", "release", "download", tag, "--repo", GITHUB_REPO, "--pattern", "SHA256SUMS", "--dir", str(dest_dir)]
    )
    return dest_dir / "SHA256SUMS"


def verify_checksum(file_path: Path, expected_hash: str) -> bool:
    """Verify SHA256 checksum of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    return sha256.hexdigest() == expected_hash


def parse_checksums(checksum_file: Path) -> dict[str, str]:
    """Parse SHA256SUMS file into a dict of path -> hash."""
    checksums = {}
    with open(checksum_file) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(None, 1)
            if len(parts) == 2:
                hash_val, path = parts
                path = path.lstrip("./")
                checksums[path] = hash_val
    return checksums


def extract_tarball(tarball: Path, dest_dir: Path) -> None:
    """Extract tarball to destination directory."""
    print(f"Extracting {tarball.name}...")
    run_cmd(["tar", "-xzf", str(tarball), "-C", str(dest_dir)])


# ---------------------------------------------------------------------------
# Android
# ---------------------------------------------------------------------------


def update_android_binaries(extract_dir: Path, checksums: dict[str, str]) -> None:
    """Copy Android binaries to jniLibs directory."""
    print("\nUpdating Android binaries...")

    for arch, src_path in ANDROID_ARCHS.items():
        src_file = extract_dir / src_path
        dest_dir = JNI_LIBS_DIR / arch
        dest_file = dest_dir / "libciris_verify_ffi.so"

        if not src_file.exists():
            print(f"  Missing: {src_path}")
            continue

        checksum_key = src_path
        if checksum_key in checksums:
            if verify_checksum(src_file, checksums[checksum_key]):
                print(f"  {arch}: checksum verified")
            else:
                print(f"  {arch}: CHECKSUM MISMATCH!")
                raise ValueError(f"Checksum mismatch for {src_path}")
        else:
            print(f"  {arch}: no checksum available")

        dest_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src_file, dest_file)
        print(f"  -> Copied to {dest_file.relative_to(REPO_ROOT)}")


# ---------------------------------------------------------------------------
# iOS
# ---------------------------------------------------------------------------


def convert_static_to_dynamic(static_lib: Path, output_dylib: Path, target: str) -> bool:
    """Convert a static archive (.a) to a dynamic library (.dylib).

    Uses clang to link the static archive into a shared library suitable
    for ctypes/dlopen on iOS.

    Args:
        static_lib: Path to the .a file.
        output_dylib: Where to write the .dylib.
        target: Rust-style target triple (e.g. "aarch64-apple-ios").

    Returns:
        True on success.
    """
    # Map target to clang -target and SDK
    if "sim" in target:
        sdk = "iphonesimulator"
    else:
        sdk = "iphoneos"

    sdk_path_result = run_cmd(["xcrun", "--sdk", sdk, "--show-sdk-path"], check=False)
    if sdk_path_result.returncode != 0:
        print(f"  ERROR: Could not find {sdk} SDK")
        return False
    sdk_path = sdk_path_result.stdout.strip()

    # Detect minimum deployment target from the static archive to avoid
    # version mismatch warnings.  Falls back to 16.0 on error.
    min_version = "16.0"
    otool_result = run_cmd(["otool", "-l", str(static_lib)], check=False)
    if otool_result.returncode == 0:
        for line in otool_result.stdout.splitlines():
            line = line.strip()
            if line.startswith("minos ") or line.startswith("version "):
                ver = line.split()[-1]
                # Pick the highest version seen
                try:
                    if tuple(int(x) for x in ver.split(".")) > tuple(int(x) for x in min_version.split(".")):
                        min_version = ver
                except (ValueError, IndexError):
                    pass

    if "sim" in target:
        clang_target = f"arm64-apple-ios{min_version}-simulator"
    else:
        clang_target = f"arm64-apple-ios{min_version}"

    print(f"  {target}: linking with deployment target {min_version}")

    cmd = [
        "clang",
        "-shared",
        "-arch",
        "arm64",
        "-isysroot",
        sdk_path,
        "-target",
        clang_target,
        "-Wl,-all_load",
        str(static_lib),
        "-o",
        str(output_dylib),
        "-framework",
        "CoreFoundation",
        "-framework",
        "Security",
        "-framework",
        "SystemConfiguration",
        "-install_name",
        "@rpath/CIRISVerify.framework/CIRISVerify",
    ]
    result = run_cmd(cmd, check=False)
    if result.returncode != 0:
        print(f"  ERROR: clang linking failed:\n{result.stderr}")
        return False

    # Verify it's dynamic
    file_result = run_cmd(["file", str(output_dylib)], check=False)
    if "dynamically linked" not in file_result.stdout:
        print(f"  ERROR: Output is not dynamic: {file_result.stdout.strip()}")
        return False

    size_mb = output_dylib.stat().st_size / 1024 / 1024
    print(f"  -> Converted {static_lib.name} to dylib ({size_mb:.1f}MB)")
    return True


def update_ios_from_release(version: str, extract_dir: Path, checksums: dict[str, str]) -> None:
    """Update iOS binaries from a release tarball.

    Downloads the iOS tarball, converts static archives to dynamic libraries,
    builds an XCFramework, and copies the fallback dylib.
    """
    print("\nUpdating iOS binaries from release...")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        for label, target in IOS_TARGETS.items():
            # Prefer pre-built .dylib from release (preserves registry hash)
            src_dylib = extract_dir / "ios" / target / "libciris_verify_ffi.dylib"
            src_a = extract_dir / "ios" / target / "libciris_verify_ffi.a"
            use_prebuilt = src_dylib.exists()

            if use_prebuilt:
                # Verify checksum of pre-built dylib
                checksum_key = f"ios/{target}/libciris_verify_ffi.dylib"
                if checksum_key in checksums:
                    if verify_checksum(src_dylib, checksums[checksum_key]):
                        print(f"  {label}: checksum verified")
                    else:
                        print(f"  {label}: CHECKSUM MISMATCH!")
                        raise ValueError(f"Checksum mismatch for {checksum_key}")
            elif src_a.exists():
                # Fallback: verify .a checksum
                checksum_key = f"ios/{target}/libciris_verify_ffi.a"
                if checksum_key in checksums:
                    if verify_checksum(src_a, checksums[checksum_key]):
                        print(f"  {label}: checksum verified")
                    else:
                        print(f"  {label}: CHECKSUM MISMATCH!")
                        raise ValueError(f"Checksum mismatch for {checksum_key}")
            else:
                print(f"  Missing {label}: no .dylib or .a found")
                continue

            dylib_dir = tmpdir / target
            dylib_dir.mkdir(parents=True)
            dylib_path = dylib_dir / "libciris_verify_ffi.dylib"

            if use_prebuilt:
                # Use pre-built dylib directly (preserves binary hash for registry verification)
                shutil.copy2(src_dylib, dylib_path)
                print(f"  {label}: using pre-built dylib ({dylib_path.stat().st_size / 1024 / 1024:.1f}MB)")
            else:
                # Convert .a → .dylib (legacy path for older releases)
                if not convert_static_to_dynamic(src_a, dylib_path, target):
                    print(f"  ERROR: Failed to convert {label} static lib to dynamic")
                    continue

            # Determine platform
            if "sim" in target:
                platform_name = "iPhoneSimulator"
                xcfw_slice = "ios-arm64-simulator"
            else:
                platform_name = "iPhoneOS"
                xcfw_slice = "ios-arm64"

            # Create framework bundle
            fw_dir = tmpdir / xcfw_slice / "CIRISVerify.framework"
            fw_dir.mkdir(parents=True)
            headers_dir = fw_dir / "Headers"
            headers_dir.mkdir()

            shutil.copy2(dylib_path, fw_dir / "CIRISVerify")

            # Set install name so dyld can find it at runtime.
            # Skip if already correct (v0.10.1+ bakes it in) to preserve registry hash.
            expected_id = "@rpath/CIRISVerify.framework/CIRISVerify"
            current_id = run_cmd(["otool", "-D", str(fw_dir / "CIRISVerify")], check=False)
            needs_id_fix = expected_id not in (current_id.stdout or "")
            if needs_id_fix:
                run_cmd(
                    [
                        "install_name_tool",
                        "-id",
                        expected_id,
                        str(fw_dir / "CIRISVerify"),
                    ]
                )
                print(f"  {label}: applied install_name_tool")
            else:
                print(f"  {label}: install name already correct, skipping (preserves hash)")

            plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key><string>en</string>
    <key>CFBundleExecutable</key><string>CIRISVerify</string>
    <key>CFBundleIdentifier</key><string>ai.ciris.verify</string>
    <key>CFBundleName</key><string>CIRISVerify</string>
    <key>CFBundlePackageType</key><string>FMWK</string>
    <key>CFBundleShortVersionString</key><string>{version}</string>
    <key>CFBundleVersion</key><string>1</string>
    <key>MinimumOSVersion</key><string>16.0</string>
    <key>CFBundleSupportedPlatforms</key>
    <array><string>{platform_name}</string></array>
</dict>
</plist>"""
            (fw_dir / "Info.plist").write_text(plist_content)
            print(f"  {label}: prepared framework")

        # Build XCFramework
        framework_args = []
        for slice_name in ["ios-arm64", "ios-arm64-simulator"]:
            fw = tmpdir / slice_name / "CIRISVerify.framework"
            if fw.exists():
                framework_args.extend(["-framework", str(fw)])

        if not framework_args:
            print("  ERROR: No iOS frameworks produced")
            return

        if IOS_XCFRAMEWORK_DIR.exists():
            shutil.rmtree(IOS_XCFRAMEWORK_DIR)

        cmd = ["xcodebuild", "-create-xcframework"] + framework_args + ["-output", str(IOS_XCFRAMEWORK_DIR)]
        result = run_cmd(cmd, check=False)
        if result.returncode != 0:
            print(f"  ERROR: xcodebuild failed: {result.stderr}")
            return

        print(f"  -> XCFramework written to {IOS_XCFRAMEWORK_DIR.relative_to(REPO_ROOT)}")

        # Copy device dylib as fallback into Python bindings dir
        device_dylib = tmpdir / "aarch64-apple-ios" / "libciris_verify_ffi.dylib"
        if device_dylib.exists():
            IOS_PYTHON_DIR.mkdir(parents=True, exist_ok=True)
            dest = IOS_PYTHON_DIR / "libciris_verify_ffi.dylib"
            shutil.copy2(device_dylib, dest)
            print(f"  -> Fallback dylib copied ({dest.stat().st_size / 1024 / 1024:.1f}MB)")


def build_ios_xcframework(ciris_verify_root: Path, version: str) -> None:
    """Build iOS XCFramework from local CIRISVerify dylibs.

    CRITICAL: The XCFramework MUST contain dynamic libraries (.dylib), NOT
    static archives (.a). Python's ctypes.CDLL() cannot resolve symbols
    from static archives via dlsym.

    The CIRISVerify Rust build produces both .a and .dylib for each target.
    This function takes the .dylib files, wraps them in .framework bundles
    with correct @rpath install names, and creates an XCFramework.
    """
    print("\nBuilding iOS XCFramework (dynamic)...")

    bridging_header = ciris_verify_root / "bindings" / "swift" / "CIRISVerify-Bridging-Header.h"
    if not bridging_header.exists():
        print(f"  Warning: bridging header not found at {bridging_header}")
        bridging_header = None

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        framework_args = []

        for label, target in IOS_TARGETS.items():
            dylib = ciris_verify_root / "target" / target / "release" / "libciris_verify_ffi.dylib"
            if not dylib.exists():
                print(f"  Missing {label} dylib: {dylib}")
                print(f"  Build with: cargo build --release --target {target} -p ciris-verify-ffi --features ios")
                continue

            # Verify it's actually a dynamic library
            result = run_cmd(["file", str(dylib)], check=False)
            if "dynamically linked" not in result.stdout:
                print(f"  ERROR: {label} binary is NOT a dynamic library!")
                print(f"  file output: {result.stdout.strip()}")
                raise ValueError(f"{dylib} is not a dynamic library")

            # Determine platform
            if "sim" in target:
                platform_name = "iPhoneSimulator"
                xcfw_slice = "ios-arm64-simulator"
            else:
                platform_name = "iPhoneOS"
                xcfw_slice = "ios-arm64"

            # Create framework bundle
            fw_dir = tmpdir / xcfw_slice / "CIRISVerify.framework"
            fw_dir.mkdir(parents=True)
            headers_dir = fw_dir / "Headers"
            headers_dir.mkdir()

            # Copy dylib as the framework binary
            shutil.copy2(dylib, fw_dir / "CIRISVerify")

            # Set install name for embedded framework
            run_cmd(
                [
                    "install_name_tool",
                    "-id",
                    "@rpath/CIRISVerify.framework/CIRISVerify",
                    str(fw_dir / "CIRISVerify"),
                ]
            )

            # Copy header
            if bridging_header:
                shutil.copy2(bridging_header, headers_dir / "ciris_verify.h")

            # Write Info.plist
            plist_content = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleDevelopmentRegion</key><string>en</string>
    <key>CFBundleExecutable</key><string>CIRISVerify</string>
    <key>CFBundleIdentifier</key><string>ai.ciris.verify</string>
    <key>CFBundleName</key><string>CIRISVerify</string>
    <key>CFBundlePackageType</key><string>FMWK</string>
    <key>CFBundleShortVersionString</key><string>{version}</string>
    <key>CFBundleVersion</key><string>1</string>
    <key>MinimumOSVersion</key><string>16.0</string>
    <key>CFBundleSupportedPlatforms</key>
    <array><string>{platform_name}</string></array>
</dict>
</plist>"""
            (fw_dir / "Info.plist").write_text(plist_content)

            framework_args.extend(["-framework", str(fw_dir)])
            print(f"  {label}: prepared framework from {dylib.name}")

        if not framework_args:
            print("  ERROR: No iOS targets found! Build CIRISVerify for iOS first.")
            return

        # Remove old XCFramework
        if IOS_XCFRAMEWORK_DIR.exists():
            shutil.rmtree(IOS_XCFRAMEWORK_DIR)

        # Create XCFramework
        cmd = ["xcodebuild", "-create-xcframework"] + framework_args + ["-output", str(IOS_XCFRAMEWORK_DIR)]
        result = run_cmd(cmd, check=False)
        if result.returncode != 0:
            print(f"  ERROR: xcodebuild failed: {result.stderr}")
            raise RuntimeError("Failed to create XCFramework")

        print(f"  -> XCFramework written to {IOS_XCFRAMEWORK_DIR.relative_to(REPO_ROOT)}")

        # Verify the result
        for label, target in IOS_TARGETS.items():
            slice_name = "ios-arm64-simulator" if "sim" in target else "ios-arm64"
            binary = IOS_XCFRAMEWORK_DIR / slice_name / "CIRISVerify.framework" / "CIRISVerify"
            if binary.exists():
                result = run_cmd(["file", str(binary)], check=False)
                if "dynamically linked" in result.stdout:
                    print(f"  {label}: verified dynamic library")
                else:
                    print(f"  WARNING: {label} is NOT dynamic: {result.stdout.strip()}")


def update_ios_python_bindings(source_dir: Path) -> None:
    """Copy Python bindings to iOS Resources.

    Args:
        source_dir: Directory containing the Python source files.
                    Typically the Android Python dir or a wheel extract.
    """
    print("\nUpdating iOS Python bindings...")

    IOS_PYTHON_DIR.mkdir(parents=True, exist_ok=True)

    for py_file in source_dir.glob("*.py"):
        dest = IOS_PYTHON_DIR / py_file.name
        shutil.copy2(py_file, dest)
        print(f"  -> {py_file.name}")

    # Ensure py.typed marker exists
    py_typed = IOS_PYTHON_DIR / "py.typed"
    if not py_typed.exists():
        py_typed.touch()


def update_ios_dylib(ciris_verify_root: Path) -> None:
    """Copy the device dylib to iOS Resources as a fallback."""
    print("\nUpdating iOS fallback dylib...")

    device_dylib = ciris_verify_root / "target" / "aarch64-apple-ios" / "release" / "libciris_verify_ffi.dylib"
    if not device_dylib.exists():
        print(f"  Missing: {device_dylib}")
        return

    dest = IOS_PYTHON_DIR / "libciris_verify_ffi.dylib"
    shutil.copy2(device_dylib, dest)
    print(f"  -> Copied {device_dylib.stat().st_size / 1024 / 1024:.1f}MB dylib")


def sync_ios_adapter() -> None:
    """Sync adapter code from repo to iOS Resources, preserving iOS patches.

    The iOS service.py has a critical 8MB stack thread fix that the repo
    version does not have. This function syncs all adapter files EXCEPT
    service.py, which requires manual merging.
    """
    print("\nSyncing iOS adapter code...")

    if not REPO_ADAPTER_DIR.exists():
        print(f"  Repo adapter not found: {REPO_ADAPTER_DIR}")
        return

    IOS_ADAPTER_DIR.mkdir(parents=True, exist_ok=True)

    # Files safe to overwrite directly
    safe_files = ["adapter.py", "__init__.py", "manifest.json"]
    for filename in safe_files:
        src = REPO_ADAPTER_DIR / filename
        if src.exists():
            shutil.copy2(src, IOS_ADAPTER_DIR / filename)
            print(f"  -> {filename}")

    # service.py needs special handling - patch rather than replace
    _patch_ios_service_py()


def _patch_ios_service_py() -> None:
    """Update iOS service.py from repo while preserving the 8MB stack thread fix.

    Strategy: take the repo version and apply the iOS-specific patch
    (threading import + large-stack initialize method).
    """
    repo_service = REPO_ADAPTER_DIR / "service.py"
    ios_service = IOS_ADAPTER_DIR / "service.py"

    if not repo_service.exists():
        print("  service.py: repo file missing, skipping")
        return

    content = repo_service.read_text()

    # Check if already patched
    if "threading.stack_size" in content:
        shutil.copy2(repo_service, ios_service)
        print("  -> service.py (already has stack fix)")
        return

    # Add threading import
    if "import threading" not in content:
        content = content.replace(
            "import asyncio\nimport logging\nimport os\n",
            "import asyncio\nimport logging\nimport os\nimport threading\n",
        )

    # Replace the initialize method with the 8MB stack version
    # Match the standard initialize pattern
    old_init = '''    async def initialize(self) -> bool:
        """Initialize the verification client.

        Returns:
            True if initialization successful, False otherwise.
        """
        if self._initialized:
            return True

        try:
            self._client = CIRISVerify(
                binary_path=self.config.binary_path,
                timeout_seconds=self.config.timeout_seconds,
            )
            self._initialized = True
            logger.info("CIRISVerify service initialized successfully")
            return True'''

    new_init = '''    async def initialize(self) -> bool:
        """Initialize the verification client.

        The Rust/Tokio runtime inside CIRISVerify requires ~8MB of stack
        space for initialization. On iOS the default thread stack is only
        512KB, so we spawn a dedicated large-stack thread for the init call.

        Returns:
            True if initialization successful, False otherwise.
        """
        if self._initialized:
            return True

        try:
            init_result: list = [None, None]  # [client, error]

            def _init_on_large_stack() -> None:
                try:
                    init_result[0] = CIRISVerify(
                        binary_path=self.config.binary_path,
                        timeout_seconds=self.config.timeout_seconds,
                    )
                except Exception as exc:
                    init_result[1] = exc

            old_stack = threading.stack_size()
            try:
                threading.stack_size(8 * 1024 * 1024)
                t = threading.Thread(target=_init_on_large_stack, daemon=True)
                t.start()
                t.join(timeout=15)
            finally:
                threading.stack_size(old_stack)

            if init_result[1] is not None:
                raise init_result[1]
            if init_result[0] is None:
                raise RuntimeError("CIRISVerify init timed out (15s)")

            self._client = init_result[0]
            self._initialized = True
            logger.info("CIRISVerify service initialized successfully")
            return True'''

    if old_init in content:
        content = content.replace(old_init, new_init)
        print("  -> service.py (patched with 8MB stack thread fix)")
    else:
        # Couldn't find the exact pattern to patch - check if iOS version exists and keep it
        if ios_service.exists() and "threading.stack_size" in ios_service.read_text():
            print("  -> service.py: keeping existing iOS version (has stack fix)")
            return
        else:
            print("  WARNING: Could not auto-patch service.py - initialize() pattern changed")
            print("  The iOS version needs the 8MB stack thread fix in initialize().")
            print("  Copying repo version anyway - MANUAL PATCH REQUIRED")

    ios_service.write_text(content)


def ensure_device_fwork_stubs() -> None:
    """Create iphoneos .fwork stubs alongside iphonesimulator ones.

    Python on iOS uses .fwork redirect files to find native modules in
    Frameworks/.  The Resources directory ships with simulator stubs
    (``*.cpython-310-iphonesimulator.fwork``).  On a physical device
    Python looks for ``*.cpython-310-iphoneos.fwork`` instead, so we
    duplicate every simulator stub with a device-named copy.
    """
    print("\nEnsuring device .fwork stubs exist...")
    count = 0
    for fwork in IOS_RESOURCES_DIR.rglob("*.cpython-310-iphonesimulator.fwork"):
        device_fwork = fwork.with_name(fwork.name.replace("iphonesimulator", "iphoneos"))
        if not device_fwork.exists():
            shutil.copy2(fwork, device_fwork)
            count += 1
    print(f"  -> Created {count} device .fwork stubs")


def rebuild_resources_zip() -> None:
    """Rebuild the iOS Resources.zip."""
    # Ensure device .fwork stubs before zipping
    ensure_device_fwork_stubs()

    print("\nRebuilding Resources.zip...")

    if IOS_RESOURCES_ZIP.exists():
        IOS_RESOURCES_ZIP.unlink()

    # zip from inside the Resources directory (MUST set cwd to avoid zipping entire repo!)
    cmd = ["zip", "-q", "-r", str(IOS_RESOURCES_ZIP), "."]
    print(f"  $ zip -q -r {IOS_RESOURCES_ZIP.name} .")
    subprocess.run(cmd, cwd=str(IOS_RESOURCES_DIR), check=True)

    size_mb = IOS_RESOURCES_ZIP.stat().st_size / 1024 / 1024
    print(f"  -> Resources.zip ({size_mb:.1f}MB)")


# ---------------------------------------------------------------------------
# Python bindings (shared)
# ---------------------------------------------------------------------------


def update_python_bindings(version: str, tmpdir: Path) -> None:
    """Download and extract Python bindings from PyPI."""
    print(f"\nUpdating Python bindings from PyPI...")

    result = run_cmd(
        [sys.executable, "-m", "pip", "download", f"ciris-verify=={version}", "--no-deps", "-d", str(tmpdir)],
        check=False,
    )

    wheel_file = None
    for f in tmpdir.iterdir():
        if f.name.startswith(f"ciris_verify-{version}") and f.suffix == ".whl":
            wheel_file = f
            break

    if not wheel_file:
        print(f"  Could not download wheel from PyPI for version {version}")
        print(f"  -> Falling back to updating version string only")
        update_python_version_string(version, ANDROID_PYTHON_DIR)
        return

    print(f"  Downloaded: {wheel_file.name}")

    extract_dir = tmpdir / "wheel_extract"
    extract_dir.mkdir()

    with zipfile.ZipFile(wheel_file, "r") as zf:
        for name in zf.namelist():
            if name.startswith("ciris_verify/") and name.endswith(".py"):
                zf.extract(name, extract_dir)
                print(f"  Extracted: {name}")

    src_dir = extract_dir / "ciris_verify"
    if src_dir.exists():
        # Update Android
        ANDROID_PYTHON_DIR.mkdir(parents=True, exist_ok=True)
        for py_file in src_dir.glob("*.py"):
            dest_file = ANDROID_PYTHON_DIR / py_file.name
            shutil.copy2(py_file, dest_file)
            print(f"  -> Android: {py_file.name}")

        # Update iOS
        update_ios_python_bindings(src_dir)
    else:
        print(f"  No Python files found in wheel")


def update_python_version_string(version: str, python_dir: Path) -> None:
    """Update version string in Python __init__.py."""
    init_file = python_dir / "__init__.py"

    if not init_file.exists():
        print(f"  Python init not found: {init_file}")
        return

    content = init_file.read_text()
    new_content = re.sub(r'__version__\s*=\s*"[^"]+"', f'__version__ = "{version}"', content)

    if new_content != content:
        init_file.write_text(new_content)
        print(f'  Updated __version__ to "{version}" in {init_file.relative_to(REPO_ROOT)}')


# ---------------------------------------------------------------------------
# Local build mode
# ---------------------------------------------------------------------------


def update_from_local(ciris_verify_root: Path, android: bool, ios: bool) -> None:
    """Update from a local CIRISVerify build directory."""
    ciris_verify_root = ciris_verify_root.resolve()
    if not ciris_verify_root.exists():
        print(f"Error: CIRISVerify directory not found: {ciris_verify_root}")
        sys.exit(1)

    # Detect version from Cargo.toml
    cargo_toml = ciris_verify_root / "Cargo.toml"
    version = "unknown"
    if cargo_toml.exists():
        content = cargo_toml.read_text()
        match = re.search(r'^version\s*=\s*"([^"]+)"', content, re.MULTILINE)
        if match:
            version = match.group(1)

    print(f"\n{'='*50}")
    print(f"Updating CIRISVerify from local build (v{version})")
    print(f"Source: {ciris_verify_root}")
    print(f"{'='*50}\n")

    # Find Python bindings source (prefer the Android copy in our repo as canonical)
    python_src = ANDROID_PYTHON_DIR
    local_python = ciris_verify_root / "bindings" / "python" / "ciris_verify"
    if local_python.exists():
        python_src = local_python

    if android:
        # Android: copy .so files from local build
        print("\nUpdating Android binaries from local build...")
        local_android_archs = {
            "arm64-v8a": "aarch64-linux-android",
            "x86_64": "x86_64-linux-android",
            "armeabi-v7a": "armv7-linux-androideabi",
        }
        for arch, target in local_android_archs.items():
            src = ciris_verify_root / "target" / target / "release" / "libciris_verify_ffi.so"
            if not src.exists():
                print(f"  Missing: {src}")
                continue
            dest_dir = JNI_LIBS_DIR / arch
            dest_dir.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dest_dir / "libciris_verify_ffi.so")
            print(f"  -> {arch}: {src.stat().st_size / 1024 / 1024:.1f}MB")

    if ios:
        # iOS: build XCFramework, copy dylib, sync adapter
        build_ios_xcframework(ciris_verify_root, version)
        update_ios_python_bindings(python_src)
        update_ios_dylib(ciris_verify_root)
        sync_ios_adapter()
        rebuild_resources_zip()

    print(f"\n{'='*50}")
    print(f"CIRISVerify v{version} updated successfully")
    print(f"{'='*50}")

    if ios:
        print("\niOS next steps:")
        print("  1. Open mobile/iosApp/iosApp.xcodeproj in Xcode")
        print("  2. DELETE the app from the device (Resources.zip cache!)")
        print("  3. Cmd+R to build and run")

    if android:
        print("\nAndroid next steps:")
        print("  1. cd mobile && ./gradlew :androidApp:assembleDebug")
        print("  2. adb install -r androidApp/build/outputs/apk/debug/androidApp-debug.apk")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Update CIRISVerify binaries and Python bindings",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s 0.6.16                        # From GitHub release
  %(prog)s --local ../CIRISVerify        # From local build (both platforms)
  %(prog)s --local ../CIRISVerify --ios-only   # iOS only from local build
  %(prog)s --local ../CIRISVerify --android-only  # Android only
""",
    )
    parser.add_argument("version", nargs="?", help="Version to download (e.g., 0.6.16). Defaults to latest release.")
    parser.add_argument("--local", type=Path, metavar="PATH", help="Path to local CIRISVerify repo (skips download)")
    parser.add_argument("--skip-checksums", action="store_true", help="Skip checksum verification")
    parser.add_argument("--ios-only", action="store_true", help="Only update iOS")
    parser.add_argument("--android-only", action="store_true", help="Only update Android")
    parser.add_argument("--no-zip", action="store_true", help="Skip rebuilding Resources.zip")
    args = parser.parse_args()

    # Determine platforms
    do_android = not args.ios_only
    do_ios = not args.android_only

    # Local build mode
    if args.local:
        update_from_local(args.local, android=do_android, ios=do_ios)
        return

    # GitHub release mode
    try:
        run_cmd(["gh", "--version"])
    except FileNotFoundError:
        print("Error: GitHub CLI (gh) not found. Install it: https://cli.github.com/")
        sys.exit(1)

    if args.version:
        version = args.version.lstrip("v")
    else:
        version = get_latest_release_version()

    print(f"\n{'='*50}")
    print(f"Updating CIRISVerify to v{version}")
    print(f"{'='*50}\n")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        checksums = {}
        if not args.skip_checksums:
            try:
                checksum_file = download_checksums(version, tmpdir)
                checksums = parse_checksums(checksum_file)
                print(f"  Loaded {len(checksums)} checksums")
            except Exception as e:
                print(f"  Could not load checksums: {e}")

        if do_android:
            android_dir = tmpdir / "android_dl"
            android_dir.mkdir()
            tarball = download_release(version, android_dir, platform="android")
            extract_dir = tmpdir / "android_extracted"
            extract_dir.mkdir()
            extract_tarball(tarball, extract_dir)
            update_android_binaries(extract_dir, checksums)

        if do_ios:
            ios_dir = tmpdir / "ios_dl"
            ios_dir.mkdir()
            try:
                ios_tarball = download_release(version, ios_dir, platform="ios")
                ios_extract_dir = tmpdir / "ios_extracted"
                ios_extract_dir.mkdir()
                extract_tarball(ios_tarball, ios_extract_dir)
                update_ios_from_release(version, ios_extract_dir, checksums)
                sync_ios_adapter()
            except FileNotFoundError:
                print("\n  iOS tarball not found in release.")
                print("  For iOS, use --local with a CIRISVerify build:")
                print("  python -m tools.update_ciris_verify --local /path/to/CIRISVerify --ios-only")

        # Python bindings (shared between platforms)
        update_python_bindings(version, tmpdir)

    if do_ios and not args.no_zip:
        rebuild_resources_zip()

    print(f"\n{'='*50}")
    print(f"CIRISVerify updated to v{version}")
    print(f"{'='*50}")

    if do_android:
        print("\nAndroid next steps:")
        print("  1. cd mobile && ./gradlew :androidApp:assembleDebug")
        print("  2. adb install -r androidApp/build/outputs/apk/debug/androidApp-debug.apk")

    if do_ios:
        print("\niOS next steps:")
        print("  1. Bump CFBundleVersion in Info.plist")
        print("  2. Build and deploy to device")


if __name__ == "__main__":
    main()
