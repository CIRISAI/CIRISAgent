#!/usr/bin/env python3
"""
Update CIRIS iOS native libraries from GitHub Releases.

THIN WRAPPER — this script now delegates to the unified
``tools/update_substrate_libs.py`` with ``--platform ios``. The CLI surface
is unchanged (``--lib``, positional version, ``--rebuild-zip-only``,
``--repair-info-plists``, ``--skip-checksums``), so the CI workflow
(.github/workflows/refresh-ios-substrate.yml) and existing docs keep working;
the library registry, download / extract / install logic, XCFramework build,
PyO3 bundling, and Resources.zip rebuild all live in the unified tool.

Handles: ciris-verify, ciris-persist, ciris-edge, ciris-lens-core
(and future: ciris-nodecore).

Each library follows the same pattern:
  1. Download iOS tarball from GitHub Release
  2. Build XCFramework from device + simulator dylibs (ctypes FFI libs)
     or bundle the PyO3 .abi3.so + .fwork redirect (PyO3 libs)
  3. Copy fallback dylib into Resources/app_packages/{name}/
  4. Update Python bindings from PyPI wheel
  5. Rebuild Resources.zip

Usage:
    python -m tools.update_ios_libs                          # Update all to pinned versions
    python -m tools.update_ios_libs --lib verify 3.0.1       # Update single lib
    python -m tools.update_ios_libs --lib persist 2.0.3      # Update persist
    python -m tools.update_ios_libs --rebuild-zip-only       # Just rebuild Resources.zip
"""

import sys
from pathlib import Path
from typing import List, Optional

# Allow direct invocation (`python tools/update_ios_libs.py`) in addition
# to `python -m tools.update_ios_libs`.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).parent.parent))

# Re-export the registry + version helper for any callers that imported them
# from this module before the unification.
from tools.update_substrate_libs import (  # noqa: F401,E402
    LIBS,
    SubstrateLib,
    get_pinned_version,
    repair_xcframework_info_plists,
)
from tools.update_substrate_libs import main as _unified_main  # noqa: E402

# Backwards-compatible alias: the per-platform IOSLib dataclass was merged
# into the unified SubstrateLib.
IOSLib = SubstrateLib


def main(argv: Optional[List[str]] = None) -> None:
    """Delegate to the unified substrate updater, pinned to iOS."""
    args = list(sys.argv[1:] if argv is None else argv)
    # Platform pin goes LAST so it wins over any caller-supplied --platform —
    # this wrapper is iOS by definition.
    _unified_main([*args, "--platform", "ios"])


if __name__ == "__main__":
    main()
