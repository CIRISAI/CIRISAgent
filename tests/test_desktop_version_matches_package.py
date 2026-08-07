"""The desktop JAR must report the version of the release it ships in.

`client/desktopApp/build.gradle.kts` sets Compose's `packageVersion`, which
names the built JAR (`CIRIS-linux-x64-<version>.jar`) and is what the desktop
app reports about itself. `tools/dev/bump_version.py` knew about
`androidApp/build.gradle` and the iOS plist and NOT about desktopApp, so it sat
at **2.6.0 while the wheel said 2.9.10** — across every 2.7, 2.8 and 2.9 release.

The code was never stale: CI rebuilds the JAR each run and copies it out of
`desktopApp/build/compose/jars/`. Only the IDENTITY was frozen, which is the
worse half of the two — a binary that is current but reports a version from many
releases back sends anyone diagnosing it to the wrong tree, and does so
confidently. `tools/update_substrate_libs.py` already carries the note about an
APK shipping a wheel eight releases stale, where "a whole diagnosis was
conducted against that stale runtime".

Guarded here rather than trusted to the bump tool, because the bump tool is
exactly what failed: it did the right thing for the platforms it knew about, and
there was nothing anywhere that noticed the one it did not.
"""

from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
GRADLE = ROOT / "client/desktopApp/build.gradle.kts"
CONSTANTS = ROOT / "ciris_engine/constants.py"


def _package_version() -> str:
    """MAJOR.MINOR.PATCH from CIRIS_VERSION, without the stage suffix."""
    m = re.search(r'CIRIS_VERSION\s*=\s*"([^"]+)"', CONSTANTS.read_text(encoding="utf-8"))
    assert m, "CIRIS_VERSION not found in ciris_engine/constants.py"
    return ".".join(m.group(1).split("-")[0].split(".")[:3])


def _desktop_version() -> str:
    m = re.search(r'packageVersion\s*=\s*"([^"]+)"', GRADLE.read_text(encoding="utf-8"))
    assert m, "packageVersion not found in client/desktopApp/build.gradle.kts"
    return m.group(1)


def test_desktop_package_version_matches_the_release() -> None:
    want, got = _package_version(), _desktop_version()
    assert got == want, (
        f"desktop packageVersion is {got!r} but this release is {want!r}. The JAR is rebuilt "
        f"every CI run, so the code is current and only the version it REPORTS is wrong — which "
        f"sends anyone debugging a desktop issue to a tree from a different release. "
        f"Run tools/dev/bump_version.py, which now updates this file."
    )


def test_desktop_version_has_no_stage_suffix() -> None:
    """Compose rejects a non-numeric packageVersion.

    `CIRIS_VERSION` carries a stage suffix (`2.9.10-stable`); packaging fails if
    that reaches `packageVersion`, so the bump tool deliberately writes the
    plain triple. Asserted so a future 'just use the full version' change fails
    here rather than in a platform packaging task.
    """
    got = _desktop_version()
    assert re.fullmatch(r"\d+\.\d+\.\d+", got), (
        f"packageVersion {got!r} must be MAJOR.MINOR.PATCH — Compose packaging rejects "
        f"a stage suffix, and it fails in the packaging task rather than here."
    )


def test_the_bump_tool_knows_about_desktop() -> None:
    """The cause, not just the symptom.

    Syncing the number without teaching the tool leaves it to drift again on the
    next release, which is precisely how it reached 2.6.0.
    """
    src = (ROOT / "tools/dev/bump_version.py").read_text(encoding="utf-8")
    assert "desktopApp" in src and "packageVersion" in src, (
        "bump_version.py no longer updates client/desktopApp/build.gradle.kts. "
        "It updated Android and iOS and not desktop, and the desktop version sat "
        "at 2.6.0 through every 2.7/2.8/2.9 release because nothing checked."
    )
