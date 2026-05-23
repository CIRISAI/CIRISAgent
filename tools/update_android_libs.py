#!/usr/bin/env python3
"""
Update CIRIS Android native libraries from GitHub Releases.

Counterpart to ``tools/update_ios_libs.py``. Same library registry shape,
same arguments — Android-side paths and packaging instead of iOS.

Handles: ciris-verify, ciris-persist (and future: ciris-edge, ciris-lenscore,
ciris-nodecore).

Each library follows the same pattern:
  1. Download Android tarball from GitHub Release
  2. Copy per-ABI .so files into client/androidApp/src/main/jniLibs/{abi}/
  3. Update agent-side Python bindings from PyPI wheel (when has_adapter)
  4. Update __version__ in the agent's adapter ffi_bindings/__init__.py

Android does NOT need:
  - XCFramework building (iOS-only concept)
  - .fwork redirects (BeeWare iOS-only convention)
  - Resources.zip rebuild (Chaquopy bundles at gradle build time, no zip)

Usage:
    python -m tools.update_android_libs                          # Update all to pinned versions
    python -m tools.update_android_libs --lib verify 3.0.1       # Update single lib
    python -m tools.update_android_libs --lib persist 2.0.5      # Update persist
    python -m tools.update_android_libs --skip-bindings          # Only refresh .so files
"""

import argparse
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

REPO_ROOT = Path(__file__).parent.parent
CLIENT_ROOT = REPO_ROOT / "client"
ANDROID_APP_DIR = CLIENT_ROOT / "androidApp"
JNI_LIBS_DIR = ANDROID_APP_DIR / "src" / "main" / "jniLibs"


@dataclass
class AndroidLib:
    """Definition of an Android native library.

    Mirrors ``update_ios_libs.IOSLib`` but uses the per-ABI JNI layout
    Android requires and skips iOS-only packaging stages.
    """

    name: str  # e.g. "verify", "persist"
    github_repo: str  # e.g. "CIRISAI/CIRISVerify"
    pypi_package: str  # e.g. "ciris-verify"
    tarball_prefix: str  # e.g. "ciris-verify"
    so_filename: str  # e.g. "libciris_verify_ffi.so" or "libciris_persist.so"
    bindings_package: str  # e.g. "ciris_verify" (PyPI wheel top-level package)
    # ABIs this library publishes Android binaries for. The tarball layout
    # is android/{abi}/{so_filename} for each entry in this list.
    abis: List[str] = field(default_factory=lambda: ["arm64-v8a", "x86_64", "armeabi-v7a"])
    # PyO3 modules expose Python imports; ctypes FFI libs do not. Android
    # doesn't need to branch on this for placement (.so → jniLibs either way),
    # but we keep the flag for symmetry with the iOS script.
    is_pyo3: bool = False
    # Whether this lib has an in-tree adapter under ciris_adapters/. When True,
    # the wheel's .py / .pyi files are extracted into
    # ciris_adapters/{adapter_name}/ffi_bindings/ and __version__ is bumped.
    has_adapter: bool = True
    adapter_name: Optional[str] = None  # defaults to bindings_package


# Library definitions — add new libs here.
LIBS: Dict[str, AndroidLib] = {
    "verify": AndroidLib(
        name="verify",
        github_repo="CIRISAI/CIRISVerify",
        pypi_package="ciris-verify",
        tarball_prefix="ciris-verify",
        so_filename="libciris_verify_ffi.so",
        bindings_package="ciris_verify",
        abis=["arm64-v8a", "x86_64", "armeabi-v7a"],
        has_adapter=True,
        adapter_name="ciris_verify",
    ),
    "persist": AndroidLib(
        name="persist",
        github_repo="CIRISAI/CIRISPersist",
        pypi_package="ciris-persist",
        tarball_prefix="ciris-persist",
        so_filename="libciris_persist.so",
        bindings_package="ciris_persist",
        # CIRISPersist's Android tarball ships arm64-v8a + x86_64 only —
        # PyO3 wheels typically skip 32-bit ARM. armeabi-v7a is intentionally
        # absent from the upstream release artifact.
        abis=["arm64-v8a", "x86_64"],
        is_pyo3=True,
        has_adapter=False,
    ),
    # Future:
    # "edge": AndroidLib(...),
    # "lenscore": AndroidLib(...),
    # "nodecore": AndroidLib(...),
}


def run_cmd(cmd: List[str], check: bool = True) -> subprocess.CompletedProcess:
    print(f"  $ {' '.join(cmd)}")
    return subprocess.run(cmd, capture_output=True, text=True, check=check)


