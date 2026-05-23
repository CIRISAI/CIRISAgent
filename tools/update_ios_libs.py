#!/usr/bin/env python3
"""
Update CIRIS iOS native libraries from GitHub Releases.

Handles: ciris-verify, ciris-persist (and future: ciris-edge, ciris-lenscore, ciris-nodecore)

Each library follows the same pattern:
  1. Download iOS tarball from GitHub Release
  2. Build XCFramework from device + simulator dylibs
  3. Copy fallback dylib into Resources/app_packages/{name}/
  4. Update Python bindings from PyPI wheel
  5. Rebuild Resources.zip

Usage:
    python -m tools.update_ios_libs                          # Update all to pinned versions
    python -m tools.update_ios_libs --lib verify 3.0.1       # Update single lib
    python -m tools.update_ios_libs --lib persist 2.0.3      # Update persist
    python -m tools.update_ios_libs --rebuild-zip-only        # Just rebuild Resources.zip
"""

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional

REPO_ROOT = Path(__file__).parent.parent
CLIENT_ROOT = REPO_ROOT / "client"
IOS_APP_DIR = CLIENT_ROOT / "iosApp"
IOS_FRAMEWORKS_DIR = IOS_APP_DIR / "Frameworks"
IOS_RESOURCES_DIR = IOS_APP_DIR / "Resources"


@dataclass
class IOSLib:
    """Definition of an iOS native library."""
    name: str                    # e.g. "verify", "persist"
    github_repo: str             # e.g. "CIRISAI/CIRISVerify"
    pypi_package: str            # e.g. "ciris-verify"
    framework_name: str          # e.g. "CIRISVerify"
    ffi_lib_name: str            # e.g. "libciris_verify_ffi"
    tarball_prefix: str          # e.g. "ciris-verify"
    # Paths within the iOS tarball
    device_dir: str              # e.g. "ios-device" or "ios/aarch64-apple-ios"
    simulator_dir: str           # e.g. "ios-simulator" or "ios/aarch64-apple-ios-sim"
    dylib_filename: str          # e.g. "libciris_verify_ffi.dylib" or "libciris_persist.dylib"
    # Python bindings location
    bindings_package: str        # e.g. "ciris_verify"
    # PyO3 modules load via Python import (app_packages_native + .fwork redirect)
    # ctypes FFI libs load via xcframework embedding
    is_pyo3: bool = False
    # Whether this lib has an adapter in ciris_adapters/
    has_adapter: bool = True
    adapter_name: Optional[str] = None  # defaults to bindings_package


# Library definitions — add new libs here
LIBS: Dict[str, IOSLib] = {
    "verify": IOSLib(
        name="verify",
        github_repo="CIRISAI/CIRISVerify",
        pypi_package="ciris-verify",
        framework_name="CIRISVerify",
        ffi_lib_name="libciris_verify_ffi",
        tarball_prefix="ciris-verify",
        device_dir="ios/aarch64-apple-ios",
        simulator_dir="ios/aarch64-apple-ios-sim",
        dylib_filename="libciris_verify_ffi.dylib",
        bindings_package="ciris_verify",
        has_adapter=True,
        adapter_name="ciris_verify",
    ),
    "persist": IOSLib(
        name="persist",
        github_repo="CIRISAI/CIRISPersist",
        pypi_package="ciris-persist",
        framework_name="CIRISPersist",
        ffi_lib_name="ciris_persist",
        tarball_prefix="ciris-persist",
        device_dir="ios-device",
        simulator_dir="ios-simulator",
        dylib_filename="ciris_persist.abi3.so",  # PyO3 module, not ctypes FFI
        bindings_package="ciris_persist",
        is_pyo3=True,  # Loads via Python import, not xcframework
        has_adapter=False,
    ),
    # Future:
    # "edge": IOSLib(...),
    # "lenscore": IOSLib(...),
    # "nodecore": IOSLib(...),
}


def run_cmd(cmd: List[str], check: bool = True) -> subprocess.CompletedProcess:
    print(f"  $ {' '.join(cmd)}")
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def get_pinned_version(pypi_package: str) -> Optional[str]:
    """Extract the pinned version floor from requirements.txt."""
    req_file = REPO_ROOT / "requirements.txt"
    if not req_file.exists():
        return None
    for line in req_file.read_text().splitlines():
        if line.strip().startswith(pypi_package):
            match = re.search(r">=(\d+\.\d+\.\d+)", line)
            if match:
                return match.group(1)
    return None


