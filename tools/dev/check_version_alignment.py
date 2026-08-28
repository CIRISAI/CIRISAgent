#!/usr/bin/env python3
"""
Pre-commit check: Verify all version constants are aligned.

Checks that the engine version in constants.py matches:
  - iOS Info.plist CFBundleShortVersionString
  - Android build.gradle versionName
  - Mobile Python version files (android/ios)

Exit 0 = all aligned, Exit 1 = mismatch found.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.parent


def get_engine_version() -> tuple[str, int, int, int]:
    """Extract major.minor.patch from constants.py."""
    constants = ROOT / "ciris_engine" / "constants.py"
    content = constants.read_text()
    major = int(re.search(r"CIRIS_VERSION_MAJOR = (\d+)", content).group(1))
    minor = int(re.search(r"CIRIS_VERSION_MINOR = (\d+)", content).group(1))
    patch = int(re.search(r"CIRIS_VERSION_PATCH = (\d+)", content).group(1))
    return f"{major}.{minor}.{patch}", major, minor, patch


def check_all() -> list[str]:
    errors = []
    display_version, major, minor, patch = get_engine_version()

    # iOS Info.plist CFBundleShortVersionString
    plist = ROOT / "apps" / "ios" / "iosApp" / "Info.plist"
    if plist.exists():
        content = plist.read_text()
        m = re.search(r"<key>CFBundleShortVersionString</key>\s*<string>([^<]+)</string>", content)
        if m and m.group(1) != display_version:
            errors.append(f"iOS CFBundleShortVersionString: {m.group(1)} != {display_version}")

    # Android build.gradle versionName
    gradle = ROOT / "apps" / "android" / "build.gradle"
    if gradle.exists():
        content = gradle.read_text()
        m = re.search(r'versionName "([^"]+)"', content)
        if m and m.group(1) != display_version:
            errors.append(f"Android versionName: {m.group(1)} != {display_version}")

    # Client Python version files
    version_files = [
        ("apps/android/src/main/python/version.py", f"android-{display_version}"),
        ("android/app/src/main/python/version.py", f"android-{display_version}"),
        ("ios/CirisiOS/src/ciris_ios/version.py", f"ios-{display_version}"),
    ]
    for rel_path, expected in version_files:
        vf = ROOT / rel_path
        if vf.exists():
            content = vf.read_text()
            m = re.search(r'__version__ = "([^"]+)"', content)
            if m and m.group(1) != expected:
                errors.append(f"{rel_path}: {m.group(1)} != {expected}")

    errors.extend(_check_substrate_client_version())

    return errors


def _check_substrate_client_version() -> list[str]:
    """The substrate pins this repo still owns must agree.

    The client shows a VERSION-MISMATCH banner whenever the node it talks to
    reports a different version than `CLIENT_VERSION` (ClientMode.kt). On mobile
    the node IS the bundled wheel, so these two must be the same number or the
    app flags itself as out of date against its own runtime.

    Upstream (CIRISServer) keeps CLIENT_VERSION in lockstep with Cargo.toml via
    scripts/sync-client-version.sh + a CI --check. This repo has neither file, so
    the constant simply drifted: it sat at 0.5.159 while the bundled node moved
    to 0.5.163, and every 2.9.14 build showed the banner. Nothing failed — the
    banner is non-blocking — which is exactly why it went unnoticed.
    """
    errors: list[str] = []

    req = ROOT / "requirements.txt"
    if not req.exists():
        return errors
    req_text = req.read_text()

    pin = re.search(r"^ciris-server==([0-9][^\s#]*)", req_text, re.M)
    if not pin:
        return errors

    # The CLIENT_VERSION half of this check is GONE, not broken. It compared a
    # Kotlin constant in client/shared against the server pin; that module is
    # built by CIRISAI/CIRISClient now, so the constant is theirs and the drift
    # it caught cannot happen here. It was removed rather than left to skip on a
    # missing file -- a check that can never fire reads as coverage.
    #
    # What replaces it is the pin this repo still owns: ciris-client must BE
    # pinned. ciris-server requires a RANGE, so without an explicit pin the .aar
    # in apps/android/libs, the .xcframework, and the client inside the wheel can
    # all be different builds that merely satisfy the same constraint.
    if not re.search(r"^ciris-client==([0-9][^\s#]*)", req_text, re.M):
        errors.append(
            "requirements.txt has no `ciris-client==` pin. ciris-server requires a "
            "RANGE, so the app shells and the wheel would each resolve their own "
            "client build. tools/fetch_client_artifacts.py reads this pin."
        )

    # The Android gradle pin installs the wheel; if it disagrees with
    # requirements.txt the device runs a different substrate than CI tested.
    gradle = ROOT / "apps/android/build.gradle"
    if gradle.exists():
        g = re.search(r'install "ciris-server==([^"]+)"', gradle.read_text())
        if g and g.group(1) != pin.group(1):
            errors.append(
                f"apps/android/build.gradle ciris-server pin: {g.group(1)} != {pin.group(1)} (requirements.txt)"
            )

    return errors


def main():
    errors = check_all()
    if errors:
        print("Version alignment check FAILED:")
        for e in errors:
            print(f"  - {e}")
        print(f"\nFix: python tools/dev/bump_version.py patch")
        sys.exit(1)
    else:
        print("Version alignment: all constants match")
        sys.exit(0)


if __name__ == "__main__":
    main()
