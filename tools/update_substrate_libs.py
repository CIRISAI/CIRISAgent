#!/usr/bin/env python3
"""
Update CIRIS substrate native libraries (Android + iOS) from GitHub Releases.

Unifies the previously separate ``tools/update_android_libs.py`` and
``tools/update_ios_libs.py`` behind ONE library registry covering both
platforms. Those two scripts remain as thin argparse-compatible wrappers that
delegate here (CI — .github/workflows/refresh-ios-substrate.yml — and docs
keep working unchanged).

Handles the substrate quad: ciris-verify, ciris-persist, ciris-edge,
ciris-lens-core (and future: ciris-nodecore).

NOTE: ``tools/update_ciris_verify.py`` is a SEPARATE, verify-specific tool
with unique mobile-bundle (Resources.zip) behavior — it is intentionally NOT
folded into this script.

Per library, per platform:

Android:
  1. Download ``{prefix}-v{ver}-android.tar.gz`` from the GitHub Release
     (verified against the release's SHA256SUMS asset when one is published)
  2. Copy per-ABI .so files into client/androidApp/src/main/jniLibs/{abi}/
  3. For PyO3 libs the agent must `import`: download
     ``{prefix}-v{ver}-android-wheels.tar.gz`` and drop the Chaquopy-shaped
     wheels into client/androidApp/wheels/ (pruning stale versions), then
     pin ``install "{pkg}=={ver}"`` in client/androidApp/build.gradle
  4. Update agent-side Python bindings from PyPI wheel (when has_adapter)
  5. Update __version__ in the agent's adapter ffi_bindings/__init__.py

iOS:
  1. Download ``{prefix}-v{ver}-ios.tar.gz`` (same SHA256SUMS verification)
  2. ctypes FFI libs (verify): build XCFramework from device + simulator
     dylibs — requires macOS with xcodebuild (CI runs this leg on
     macos-latest via refresh-ios-substrate.yml)
     PyO3 libs (persist/edge/lens): bundle the .abi3.so into
     app_packages_native/ + write the BeeWare .fwork redirect
  3. Update Python bindings into Resources/app_packages/{pkg}/
  4. Repair XCFramework Info.plists (App Store error 90056 guard)
  5. Rebuild Resources.zip

Usage:
    python -m tools.update_substrate_libs                            # all libs, both platforms
    python -m tools.update_substrate_libs --platform android         # all libs, Android only
    python -m tools.update_substrate_libs --platform ios --lib verify 5.1.0
    python -m tools.update_substrate_libs --lib persist 5.2.0        # both platforms
    python -m tools.update_substrate_libs --platform android --skip-bindings

Version defaults to the per-library pin floor in requirements.txt.
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
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).parent.parent
CLIENT_ROOT = REPO_ROOT / "client"

# Android paths
ANDROID_APP_DIR = CLIENT_ROOT / "androidApp"
JNI_LIBS_DIR = ANDROID_APP_DIR / "src" / "main" / "jniLibs"
WHEELS_DIR = ANDROID_APP_DIR / "wheels"
ANDROID_BUILD_GRADLE = ANDROID_APP_DIR / "build.gradle"

# iOS paths
IOS_APP_DIR = CLIENT_ROOT / "iosApp"
IOS_FRAMEWORKS_DIR = IOS_APP_DIR / "Frameworks"
IOS_RESOURCES_DIR = IOS_APP_DIR / "Resources"


class UpdateStatus(str, Enum):
    """Outcome of one (library, platform) update leg."""

    SUCCESS = "success"
    FAILED = "failed"
    # Upstream has not published release artifacts for this platform yet
    # (only set for libs carrying a release_pending_note, e.g. lens).
    PENDING = "pending"


@dataclass
class SubstrateLib:
    """Definition of a substrate native library, covering BOTH platforms.

    Merges the former ``update_android_libs.AndroidLib`` and
    ``update_ios_libs.IOSLib`` registries — one entry per library, platform
    specifics carried side by side.
    """

    name: str  # e.g. "verify", "persist"
    github_repo: str  # e.g. "CIRISAI/CIRISVerify"
    pypi_package: str  # e.g. "ciris-verify"
    tarball_prefix: str  # e.g. "ciris-verify"
    bindings_package: str  # e.g. "ciris_verify" (PyPI wheel top-level package)

    # --- Android ---
    so_filename: str  # e.g. "libciris_verify_ffi.so" or "libciris_persist.so"
    # ABIs this library publishes Android binaries for. The tarball layout
    # is android/{abi}/{so_filename} for each entry in this list.
    abis: List[str] = field(default_factory=lambda: ["arm64-v8a", "x86_64", "armeabi-v7a"])
    # Whether the GitHub release publishes a Chaquopy-shaped Android wheels
    # tarball (`{prefix}-v{version}-android-wheels.tar.gz`) containing one
    # `*-cp310-abi3-android_24_{abi}.whl` per supported ABI. When True the
    # tarball is downloaded and its wheels are dropped into
    # client/androidApp/wheels/ so Chaquopy's `--find-links wheels` resolves
    # them at gradle build time, and the matching `install "{pkg}==X"` pin in
    # client/androidApp/build.gradle is rewritten (or activated). Required
    # for PyO3 libs whose Python module has to be `import`-able from the
    # agent (persist/edge/lens) — vs. ctypes-FFI libs whose .so is loaded
    # directly via JNI (verify), which don't need this.
    has_android_wheels: bool = False

    # --- iOS ---
    framework_name: str = ""  # e.g. "CIRISVerify"
    ffi_lib_name: str = ""  # e.g. "libciris_verify_ffi"
    # Paths within the iOS tarball
    device_dir: str = "ios-device"  # or "ios/aarch64-apple-ios"
    simulator_dir: str = "ios-simulator"  # or "ios/aarch64-apple-ios-sim"
    dylib_filename: str = ""  # e.g. "libciris_verify_ffi.dylib" or "ciris_persist.abi3.so"

    # --- Shared ---
    # PyO3 modules expose Python imports (iOS: app_packages_native + .fwork
    # redirect; Android: Chaquopy wheel); ctypes FFI libs load via
    # xcframework embedding (iOS) / direct JNI (Android).
    is_pyo3: bool = False
    # Whether this lib has an in-tree adapter under ciris_adapters/. When
    # True, the wheel's .py / .pyi files are extracted into
    # ciris_adapters/{adapter_name}/ffi_bindings/ and __version__ is bumped.
    has_adapter: bool = True
    adapter_name: Optional[str] = None  # defaults to bindings_package
    # When set, a 404 on the release/asset download is reported as PENDING
    # with this actionable message ({version}/{platform} are interpolated)
    # instead of a generic download failure. Used for libs whose upstream
    # has not started publishing GitHub release artifacts yet (lens).
    release_pending_note: Optional[str] = None


_LENS_PENDING_NOTE = (
    "CIRISLensCore release artifacts pending (see CIRISAgent#866 thread).\n"
    "  CIRISLensCore currently publishes to PyPI only (linux x86_64/aarch64 +\n"
    "  macOS arm64 wheels) — no GitHub release tarballs for Android/iOS yet.\n"
    "  The upstream release-artifact ask has been filed. Re-run this tool once\n"
    "  {tarball} lands on https://github.com/CIRISAI/CIRISLensCore/releases."
)


# Library definitions — add new libs here.
LIBS: Dict[str, SubstrateLib] = {
    "verify": SubstrateLib(
        name="verify",
        github_repo="CIRISAI/CIRISVerify",
        pypi_package="ciris-verify",
        tarball_prefix="ciris-verify",
        bindings_package="ciris_verify",
        so_filename="libciris_verify_ffi.so",
        abis=["arm64-v8a", "x86_64", "armeabi-v7a"],
        framework_name="CIRISVerify",
        ffi_lib_name="libciris_verify_ffi",
        device_dir="ios/aarch64-apple-ios",
        simulator_dir="ios/aarch64-apple-ios-sim",
        dylib_filename="libciris_verify_ffi.dylib",
        has_adapter=True,
        adapter_name="ciris_verify",
    ),
    "persist": SubstrateLib(
        name="persist",
        github_repo="CIRISAI/CIRISPersist",
        pypi_package="ciris-persist",
        tarball_prefix="ciris-persist",
        bindings_package="ciris_persist",
        so_filename="libciris_persist.so",
        # CIRISPersist ships all 3 ABIs as of v2.0.6 (CIRISPersist#97 —
        # armeabi-v7a wheel added; v2.0.5 was arm64-v8a + x86_64 only).
        abis=["arm64-v8a", "x86_64", "armeabi-v7a"],
        # Persist's PyO3 module must be `import ciris_persist`-able from the
        # agent (the entire 2.9.0 persist substrate lives behind this import).
        # The release publishes `ciris-persist-v{ver}-android-wheels.tar.gz`
        # containing the Chaquopy-shaped wheels for that purpose.
        has_android_wheels=True,
        framework_name="CIRISPersist",
        ffi_lib_name="ciris_persist",
        device_dir="ios-device",
        simulator_dir="ios-simulator",
        dylib_filename="ciris_persist.abi3.so",  # PyO3 module, not ctypes FFI
        is_pyo3=True,  # Loads via Python import, not xcframework
        has_adapter=False,
    ),
    "edge": SubstrateLib(
        name="edge",
        github_repo="CIRISAI/CIRISEdge",
        pypi_package="ciris-edge",
        tarball_prefix="ciris-edge",
        bindings_package="ciris_edge",
        so_filename="libciris_edge.so",
        # CIRISEdge 1.0+ ships all three Android ABIs in the wheels tarball.
        abis=["arm64-v8a", "x86_64", "armeabi-v7a"],
        # The agent's `init_edge_runtime` imports `ciris_edge` directly, so
        # the Chaquopy-shaped wheels MUST land in client/androidApp/wheels/ —
        # otherwise the Android-bundled Python raises "ciris-edge not
        # importable but is REQUIRED for 2.9.4+" at boot and
        # `/v1/federation/identity` returns 503 to the UI.
        has_android_wheels=True,
        framework_name="CIRISEdge",
        ffi_lib_name="ciris_edge",
        # Tarball layout matches persist (CIRISEdge v1.1.5):
        #   ios-device/ciris_edge.abi3.so
        #   ios-simulator/ciris_edge.abi3.so
        device_dir="ios-device",
        simulator_dir="ios-simulator",
        dylib_filename="ciris_edge.abi3.so",  # PyO3 module, not ctypes FFI
        is_pyo3=True,  # Loads via Python import, not xcframework
        has_adapter=False,
    ),
    "lens": SubstrateLib(
        name="lens",
        github_repo="CIRISAI/CIRISLensCore",
        pypi_package="ciris-lens-core",
        tarball_prefix="ciris-lens-core",
        bindings_package="ciris_lens_core",
        so_filename="libciris_lens_core.so",
        abis=["arm64-v8a", "x86_64", "armeabi-v7a"],
        # Fourth substrate leg (2.9.6 — CIRISAgent#866/#857): the
        # observability orchestrator. PyO3 abi3 module like persist/edge —
        # the agent imports `ciris_lens_core` directly, so once upstream
        # ships `ciris-lens-core-v{ver}-android-wheels.tar.gz` the wheels go
        # into client/androidApp/wheels/ and the (currently commented)
        # `install "ciris-lens-core==X"` gradle pin gets activated.
        has_android_wheels=True,
        framework_name="CIRISLensCore",
        ffi_lib_name="ciris_lens_core",
        device_dir="ios-device",
        simulator_dir="ios-simulator",
        dylib_filename="ciris_lens_core.abi3.so",  # PyO3 module, not ctypes FFI
        is_pyo3=True,
        has_adapter=False,
        # CIRISLensCore publishes NO GitHub release artifacts yet (PyPI
        # only). Until the upstream ask lands, downloads 404 and this entry
        # reports PENDING with the actionable note below instead of a
        # generic download failure.
        release_pending_note=_LENS_PENDING_NOTE,
    ),
    # Future:
    # "nodecore": SubstrateLib(...),
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


def download_release_tarball(
    lib: SubstrateLib, version: str, platform_suffix: str, dest_dir: Path
) -> Optional[Path]:
    """Download a platform tarball from the GitHub Release.

    Tries both `{prefix}-v{version}-{platform}.tar.gz` and
    `{prefix}-{version}-{platform}.tar.gz` (release-asset naming conventions
    vary between repos).
    """
    tag = f"v{version}"
    patterns = [
        f"{lib.tarball_prefix}-v{version}-{platform_suffix}.tar.gz",
        f"{lib.tarball_prefix}-{version}-{platform_suffix}.tar.gz",
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
            if f.suffix == ".gz" and platform_suffix in f.name.lower():
                print(f"  Downloaded: {f.name}")
                return f
    return None


def verify_tarball_checksum(
    lib: SubstrateLib, version: str, tarball: Path, skip: bool = False
) -> bool:
    """Verify a downloaded tarball against the release's SHA256SUMS asset.

    Best-effort: releases that don't publish a SHA256SUMS asset (or whose
    SHA256SUMS has no entry for this tarball) skip verification with a note.
    A present-but-mismatching checksum is a hard failure.
    """
    if skip:
        print("  (checksum verification skipped via --skip-checksums)")
        return True
    tag = f"v{version}"
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        run_cmd(
            [
                "gh", "release", "download", tag,
                "--repo", lib.github_repo,
                "--pattern", "SHA256SUMS",
                "--dir", str(tmp_path),
            ],
            check=False,
        )
        sums_file = tmp_path / "SHA256SUMS"
        if not sums_file.exists():
            print(f"  (no SHA256SUMS asset on {lib.github_repo} {tag} — skipping checksum verification)")
            return True
        expected: Optional[str] = None
        for line in sums_file.read_text().splitlines():
            parts = line.split()
            # `sha256sum` format: "<hex>  <name>" (binary mode prefixes '*')
            if len(parts) >= 2 and parts[-1].lstrip("*") == tarball.name:
                expected = parts[0]
                break
        if expected is None:
            print(f"  (SHA256SUMS has no entry for {tarball.name} — skipping checksum verification)")
            return True
        actual = hashlib.sha256(tarball.read_bytes()).hexdigest()
        if actual != expected:
            print(f"  ERROR: SHA256 mismatch for {tarball.name}")
            print(f"    expected {expected}")
            print(f"    actual   {actual}")
            return False
        print(f"  ✓ SHA256 verified: {tarball.name}")
        return True


def _report_download_failure(lib: SubstrateLib, version: str, platform_suffix: str) -> UpdateStatus:
    """Print the right failure message for a missing release tarball."""
    if lib.release_pending_note:
        tarball = f"{lib.tarball_prefix}-v{version}-{platform_suffix}.tar.gz"
        print(f"\n  PENDING: {lib.release_pending_note.format(tarball=tarball)}")
        return UpdateStatus.PENDING
    print(f"  ERROR: Failed to download {platform_suffix} tarball for {lib.name} v{version}")
    return UpdateStatus.FAILED


# ---------------------------------------------------------------------------
# Android
# ---------------------------------------------------------------------------


def install_jni_libs(lib: SubstrateLib, extract_dir: Path) -> bool:
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


def install_android_wheels(lib: SubstrateLib, version: str, skip_checksums: bool = False) -> bool:
    """Download `*-android-wheels.tar.gz` and drop wheels into wheels dir.

    Each wheel inside the tarball is Chaquopy-shaped — `cp310-…-
    android_24_{abi}` — and includes both `__init__.py` and the per-ABI
    `*.so` so `pip install` via Chaquopy's `--find-links wheels` resolves
    cleanly. Wheels for older versions of the same lib are pruned so
    Chaquopy doesn't try to satisfy a new pin from a stale candidate.
    """
    if not lib.has_android_wheels:
        return True
    print(f"\n  Installing Android wheels for {lib.name}...")
    tag = f"v{version}"
    pattern = f"{lib.tarball_prefix}-v{version}-android-wheels.tar.gz"
    with tempfile.TemporaryDirectory() as tmp:
        dl_dir = Path(tmp)
        run_cmd(
            [
                "gh", "release", "download", tag,
                "--repo", lib.github_repo,
                "--pattern", pattern,
                "--dir", str(dl_dir),
            ],
            check=False,
        )
        tarball = next((p for p in dl_dir.iterdir() if p.name == pattern), None)
        if not tarball:
            print(f"  WARNING: no {pattern} on the release; skipping wheels install")
            return False

        if not verify_tarball_checksum(lib, version, tarball, skip=skip_checksums):
            return False

        extract_dir = dl_dir / "extracted"
        extract_dir.mkdir()
        run_cmd(["tar", "-xzf", str(tarball), "-C", str(extract_dir)])

        WHEELS_DIR.mkdir(parents=True, exist_ok=True)
        # Prune older wheels for this package so Chaquopy doesn't see two
        # candidates. Wheel naming convention is `{pkg}-{version}-…whl`,
        # where {pkg} is the wheel-distribution name (underscored, e.g.
        # `ciris_persist` for `ciris-persist`).
        wheel_prefix = lib.pypi_package.replace("-", "_") + "-"
        for stale in WHEELS_DIR.glob(f"{wheel_prefix}*.whl"):
            if version not in stale.name:
                stale.unlink()
                print(f"  pruned stale wheel: {stale.name}")

        installed = 0
        for src in extract_dir.rglob("*.whl"):
            dest = WHEELS_DIR / src.name
            shutil.copy2(src, dest)
            size_mb = dest.stat().st_size / 1024 / 1024
            print(f"  {dest.relative_to(REPO_ROOT)} ({size_mb:.1f}MB)")
            installed += 1
        if installed == 0:
            print("  WARNING: tarball had no wheels inside")
            return False
    return True


def update_gradle_pin(lib: SubstrateLib, version: str) -> None:
    """Pin ``install "{pkg}==X"`` in client/androidApp/build.gradle.

    Chaquopy resolves the substrate wheels from wheels/ via --find-links;
    the gradle pin MUST match the wheel version dropped there or the build
    falls back to a stale candidate / fails resolution (version skew breaks
    cohabitation — CIRISEdge#16/#43 etc.). Three cases:

      - active ``install "pkg==X"`` line   -> rewrite the version
      - commented ``// install "pkg==X"``  -> uncomment + pin (fires the
        first time upstream ships Android wheels, e.g. ciris-lens-core)
      - no line at all                      -> insert after the last
        ``install "ciris-*"`` line with an explanatory comment

    Only called after the wheels actually landed in wheels/, so an
    activated pin is always satisfiable at gradle build time.
    """
    if not lib.has_android_wheels:
        return
    if not ANDROID_BUILD_GRADLE.exists():
        print(f"  WARNING: {ANDROID_BUILD_GRADLE.relative_to(REPO_ROOT)} not found; gradle pin not updated")
        return

    pkg = lib.pypi_package
    text = ANDROID_BUILD_GRADLE.read_text()
    pin_line = f'install "{pkg}=={version}"'
    active_re = re.compile(rf'^(?P<indent>[ \t]*)install "{re.escape(pkg)}==[^"]*"', re.MULTILINE)
    commented_re = re.compile(rf'^(?P<indent>[ \t]*)//[ \t]*install "{re.escape(pkg)}==[^"]*"', re.MULTILINE)

    if active_re.search(text):
        new_text = active_re.sub(lambda m: f'{m.group("indent")}{pin_line}', text)
        action = "updated"
    elif commented_re.search(text):
        new_text = commented_re.sub(lambda m: f'{m.group("indent")}{pin_line}', text)
        action = "ACTIVATED (uncommented — upstream Android wheels have landed)"
    else:
        # Insert after the last existing ciris-* install line (active or
        # commented) so the substrate pins stay grouped together.
        anchor_re = re.compile(r'^[ \t]*(?://[ \t]*)?install "ciris-[^"]*"[^\n]*$', re.MULTILINE)
        anchors = list(anchor_re.finditer(text))
        if not anchors:
            print(
                f'  WARNING: no `install "ciris-*"` anchor in build.gradle; '
                f"add `{pin_line}` manually"
            )
            return
        last = anchors[-1]
        indent_match = re.match(r"[ \t]*", last.group(0))
        indent = indent_match.group(0) if indent_match else "                "
        insertion = (
            f"\n{indent}// {pkg} wheels land in wheels/ via"
            f"\n{indent}// tools/update_substrate_libs.py; pin MUST match"
            f"\n{indent}// requirements.txt (version skew breaks cohabitation)."
            f"\n{indent}{pin_line}"
        )
        new_text = text[: last.end()] + insertion + text[last.end() :]
        action = "added"

    if new_text != text:
        ANDROID_BUILD_GRADLE.write_text(new_text)
        print(f"  gradle pin {action}: `{pin_line}` in {ANDROID_BUILD_GRADLE.relative_to(REPO_ROOT)}")
    else:
        print(f"  gradle pin already `{pin_line}`")


def update_python_bindings_android(lib: SubstrateLib, version: str) -> bool:
    """Extract the wheel's Python bindings into the agent's adapter dir.

    Only runs when ``lib.has_adapter`` is True. The agent-side
    ``ciris_adapters/{adapter_name}/ffi_bindings/`` location is shared across
    platforms (only the .so changes per platform).
    """
    if not lib.has_adapter or not lib.adapter_name:
        print(f"\n  Skipping Python bindings for {lib.name} (no in-tree adapter)")
        return True

    print(f"\n  Updating Python bindings from PyPI ({lib.pypi_package}=={version})...")

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        run_cmd(
            [
                sys.executable, "-m", "pip", "download",
                f"{lib.pypi_package}=={version}",
                "--no-deps",
                "-d", str(tmpdir),
            ],
            check=False,
        )

        wheel = next((f for f in tmpdir.iterdir() if f.suffix == ".whl"), None)
        if not wheel:
            print(f"  WARNING: No wheel found for {lib.pypi_package}=={version}")
            return False
        print(f"  Downloaded: {wheel.name}")

        # Agent-managed __init__.py / client.py are skipped — the agent ships
        # enhanced versions; only their __version__ is bumped by
        # update_version_string() below.
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


def update_version_string(lib: SubstrateLib, version: str, include_ios_copy: bool) -> None:
    """Update ``__version__`` in the adapter's ffi_bindings/__init__.py.

    When ``include_ios_copy`` is True the iOS Resources mirror of the adapter
    __init__ is bumped too (Android doesn't keep a per-platform mirror).
    """
    if not lib.has_adapter or not lib.adapter_name:
        return

    agent_init = REPO_ROOT / "ciris_adapters" / lib.adapter_name / "ffi_bindings" / "__init__.py"
    if agent_init.exists():
        content = agent_init.read_text()
        new_content = re.sub(r'__version__\s*=\s*"[^"]+"', f'__version__ = "{version}"', content)
        if new_content != content:
            agent_init.write_text(new_content)
            print(f"  Updated __version__ in {agent_init.relative_to(REPO_ROOT)}")

    if not include_ios_copy:
        return

    ios_init = (
        IOS_RESOURCES_DIR
        / "app"
        / "ciris_adapters"
        / (lib.adapter_name or lib.bindings_package)
        / "ffi_bindings"
        / "__init__.py"
    )
    if ios_init.exists():
        content = ios_init.read_text()
        new_content = re.sub(r'__version__\s*=\s*"[^"]+"', f'__version__ = "{version}"', content)
        if new_content != content:
            ios_init.write_text(new_content)
            print("  Updated __version__ in iOS Resources copy")


def verify_so_version(lib: SubstrateLib, version: str) -> bool:
    """Verify each per-ABI .so embeds the expected version string.

    Best-effort ``strings`` grep. A library that doesn't embed its version
    literally won't fail the run; it just won't print a ✓.
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


def update_lib_android(
    lib: SubstrateLib, version: str, skip_bindings: bool = False, skip_checksums: bool = False
) -> UpdateStatus:
    """Full Android update flow for a single library."""
    print(f"\n{'='*60}")
    print(f"  Updating {lib.name} to v{version} (Android)")
    print(f"  Repo: {lib.github_repo}")
    print(f"{'='*60}")

    with tempfile.TemporaryDirectory() as tmp:
        dl_dir = Path(tmp)

        tarball = download_release_tarball(lib, version, "android", dl_dir)
        if not tarball:
            return _report_download_failure(lib, version, "android")

        if not verify_tarball_checksum(lib, version, tarball, skip=skip_checksums):
            return UpdateStatus.FAILED

        extract_dir = dl_dir / "extracted"
        extract_dir.mkdir()
        run_cmd(["tar", "-xzf", str(tarball), "-C", str(extract_dir)])

        if not install_jni_libs(lib, extract_dir):
            return UpdateStatus.FAILED

    # Chaquopy-shaped Android wheels go into client/androidApp/wheels/ for
    # PyO3 libs the agent has to `import` from Python (separate release
    # asset). Failure here is non-fatal so a transient gh / network blip
    # doesn't trash the run, but logged loudly. The gradle pin is only
    # touched when the wheels actually landed.
    if lib.has_android_wheels:
        if install_android_wheels(lib, version, skip_checksums=skip_checksums):
            update_gradle_pin(lib, version)
        else:
            print(
                f"  WARNING: android wheels NOT installed for {lib.name}; "
                f"Chaquopy import path will be broken until this lands"
            )

    if not skip_bindings:
        update_python_bindings_android(lib, version)
        update_version_string(lib, version, include_ios_copy=False)

    return UpdateStatus.SUCCESS


# ---------------------------------------------------------------------------
# iOS
# ---------------------------------------------------------------------------


_PLIST_SHORT_VERSION_RE = re.compile(
    r"^(?P<indent>[ \t]*)<key>CFBundleShortVersionString</key><string>(?P<v>[^<]+)</string>[ \t]*$",
    re.MULTILINE,
)


def repair_xcframework_info_plists() -> int:
    """Idempotently add a missing CFBundleVersion key to every XCFramework's
    inner framework Info.plist under client/iosApp/Frameworks/.

    Apple App Store validation (error 90056) requires every framework bundle
    Info.plist to carry both CFBundleShortVersionString AND CFBundleVersion.
    This tool's plist template writes both; this function repairs any
    already-checked-in artifacts produced by older template versions so a
    single tool run produces a fully-correct tree.

    Behavior: when a plist has CFBundleShortVersionString but no
    CFBundleVersion, insert a CFBundleVersion line with the same value
    immediately after the short-version line. No-op when CFBundleVersion is
    already present (or when there is no short-version string to mirror).
    Returns the number of plists modified.
    """
    if not IOS_FRAMEWORKS_DIR.exists():
        return 0
    patched = 0
    for info_plist in sorted(IOS_FRAMEWORKS_DIR.glob("*.xcframework/*/*.framework/Info.plist")):
        text = info_plist.read_text(encoding="utf-8")
        if "<key>CFBundleVersion</key>" in text:
            continue
        m = _PLIST_SHORT_VERSION_RE.search(text)
        if not m:
            continue
        new_line = f"{m['indent']}<key>CFBundleVersion</key><string>{m['v']}</string>"
        new_text = _PLIST_SHORT_VERSION_RE.sub(
            lambda mm: mm.group(0) + "\n" + new_line,
            text,
            count=1,
        )
        info_plist.write_text(new_text, encoding="utf-8")
        rel = info_plist.relative_to(REPO_ROOT)
        print(f"  REPAIRED {rel}: added CFBundleVersion={m['v']}")
        patched += 1
    return patched


def ios_toolchain_available() -> bool:
    """XCFramework builds need macOS with xcodebuild/otool/install_name_tool."""
    return sys.platform == "darwin" and shutil.which("xcodebuild") is not None


def build_xcframework(lib: SubstrateLib, extract_dir: Path, version: str) -> bool:
    """Build XCFramework from extracted iOS tarball (ctypes FFI libs only)."""
    print(f"\n  Building {lib.framework_name}.xcframework...")

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)

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
    <key>CFBundleVersion</key><string>{version}</string>
    <key>MinimumOSVersion</key><string>16.0</string>
    <key>CFBundleSupportedPlatforms</key>
    <array><string>{platform}</string></array>