def get_pinned_version(pypi_package: str) -> Optional[str]:
    """Extract the pinned version floor from requirements.txt.

    Identical contract to ``update_ios_libs.get_pinned_version`` — keep in
    sync so a single ``--lib X 1.2.3`` invocation behaves the same on either
    platform's script.
    """
    req_file = REPO_ROOT / "requirements.txt"
    if not req_file.exists():
        return None
    for line in req_file.read_text().splitlines():
        if line.strip().startswith(pypi_package):
            match = re.search(r">=(\d+\.\d+\.\d+)", line)
            if match:
                return match.group(1)
    return None


def download_android_tarball(lib: AndroidLib, version: str, dest_dir: Path) -> Optional[Path]:
    """Download Android tarball from GitHub Release.

    Tries both `{prefix}-v{version}-android.tar.gz` and
    `{prefix}-{version}-android.tar.gz` (release-asset naming conventions
    vary between repos).
    """
    tag = f"v{version}"
    patterns = [
        f"{lib.tarball_prefix}-v{version}-android.tar.gz",
        f"{lib.tarball_prefix}-{version}-android.tar.gz",
    ]
    for pattern in patterns:
        print(f"  Trying {pattern}...")
        run_cmd(
            [
                "gh", "release", "download", tag,
                "--repo", lib.github_repo,
                "--pattern", pattern,
                "--dir", str(dest_dir),
            ],
            check=False,
        )
        for f in dest_dir.iterdir():
            if f.suffix == ".gz" and "android" in f.name.lower():
                print(f"  Downloaded: {f.name}")
                return f
    return None


def install_jni_libs(lib: AndroidLib, extract_dir: Path) -> bool:
    """Copy per-ABI .so files from extracted tarball into the Android app.

    Tarball layout: ``android/{abi}/{so_filename}``.
    Destination:    ``client/androidApp/src/main/jniLibs/{abi}/{so_filename}``.
    """
    print(f"\n  Installing JNI libs for {lib.name}...")
    any_installed = False
    for abi in lib.abis:
        src = extract_dir / "android" / abi / lib.so_filename
        if not src.exists():
            # Try with no leading 'android/' wrapper too — older tarballs
            # occasionally shipped flat.
            alt = extract_dir / abi / lib.so_filename
            if alt.exists():
                src = alt
            else:
                print(f"  {abi}: MISSING ({src.relative_to(extract_dir)}) — skipping")
                continue

        dest_dir = JNI_LIBS_DIR / abi
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest = dest_dir / lib.so_filename
        shutil.copy2(src, dest)
        size_mb = dest.stat().st_size / 1024 / 1024
        print(f"  {abi}: {dest.relative_to(REPO_ROOT)} ({size_mb:.1f}MB)")
        any_installed = True

    if not any_installed:
        print(f"  ERROR: No JNI libs installed for {lib.name}")
        return False
    return True


