"""The iOS Resources.zip carries the engine this release ships, not an old one.

The zip is a committed artifact, and CI signs the iOS build manifest from the
engine inside it. Through 2.21.0 its ciris_engine was still 2.18.0: every
release since registered a stale tree as its iOS build, while the zip's
localization and native libraries were refreshed. Sync it with
tools/build_mobile.sh's rsync step, then
`python3 tools/update_substrate_libs.py --platform ios --rebuild-zip-only`.
"""

import re
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ZIP = ROOT / "apps" / "ios" / "Resources.zip"


def _version(text: str) -> str:
    match = re.search(r'^CIRIS_VERSION = "([^"]+)"', text, re.M)
    assert match, "no CIRIS_VERSION"
    return match.group(1)


def test_the_bundled_engine_version_matches_the_source():
    with zipfile.ZipFile(ZIP) as z:
        bundled = _version(z.read("app/ciris_engine/constants.py").decode("utf-8"))
    assert bundled == _version((ROOT / "ciris_engine" / "constants.py").read_text(encoding="utf-8"))


def test_the_bundle_carries_no_build_secrets():
    with zipfile.ZipFile(ZIP) as z:
        assert not [n for n in z.namelist() if "_build_secrets" in n]
