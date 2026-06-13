#!/usr/bin/env python3
"""
Update CIRIS Android native libraries from GitHub Releases.

THIN WRAPPER — this script now delegates to the unified
``tools/update_substrate_libs.py`` with ``--platform android``. The CLI
surface is unchanged (``--lib``, positional version, ``--skip-bindings``),
so existing docs and automation keep working; the library registry, download
/ extract / install logic, Chaquopy wheels handling, and build.gradle pin
updates all live in the unified tool.

Handles: ciris-verify, ciris-persist, ciris-edge, ciris-lens-core
(and future: ciris-nodecore).

Each library follows the same pattern:
  1. Download Android tarball from GitHub Release
  2. Copy per-ABI .so files into client/androidApp/src/main/jniLibs/{abi}/
  3. Update agent-side Python bindings from PyPI wheel (when has_adapter)
  4. Update __version__ in the agent's adapter ffi_bindings/__init__.py

Android does NOT need:
  - XCFramework building (iOS-only concept)
  - .fwork redirects (BeeWare iOS-only convention)
  - Resources.zip rebuild (Chaquopy bundles at gradle build time, no zip)

Usage:
    python -m tools.update_android_libs                          # Update all to pinned versions
    python -m tools.update_android_libs --lib verify 3.0.1       # Update single lib
    python -m tools.update_android_libs --lib persist 2.0.5      # Update persist
    python -m tools.update_android_libs --skip-bindings          # Only refresh .so files
"""

import sys
from pathlib import Path
from typing import List, Optional

# Allow direct invocation (`python tools/update_android_libs.py`) in addition
# to `python -m tools.update_android_libs`.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).parent.parent))

# Re-export the registry + version helper for any callers that imported them
# from this module before the unification.
from tools.update_substrate_libs import (  # noqa: F401,E402
    LIBS,
    SubstrateLib,
    get_pinned_version,
)
from tools.update_substrate_libs import main as _unified_main  # noqa: E402

# Backwards-compatible alias: the per-platform AndroidLib dataclass was
# merged into the unified SubstrateLib.
AndroidLib = SubstrateLib


def main(argv: Optional[List[str]] = None) -> None:
    """Delegate to the unified substrate updater, pinned to Android."""
    args = list(sys.argv[1:] if argv is None else argv)
    # Platform pin goes LAST so it wins over any caller-supplied --platform —
    # this wrapper is Android by definition.
    _unified_main([*args, "--platform", "android"])


if __name__ == "__main__":
    main()