def download_ios_tarball(lib: IOSLib, version: str, dest_dir: Path) -> Optional[Path]:
    """Download iOS tarball from GitHub Release."""
    tag = f"v{version}"
    patterns = [
        f"{lib.tarball_prefix}-v{version}-ios.tar.gz",
        f"{lib.tarball_prefix}-{version}-ios.tar.gz",
    ]
    for pattern in patterns:
        print(f"  Trying {pattern}...")
        result = run_cmd(
            ["gh", "release", "download", tag, "--repo", lib.github_repo,
             "--pattern", pattern, "--dir", str(dest_dir)],
            check=False,
        )
        for f in dest_dir.iterdir():
            if f.suffix == ".gz" and "ios" in f.name.lower():
                print(f"  Downloaded: {f.name}")
                return f
    return None


def build_xcframework(lib: IOSLib, extract_dir: Path, version: str) -> bool:
    """Build XCFramework from extracted iOS tarball."""
    print(f"\n  Building {lib.framework_name}.xcframework...")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        for label, src_subdir, xcfw_slice in [
            ("device", lib.device_dir, "ios-arm64"),
            ("simulator", lib.simulator_dir, "ios-arm64-simulator"),
        ]:
            src_dylib = extract_dir / src_subdir / lib.dylib_filename
            if not src_dylib.exists():
                print(f"  {label}: dylib not found at {src_dylib}")
                # Try without subdirectory
                src_dylib = extract_dir / lib.dylib_filename
                if not src_dylib.exists():
                    print(f"  {label}: MISSING — skipping")
                    continue

            size_mb = src_dylib.stat().st_size / 1024 / 1024
            print(f"  {label}: using dylib ({size_mb:.1f}MB)")

            # Create framework bundle
            platform = "iPhoneOS" if label == "device" else "iPhoneSimulator"
            fw_dir = tmpdir / xcfw_slice / f"{lib.framework_name}.framework"
            fw_dir.mkdir(parents=True)
            (fw_dir / "Headers").mkdir()

            shutil.copy2(src_dylib, fw_dir / lib.framework_name)

            # Set install name
            expected_id = f"@rpath/{lib.framework_name}.framework/{lib.framework_name}"
            current = run_cmd(["otool", "-D", str(fw_dir / lib.framework_name)], check=False)
            if expected_id not in (current.stdout or ""):
                run_cmd(["install_name_tool", "-id", expected_id, str(fw_dir / lib.framework_name)])
                print(f"  {label}: set install name")
            else:
                print(f"  {label}: install name correct")

            # Info.plist
            plist = f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key><string>{lib.framework_name}</string>
    <key>CFBundleIdentifier</key><string>ai.ciris.{lib.name}</string>
    <key>CFBundlePackageType</key><string>FMWK</string>
    <key>CFBundleShortVersionString</key><string>{version}</string>
    <key>MinimumOSVersion</key><string>16.0</string>
    <key>CFBundleSupportedPlatforms</key>
    <array><string>{platform}</string></array>
