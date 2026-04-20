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
