"""The published client unpacks to `shared.xcframework`, and everything must agree.

This is pinned because the name is NOT ours: CIRISClient publishes
`ciris-client-<version>.xcframework.zip`, and the DIRECTORY inside is
`shared.xcframework`. Assuming the versioned name broke three things at once,
none of which announced itself:

  * fetch_client_artifacts computed a target that never existed, so it
    re-extracted 108MB every run and its prune matched nothing — a stale
    framework survived indefinitely, which is the exact "ship code nobody
    thinks is in it" failure prune_stale exists to prevent
  * rebuild_and_deploy's fallback searched for the versioned name and reported
    "no xcframework" on a runner where the fetch had visibly succeeded
  * project.yml still looked only in apps/shared/build/bin — a gradle output
    directory this repo has not contained since the client moved to published
    artifacts (see apps/settings.gradle.kts)
"""

from __future__ import annotations

import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[2]
FETCH = ROOT / "tools" / "fetch_client_artifacts.py"
DEPLOY = ROOT / "apps" / "ios" / "scripts" / "rebuild_and_deploy.sh"
PROJECT = ROOT / "apps" / "ios" / "project.yml"

PUBLISHED = "shared.xcframework"


def test_fetch_targets_the_real_directory_name() -> None:
    src = FETCH.read_text(encoding="utf-8")
    assert f'IOS_FRAMEWORKS / "{PUBLISHED}"' in src
    assert 'f"ciris-client-{version}.xcframework"' not in src, (
        "the versioned name is the archive, not the directory it unpacks to"
    )


def test_fetch_removes_the_previous_copy() -> None:
    """extractall MERGES into an existing directory.

    Without an explicit removal, files deleted upstream persist forever — a
    stale framework that no version check would notice.
    """
    src = FETCH.read_text(encoding="utf-8")
    assert "shutil.rmtree(target)" in src


def test_the_deploy_fallback_looks_for_what_actually_lands() -> None:
    src = DEPLOY.read_text(encoding="utf-8")
    assert f'-name "{PUBLISHED}"' in src
    assert '-name "ciris-client-*.xcframework"' not in src


@pytest.mark.parametrize("slice_dir", ["ios-arm64", "ios-arm64-simulator"])
def test_project_searches_the_published_slices(slice_dir: str) -> None:
    """Both slices must be on FRAMEWORK_SEARCH_PATHS, or the linker cannot see them.

    `Frameworks` alone is not enough: shared.framework sits one level deeper,
    inside the xcframework's per-platform slice.
    """
    src = PROJECT.read_text(encoding="utf-8")
    assert f"Frameworks/{PUBLISHED}/{slice_dir}" in src


def test_the_gradle_path_still_wins() -> None:
    """A developer building from source must be unaffected by the fallback."""
    src = PROJECT.read_text(encoding="utf-8")
    gradle = src.index("../shared/build/bin/iosSimulatorArm64")
    published = src.index(f"Frameworks/{PUBLISHED}/ios-arm64-simulator")
    assert gradle < published, "the published slice must be listed after the gradle output"


def test_the_link_step_names_both_recovery_paths() -> None:
    """When neither exists, say how to get each — the previous message named
    a gradle module that no longer exists in this tree."""
    src = PROJECT.read_text(encoding="utf-8")
    script = src[src.index("Link KMP Shared Framework"):]
    assert "fetch_client_artifacts.py --platform ios" in script
    assert not re.search(r"cd mobile && \./gradlew", script), "stale instruction: there is no mobile/ tree"