</dict>
</plist>"""
            (fw_dir / "Info.plist").write_text(plist)
            print(f"  {label}: framework prepared")

        # Build XCFramework
        fw_args = []
        for slice_name in ["ios-arm64", "ios-arm64-simulator"]:
            fw = tmpdir / slice_name / f"{lib.framework_name}.framework"
            if fw.exists():
                fw_args.extend(["-framework", str(fw)])

        if not fw_args:
            print(f"  ERROR: No frameworks produced for {lib.framework_name}")
            return False

        xcfw_dest = IOS_FRAMEWORKS_DIR / f"{lib.framework_name}.xcframework"
        if xcfw_dest.exists():
            shutil.rmtree(xcfw_dest)

        result = run_cmd(
            ["xcodebuild", "-create-xcframework"] + fw_args + ["-output", str(xcfw_dest)],
            check=False,
        )
        if result.returncode != 0:
            print(f"  ERROR: xcodebuild failed: {result.stderr}")
            return False

        print(f"  -> XCFramework: {xcfw_dest.relative_to(REPO_ROOT)}")

        # Copy device dylib as fallback
        device_dylib = None
        for slice_name in ["ios-arm64"]:
            fw = tmpdir / slice_name / f"{lib.framework_name}.framework" / lib.framework_name
            if fw.exists():
                device_dylib = fw
                break

        if device_dylib:
            pkg_dir = IOS_RESOURCES_DIR / "app_packages" / lib.bindings_package
            pkg_dir.mkdir(parents=True, exist_ok=True)
            dest = pkg_dir / lib.dylib_filename
            shutil.copy2(device_dylib, dest)
            size_mb = dest.stat().st_size / 1024 / 1024
            print(f"  -> Fallback dylib: {dest.name} ({size_mb:.1f}MB)")

    return True


def bundle_pyo3_module(lib: IOSLib, extract_dir: Path, version: str) -> bool:
    """Bundle a PyO3 extension module for iOS.

    PyO3 modules load via Python's import mechanism, NOT xcframework.
    The .abi3.so goes into app_packages_native/{name}/ and a .fwork
    redirect in Resources/app_packages/{name}/ tells BeeWare's Python
    where to find the framework-wrapped binary at runtime.

    The embed_native_frameworks.sh build script converts the .so into
    a signed .framework bundle during xcodebuild.
    """
    print(f"\n  Bundling PyO3 module for {lib.name}...")

    device_so = extract_dir / lib.device_dir / lib.dylib_filename
    if not device_so.exists():
        print(f"  ERROR: {lib.dylib_filename} not found in {lib.device_dir}")
        return False

    size_mb = device_so.stat().st_size / 1024 / 1024
    print(f"  Device .so: {size_mb:.1f}MB")

    # 1. Copy to app_packages_native (embed script picks it up at build time)
    native_dir = IOS_APP_DIR / "app_packages_native" / lib.bindings_package
    native_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(device_so, native_dir / lib.dylib_filename)
    print(f"  -> app_packages_native/{lib.bindings_package}/{lib.dylib_filename}")

    # 2. Create .fwork redirect in Resources/app_packages
    # The framework name follows BeeWare convention: {package}.{module}.framework
    pkg_dir = IOS_RESOURCES_DIR / "app_packages" / lib.bindings_package
    pkg_dir.mkdir(parents=True, exist_ok=True)

    # Remove any bare .so (must go through framework pipeline)
    bare_so = pkg_dir / lib.dylib_filename
    if bare_so.exists():
        bare_so.unlink()

    # .fwork content: path to the framework binary inside Frameworks/
    fw_name = f"{lib.bindings_package}.{lib.bindings_package}"
    fwork_content = f"Frameworks/{fw_name}.framework/{fw_name}"
    fwork_file = pkg_dir / f"{lib.dylib_filename.replace('.so', '.fwork')}"
    fwork_file.write_text(fwork_content)
    print(f"  -> {fwork_file.name} → {fwork_content}")

    return True


def update_python_bindings(lib: IOSLib, version: str) -> bool:
    """Update Python bindings from PyPI wheel."""
    print(f"\n  Updating Python bindings from PyPI ({lib.pypi_package}=={version})...")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        result = run_cmd(
            [sys.executable, "-m", "pip", "download",
             f"{lib.pypi_package}=={version}", "--no-deps", "-d", str(tmpdir)],
            check=False,
        )

        wheel = None
        for f in tmpdir.iterdir():
            if f.suffix == ".whl":
                wheel = f
                break

        if not wheel:
            print(f"  WARNING: No wheel found for {lib.pypi_package}=={version}")
            return False

        print(f"  Downloaded: {wheel.name}")

        # Extract Python files
        pkg_dir = IOS_RESOURCES_DIR / "app_packages" / lib.bindings_package
        pkg_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(wheel, "r") as zf:
            for name in zf.namelist():
                if name.startswith(f"{lib.bindings_package}/") and (name.endswith(".py") or name.endswith(".pyi")):
                    basename = Path(name).name
                    content = zf.read(name)
                    (pkg_dir / basename).write_bytes(content)
                    print(f"  -> {basename}")

        # Ensure py.typed marker
        (pkg_dir / "py.typed").touch()

    return True


def update_version_string(lib: IOSLib, version: str) -> None:
    """Update __version__ in the agent's ffi_bindings __init__.py."""
    # Agent-managed copy
    agent_init = REPO_ROOT / "ciris_adapters" / lib.adapter_name / "ffi_bindings" / "__init__.py"
    if agent_init.exists():
        content = agent_init.read_text()
        new_content = re.sub(r'__version__\s*=\s*"[^"]+"', f'__version__ = "{version}"', content)
        if new_content != content:
            agent_init.write_text(new_content)
            print(f"  Updated __version__ in {agent_init.relative_to(REPO_ROOT)}")

    # iOS Resources copy
    ios_init = IOS_RESOURCES_DIR / "app" / "ciris_adapters" / (lib.adapter_name or lib.bindings_package) / "ffi_bindings" / "__init__.py"
    if ios_init.exists():
        content = ios_init.read_text()
        new_content = re.sub(r'__version__\s*=\s*"[^"]+"', f'__version__ = "{version}"', content)
        if new_content != content:
            ios_init.write_text(new_content)
            print(f"  Updated __version__ in iOS Resources copy")


