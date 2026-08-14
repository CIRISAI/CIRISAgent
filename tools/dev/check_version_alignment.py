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
    plist = ROOT / "client" / "iosApp" / "iosApp" / "Info.plist"
    if plist.exists():
        content = plist.read_text()
        m = re.search(r"<key>CFBundleShortVersionString</key>\s*<string>([^<]+)</string>", content)
        if m and m.group(1) != display_version:
            errors.append(f"iOS CFBundleShortVersionString: {m.group(1)} != {display_version}")

    # Android build.gradle versionName
    gradle = ROOT / "client" / "androidApp" / "build.gradle"
    if gradle.exists():
        content = gradle.read_text()
        m = re.search(r'versionName "([^"]+)"', content)
        if m and m.group(1) != display_version:
            errors.append(f"Android versionName: {m.group(1)} != {display_version}")

    # Client Python version files
    version_files = [
        ("client/androidApp/src/main/python/version.py", f"android-{display_version}"),
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
    """CLIENT_VERSION must equal the ciris-server wheel the app ships with.

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
    kt = ROOT / "client/shared/src/commonMain/kotlin/ai/ciris/mobile/shared/models/ClientMode.kt"
    if not (req.exists() and kt.exists()):
        return errors

    pin = re.search(r"^ciris-server==([0-9][^\s#]*)", req.read_text(), re.M)
    client = re.search(r'const val CLIENT_VERSION = "([^"]+)"', kt.read_text())
    if not (pin and client):
        return errors

    if pin.group(1) != client.group(1):
        errors.append(
            f"ClientMode.kt CLIENT_VERSION: {client.group(1)} != {pin.group(1)} "
            f"(the ciris-server pin in requirements.txt). The app would show a "
            f"VERSION-MISMATCH banner against the node it bundles. Fix: set "
            f"CLIENT_VERSION to {pin.group(1)}, and keep the Android gradle pin "
            f"in lockstep too."
        )

    # The Android gradle pin installs the wheel; if it disagrees with
    # requirements.txt the device runs a different substrate than CI tested.
    gradle = ROOT / "client/androidApp/build.gradle"
    if gradle.exists():
        g = re.search(r'install "ciris-server==([^"]+)"', gradle.read_text())
        if g and g.group(1) != pin.group(1):
            errors.append(
                f"androidApp/build.gradle ciris-server pin: {g.group(1)} != "
                f"{pin.group(1)} (requirements.txt)"
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
