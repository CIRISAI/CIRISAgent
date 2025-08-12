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
    - CIRISGUI/apps/agui/package.json (GUI version)
    - CIRISGUI/apps/agui/lib/ciris-sdk/version.ts (SDK version)
    - README.md (documentation version)
"""

import json
import re
import sys
from pathlib import Path


def bump_version(bump_type: str):
    """Bump the version in constants.py."""
    constants_file = Path(__file__).parent.parent / "ciris_engine" / "constants.py"

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
    gui_package_file = Path(__file__).parent.parent / "CIRISGUI" / "apps" / "agui" / "package.json"
    if gui_package_file.exists():
        with open(gui_package_file, "r") as f:
            package_data = json.load(f)
        package_data["version"] = new_version
        with open(gui_package_file, "w") as f:
            json.dump(package_data, f, indent=2)
            f.write("\n")  # Add newline at end
        print(f"  Updated GUI package.json to {new_version}")

    # Update SDK version.ts
    sdk_version_file = Path(__file__).parent.parent / "CIRISGUI" / "apps" / "agui" / "lib" / "ciris-sdk" / "version.ts"
    if sdk_version_file.exists():
        with open(sdk_version_file, "r") as f:
            sdk_content = f.read()
        sdk_content = re.sub(r"version: '[^']+'", f"version: '{new_version}'", sdk_content)
        with open(sdk_version_file, "w") as f:
            f.write(sdk_content)
        print(f"  Updated SDK version.ts to {new_version}")

    # Update README.md
    readme_file = Path(__file__).parent.parent / "README.md"
    if readme_file.exists():
        with open(readme_file, "r") as f:
            readme_content = f.read()
        # Update the BETA RELEASE line
        readme_content = re.sub(r"\*\*BETA RELEASE [\d\.]+-\w+\*\*", f"**BETA RELEASE {new_version}**", readme_content)
        with open(readme_file, "w") as f:
            f.write(readme_content)
        print(f"  Updated README.md to {new_version}")

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
