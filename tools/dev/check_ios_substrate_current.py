#!/usr/bin/env python3
"""Is the iOS bundle built from the substrate this branch pins?

WHY THIS EXISTS. You should be able to check out main, open Xcode, build and
sign, and get an app whose bundled substrate matches everything else we ship.
Until now nothing could tell you whether that was true.

`apps/ios/Resources.zip` records no version of its own: the vendored
`app_packages/ciris_server/` declares no `__version__`, and the `.so` embeds no
version literal — `update_substrate_libs.py` says so itself when it probes and
finds nothing. So the only way to know which substrate iOS carried was to have
been the macOS host that built it.

Predictably, it drifted. Every other platform moved to 0.5.173 — requirements.txt,
CLIENT_VERSION, the Android gradle pin, the Android wheels — while iOS stayed on
0.5.172, because the refresh needs a materialised Resources tree that only the
macOS runner has. That is exactly the one-platform split that resurfaces later as
a version-mismatch banner, on the one platform where shipping a fix is slowest.

`substrate.lock.json` is written by the updater on every iOS refresh and tracked,
so this check runs on any runner in milliseconds.

Exit 0 = iOS is current. Exit 1 = iOS is behind; dispatch
`refresh-ios-substrate.yml` against this branch before cutting.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / "apps" / "ios" / "substrate.lock.json"
REQUIREMENTS = ROOT / "requirements.txt"

#: pin name in requirements.txt -> lib name the updater records
_TRACKED = {"ciris-server": "server"}


def _pin(name: str) -> str | None:
    m = re.search(rf"^{re.escape(name)}==([0-9][^\s#]*)", REQUIREMENTS.read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else None


def main() -> int:
    if not LOCK.exists():
        print(
            f"::error::{LOCK.relative_to(ROOT)} is missing. It records what the iOS "
            f"bundle was built from; without it nobody can tell whether an Xcode "
            f"build off this branch ships the pinned substrate. Run "
            f"`tools/update_substrate_libs.py --platform ios` on a macOS host."
        )
        return 1

    try:
        libs = json.loads(LOCK.read_text(encoding="utf-8")).get("libs") or {}
    except json.JSONDecodeError as e:
        print(f"::error::{LOCK.name} is not valid JSON: {e}")
        return 1

    problems = []
    for pin_name, lib in _TRACKED.items():
        want = _pin(pin_name)
        if want is None:
            continue  # not pinned on this branch; nothing to hold iOS to
        have = libs.get(lib)
        if have != want:
            problems.append(
                f"  iOS bundle was built from {lib}={have or '<unrecorded>'}, "
                f"but this branch pins {pin_name}=={want}"
            )

    if problems:
        print("::error::The iOS bundle is not built from this branch's substrate pins.")
        print("\n".join(problems))
        print(
            "\nAn Xcode build off this branch would ship a DIFFERENT substrate than "
            "every other platform, and users would see a version-mismatch banner on "
            "iOS only.\n"
            "Fix: dispatch `refresh-ios-substrate.yml` against this branch (it runs on "
            "macos-latest, the only host with a materialised Resources tree), then "
            "merge the refresh it pushes.\n"
            "This cannot be fixed on Linux: a rebuild there produces a bundle missing "
            "~94% of its entries, which is why the updater now refuses it outright."
        )
        return 1

    shipped = ", ".join(f"{k}={v}" for k, v in sorted(libs.items()))
    print(f"iOS substrate is current ({shipped}) — safe to build and sign off this branch.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