</dict>
</plist>"""
            (fw_dir / "Info.plist").write_text(plist)
            print(f"  {label}: framework prepared")

        # Build XCFramework
        fw_args: List[str] = []
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


def bundle_pyo3_module(lib: SubstrateLib, extract_dir: Path) -> bool:
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


def update_python_bindings_ios(lib: SubstrateLib, version: str) -> bool:
    """Update Python bindings into iOS Resources/app_packages from PyPI wheel."""
    print(f"\n  Updating Python bindings from PyPI ({lib.pypi_package}=={version})...")

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = Path(tmp)
        run_cmd(
            [sys.executable, "-m", "pip", "download", f"{lib.pypi_package}=={version}", "--no-deps", "-d", str(tmpdir)],
            check=False,
        )

        wheel = next((f for f in tmpdir.iterdir() if f.suffix == ".whl"), None)
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
                    (pkg_dir / basename).write_bytes(zf.read(name))
                    print(f"  -> {basename}")

        # Ensure py.typed marker
        (pkg_dir / "py.typed").touch()

    return True


def rebuild_resources_zip() -> None:
    """Rebuild Resources.zip from the Resources directory."""
    print("\nRebuilding Resources.zip...")
    os.chdir(IOS_RESOURCES_DIR)
    zip_path = IOS_APP_DIR / "Resources.zip"
    zip_path.unlink(missing_ok=True)
    run_cmd(["zip", "-q", "-r", str(zip_path), "."], check=True)
    size_mb = zip_path.stat().st_size / 1024 / 1024
    print(f"  -> Resources.zip ({size_mb:.1f}MB)")


def verify_dylib_version(lib: SubstrateLib, version: str) -> bool:
    """Verify the iOS native library contains the expected version string."""
    if lib.is_pyo3:
        dylib = IOS_APP_DIR / "app_packages_native" / lib.bindings_package / lib.dylib_filename
    else:
        dylib = IOS_RESOURCES_DIR / "app_packages" / lib.bindings_package / lib.dylib_filename
    if not dylib.exists():
        print(f"  ✗ Native library missing: {dylib.name}")
        return False

    result = subprocess.run(["strings", str(dylib)], capture_output=True, text=True)
    for line in result.stdout.splitlines():
        # Substring, not exact-line: ctypes FFI crates (verify) embed a bare
        # "X.Y.Z" line, but PyO3 crates (persist/edge) may embed it only as
        # part of a larger token (e.g. "CIRISPersist/4.0.1") or not at all.
        if version in line:
            print(f"  ✓ {lib.name}: {dylib.name} embeds v{version}")
            return True

    # Not embedding the literal version is ADVISORY, not fatal — provenance is
    # already guaranteed by the tag-pinned `gh release download v{version}`
    # above. Several Rust crates (notably the PyO3 modules) don't write the
    # version into their string table, so an exact match was never reachable
    # for them. Same policy as the Android-side check.
    print(
        f"  ? {lib.name}: {dylib.name} does not embed literal '{version}' "
        f"(may be normal for PyO3 Rust crates — binary provenance is the "
        f"release-tag download, not this string check)"
    )
    return True


def update_lib_ios(lib: SubstrateLib, version: str, skip_checksums: bool = False) -> UpdateStatus:
    """Full iOS update flow for a single library."""
    print(f"\n{'='*60}")
    print(f"  Updating {lib.name} to v{version} (iOS)")
    print(f"  Repo: {lib.github_repo}")
    print(f"{'='*60}")

    if not lib.is_pyo3 and not ios_toolchain_available():
        print(
            f"  ERROR: {lib.name} needs an XCFramework build, which requires "
            f"macOS with xcodebuild (+ otool/install_name_tool).\n"
            f"  Run this on a Mac, or via the CI workflow: "
            f".github/workflows/refresh-ios-substrate.yml (macos-latest)."
        )
        return UpdateStatus.FAILED

    with tempfile.TemporaryDirectory() as tmp:
        dl_dir = Path(tmp)

        tarball = download_release_tarball(lib, version, "ios", dl_dir)
        if not tarball:
            return _report_download_failure(lib, version, "ios")

        if not verify_tarball_checksum(lib, version, tarball, skip=skip_checksums):
            return UpdateStatus.FAILED

        extract_dir = dl_dir / "extracted"
        extract_dir.mkdir()
        run_cmd(["tar", "-xzf", str(tarball), "-C", str(extract_dir)])

        if lib.is_pyo3:
            # PyO3: .abi3.so → app_packages_native + .fwork redirect
            if not bundle_pyo3_module(lib, extract_dir):
                return UpdateStatus.FAILED
        else:
            # ctypes FFI: build xcframework + fallback dylib
            if not build_xcframework(lib, extract_dir, version):
                return UpdateStatus.FAILED

    update_python_bindings_ios(lib, version)

    if lib.has_adapter and lib.adapter_name:
        update_version_string(lib, version, include_ios_copy=True)

    return UpdateStatus.SUCCESS


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: Optional[List[str]] = None) -> None:
    parser = argparse.ArgumentParser(
        description="Update CIRIS substrate native libraries (Android + iOS) from GitHub Releases",
    )
    parser.add_argument(
        "--platform",
        choices=["android", "ios", "all"],
        default="all",
        help="Which platform(s) to refresh (default: all)",
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
        help="(Android) Skip Python bindings + __version__ refresh (only update jniLibs)",
    )
    parser.add_argument(
        "--rebuild-zip-only",
        action="store_true",
        help="(iOS) Only rebuild Resources.zip",
    )
    parser.add_argument(
        "--repair-info-plists",
        action="store_true",
        help="(iOS) Only repair missing CFBundleVersion keys in checked-in XCFramework Info.plists, then exit",
    )
    parser.add_argument("--skip-checksums", action="store_true", help="Skip SHA256SUMS verification")
    args = parser.parse_args(argv)

    do_android = args.platform in ("android", "all")
    do_ios = args.platform in ("ios", "all")

    if args.repair_info_plists:
        n = repair_xcframework_info_plists()
        print(
            f"\n  Repaired {n} Info.plist(s)" if n else "\n  All XCFramework Info.plists already have CFBundleVersion"
        )
        return

    # Always run the idempotent Info.plist repair before any iOS download/build
    # work so a checked-in artifact missing CFBundleVersion gets fixed even when
    # the caller doesn't think to ask. App Store error 90056 is hard to recover
    # from late in the upload flow.
    if do_ios:
        repair_xcframework_info_plists()

    if args.rebuild_zip_only:
        rebuild_resources_zip()
        return

    explicit = args.lib is not None
    names = [args.lib] if explicit else list(LIBS.keys())

    versions: Dict[str, str] = {}
    results: List[Tuple[str, str, UpdateStatus]] = []  # (lib_name, platform, status)

    for name in names:
        lib = LIBS[name]
        version = args.version or get_pinned_version(lib.pypi_package)
        if not version:
            if explicit:
                print(f"ERROR: No version specified and no pin found for {lib.pypi_package}")
                sys.exit(1)
            print(f"  SKIP {name}: no version pin found")
            continue
        versions[name] = version

        if do_android:
            status = update_lib_android(
                lib, version, skip_bindings=args.skip_bindings, skip_checksums=args.skip_checksums
            )
            results.append((name, "android", status))
        if do_ios:
            status = update_lib_ios(lib, version, skip_checksums=args.skip_checksums)
            results.append((name, "ios", status))

    android_ok = [n for n, p, s in results if p == "android" and s is UpdateStatus.SUCCESS]
    ios_ok = [n for n, p, s in results if p == "ios" and s is UpdateStatus.SUCCESS]
    failed = [(n, p) for n, p, s in results if s is UpdateStatus.FAILED]
    pending = [(n, p) for n, p, s in results if s is UpdateStatus.PENDING]

    verify_ok = True

    if android_ok:
        print("\nVerifying bundled .so files embed expected versions...")
        for name in android_ok:
            if not verify_so_version(LIBS[name], versions[name]):
                verify_ok = False

    if ios_ok:
        rebuild_resources_zip()
        print("\nVerifying bundled iOS binaries...")
        for name in ios_ok:
            if not verify_dylib_version(LIBS[name], versions[name]):
                verify_ok = False

    print(f"\n{'='*60}")
    for name, plat, status in results:
        print(f"  {name:8s} {plat:8s} {status.value.upper()}")
    if failed or not verify_ok:
        print("  WARNING: Some library updates failed or are unverifiable")
    elif pending:
        print("  Updates complete (some upstream release artifacts still pending)")
    else:
        print("  All substrate libraries updated successfully")
    print(f"{'='*60}")

    if android_ok:
        print("\nAndroid next steps:")
        print("  1. cd client && ./gradlew :androidApp:assembleDebug")
        print("  2. adb shell am force-stop ai.ciris.mobile.debug")
        print("  3. adb install -r androidApp/build/outputs/apk/debug/androidApp-debug.apk")

    # Exit policy: hard failures (and verification misses) always fail the
    # run. PENDING (upstream hasn't published artifacts yet — lens) fails the
    # run only when that lib was explicitly requested via --lib; in registry-
    # wide runs it's a loud warning so the other libs' refresh still lands.
    if failed or not verify_ok:
        sys.exit(1)
    if pending and explicit:
        sys.exit(1)


if __name__ == "__main__":
    main()
