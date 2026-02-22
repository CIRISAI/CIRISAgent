#!/usr/bin/env python3
"""
Update CIRISVerify binaries and Python bindings from GitHub releases and PyPI.

Usage:
    python -m tools.update_ciris_verify [version]

Examples:
    python -m tools.update_ciris_verify 0.6.7
    python -m tools.update_ciris_verify  # Uses latest release
"""

import argparse
import hashlib
import os
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
JNI_LIBS_DIR = MOBILE_ROOT / "androidApp" / "src" / "main" / "jniLibs"
PYTHON_DIR = MOBILE_ROOT / "androidApp" / "src" / "main" / "python" / "ciris_verify"

# Android architectures mapping
ANDROID_ARCHS = {
    "arm64-v8a": "android/arm64-v8a/libciris_verify_ffi.so",
    "x86_64": "android/x86_64/libciris_verify_ffi.so",
    "armeabi-v7a": "android/armeabi-v7a/libciris_verify_ffi.so",
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
    # Remove 'v' prefix if present
    if version.startswith("v"):
        version = version[1:]
    return version


def download_release(version: str, dest_dir: Path) -> Path:
    """Download Android release tarball from GitHub."""
    tag = f"v{version}"

    # Try versioned name first (new format), then legacy name
    asset_patterns = [
        f"ciris-verify-v{version}-android.tar.gz",  # New format: ciris-verify-v0.5.5-android.tar.gz
        f"ciris-verify-{version}-android.tar.gz",  # Alt format without 'v'
        "ciris-verify-ffi.tar.gz",  # Legacy format
    ]

    for pattern in asset_patterns:
        dest_file = dest_dir / pattern.replace("*", "")
        print(f"Trying to download {pattern} from release {tag}...")
        result = run_cmd(
            ["gh", "release", "download", tag, "--repo", GITHUB_REPO, "--pattern", pattern, "--dir", str(dest_dir)],
            check=False,
        )

        # Find the downloaded file
        for f in dest_dir.iterdir():
            if f.suffix == ".gz" and "android" in f.name.lower():
                print(f"  ✓ Downloaded: {f.name}")
                return f
            elif f.name == "ciris-verify-ffi.tar.gz":
                print(f"  ✓ Downloaded: {f.name}")
                return f

    raise FileNotFoundError(f"Failed to download Android tarball from release {tag}")


def download_checksums(version: str, dest_dir: Path) -> Path:
    """Download SHA256SUMS from GitHub release."""
    tag = f"v{version}"
    dest_file = dest_dir / "SHA256SUMS"

    print("Downloading SHA256SUMS...")
    run_cmd(
        ["gh", "release", "download", tag, "--repo", GITHUB_REPO, "--pattern", "SHA256SUMS", "--dir", str(dest_dir)]
    )

    return dest_file


def verify_checksum(file_path: Path, expected_hash: str) -> bool:
    """Verify SHA256 checksum of a file."""
    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256.update(chunk)
    actual_hash = sha256.hexdigest()
    return actual_hash == expected_hash


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
                # Normalize path (remove ./ prefix)
                path = path.lstrip("./")
                checksums[path] = hash_val
    return checksums


def extract_tarball(tarball: Path, dest_dir: Path) -> None:
    """Extract tarball to destination directory."""
    print(f"Extracting {tarball.name}...")
    run_cmd(["tar", "-xzf", str(tarball), "-C", str(dest_dir)])


def update_android_binaries(extract_dir: Path, checksums: dict[str, str]) -> None:
    """Copy Android binaries to jniLibs directory."""
    print("\nUpdating Android binaries...")

    for arch, src_path in ANDROID_ARCHS.items():
        src_file = extract_dir / src_path
        dest_dir = JNI_LIBS_DIR / arch
        dest_file = dest_dir / "libciris_verify_ffi.so"

        if not src_file.exists():
            print(f"  ⚠ Missing: {src_path}")
            continue

        # Verify checksum
        checksum_key = src_path
        if checksum_key in checksums:
            if verify_checksum(src_file, checksums[checksum_key]):
                print(f"  ✓ {arch}: checksum verified")
            else:
                print(f"  ✗ {arch}: CHECKSUM MISMATCH!")
                raise ValueError(f"Checksum mismatch for {src_path}")
        else:
            print(f"  ? {arch}: no checksum available")

        # Create dest dir if needed
        dest_dir.mkdir(parents=True, exist_ok=True)

        # Copy binary
        shutil.copy2(src_file, dest_file)
        print(f"  → Copied to {dest_file.relative_to(REPO_ROOT)}")


def update_python_bindings(version: str, tmpdir: Path) -> None:
    """Download and extract Python bindings from PyPI."""
    print(f"\nUpdating Python bindings from PyPI...")

    # Download wheel from PyPI
    wheel_name = f"ciris_verify-{version}-py3-none-manylinux_2_17_x86_64.whl"
    wheel_path = tmpdir / wheel_name

    result = run_cmd(["pip", "download", f"ciris-verify=={version}", "--no-deps", "-d", str(tmpdir)], check=False)

    # Find downloaded wheel (might have different platform suffix)
    wheel_file = None
    for f in tmpdir.iterdir():
        if f.name.startswith(f"ciris_verify-{version}") and f.suffix == ".whl":
            wheel_file = f
            break

    if not wheel_file:
        print(f"  ⚠ Could not download wheel from PyPI for version {version}")
        print(f"  → Falling back to updating version string only")
        update_python_version_string(version)
        return

    print(f"  ✓ Downloaded: {wheel_file.name}")

    # Extract Python files from wheel
    extract_dir = tmpdir / "wheel_extract"
    extract_dir.mkdir()

    with zipfile.ZipFile(wheel_file, "r") as zf:
        for name in zf.namelist():
            if name.startswith("ciris_verify/") and name.endswith(".py"):
                zf.extract(name, extract_dir)
                print(f"  ✓ Extracted: {name}")

    # Copy to project
    src_dir = extract_dir / "ciris_verify"
    if src_dir.exists():
        PYTHON_DIR.mkdir(parents=True, exist_ok=True)
        for py_file in src_dir.glob("*.py"):
            dest_file = PYTHON_DIR / py_file.name
            shutil.copy2(py_file, dest_file)
            print(f"  → Copied {py_file.name} to {dest_file.relative_to(REPO_ROOT)}")
    else:
        print(f"  ⚠ No Python files found in wheel")


def update_python_version_string(version: str) -> None:
    """Update version string in Python __init__.py (fallback)."""
    init_file = PYTHON_DIR / "__init__.py"

    if not init_file.exists():
        print(f"  ⚠ Python init not found: {init_file}")
        return

    content = init_file.read_text()

    # Replace version line
    import re

    new_content = re.sub(r'__version__\s*=\s*"[^"]+"', f'__version__ = "{version}"', content)

    if new_content != content:
        init_file.write_text(new_content)
        print(f'  ✓ Updated __version__ to "{version}"')
    else:
        print(f"  - Version already set to {version}")


def main():
    parser = argparse.ArgumentParser(description="Update CIRISVerify binaries from GitHub releases")
    parser.add_argument("version", nargs="?", help="Version to download (e.g., 0.5.5). Defaults to latest release.")
    parser.add_argument("--skip-checksums", action="store_true", help="Skip checksum verification")
    args = parser.parse_args()

    # Check gh CLI is available
    try:
        run_cmd(["gh", "--version"])
    except FileNotFoundError:
        print("Error: GitHub CLI (gh) not found. Install it: https://cli.github.com/")
        sys.exit(1)

    # Get version
    if args.version:
        version = args.version.lstrip("v")
    else:
        version = get_latest_release_version()

    print(f"\n{'='*50}")
    print(f"Updating CIRISVerify to v{version}")
    print(f"{'='*50}\n")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir = Path(tmpdir)

        # Download release
        tarball = download_release(version, tmpdir)

        # Download and parse checksums
        checksums = {}
        if not args.skip_checksums:
            try:
                checksum_file = download_checksums(version, tmpdir)
                checksums = parse_checksums(checksum_file)
                print(f"  Loaded {len(checksums)} checksums")
            except Exception as e:
                print(f"  ⚠ Could not load checksums: {e}")

        # Extract
        extract_dir = tmpdir / "extracted"
        extract_dir.mkdir()
        extract_tarball(tarball, extract_dir)

        # Update Android binaries
        update_android_binaries(extract_dir, checksums)

        # Update Python bindings from PyPI
        update_python_bindings(version, tmpdir)

    print(f"\n{'='*50}")
    print(f"✓ CIRISVerify updated to v{version}")
    print(f"{'='*50}")
    print("\nNext steps:")
    print("  1. Rebuild the app: cd mobile && ./gradlew :androidApp:assembleDebug")
    print("  2. Install: adb install -r androidApp/build/outputs/apk/debug/androidApp-debug.apk")


if __name__ == "__main__":
    main()
