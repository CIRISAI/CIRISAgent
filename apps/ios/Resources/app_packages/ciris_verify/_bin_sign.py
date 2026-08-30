"""Console-script shim for the ciris-build-sign Rust binary.

The actual binary is bundled inside this package's ``_bin`` directory at wheel
build time. This module is registered as the ``ciris-build-sign`` console
script via ``[project.scripts]``; on invocation it locates the bundled binary
for the current platform and replaces the current process via ``os.execv``
(POSIX) or spawns + propagates exit code (Windows, where ``execv`` semantics
differ).

The wheel is platform-tagged, so the binary in ``_bin/`` is guaranteed to
match the host platform when installed via pip.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


_BIN_NAME = "ciris-build-sign"


def _binary_path() -> Path:
    """Return the absolute path to the bundled ``ciris-build-sign`` binary."""
    pkg_dir = Path(__file__).resolve().parent
    candidates = [
        pkg_dir / "_bin" / _BIN_NAME,
        pkg_dir / "_bin" / f"{_BIN_NAME}.exe",
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        f"ciris-build-sign binary not found in {pkg_dir / '_bin'}. "
        "This indicates a packaging defect; please file an issue at "
        "https://github.com/CIRISAI/CIRISVerify/issues with your platform "
        "and the wheel filename you installed."
    )


def main() -> None:
    binary = _binary_path()
    argv = [str(binary), *sys.argv[1:]]
    if os.name == "nt":
        # Windows has no real execv; spawn and exit with the child's status.
        import subprocess

        sys.exit(subprocess.run(argv).returncode)
    os.execv(str(binary), argv)


if __name__ == "__main__":
    main()
