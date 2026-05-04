"""Parity gate: requirements.txt ciris-verify pin must match mobile FFI binaries.

Why this test exists (2.8.2):

  Desktop FFI is resolved via the pip-installed wheel (single source of
  truth = the pin in requirements.txt). Mobile platforms (Android JNI,
  iOS framework) are NOT pip-resolved — they ship as platform-specific
  binary artifacts in the repo:

    client/androidApp/src/main/jniLibs/{arm64-v8a, x86_64,
        armeabi-v7a}/libciris_verify_ffi.so
    client/iosApp/...      (framework variant; not yet covered)

  Those binaries are downloaded by `tools/update_ciris_verify.py <version>`
  from the CIRISVerify GitHub releases. The asymmetry: bumping the
  requirements.txt pin upgrades desktop atomically (next pip install)
  but does NOT update the mobile binaries. Without a parity gate the
  mobile FFI silently lags the pin — exactly the failure mode that
  surfaced in 2.8.0/2.8.1 when the agent reported FFI v1.6.3 at
  startup while requirements.txt had been at v1.10.1+ for two
  releases.

  This test reads:
    1. The pinned version from requirements.txt (`ciris-verify>=X.Y.Z`)
    2. The version string baked into each mobile JNI binary
       (`CIRISVerify FFI init starting (vX.Y.Z)`)
  and fails if they don't match, with a directed error pointing the
  fix path:

      requirements.txt pins ciris-verify>=1.11.1
      but Android JNI lib at jniLibs/arm64-v8a/libciris_verify_ffi.so
      is v1.6.3 — run `python tools/update_ciris_verify.py 1.11.1`
      to align mobile binaries before merge.

  Same shape as the LANGUAGE_SPECS regression guard in
  tests/tools/qa_runner/test_language_specs_coverage.py — caught at CI,
  not in production.

  iOS coverage scoped to #732 — the existing update_ciris_verify.py
  iOS flow has structural issues (over-bundles Resources.zip; doesn't
  refresh xcframework Mach-O binaries from release tarballs). Once
  the iOS update path is fixed, this test gains parametrize cases for
  the .xcframework variants.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
REQUIREMENTS = REPO_ROOT / "requirements.txt"
ANDROID_JNI_ROOT = REPO_ROOT / "client" / "androidApp" / "src" / "main" / "jniLibs"

# All Android ABIs we ship. If a new ABI is added, this list expands and
# the parity gate covers it automatically.
ANDROID_ABIS = ["arm64-v8a", "armeabi-v7a", "x86_64"]

# Pattern in requirements.txt: `ciris-verify>=X.Y.Z  # comment...`
# Tolerates `>=X.Y.Z`, `==X.Y.Z`, `~=X.Y.Z` — captures the X.Y.Z literal.
_PIN_RE = re.compile(
    r"^ciris-verify\s*[><=!~]+\s*(\d+\.\d+\.\d+)",
    re.MULTILINE,
)

# The FFI library writes a literal `CIRISVerify FFI init starting (vX.Y.Z)`
# to its .rodata section. We extract X.Y.Z from any byte stream containing
# the pattern. Stable across all platforms (same Rust source emits the
# same string).
_FFI_VERSION_RE = re.compile(
    rb"CIRISVerify FFI init starting \(v(\d+\.\d+\.\d+)\)",
)


def _read_pinned_version() -> str:
    """Return the X.Y.Z pin from requirements.txt for `ciris-verify`."""
    text = REQUIREMENTS.read_text(encoding="utf-8")
    match = _PIN_RE.search(text)
    assert match, (
        f"Could not find a `ciris-verify >= X.Y.Z` line in {REQUIREMENTS}. "
        f"This test reads the pinned version from there; if the pin format "
        f"has changed, update the regex in this test."
    )
    return match.group(1)


def _read_ffi_version_from_binary(binary_path: Path) -> str | None:
    """Return X.Y.Z from a libciris_verify_ffi.* binary, or None if absent.

    Reads the file in binary mode and grep's the `.rodata` for the FFI
    init log string. Faster + simpler than running `strings(1)`; works
    regardless of platform tooling.
    """
    if not binary_path.is_file():
        return None
    data = binary_path.read_bytes()
    match = _FFI_VERSION_RE.search(data)
    return match.group(1).decode("ascii") if match else None


def test_requirements_txt_has_ciris_verify_pin() -> None:
    """Sanity-check: the pin exists and is parseable.

    If this fails, requirements.txt has lost the `ciris-verify>=X.Y.Z`
    line — almost certainly an editing mistake. The mobile-parity gate
    below depends on this returning a value.
    """
    version = _read_pinned_version()
    assert re.match(r"^\d+\.\d+\.\d+$", version), (
        f"Parsed ciris-verify pin '{version}' is not a clean X.Y.Z semver."
    )


@pytest.mark.parametrize("abi", ANDROID_ABIS)
def test_android_jni_ffi_version_matches_pin(abi: str) -> None:
    """The Android JNI lib for each ABI must report the same FFI version
    as the pin in requirements.txt.

    Surfaces stale mobile binaries before merge. The fix path is
    `python tools/update_ciris_verify.py <pinned-version>` — error
    message includes the exact command.
    """
    pinned = _read_pinned_version()
    binary = ANDROID_JNI_ROOT / abi / "libciris_verify_ffi.so"

    assert binary.is_file(), (
        f"Missing Android JNI binary for ABI '{abi}': {binary}\n"
        f"Mobile build pipeline expects all 3 ABIs ({ANDROID_ABIS}) to ship.\n"
        f"Run `python tools/update_ciris_verify.py {pinned}` to download."
    )

    actual = _read_ffi_version_from_binary(binary)
    assert actual is not None, (
        f"Android JNI binary at {binary} does not contain the expected "
        f"`CIRISVerify FFI init starting (vX.Y.Z)` string. The binary may "
        f"be corrupt, truncated, or built from an FFI source that doesn't "
        f"emit the version log line — bump CIRISVerify to a version that does."
    )

    assert actual == pinned, (
        f"\n"
        f"Mobile FFI version drift detected for Android ABI '{abi}':\n"
        f"  requirements.txt pins  ciris-verify>={pinned}\n"
        f"  but {binary.relative_to(REPO_ROOT)} reports v{actual}\n"
        f"\n"
        f"To align mobile binaries with the pin:\n"
        f"  python tools/update_ciris_verify.py {pinned}\n"
        f"\n"
        f"Then commit the updated client/androidApp/src/main/jniLibs/*/\n"
        f"libciris_verify_ffi.so binaries. The release/mobile branch is\n"
        f"cut from main, so mobile parity at every merge is the contract.\n"
    )
