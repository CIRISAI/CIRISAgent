#!/usr/bin/env python3
"""Fetch the published CIRISClient artifacts the app shells build against.

The shared Kotlin/Compose client lives in CIRISAI/CIRISClient and is published
as GitHub release assets:

    ciris-client-<version>.aar             -> apps/android/libs/   (Gradle)
    ciris-client-<version>.xcframework.zip -> apps/ios/Frameworks/ (Xcode)

They are NOT committed. Both are pre-built binaries of another repo's source,
which is exactly what CLAUDE.md's repo-size rule excludes: "Build artifacts and
pre-built binaries do not belong in git — distribute via GitHub Releases and
fetch on install". At 15 MB and 108 MB, committing them on every bump would put
the repo into the size audit's failure band within a handful of releases.

Neither is on Maven Central and neither has a POM, so Gradle cannot resolve
them transitively: `apps/android/build.gradle` declares the shared client's
own dependencies itself. See the CIRIS-CLIENT DEPENDENCIES block there.

The version comes from requirements.txt's `ciris-client==` pin. That pin exists
because ciris-server Requires a RANGE (`ciris-client>=0.5.190,<0.6`), and a
range gives a different answer on different machines -- the .aar here and the
client inside the wheel must be the same build, not merely compatible ones.

Usage:
    python3 tools/fetch_client_artifacts.py                 # both, resolved version
    python3 tools/fetch_client_artifacts.py --platform android
    python3 tools/fetch_client_artifacts.py 0.5.192         # pin explicitly
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ANDROID_LIBS = ROOT / "apps" / "android" / "libs"
IOS_FRAMEWORKS = ROOT / "apps" / "ios" / "Frameworks"
REPO = "CIRISAI/CIRISClient"


def resolve_version() -> str:
    """The ciris-client version to fetch: the requirements.txt pin, always.

    NOT `importlib.metadata.version("ciris-client")`. The ambient environment is
    not the authority -- an unrelated install of an older client on the build
    host resolved 0.5.188 here while the tree wanted 0.5.192, which would have
    silently built the APK against a four-release-old client.
    """
    req = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    m = re.search(r"^ciris-client==([0-9.]+)", req, re.MULTILINE)
    if not m:
        raise SystemExit("no ciris-client pin in requirements.txt")
    return m.group(1)


def asset_url(version: str, name: str) -> str:
    out = subprocess.run(
        ["gh", "release", "view", f"v{version}", "--repo", REPO, "--json", "assets"],
        capture_output=True,
        text=True,
        check=True,
    )
    for asset in json.loads(out.stdout)["assets"]:
        if asset["name"] == name:
            return asset["url"]
    raise SystemExit(f"{REPO} v{version} has no asset named {name}")


def download(url: str, dest: Path) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        print(f"  {dest.name} already present, skipping")
        return dest
    print(f"  downloading {dest.name} ...")
    tmp = dest.with_suffix(dest.suffix + ".part")
    with urllib.request.urlopen(url) as r, open(tmp, "wb") as f:  # noqa: S310 - github release URL
        digest = hashlib.sha256()
        while chunk := r.read(1 << 20):
            f.write(chunk)
            digest.update(chunk)
    tmp.replace(dest)
    print(f"  {dest.name}  {dest.stat().st_size / 1048576:.1f} MB  sha256={digest.hexdigest()[:16]}...")
    return dest


def prune_stale(directory: Path, keep: str, pattern: str) -> None:
    """Remove other versions, so a stale artifact cannot be picked up.

    Gradle's flatDir resolves by name, and Xcode embeds whatever is in
    Frameworks/. A leftover from the previous bump is how a build ships code
    nobody thinks is in it -- the same failure the desktop-jar freshness check
    in build.yml exists to prevent.
    """
    if not directory.exists():
        return
    for old in directory.glob(pattern):
        if keep not in old.name:
            print(f"  pruning stale {old.name}")
            if old.is_dir():
                subprocess.run(["rm", "-rf", str(old)], check=True)
            else:
                old.unlink()


def fetch_android(version: str) -> None:
    name = f"ciris-client-{version}.aar"
    prune_stale(ANDROID_LIBS, version, "ciris-client-*.aar")
    download(asset_url(version, name), ANDROID_LIBS / name)


def fetch_ios(version: str) -> None:
    name = f"ciris-client-{version}.xcframework.zip"
    prune_stale(IOS_FRAMEWORKS, version, "ciris-client-*.xcframework")
    zip_path = download(asset_url(version, name), IOS_FRAMEWORKS / name)
    target = IOS_FRAMEWORKS / f"ciris-client-{version}.xcframework"
    if not target.exists():
        print(f"  unpacking {name} ...")
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(IOS_FRAMEWORKS)
    zip_path.unlink(missing_ok=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("version", nargs="?", help="ciris-client version (default: resolved)")
    ap.add_argument("--platform", choices=("android", "ios", "all"), default="all")
    args = ap.parse_args()

    version = args.version or resolve_version()
    print(f"CIRISClient artifacts -> v{version}")

    if args.platform in ("android", "all"):
        fetch_android(version)
    if args.platform in ("ios", "all"):
        fetch_ios(version)

    print("done")
    return 0


if __name__ == "__main__":
    sys.exit(main())