def update_python_bindings(lib: AndroidLib, version: str) -> bool:
    """Extract the wheel's Python bindings into the agent's adapter dir.

    Only runs when ``lib.has_adapter`` is True — keeps in sync with the iOS
    script, which puts the same files at ``client/iosApp/Resources/app_packages``.
    The agent-side ``ciris_adapters/{adapter_name}/ffi_bindings/`` location is
    shared across platforms (only the .so changes per platform).
    """
    if not lib.has_adapter or not lib.adapter_name:
        print(f"\n  Skipping Python bindings for {lib.name} (no in-tree adapter)")
        return True

    print(f"\n  Updating Python bindings from PyPI ({lib.pypi_package}=={version})...")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)
        run_cmd(
            [
                sys.executable, "-m", "pip", "download",
                f"{lib.pypi_package}=={version}",
                "--no-deps",
                "-d", str(tmpdir),
            ],
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

        # Agent-managed __init__.py / client.py are skipped — the agent ships
        # enhanced versions; only their __version__ is bumped by
        # update_version_string() below. Same exclude-list as update_ios_libs.
        agent_managed = {"__init__.py", "client.py"}

        pkg_dir = REPO_ROOT / "ciris_adapters" / lib.adapter_name / "ffi_bindings"
        pkg_dir.mkdir(parents=True, exist_ok=True)

        with zipfile.ZipFile(wheel, "r") as zf:
            for name in zf.namelist():
                if not name.startswith(f"{lib.bindings_package}/"):
                    continue
                if not (name.endswith(".py") or name.endswith(".pyi")):
                    continue
                basename = Path(name).name
                if basename in agent_managed:
                    print(f"  -> {basename} (SKIPPED — agent-managed enhanced version)")
                    continue
                (pkg_dir / basename).write_bytes(zf.read(name))
                print(f"  -> {basename}")

        # py.typed marker so mypy picks up the .pyi stubs.
        (pkg_dir / "py.typed").touch()

    return True


def update_version_string(lib: AndroidLib, version: str) -> None:
    """Update ``__version__`` in the adapter's ffi_bindings/__init__.py.

    Mirrors update_ios_libs.update_version_string but skips the iOS Resources
    copy (Android doesn't keep a per-platform mirror of the adapter __init__).
    """
    if not lib.has_adapter or not lib.adapter_name:
        return

    init_path = REPO_ROOT / "ciris_adapters" / lib.adapter_name / "ffi_bindings" / "__init__.py"
    if not init_path.exists():
        return

    content = init_path.read_text()
    new_content = re.sub(
        r'__version__\s*=\s*"[^"]+"',
        f'__version__ = "{version}"',
        content,
    )
    if new_content != content:
        init_path.write_text(new_content)
        print(f"  Updated __version__ in {init_path.relative_to(REPO_ROOT)}")


def verify_so_version(lib: AndroidLib, version: str) -> bool:
    """Verify each per-ABI .so embeds the expected version string.

    Same idea as ``update_ios_libs.verify_dylib_version`` — best-effort
    ``strings`` grep. A library that doesn't embed its version literally
    won't fail the run; it just won't print a ✓.
    """
    all_ok = True
    for abi in lib.abis:
        so = JNI_LIBS_DIR / abi / lib.so_filename
        if not so.exists():
            print(f"  ✗ {lib.name}/{abi}: {lib.so_filename} missing")
            all_ok = False
            continue
        result = subprocess.run(["strings", str(so)], capture_output=True, text=True)
        if any(line.strip() == version for line in result.stdout.splitlines()):
            print(f"  ✓ {lib.name}/{abi}: {lib.so_filename} embeds v{version}")
        else:
            # Some libs don't include a literal version string in the .so —
            # don't fail solely on that. Report it and move on.
            print(
                f"  ? {lib.name}/{abi}: {lib.so_filename} does not contain "
                f"literal '{version}' (may be normal — verify the build "
                f"contract before relying on this)"
            )
    return all_ok


def update_lib(lib: AndroidLib, version: str, skip_bindings: bool = False) -> bool:
    """Full update flow for a single library."""
    print(f"\n{'='*60}")
    print(f"  Updating {lib.name} to v{version} (Android)")
    print(f"  Repo: {lib.github_repo}")
    print(f"{'='*60}")

    with tempfile.TemporaryDirectory() as dl_dir:
        dl_dir = Path(dl_dir)

        tarball = download_android_tarball(lib, version, dl_dir)
        if not tarball:
            print(f"  ERROR: Failed to download Android tarball")
            return False

        extract_dir = dl_dir / "extracted"
        extract_dir.mkdir()
        run_cmd(["tar", "-xzf", str(tarball), "-C", str(extract_dir)])

        if not install_jni_libs(lib, extract_dir):
            return False

    if not skip_bindings:
        update_python_bindings(lib, version)
        update_version_string(lib, version)

    return True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Update CIRIS Android native libraries (counterpart to update_ios_libs)",
    )
    parser.add_argument("--lib", choices=list(LIBS.keys()), help="Update a specific library")
    parser.add_argument(
        "version",
        nargs="?",
        help="Version to update to (default: from requirements.txt)",
    )
    parser.add_argument(
        "--skip-bindings",
        action="store_true",
        help="Skip Python bindings + __version__ refresh (only update jniLibs)",
    )
    args = parser.parse_args()

    if args.lib:
        lib = LIBS[args.lib]
        version = args.version or get_pinned_version(lib.pypi_package)
        if not version:
            print(f"ERROR: No version specified and no pin found for {lib.pypi_package}")
            sys.exit(1)
        if not update_lib(lib, version, skip_bindings=args.skip_bindings):
            sys.exit(1)
        targets = [(args.lib, lib)]
    else:
        targets = []
        for name, lib in LIBS.items():
            version = args.version or get_pinned_version(lib.pypi_package)
            if not version:
                print(f"  SKIP {name}: no version pin found")
                continue
            update_lib(lib, version, skip_bindings=args.skip_bindings)
            targets.append((name, lib))

    print(f"\nVerifying bundled .so files embed expected versions...")
    all_ok = True
    for _, lib in targets:
        version = args.version or get_pinned_version(lib.pypi_package)
        if version and not verify_so_version(lib, version):
            all_ok = False

    print(f"\n{'='*60}")
    if all_ok:
        print(f"  All Android libraries updated successfully")
    else:
        print(f"  WARNING: Some .so files missing or unverifiable")
    print(f"{'='*60}")

    print("\nAndroid next steps:")
    print("  1. cd client && ./gradlew :androidApp:assembleDebug")
    print("  2. adb shell am force-stop ai.ciris.mobile.debug")
    print("  3. adb install -r androidApp/build/outputs/apk/debug/androidApp-debug.apk")

    if not all_ok:
        sys.exit(1)


if __name__ == "__main__":
    main()
