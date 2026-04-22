#!/usr/bin/env python3
"""
Version bumping tool for CIRIS.

Usage:
    python tools/bump_version.py build    # Increment build number (1.0.4.1 -> 1.0.4.2)
    python tools/bump_version.py patch    # Increment patch (1.0.4 -> 1.0.5)
    python tools/bump_version.py minor    # Increment minor (1.0.4 -> 1.1.0)
    python tools/bump_version.py major    # Increment major (1.0.4 -> 2.0.0)

This tool updates version in:
    - ciris_engine/constants.py (main version source)
    - client/iosApp/iosApp/Info.plist (iOS CFBundleVersion)
    - client/androidApp/build.gradle (Android versionCode + versionName)
    - CIRISGUI/apps/agui/package.json (GUI version)
    - CIRISGUI/apps/agui/lib/ciris-sdk/version.ts (SDK version)
    - README.md (automatically switches between STABLE/BETA RELEASE based on version stage)
"""

import json
import re
import sys
from pathlib import Path


def bump_version(bump_type: str):
    """Bump the version in constants.py."""
    constants_file = Path(__file__).parent.parent.parent / "ciris_engine" / "constants.py"

    with open(constants_file, "r") as f:
        content = f.read()

    # Extract current version parts
    major_match = re.search(r"CIRIS_VERSION_MAJOR = (\d+)", content)
    minor_match = re.search(r"CIRIS_VERSION_MINOR = (\d+)", content)
    patch_match = re.search(r"CIRIS_VERSION_PATCH = (\d+)", content)
    build_match = re.search(r"CIRIS_VERSION_BUILD = (\d+)", content)
    stage_match = re.search(r'CIRIS_VERSION_STAGE = "([^"]+)"', content)

    if not all([major_match, minor_match, patch_match]):
        print("Error: Could not parse version from constants.py")
        return False

    major = int(major_match.group(1))
    minor = int(minor_match.group(1))
    patch = int(patch_match.group(1))
    build = int(build_match.group(1)) if build_match else 0
    stage = stage_match.group(1) if stage_match else "beta"

    # Apply bump
    if bump_type == "build":
        build += 1
    elif bump_type == "patch":
        patch += 1
        build = 0  # Reset build on patch bump
    elif bump_type == "minor":
        minor += 1
        patch = 0
        build = 0
    elif bump_type == "major":
        major += 1
        minor = 0
        patch = 0
        build = 0
    else:
        print(f"Error: Unknown bump type '{bump_type}'")
        return False

    # Construct new version string
    # Handle RC versions specially
    if stage == "rc":
        if build > 0:
            new_version = f"{major}.{minor}.{patch}-rc{build}"
        else:
            new_version = f"{major}.{minor}.{patch}"  # No stage for release version
    else:
        # Regular versioning for beta, alpha, etc.
        if build > 0:
            new_version = f"{major}.{minor}.{patch}.{build}-{stage}"
        else:
            new_version = f"{major}.{minor}.{patch}-{stage}"

    # Update content
    content = re.sub(r'CIRIS_VERSION = "[^"]+"', f'CIRIS_VERSION = "{new_version}"', content)
    content = re.sub(r"CIRIS_VERSION_MAJOR = \d+", f"CIRIS_VERSION_MAJOR = {major}", content)
    content = re.sub(r"CIRIS_VERSION_MINOR = \d+", f"CIRIS_VERSION_MINOR = {minor}", content)
    content = re.sub(r"CIRIS_VERSION_PATCH = \d+", f"CIRIS_VERSION_PATCH = {patch}", content)

    # Handle build line - add it if missing, update if present
    if build_match:
        content = re.sub(r"CIRIS_VERSION_BUILD = \d+", f"CIRIS_VERSION_BUILD = {build}", content)
    elif build > 0:
        # Add build line after patch
        content = re.sub(
            r"(CIRIS_VERSION_PATCH = \d+)",
            f"\\1\nCIRIS_VERSION_BUILD = {build}  # Build number for incremental improvements",
            content,
        )

    # Write back
    with open(constants_file, "w") as f:
        f.write(content)

    # Update GUI package.json
    gui_package_file = Path(__file__).parent.parent.parent / "CIRISGUI" / "apps" / "agui" / "package.json"
    if gui_package_file.exists():
        with open(gui_package_file, "r") as f:
            package_data = json.load(f)
        package_data["version"] = new_version
        with open(gui_package_file, "w") as f:
            json.dump(package_data, f, indent=2)
            f.write("\n")  # Add newline at end
        print(f"  Updated GUI package.json to {new_version}")

    # Update SDK version.ts
    sdk_version_file = (
        Path(__file__).parent.parent.parent / "CIRISGUI" / "apps" / "agui" / "lib" / "ciris-sdk" / "version.ts"
    )
    if sdk_version_file.exists():
        with open(sdk_version_file, "r") as f:
            sdk_content = f.read()
        sdk_content = re.sub(r"version: '[^']+'", f"version: '{new_version}'", sdk_content)
        with open(sdk_version_file, "w") as f:
            f.write(sdk_content)
        print(f"  Updated SDK version.ts to {new_version}")

    # Update README.md
    readme_file = Path(__file__).parent.parent.parent / "README.md"
    if readme_file.exists():
        with open(readme_file, "r") as f:
            readme_content = f.read()

        # Determine if this is a stable or beta release based on version stage
        if stage == "rc" and build == 0:
            # Final release version (no stage suffix)
            release_type = "STABLE RELEASE"
        else:
            # Pre-release version (has stage suffix)
            release_type = "BETA RELEASE"

        # Update both STABLE RELEASE and BETA RELEASE patterns
        readme_content = re.sub(
            r"\*\*(STABLE|BETA) RELEASE [^\*]+\*\*", f"**{release_type} {new_version}**", readme_content
        )

        with open(readme_file, "w") as f:
            f.write(readme_content)
        print(f"  Updated README.md to {release_type} {new_version}")

    # Update iOS Info.plist CFBundleVersion + CFBundleShortVersionString
    ios_plist_file = Path(__file__).parent.parent.parent / "client" / "iosApp" / "iosApp" / "Info.plist"
    if ios_plist_file.exists():
        with open(ios_plist_file, "r") as f:
            plist_content = f.read()

        # Update CFBundleVersion (build number, always increment)
        bundle_version_match = re.search(r"<key>CFBundleVersion</key>\s*<string>(\d+)</string>", plist_content)
        if bundle_version_match:
            old_build = int(bundle_version_match.group(1))
            new_build = old_build + 1
            plist_content = re.sub(
                r"(<key>CFBundleVersion</key>\s*<string>)\d+(</string>)",
                rf"\g<1>{new_build}\2",
                plist_content,
            )
            print(f"  Updated iOS CFBundleVersion: {old_build} -> {new_build}")

        # Update CFBundleShortVersionString (display version, sync with engine)
        display_version = f"{major}.{minor}.{patch}"
        old_short_match = re.search(r"<key>CFBundleShortVersionString</key>\s*<string>([^<]+)</string>", plist_content)
        old_short = old_short_match.group(1) if old_short_match else "unknown"
        plist_content = re.sub(
            r"(<key>CFBundleShortVersionString</key>\s*<string>)[^<]+(</string>)",
            rf"\g<1>{display_version}\2",
            plist_content,
        )
        if old_short != display_version:
            print(f"  Updated iOS CFBundleShortVersionString: {old_short} -> {display_version}")

        with open(ios_plist_file, "w") as f:
            f.write(plist_content)

    # Update Android build.gradle
    android_gradle_file = Path(__file__).parent.parent.parent / "client" / "androidApp" / "build.gradle"
    if android_gradle_file.exists():
        with open(android_gradle_file, "r") as f:
            gradle_content = f.read()

        # Extract and increment versionCode
        version_code_match = re.search(r"versionCode (\d+)", gradle_content)
        if version_code_match:
            old_code = int(version_code_match.group(1))
            new_code = old_code + 1
            gradle_content = re.sub(r"versionCode \d+", f"versionCode {new_code}", gradle_content)
            print(f"  Updated Android versionCode: {old_code} -> {new_code}")

        # Update versionName (use version without stage suffix for cleaner display)
        display_version = f"{major}.{minor}.{patch}"
        gradle_content = re.sub(r'versionName "[^"]+"', f'versionName "{display_version}"', gradle_content)
        print(f"  Updated Android versionName: {display_version}")

        with open(android_gradle_file, "w") as f:
            f.write(gradle_content)

    # Update client Python version files (android + iOS)
    display_version = f"{major}.{minor}.{patch}"
    client_version_files = [
        ("client/androidApp/src/main/python/version.py", f"android-{display_version}"),
        ("android/app/src/main/python/version.py", f"android-{display_version}"),
        ("ios/CirisiOS/src/ciris_ios/version.py", f"ios-{display_version}"),
    ]
    for rel_path, platform_version in client_version_files:
        version_file = Path(__file__).parent.parent.parent / rel_path
        if version_file.exists():
            with open(version_file, "r") as f:
                content_vf = f.read()
            old_match = re.search(r'__version__ = "([^"]+)"', content_vf)
            old_ver = old_match.group(1) if old_match else "unknown"
            content_vf = re.sub(
                r'__version__ = "[^"]+"',
                f'__version__ = "{platform_version}"',
                content_vf,
            )
            with open(version_file, "w") as f:
                f.write(content_vf)
            if old_ver != platform_version:
                print(f"  Updated {rel_path}: {old_ver} -> {platform_version}")

    print(f"Version bumped to {new_version}")
    return True


def main():
    if len(sys.argv) != 2:
        print(__doc__)
        sys.exit(1)

    bump_type = sys.argv[1]
    if bump_type not in ["build", "patch", "minor", "major"]:
        print(f"Error: Invalid bump type '{bump_type}'")
        print("Valid types: build, patch, minor, major")
        sys.exit(1)

    if bump_version(bump_type):
        print("Don't forget to commit the version change!")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