def rebuild_resources_zip() -> None:
    """Rebuild Resources.zip from Resources directory."""
    print("\nRebuilding Resources.zip...")
    zip_path = IOS_APP_DIR / "Resources.zip"
    zip_path.unlink(missing_ok=True)
    run_cmd(["zip", "-q", "-r", str(zip_path), "."], check=True)
    size_mb = zip_path.stat().st_size / 1024 / 1024
    print(f"  -> Resources.zip ({size_mb:.1f}MB)")


def verify_dylib_version(lib: IOSLib, version: str) -> bool:
    """Verify the native library contains the expected version string."""
    if lib.is_pyo3:
        dylib = IOS_APP_DIR / "app_packages_native" / lib.bindings_package / lib.dylib_filename
    else:
        dylib = IOS_RESOURCES_DIR / "app_packages" / lib.bindings_package / lib.dylib_filename
    if not dylib.exists():
        print(f"  ✗ Native library missing: {dylib.name}")
        return False

    result = subprocess.run(["strings", str(dylib)], capture_output=True, text=True)
    for line in result.stdout.splitlines():
        if line.strip() == version:
            print(f"  ✓ {lib.name}: {dylib.name} embeds v{version}")
            return True

    print(f"  ✗ {lib.name}: {dylib.name} does NOT contain version string '{version}'")
    return False


def update_lib(lib: IOSLib, version: str) -> bool:
    """Full update flow for a single library."""
    print(f"\n{'='*60}")
    print(f"  Updating {lib.name} to v{version}")
    print(f"  Repo: {lib.github_repo}")
    print(f"{'='*60}")

    with tempfile.TemporaryDirectory() as dl_dir:
        dl_dir = Path(dl_dir)

        # Download
        tarball = download_ios_tarball(lib, version, dl_dir)
        if not tarball:
            print(f"  ERROR: Failed to download iOS tarball")
            return False

        # Extract
        extract_dir = dl_dir / "extracted"
        extract_dir.mkdir()
        run_cmd(["tar", "-xzf", str(tarball), "-C", str(extract_dir)])

        # Bundle native library
        if lib.is_pyo3:
            # PyO3: .abi3.so → app_packages_native + .fwork redirect
            if not bundle_pyo3_module(lib, extract_dir, version):
                return False
        else:
            # ctypes FFI: build xcframework + fallback dylib
            if not build_xcframework(lib, extract_dir, version):
                return False

    # Python bindings
    update_python_bindings(lib, version)

    # Version strings
    if lib.has_adapter and lib.adapter_name:
        update_version_string(lib, version)

    return True


def main():
    parser = argparse.ArgumentParser(description="Update CIRIS iOS native libraries")
    parser.add_argument("--lib", choices=list(LIBS.keys()), help="Update a specific library")
    parser.add_argument("version", nargs="?", help="Version to update to (default: from requirements.txt)")
    parser.add_argument("--rebuild-zip-only", action="store_true", help="Only rebuild Resources.zip")
    parser.add_argument("--skip-checksums", action="store_true", help="Skip checksum verification")
    args = parser.parse_args()

    if args.rebuild_zip_only:
        import os
        os.chdir(IOS_RESOURCES_DIR)
        rebuild_resources_zip()
        return

    if args.lib:
        # Single library update
        lib = LIBS[args.lib]
        version = args.version or get_pinned_version(lib.pypi_package)
        if not version:
            print(f"ERROR: No version specified and couldn't find pin in requirements.txt")
            sys.exit(1)

        success = update_lib(lib, version)
        if not success:
            sys.exit(1)
    else:
        # Update all libraries
        for name, lib in LIBS.items():
            version = args.version or get_pinned_version(lib.pypi_package)
            if not version:
                print(f"  SKIP {name}: no version pin found")
                continue
            update_lib(lib, version)

    # Rebuild zip
    import os
    os.chdir(IOS_RESOURCES_DIR)
    rebuild_resources_zip()

    # Verify
    print(f"\nVerifying bundled binaries...")
    all_ok = True
    for name, lib in ([(args.lib, LIBS[args.lib])] if args.lib else LIBS.items()):
        version = args.version or get_pinned_version(lib.pypi_package)
        if version and not verify_dylib_version(lib, version):
            all_ok = False

    if all_ok:
        print(f"\n{'='*60}")
        print(f"  All iOS libraries updated successfully")
        print(f"{'='*60}")
    else:
        print(f"\n  WARNING: Some verifications failed")
        sys.exit(1)


if __name__ == "__main__":
    main()
