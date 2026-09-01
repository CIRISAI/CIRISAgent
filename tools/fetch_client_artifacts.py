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
import shutil
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
        check=False,
    )
    if out.returncode != 0:
        # PyPI and GitHub Releases are SEPARATE publications. The wheels can be
        # up (carrying the desktop jar) while the .aar and .xcframework, which
        # only exist as release assets, are not. Say which channel is missing --
        # "release not found" alone reads as "the version does not exist".
        raise SystemExit(
            f"{REPO} has no GitHub release v{version}.\n"
            f"  The PyPI wheels for {version} may already be published -- they are a\n"
            f"  DIFFERENT channel. The .aar and .xcframework exist only as release\n"
            f"  assets, so Android and iOS cannot be built against {version} until the\n"
            f"  release is cut. Desktop is unaffected: its jar ships inside the wheel."
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
    # DOWNLOAD FIRST, PRUNE AFTER. Pruning first meant a fetch that failed for
    # any reason -- an uncut release, a network blip -- deleted the working .aar
    # and left the tree unbuildable, turning "could not update" into "cannot
    # build at all". A failed fetch must be a no-op.
    download(asset_url(version, name), ANDROID_LIBS / name)
    prune_stale(ANDROID_LIBS, version, "ciris-client-*.aar")


def fetch_ios(version: str) -> None:
    """Unpack the published client xcframework.

    THE ARCHIVE UNPACKS TO `shared.xcframework`, NOT `ciris-client-<v>.xcframework`.
    That name is not ours to choose — it is what CIRISClient publishes, and it
    matches the `shared.framework` the Xcode link step looks for.

    Assuming the versioned name broke two things silently:

      * `target.exists()` was never true, so every run re-extracted 108MB over
        itself. Wasteful, invisible.
      * `prune_stale(..., "ciris-client-*.xcframework")` matched NOTHING, so the
        pruning that exists precisely to stop a build shipping code nobody thinks
        is in it did not run on iOS at all. An older `shared.xcframework` simply
        survived, and since the extract merges into an existing directory rather
        than replacing it, files removed upstream persisted indefinitely.

    So: remove the previous copy outright, then extract. A version marker records
    what is actually on disk, since the directory name no longer carries it.
    """
    name = f"ciris-client-{version}.xcframework.zip"
    # Download before pruning, for the reason in fetch_android().
    zip_path = download(asset_url(version, name), IOS_FRAMEWORKS / name)
    target = IOS_FRAMEWORKS / "shared.xcframework"

    # EXTRACT FIRST, REPLACE SECOND. Removing the old copy up front meant a
    # corrupt archive, a changed layout, or a disk that filled mid-extract left
    # the checkout with NO framework at all — a failed update that destroys the
    # working one, which is the opposite of the download-before-prune care taken
    # in fetch_android(). Stage into a sibling directory, verify the expected
    # layout is there, and only then swap.
    staging = IOS_FRAMEWORKS / ".shared.xcframework.incoming"
    if staging.exists():
        shutil.rmtree(staging)
    staging.mkdir(parents=True)
    try:
        print(f"  unpacking {name} ...")
        with zipfile.ZipFile(zip_path) as z:
            z.extractall(staging)
        staged = staging / "shared.xcframework"
        if not staged.is_dir():
            raise SystemExit(f"{name} did not contain shared.xcframework — layout changed upstream")
        if not any(staged.glob("ios-arm64*")):
            raise SystemExit(f"{name} contains no ios-arm64* slice — layout changed upstream")
        if target.exists():
            shutil.rmtree(target)
        staged.rename(target)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    zip_path.unlink(missing_ok=True)
    (IOS_FRAMEWORKS / "shared.xcframework.version").write_text(version + "\n", encoding="utf-8")
    print(f"  {target.name} <- ciris-client {version}")


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
